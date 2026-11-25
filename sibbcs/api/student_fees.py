# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""A student's own fee records: what was billed, what was paid, and receipts.

Until this existed the portal showed only what a student *currently owes*. Once
an invoice was settled it vanished from every screen, nothing said a payment had
been received, and there was no receipt and no statement -- the only place a
student could see a paid invoice was the Frappe Desk, which they no longer reach.

Scoped like everything else in the student portal: **no endpoint here takes a
student**. The student is whoever is signed in, so there is no parameter through
which one student could read another's money. A receipt for somebody else's
payment is refused with the same answer as one that does not exist, so the
refusal cannot be used to find out which receipt numbers are real.

Three views of the same facts:

  fees()       the page -- invoices, payments, and a statement
  receipt()    one payment, as a PDF
  statement()  the whole account, as a PDF

What is deliberately left out, and why:

  * **Cancelled invoices.** A cancelled tuition invoice is a correction the
    college made to its own books, and the term is billed again; showing it
    would only invite "why was I billed twice".
  * **The application fee.** It is owed before a Student exists, so it sits on
    the Admission Application, and when it is taken by hand the only record of
    it is a free-text note on the invoice -- no date, no mode a receipt could be
    built from. It belongs here once it is recorded as a payment.
  * **Who recorded a payment.** That is the office's business, not the student's.
"""

import html

import frappe
from frappe import _
from frappe.utils import flt, fmt_money, formatdate, getdate, today

from sibbcs.api.student import _enrollment_header, _require_enrollment

COLLEGE_NAME = "South India Baptist Bible College & Seminary"

# An invoice in one of these has nothing left to pay. Waived is here because the
# college chose not to collect it: its net is still on the invoice, but the
# student owes none of it.
NOTHING_OWED = ("Paid", "Waived", "Cancelled")


# ---------------------------------------------------------------------------
# who is asking
# ---------------------------------------------------------------------------


def _me():
	"""The signed-in student's enrollment header, or None for an applicant."""
	enrollment = _require_enrollment()
	if not enrollment:
		return None
	return _enrollment_header(enrollment)


def _money(value):
	return fmt_money(flt(value), precision=2, currency="INR")


# ---------------------------------------------------------------------------
# the records
# ---------------------------------------------------------------------------


def _invoices(student):
	"""Every invoice but the cancelled ones, soonest due first among the unpaid."""
	rows = frappe.get_all(
		"Fee Invoice",
		filters={"student": student, "status": ("!=", "Cancelled")},
		fields=[
			"name", "fee_type", "category", "term", "status", "due_date", "creation",
			"gross_amount", "discount_amount", "net_amount", "paid_amount",
			"outstanding_amount", "payment_link",
		],
		order_by="due_date desc, creation desc",
	)

	for row in rows:
		# A waived invoice keeps its net on the record. Showing that as
		# "outstanding" would tell a student they owe what the college forgave.
		if row.status in NOTHING_OWED:
			row["outstanding_amount"] = 0.0
		row["overdue"] = bool(
			row.due_date
			and row.status not in NOTHING_OWED
			and getdate(row.due_date) < getdate(today())
		)
		row.pop("creation", None)

	return rows


def _payments(student, invoices):
	"""Each payment received, with the invoices it was applied to."""
	entries = frappe.get_all(
		"Payment Entry",
		filters={"student": student, "docstatus": ("<", 2)},
		fields=[
			"name", "received_on", "amount", "mode", "reference_no",
			"allocated_amount", "unallocated_amount", "creation",
		],
		order_by="received_on desc, creation desc",
	)
	if not entries:
		return []

	by_invoice = {row.name: row for row in invoices}
	allocations = frappe.get_all(
		"Payment Allocation",
		filters={"parenttype": "Payment Entry", "parent": ("in", [e.name for e in entries])},
		fields=["parent", "fee_invoice", "allocated_amount"],
		order_by="idx asc",
	)

	# An allocation can point at an invoice that was cancelled after the money
	# arrived. The payment still happened, so it is kept -- looked up directly
	# rather than from the list above, which hides cancelled invoices.
	known = {
		row.name: row
		for row in frappe.get_all(
			"Fee Invoice",
			filters={"name": ("in", list({a.fee_invoice for a in allocations}) or [""])},
			fields=["name", "fee_type", "term"],
		)
	}

	applied = {}
	for allocation in allocations:
		invoice = by_invoice.get(allocation.fee_invoice) or known.get(allocation.fee_invoice)
		applied.setdefault(allocation.parent, []).append(
			{
				"invoice": allocation.fee_invoice,
				"fee_type": invoice.fee_type if invoice else None,
				"term": invoice.term if invoice else None,
				"amount": flt(allocation.allocated_amount, 2),
			}
		)

	for entry in entries:
		entry["applied_to"] = applied.get(entry.name, [])
		entry.pop("creation", None)

	return entries


def _statement(invoices, payments):
	"""Charges and credits in date order, with a running balance.

	The same shape as the staff's Student Fee Ledger -- an invoice is a charge,
	a payment a credit -- with one correction: a waived invoice gets a credit for
	what was waived. Without it the balance would carry money the college chose
	not to collect and tell the student they still owed it.
	"""
	rows = []

	for invoice in invoices:
		date = invoice.due_date
		particulars = invoice.fee_type or invoice.category or _("Fee")
		if invoice.term:
			particulars += f" · {invoice.term}"
		if flt(invoice.discount_amount):
			particulars += _(" (scholarship −{0})").format(flt(invoice.discount_amount, 2))

		rows.append(
			{
				"date": date,
				"order": 0,
				"kind": "Invoice",
				"reference": invoice.name,
				"particulars": particulars,
				"charge": flt(invoice.net_amount, 2),
				"credit": 0.0,
			}
		)

		if invoice.status == "Waived":
			waived = flt(flt(invoice.net_amount) - flt(invoice.paid_amount), 2)
			if waived > 0:
				rows.append(
					{
						"date": date,
						"order": 1,
						"kind": "Waived",
						"reference": invoice.name,
						"particulars": _("{0} waived").format(invoice.fee_type or _("Fee")),
						"charge": 0.0,
						"credit": waived,
					}
				)

	for payment in payments:
		particulars = payment.mode or _("Payment")
		if payment.reference_no:
			particulars += f" · {payment.reference_no}"
		rows.append(
			{
				"date": payment.received_on,
				"order": 2,
				"kind": "Payment",
				"reference": payment.name,
				"particulars": particulars,
				"charge": 0.0,
				"credit": flt(payment.amount, 2),
			}
		)

	# Undated rows sort first rather than failing the whole statement.
	rows.sort(key=lambda r: (str(r["date"] or ""), r["order"], r["reference"]))

	balance = 0.0
	for row in rows:
		balance = flt(balance + flt(row["charge"]) - flt(row["credit"]), 2)
		row["balance"] = balance
		row.pop("order", None)

	return {
		"rows": rows,
		"charges": flt(sum(r["charge"] for r in rows), 2),
		"credits": flt(sum(r["credit"] for r in rows), 2),
		"balance": balance,
	}


def _summary(invoices, payments):
	open_ = [i for i in invoices if i.status not in NOTHING_OWED]
	return {
		"billed": flt(sum(flt(i.net_amount) for i in invoices if i.status != "Waived"), 2),
		"paid": flt(sum(flt(p.amount) for p in payments), 2),
		"outstanding": flt(sum(flt(i.outstanding_amount) for i in open_), 2),
		"overdue": flt(sum(flt(i.outstanding_amount) for i in open_ if i.overdue), 2),
		"overdue_count": sum(1 for i in open_ if i.overdue),
	}


def _facts(header):
	student = header["student"]
	invoices = _invoices(student)
	payments = _payments(student, invoices)
	return invoices, payments, _statement(invoices, payments)


# ---------------------------------------------------------------------------
# the page
# ---------------------------------------------------------------------------


@frappe.whitelist()
def fees():
	"""Everything the Fees page draws, in one response."""
	header = _me()
	if not header:
		# An admitted applicant waiting on the Registrar is an ordinary state.
		# The same shape, empty, so the page needs no special case for it.
		return {
			"enrollment": None,
			"summary": _summary([], []),
			"invoices": [],
			"payments": [],
			"statement": _statement([], []),
		}

	invoices, payments, statement = _facts(header)

	return {
		"enrollment": header,
		"summary": _summary(invoices, payments),
		"invoices": invoices,
		"payments": payments,
		"statement": statement,
	}


# ---------------------------------------------------------------------------
# PDFs
# ---------------------------------------------------------------------------

_STYLE = """
	body { font-family: Arial, Helvetica, sans-serif; color: #1c1e26; font-size: 12px; }
	h1 { font-size: 20px; margin: 0 0 2px; }
	h2 { font-size: 14px; margin: 22px 0 6px; }
	.college { font-size: 11px; letter-spacing: .06em; text-transform: uppercase; color: #555a6e; }
	.rule { border-top: 2px solid #2d2a8c; margin: 10px 0 16px; }
	table { border-collapse: collapse; width: 100%; }
	th { text-align: left; font-size: 10px; text-transform: uppercase; letter-spacing: .05em;
	     color: #555a6e; border-bottom: 1px solid #c8cad6; padding: 6px 6px; }
	td { padding: 6px 6px; border-bottom: 1px solid #e6e7ee; vertical-align: top; }
	.num { text-align: right; white-space: nowrap; }
	.meta td { border: 0; padding: 2px 0; }
	.meta td:first-child { color: #555a6e; width: 130px; }
	.total { font-size: 18px; font-weight: bold; }
	.box { border: 1px solid #c8cad6; padding: 10px 14px; margin: 14px 0; }
	.foot { margin-top: 28px; color: #7a7f93; font-size: 10px; }
"""


def _page(title, body):
	return (
		"<!doctype html><html><head><meta charset='utf-8'>"
		f"<title>{html.escape(title)}</title><style>{_STYLE}</style></head><body>"
		f"<div class='college'>{html.escape(COLLEGE_NAME)}</div>"
		f"<h1>{html.escape(title)}</h1><div class='rule'></div>{body}"
		"<div class='foot'>This is a computer-generated document and needs no signature.</div>"
		"</body></html>"
	)


def _e(value):
	return html.escape("" if value is None else str(value))


def _date(value):
	return formatdate(value, "dd MMM yyyy") if value else "—"


def _who(header):
	return (
		"<table class='meta'>"
		f"<tr><td>Student</td><td><b>{_e(header.get('student_name'))}</b></td></tr>"
		f"<tr><td>Student ID</td><td>{_e(header.get('student'))}</td></tr>"
		f"<tr><td>Programme</td><td>{_e(header.get('program_name') or header.get('program'))}</td></tr>"
		"</table>"
	)


def receipt_html(header, payment):
	"""One payment as a receipt. Separate from the endpoint so it can be tested
	without a PDF renderer."""
	applied = "".join(
		"<tr>"
		f"<td>{_e(row['invoice'])}</td>"
		f"<td>{_e(row['fee_type'] or '')}{(' · ' + _e(row['term'])) if row['term'] else ''}</td>"
		f"<td class='num'>{_money(row['amount'])}</td>"
		"</tr>"
		for row in payment["applied_to"]
	)
	credit = (
		f"<p>{_money(payment['unallocated_amount'])} of this payment is held as credit "
		"against future fees.</p>"
		if flt(payment["unallocated_amount"]) > 0.005
		else ""
	)

	body = (
		_who(header)
		+ "<div class='box'><table class='meta'>"
		f"<tr><td>Receipt no.</td><td><b>{_e(payment['name'])}</b></td></tr>"
		f"<tr><td>Received on</td><td>{_date(payment['received_on'])}</td></tr>"
		f"<tr><td>Paid by</td><td>{_e(payment['mode'])}</td></tr>"
		+ (
			f"<tr><td>Reference</td><td>{_e(payment['reference_no'])}</td></tr>"
			if payment["reference_no"]
			else ""
		)
		+ f"<tr><td>Amount received</td><td class='total'>{_money(payment['amount'])}</td></tr>"
		"</table></div>"
		+ (
			"<h2>Applied to</h2><table><tr><th>Invoice</th><th>For</th>"
			f"<th class='num'>Amount</th></tr>{applied}</table>"
			if applied
			else ""
		)
		+ credit
	)
	return _page(_("Payment receipt"), body)


def statement_html(header, statement):
	rows = "".join(
		"<tr>"
		f"<td>{_date(row['date'])}</td>"
		f"<td>{_e(row['particulars'])}<br><span style='color:#7a7f93'>{_e(row['reference'])}</span></td>"
		f"<td class='num'>{_money(row['charge']) if row['charge'] else ''}</td>"
		f"<td class='num'>{_money(row['credit']) if row['credit'] else ''}</td>"
		f"<td class='num'>{_money(row['balance'])}</td>"
		"</tr>"
		for row in statement["rows"]
	)
	balance = statement["balance"]
	standing = (
		_("Outstanding")
		if balance > 0.005
		else _("In credit")
		if balance < -0.005
		else _("Settled")
	)

	body = (
		_who(header)
		+ f"<p style='color:#555a6e'>As on {_date(today())}</p>"
		+ (
			"<table><tr><th>Date</th><th>Particulars</th><th class='num'>Charge</th>"
			f"<th class='num'>Paid</th><th class='num'>Balance</th></tr>{rows}</table>"
			if rows
			else "<p>Nothing has been billed to this account yet.</p>"
		)
		+ "<div class='box'><table class='meta'>"
		f"<tr><td>Total charged</td><td>{_money(statement['charges'])}</td></tr>"
		f"<tr><td>Total paid or waived</td><td>{_money(statement['credits'])}</td></tr>"
		f"<tr><td>Balance</td><td class='total'>{_money(abs(balance))} "
		f"<span style='font-size:12px;font-weight:normal'>{_e(standing)}</span></td></tr>"
		"</table></div>"
	)
	return _page(_("Statement of account"), body)


def _send_pdf(document, filename):
	"""Render and hand back as a PDF, or say plainly that it cannot be done.

	The renderer is an external program that may not be installed, so a failure
	here is reported as what it is -- the page also offers Print, which needs no
	server-side renderer at all.
	"""
	from frappe.utils.pdf import get_pdf

	try:
		content = get_pdf(document)
	except Exception:
		frappe.log_error(title="Student fee PDF could not be rendered")
		frappe.throw(
			_("The PDF could not be made just now. Use Print instead, or ask the office."),
			title=_("PDF Unavailable"),
		)

	frappe.local.response.filename = filename
	frappe.local.response.filecontent = content
	frappe.local.response.type = "pdf"


@frappe.whitelist()
def receipt(payment):
	"""One of the signed-in student's own payments, as a PDF receipt."""
	header = _me()
	if not header:
		frappe.throw(_("Receipt not found."), frappe.DoesNotExistError)

	invoices, payments, _statement_unused = _facts(header)
	mine = next((p for p in payments if p.name == payment), None)

	# Not yours and not real are one answer: this must not become a way to
	# discover which receipt numbers exist.
	if not mine:
		frappe.throw(_("Receipt not found."), frappe.DoesNotExistError)

	_send_pdf(receipt_html(header, mine), f"receipt-{mine.name}.pdf")


@frappe.whitelist()
def statement():
	"""The signed-in student's whole account, as a PDF."""
	header = _me()
	if not header:
		frappe.throw(_("There is no account to show yet."), frappe.DoesNotExistError)

	_invoices_unused, _payments_unused, account = _facts(header)
	_send_pdf(statement_html(header, account), f"statement-{header['student']}.pdf")
