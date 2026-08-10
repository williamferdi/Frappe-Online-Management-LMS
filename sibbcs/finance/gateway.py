"""Payment gateway boundary.

Everything outside `sibbcs/finance/<provider>.py` talks to the gateway through
this module, so swapping providers touches one file plus one new module -- not
the schema, the public form, the return page or the fee engine.

Which provider is live is site config, not code:

    bench --site online.sibbc.org set-config payment_provider razorpay

A provider module must expose:

    is_configured()              -> bool
    create_payment_link(invoice) -> url string
    PROVIDER_NAME                -> str, recorded on the invoice and payment

Webhooks stay provider-specific on purpose. Each gateway signs its callbacks
differently, and verifying that signature is the one part that must not be
generalised into a lowest common denominator -- so each provider owns its own
`@frappe.whitelist(allow_guest=True)` endpoint and its own verification.
"""

import frappe
from frappe import _

PROVIDERS = {
	"razorpay": "sibbcs.finance.razorpay",
}

DEFAULT_PROVIDER = "razorpay"


def active_provider():
	name = (frappe.conf.get("payment_provider") or DEFAULT_PROVIDER).strip().lower()
	return name if name in PROVIDERS else DEFAULT_PROVIDER


def get_provider(name=None):
	name = (name or active_provider()).lower()
	path = PROVIDERS.get(name)
	if not path:
		frappe.throw(
			_("Unknown payment provider '{0}'. Known: {1}").format(
				name, ", ".join(sorted(PROVIDERS))
			)
		)
	return frappe.get_module(path)


def is_configured(name=None):
	try:
		return bool(get_provider(name).is_configured())
	except Exception:
		return False


def create_payment_link(fee_invoice, name=None):
	"""Ask the live provider for a payment link for this invoice."""
	provider = get_provider(name)
	url = provider.create_payment_link(fee_invoice)

	frappe.db.set_value(
		"Fee Invoice",
		fee_invoice,
		"payment_provider",
		getattr(provider, "PROVIDER_NAME", active_provider()),
		update_modified=False,
	)
	return url


def public_url(path=""):
	"""An externally reachable URL for this site.

	Not frappe.utils.get_url(): that appends the dev webserver port (:8000)
	unless the site is running under supervisor/systemd, so on a bench-start
	deployment it produces addresses the outside world cannot reach. These URLs
	are handed to a payment gateway and to the candidate's browser, so they
	must be right regardless of how the site happens to be served.

	Set once with:
	    bench --site online.sibbc.org set-config host_name https://online.sibbc.org
	"""
	host = (frappe.conf.get("host_name") or "").strip().rstrip("/")
	if not host:
		host = frappe.utils.get_url().rstrip("/")
	if not host.startswith(("http://", "https://")):
		host = "https://" + host
	return f"{host}/{path.lstrip('/')}" if path else host


def webhook_url(name=None):
	"""The endpoint to register in the provider's dashboard."""
	provider = (name or active_provider()).lower()
	return public_url(f"/api/method/{PROVIDERS[provider]}.webhook")


@frappe.whitelist()
def status():
	"""Small report for the Desk: which gateway is live and is it usable."""
	frappe.only_for(("Accounts", "System Manager", "Registrar"))
	name = active_provider()
	return {
		"provider": name,
		"configured": is_configured(name),
		"webhook_url": webhook_url(name),
		"known_providers": sorted(PROVIDERS),
	}
