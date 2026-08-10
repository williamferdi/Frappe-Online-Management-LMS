"""Razorpay Payment Links and webhook -- architecture doc §5.

Payment *Links*, not a hosted checkout: one link per Fee Invoice, emailed or
WhatsApped, and a webhook that creates the Payment Entry and allocates it. Far
less work than a checkout page, and it handles partial and manual payments
identically.

Credentials live in site config, never in the repo:

    bench --site online.sibbc.org set-config -g razorpay_key_id     rzp_live_xxx
    bench --site online.sibbc.org set-config -g razorpay_key_secret xxx
    bench --site online.sibbc.org set-config -g razorpay_webhook_secret xxx

Webhook URL to register in the Razorpay dashboard:

    https://online.sibbc.org/api/method/sibbcs.finance.razorpay.webhook

Security notes:
* The webhook verifies Razorpay's HMAC-SHA256 signature over the raw body with
  `hmac.compare_digest`, before parsing anything. An unsigned or mis-signed
  request is refused outright -- without this, anyone who found the URL could
  mark invoices paid.
* The handler is idempotent on `gateway_payment_id`: Razorpay retries webhooks,
  and a retry must not create a second Payment Entry.
* Amounts are taken from Razorpay's payload, never from the caller's query
  string, and are reconciled against the invoice.
"""

import hashlib
import hmac
import json

import frappe
from frappe import _
from frappe.utils import flt, nowdate

from sibbcs.finance.gateway import public_url as gateway_public_url

API_BASE = "https://api.razorpay.com/v1"
TIMEOUT = 30

# Recorded on the invoice and the payment, so a ledger row always says which
# gateway handled it even after the live provider changes.
PROVIDER_NAME = "Razorpay"


# ---------------------------------------------------------------------------
# configuration
# ---------------------------------------------------------------------------


def get_credentials():
	key_id = frappe.conf.get("razorpay_key_id")
	key_secret = frappe.conf.get("razorpay_key_secret")
	return key_id, key_secret


def is_configured():
	key_id, key_secret = get_credentials()
	return bool(key_id and key_secret)


def _require_credentials():
	key_id, key_secret = get_credentials()
	if not (key_id and key_secret):
		frappe.throw(
			_(
				"Razorpay is not configured. Set razorpay_key_id and "
				"razorpay_key_secret in site config."
			),
			title=_("Razorpay Not Configured"),
		)
	return key_id, key_secret


# ---------------------------------------------------------------------------
# payment links
# ---------------------------------------------------------------------------


def create_payment_link(fee_invoice):
	"""Create a Razorpay Payment Link for one invoice and store it.

	Returns the short_url. Re-using an existing link is deliberate: generating
	a fresh link each time would leave several live links for one invoice, and
	a student paying an old one would still be paying correctly but confusingly.
	"""
	import requests

	key_id, key_secret = _require_credentials()

	invoice = frappe.get_doc("Fee Invoice", fee_invoice)

	if invoice.payment_link:
		return invoice.payment_link

	if invoice.status in ("Paid", "Waived", "Cancelled"):
		frappe.throw(
			_("{0} is {1}; no payment link is needed.").format(invoice.name, invoice.status)
		)

	outstanding = flt(invoice.outstanding_amount)
	if outstanding <= 0:
		frappe.throw(_("{0} has nothing outstanding.").format(invoice.name))

	student = frappe.db.get_value(
		"Student", invoice.student, ["full_name", "email", "mobile"], as_dict=True
	)

	payload = {
		# Razorpay works in paise.
		"amount": int(round(outstanding * 100)),
		"currency": "INR",
		"accept_partial": True,
		"description": f"{invoice.fee_type} — {invoice.name}",
		"reference_id": invoice.name,
		"customer": {
			"name": student.full_name if student else "",
			"email": student.email if student else "",
			"contact": student.mobile if student else "",
		},
		"notify": {"sms": False, "email": False},
		"reminder_enable": True,
		"notes": {
			"fee_invoice": invoice.name,
			"student": invoice.student,
			"fee_type": invoice.fee_type,
		},
		# gateway.public_url, not get_url: the latter appends the dev port and
		# would send the candidate somewhere unreachable after paying.
		"callback_url": gateway_public_url(f"/fee-paid?invoice={invoice.name}"),
		"callback_method": "get",
	}

	response = requests.post(
		f"{API_BASE}/payment_links",
		json=payload,
		auth=(key_id, key_secret),
		timeout=TIMEOUT,
	)

	if response.status_code >= 400:
		frappe.log_error(
			message=response.text, title=f"Razorpay link failed for {invoice.name}"
		)
		frappe.throw(
			_("Razorpay rejected the request: {0}").format(response.text[:300]),
			title=_("Payment Link Failed"),
		)

	data = response.json()
	invoice.db_set(
		{
			"payment_link": data.get("short_url"),
			"payment_reference": data.get("id"),
			"payment_provider": PROVIDER_NAME,
		},
		update_modified=False,
	)
	return data.get("short_url")


@frappe.whitelist()
def generate_link(fee_invoice):
	"""Desk button on Fee Invoice."""
	doc = frappe.get_doc("Fee Invoice", fee_invoice)
	doc.check_permission("write")
	url = create_payment_link(fee_invoice)
	frappe.msgprint(
		_("Payment link: <a href='{0}' target='_blank'>{0}</a>").format(url), indicator="green"
	)
	return url


# ---------------------------------------------------------------------------
# webhook
# ---------------------------------------------------------------------------


def verify_signature(raw_body, signature, secret):
	"""HMAC-SHA256 over the exact raw body, compared in constant time."""
	if not (raw_body and signature and secret):
		return False

	if isinstance(raw_body, str):
		raw_body = raw_body.encode("utf-8")

	expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
	return hmac.compare_digest(expected, signature)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def webhook():
	"""Razorpay webhook endpoint.

	Refuses anything without a valid signature. Always returns 200 for events
	we simply do not handle, so Razorpay does not retry them forever.
	"""
	secret = frappe.conf.get("razorpay_webhook_secret")
	if not secret:
		frappe.log_error(title="Razorpay webhook received but no secret configured")
		raise frappe.PermissionError("Webhook not configured")

	raw_body = frappe.request.get_data()
	signature = frappe.get_request_header("X-Razorpay-Signature")

	if not verify_signature(raw_body, signature, secret):
		frappe.log_error(title="Razorpay webhook signature rejected")
		raise frappe.PermissionError("Invalid signature")

	try:
		event = json.loads(raw_body)
	except ValueError:
		raise frappe.ValidationError("Malformed payload")

	event_type = event.get("event")
	handled = ("payment_link.paid", "payment.captured")
	if event_type not in handled:
		return {"status": "ignored", "event": event_type}

	entity = _extract_payment(event)
	if not entity:
		return {"status": "ignored", "reason": "no payment entity"}

	return record_payment(entity)


def _extract_payment(event):
	payload = event.get("payload") or {}
	payment = (payload.get("payment") or {}).get("entity")
	if payment:
		link = (payload.get("payment_link") or {}).get("entity") or {}
		payment = dict(payment)
		payment.setdefault("reference_id", link.get("reference_id"))
		payment.setdefault("notes", link.get("notes") or {})
	return payment


def record_payment(entity):
	"""Create the Payment Entry for a captured Razorpay payment. Idempotent."""
	payment_id = entity.get("id")
	if not payment_id:
		return {"status": "ignored", "reason": "no payment id"}

	existing = frappe.db.exists("Payment Entry", {"gateway_payment_id": payment_id})
	if existing:
		# Razorpay retries webhooks; a retry must not double-credit.
		return {"status": "duplicate", "payment_entry": existing}

	notes = entity.get("notes") or {}
	invoice_name = notes.get("fee_invoice") or entity.get("reference_id")

	if not invoice_name or not frappe.db.exists("Fee Invoice", invoice_name):
		frappe.log_error(
			message=json.dumps(entity)[:2000],
			title=f"Razorpay payment {payment_id} has no matching Fee Invoice",
		)
		return {"status": "unmatched", "payment": payment_id}

	invoice = frappe.get_doc("Fee Invoice", invoice_name)
	amount = flt(entity.get("amount", 0)) / 100.0

	# An application fee is paid before any Student exists, so there is no
	# Payment Entry to write -- Payment Entry.student is mandatory and the
	# applicant is not a student yet. Settle the invoice directly and place the
	# application.
	if not invoice.student and invoice.get("admission_application"):
		return _record_application_payment(invoice, entity, amount, payment_id)

	entry = frappe.get_doc(
		{
			"doctype": "Payment Entry",
			"student": invoice.student,
			"amount": amount,
			"mode": "Online",
			"gateway_payment_id": payment_id,
			"payment_provider": PROVIDER_NAME,
			"received_on": nowdate(),
			"reference_no": entity.get("order_id") or entity.get("reference_id"),
			"remarks": _("Razorpay {0}").format(entity.get("method") or ""),
		}
	)

	allocate = min(amount, flt(invoice.outstanding_amount))
	if allocate > 0:
		entry.append(
			"allocations", {"fee_invoice": invoice.name, "allocated_amount": allocate}
		)

	entry.flags.ignore_permissions = True
	entry.insert(ignore_permissions=True)

	# Anything beyond this invoice settles the student's other dues rather than
	# sitting unallocated.
	if flt(entry.unallocated_amount) > 0:
		entry.auto_allocate()
		entry.save(ignore_permissions=True)

	return {
		"status": "recorded",
		"payment_entry": entry.name,
		"invoice": invoice.name,
		"allocated": flt(entry.allocated_amount),
	}


def _record_application_payment(invoice, entity, amount, payment_id):
	"""Settle an application-fee invoice and place the application."""
	from sibbcs.finance.fees import mark_application_fee_paid

	paid = min(amount, flt(invoice.net_amount))
	invoice.db_set(
		{
			"paid_amount": paid,
			"outstanding_amount": flt(flt(invoice.net_amount) - paid, 2),
			"status": "Paid" if paid >= flt(invoice.net_amount) else "Partly Paid",
			"payment_reference": invoice.payment_reference or entity.get("payment_link_id"),
			"payment_provider": PROVIDER_NAME,
			"remarks": (invoice.remarks or "") + _(" · Razorpay {0}").format(payment_id),
		},
		update_modified=False,
	)

	state = None
	if invoice.status != "Partly Paid":
		state = mark_application_fee_paid(invoice.admission_application)

	return {
		"status": "recorded",
		"invoice": invoice.name,
		"application": invoice.admission_application,
		"workflow_state": state,
		"paid": paid,
	}
