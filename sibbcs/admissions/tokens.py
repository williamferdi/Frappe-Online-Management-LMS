"""One token-link controller, reused by every no-login form.

Architecture doc §4 lists four such forms: Reference, Mentor Consent, Mentor
Monthly Report (Phase 6) and Internship Supervisor Verification (Phase 6). They
all share the same shape -- a row somewhere carries an opaque `token`, an
outsider opens `?token=<uuid>`, fills a form once, and never authenticates.

Registering a form here is a one-line entry in `TOKEN_TARGETS`.

Security notes:
* Tokens are `secrets.token_urlsafe(32)` -- ~256 bits, not guessable, and not
  derived from any document field.
* Lookup is constant-work: we query by the token column rather than iterating.
* A token identifies exactly one child row of one parent document. It grants
  nothing else -- no session, no read access to the parent.
* Resolution refuses tokens that were already used, so a leaked link cannot
  overwrite a submitted reference.
"""

import secrets

import frappe
from frappe import _

# form key -> how to find and interpret the row carrying the token
TOKEN_TARGETS = {
	"reference": {
		"child_doctype": "Reference Request",
		"parent_doctype": "Admission Application",
		"parentfield": "reference_requests",
		"submitted_field": "submitted_on",
		"label": "Reference",
	},
	"mentor-consent": {
		"child_doctype": "Mentor Consent",
		"parent_doctype": "Admission Application",
		"parentfield": "mentor_consents",
		"submitted_field": "consented_on",
		"label": "Mentor Consent",
	},
}


class TokenError(frappe.ValidationError):
	"""Raised for missing, unknown, or already-used tokens."""


def generate_token():
	return secrets.token_urlsafe(32)


def resolve(form_key, token, allow_used=False):
	"""Look up the row a token points at.

	Returns a dict with the child row name, the parent document name and the
	target spec. Raises TokenError with a deliberately vague message -- we do
	not distinguish "no such token" from "already used" to a caller who has not
	proved anything.
	"""
	spec = TOKEN_TARGETS.get(form_key)
	if not spec:
		raise TokenError(_("Unknown form."))

	if not token or not isinstance(token, str) or len(token) < 20:
		raise TokenError(_("This link is not valid."))

	rows = frappe.get_all(
		spec["child_doctype"],
		filters={
			"token": token,
			"parenttype": spec["parent_doctype"],
			"parentfield": spec["parentfield"],
		},
		fields=["name", "parent", spec["submitted_field"]],
		limit=2,
		ignore_permissions=True,
	)

	if len(rows) != 1:
		raise TokenError(_("This link is not valid or has expired."))

	row = rows[0]
	if row.get(spec["submitted_field"]) and not allow_used:
		raise TokenError(_("This form has already been submitted. Thank you."))

	return {
		"row_name": row["name"],
		"parent": row["parent"],
		"spec": spec,
		"form_key": form_key,
	}


def get_context_for(form_key, token):
	"""Safe, minimal context for rendering a token form.

	Only what the outsider legitimately needs to recognise the request: who the
	applicant is and which program. Never the whole application.
	"""
	resolved = resolve(form_key, token)
	spec = resolved["spec"]

	row = frappe.db.get_value(
		spec["child_doctype"],
		resolved["row_name"],
		"*",
		as_dict=True,
	)
	applicant, program = frappe.db.get_value(
		spec["parent_doctype"], resolved["parent"], ["full_name", "program"]
	)

	return {
		"token": token,
		"form_key": form_key,
		"label": spec["label"],
		"applicant_name": applicant,
		"program": program,
		"row": row,
		"application": resolved["parent"],
	}


def mark_submitted(form_key, token, values):
	"""Write an outsider's answers back onto the child row.

	Runs with ignore_permissions because the submitter is Guest by design; the
	token is the authorisation. Only fields belonging to the resolved row are
	written -- `values` is applied key by key against the row's own meta, so a
	crafted payload cannot reach other fields or other documents.
	"""
	resolved = resolve(form_key, token)
	spec = resolved["spec"]

	parent = frappe.get_doc(spec["parent_doctype"], resolved["parent"])
	row = next((r for r in parent.get(spec["parentfield"]) if r.name == resolved["row_name"]), None)
	if not row:
		raise TokenError(_("This link is not valid or has expired."))

	allowed = {df.fieldname for df in frappe.get_meta(spec["child_doctype"]).fields}
	for key, value in (values or {}).items():
		if key in allowed and key not in ("token", "name", "parent", "parenttype", "parentfield"):
			row.set(key, value)

	row.set(spec["submitted_field"], frappe.utils.now_datetime())

	parent.flags.ignore_permissions = True
	parent.flags.ignore_validate_update_after_submit = True
	parent.save(ignore_permissions=True)

	# Deliberately no frappe.db.commit() here. Frappe commits automatically at
	# the end of a successful whitelisted request, so guest submissions persist
	# either way -- while an explicit commit would also commit the surrounding
	# transaction, which defeats FrappeTestCase's rollback and leaves test
	# records behind on a live site.
	return {"ok": True, "application": resolved["parent"]}


# ---------------------------------------------------------------------------
# guest endpoint
# ---------------------------------------------------------------------------


@frappe.whitelist(allow_guest=True)
def submit(form_key, token, **values):
	"""Submit a token form. The token is the only credential."""
	values.pop("cmd", None)
	try:
		return mark_submitted(form_key, token, values)
	except TokenError:
		raise
	except Exception:
		frappe.log_error(title="Token form submission failed")
		frappe.throw(_("Could not save your response. Please try again."))


@frappe.whitelist(allow_guest=True, methods=["POST"])
def submit_reference(token, answers):
	"""Submit the Spiritual and Ministerial Reference questionnaire.

	Separate from the generic `submit` because the answers are validated
	against the question definitions server-side -- the endpoint is public, so
	the browser's version of the form is not to be trusted.
	"""
	from sibbcs.admissions.reference_form import submit as submit_reference_form

	try:
		return submit_reference_form(token, answers)
	except TokenError:
		raise
	except frappe.ValidationError:
		raise
	except Exception:
		frappe.log_error(title="Reference form submission failed")
		frappe.throw(_("Could not save your response. Please try again."))
