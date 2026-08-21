"""Scholarship Form Review: the form, and the Registrar's review of it.

It sits after the Zoom interview, because that conversation is where the
college learns whether a candidate needs a scholarship at all.

The questions and the wording are the college's own, from their Zoho form:
student name, student email, a financial-need statement capped at 250 words,
and a drawn signature.

**Why this does not use tokens.py.** That controller resolves a token to one
*child row* of a parent -- a referee, a mentor, a manual. A Scholarship Request
is a standalone document referenced by `Admission Application.scholarship_request`,
so there is no child row to point at. The token therefore lives on the
application itself, next to `upload_token`, and is resolved here. One
application, one scholarship form.

**The cap is per program, and it lives on the Program.** The college's form
states 24,000 for M.Div, 16,000 for M.A.C.S. and 8,000 for the Graduate
Diploma -- 8,000 a year against programmes of three, two and one year. Putting
those numbers in code would mean a deploy every time the college revises them,
so they sit on `Program.scholarship_max` and the form reads whichever applies
to the candidate. An approval above the cap is refused.

What the candidate never sees: their own award. `approved_amount` and
`monthly_discount` are the Registrar's, set on the Scholarship Request, and
`conversion._apply_scholarship` copies them onto the Program Enrollment at
onboarding -- which is what makes the cap real, because the tuition job stops
discounting once `scholarship_used_to_date` reaches it.
"""

import base64
import re

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, today

from sibbcs.admissions.doctype.admission_application.admission_application import token_url
from sibbcs.admissions.tokens import TokenError, generate_token

from sibbcs.admissions.checklist import NO

STEP = NO["scholarship"]
FORM_KEY = "scholarship"
WORD_LIMIT = 250
DEFAULT_PER_YEAR = 8000
MAX_SIGNATURE_BYTES = 512 * 1024
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


# ---------------------------------------------------------------------------
# what the candidate is told
# ---------------------------------------------------------------------------


def per_year():
	"""The annual figure quoted in the introduction."""
	return flt(frappe.conf.get("scholarship_per_year") or DEFAULT_PER_YEAR)


def program_cap(program):
	"""The most this programme's scholarship can be worth in total."""
	if not program:
		return 0
	return flt(frappe.db.get_value("Program", program, "scholarship_max"))


def intro(program=None):
	"""The college's own wording, with the figure that applies to this one."""
	return {
		"lead": (
			"Dear Candidate, we are pleased to invite you to apply for a "
			"scholarship designed to support students who face financial "
			"challenges but are committed to pursuing ministerial training "
			"through our seminary's online programs."
		),
		"body": (
			"This scholarship program was created to help those with genuine "
			"financial need, offering up to {0} rupees per year. Our hope is that "
			"this assistance will ease your financial burden and allow you to "
			"focus wholeheartedly on your calling and your studies."
		).format(frappe.utils.fmt_money(per_year(), currency="INR", precision=0).lstrip("₹")),
		"program": program,
		"program_cap": program_cap(program),
		"terms": (
			"By accepting this scholarship, you agree to pursue your coursework "
			"diligently and to uphold the standards and expectations of the "
			"seminary. Please keep in mind that not meeting these commitments may "
			"result in the scholarship being withdrawn. We believe in your "
			"dedication and look forward to seeing you grow in both your "
			"spiritual and academic journey."
		),
		"word_limit": WORD_LIMIT,
	}


def word_count(text):
	return len([word for word in re.split(r"\s+", (text or "").strip()) if word])


# ---------------------------------------------------------------------------
# the link
# ---------------------------------------------------------------------------


def ensure_token(doc):
	if not doc.scholarship_token:
		doc.db_set("scholarship_token", generate_token(), update_modified=False)
		doc.reload()
	return doc.scholarship_token


def resolve(token):
	"""The application a scholarship token points at.

	Deliberately vague on failure: we do not tell an unauthenticated caller
	whether a token is unknown or merely spent.
	"""
	if not token or not isinstance(token, str) or len(token) < 20:
		raise TokenError(_("This link is not valid."))

	rows = frappe.get_all(
		"Admission Application",
		filters={"scholarship_token": token},
		fields=["name", "full_name", "email", "program", "scholarship_request"],
		limit=2,
		ignore_permissions=True,
	)
	if len(rows) != 1:
		raise TokenError(_("This link is not valid or has expired."))

	if rows[0].scholarship_request:
		raise TokenError(_("This form has already been submitted. Thank you."))

	return rows[0]


FALLBACK_INVITE = (
	"Scholarship form -- {{ program }}",
	"<p>Dear {{ applicant_name }},</p>"
	"<p>You may apply for a scholarship towards your studies at South India "
	"Baptist Bible College &amp; Seminary. Please complete the short form "
	"here:</p>"
	'<p><a href="{{ link }}">{{ link }}</a></p>'
	"<p>Admissions Office</p>",
)


def send_form(application):
	"""Email the candidate their scholarship form link."""
	from sibbcs.admissions.notifications import outgoing_configured, render_template

	doc = frappe.get_doc("Admission Application", application)

	report = {"application": doc.name, "link": None, "emailed": None, "warnings": []}

	if doc.scholarship_request:
		report["warnings"].append(
			f"A scholarship request ({doc.scholarship_request}) already exists for "
			"this application."
		)
		return report

	link = token_url(FORM_KEY, ensure_token(doc))
	report["link"] = link
	doc.db_set("scholarship_form_url", link, update_modified=False)

	if not doc.email:
		report["warnings"].append("This application has no email address.")
		return report

	if not outgoing_configured():
		report["warnings"].append(
			"No outgoing email account is configured, so nothing was sent."
		)
		return report

	context = {
		"applicant_name": doc.full_name,
		"program": doc.program,
		"program_cap": program_cap(doc.program),
		"per_year": per_year(),
		"link": link,
		"application_id": doc.name,
	}
	subject, message = render_template("scholarship_form", context, *FALLBACK_INVITE)

	try:
		frappe.sendmail(
			recipients=[doc.email],
			subject=subject,
			message=message,
			header=[_("Scholarship"), "blue"],
			now=False,
		)
	except Exception:
		frappe.log_error(title=f"Scholarship form failed for {doc.name}")
		report["warnings"].append("The email could not be sent.")
		return report

	report["emailed"] = doc.email
	doc.db_set("scholarship_form_sent_on", now_datetime(), update_modified=False)
	_mark_step(doc.name, "Form Sent", only_from=("Not Applicable",))
	return report


# ---------------------------------------------------------------------------
# the candidate's submission
# ---------------------------------------------------------------------------


def _decode_signature(data_url):
	"""The bytes behind a canvas data URL, checked before anything is created.

	The browser sends a data URL, so the bytes are ours to inspect rather than
	a file the candidate chose: anything that is not a PNG did not come from
	the pad. Note the throwaway name below is not `_` -- that is frappe's
	translation function, and shadowing it turns every error message in this
	function into a TypeError.
	"""
	if not data_url:
		return None

	head, _sep, encoded = str(data_url).partition(",")
	if "image/png" not in head or not encoded:
		frappe.throw(_("The signature could not be read."), title=_("Invalid Signature"))

	try:
		raw = base64.b64decode(encoded, validate=True)
	except Exception:
		frappe.throw(_("The signature could not be read."), title=_("Invalid Signature"))

	if not raw.startswith(PNG_MAGIC):
		frappe.throw(_("The signature could not be read."), title=_("Invalid Signature"))
	if len(raw) > MAX_SIGNATURE_BYTES:
		frappe.throw(_("The signature is too large."), title=_("Invalid Signature"))

	return raw


def _store_signature(raw, docname, applicant, doctype="Scholarship Request"):
	"""Attach already-validated signature bytes to a document, privately.

	Shared with the manual acknowledgement, which signs the same way. A
	signature is a person's mark: private, always, regardless of what it is
	attached to.
	"""
	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"signature-{frappe.scrub(applicant or 'candidate')}.png",
			"attached_to_doctype": doctype,
			"attached_to_name": docname,
			"attached_to_field": "signature",
			"is_private": 1,
			"content": raw,
			"decode": False,
		}
	)
	file_doc.flags.ignore_permissions = True
	file_doc.insert(ignore_permissions=True)
	return file_doc.file_url


def submit(token, statement, signature=None):
	"""Record a candidate's scholarship form. One per application."""
	app = resolve(token)

	statement = (statement or "").strip()
	if not statement:
		frappe.throw(
			_("Please explain your financial need."), title=_("Incomplete")
		)
	if word_count(statement) > WORD_LIMIT:
		frappe.throw(
			_("Please keep your answer to {0} words or fewer.").format(WORD_LIMIT),
			title=_("Too Long"),
		)
	if not signature:
		frappe.throw(_("Please sign the form."), title=_("Signature Needed"))

	# Checked before the request exists, so a bad signature cannot leave a
	# Scholarship Request behind with nothing attached to it.
	raw_signature = _decode_signature(signature)

	request = frappe.get_doc(
		{
			"doctype": "Scholarship Request",
			"application": app.name,
			"program": app.program,
			"status": "Submitted",
			"justification": statement,
			"submitted_on": now_datetime(),
			"ip_address": frappe.local.request_ip or "",
		}
	)
	request.flags.ignore_permissions = True
	request.insert(ignore_permissions=True)

	file_url = _store_signature(raw_signature, request.name, app.full_name)
	if file_url:
		request.db_set("signature", file_url, update_modified=False)

	frappe.db.set_value(
		"Admission Application",
		app.name,
		"scholarship_request",
		request.name,
		update_modified=False,
	)
	_mark_step(app.name, "Received")

	return {"ok": True, "request": request.name}


# ---------------------------------------------------------------------------
# the Registrar's review
# ---------------------------------------------------------------------------


def _mark_step(application, status, only_from=None):
	name = frappe.db.get_value(
		"Admission Checklist Item",
		{"parent": application, "parenttype": "Admission Application", "step_no": STEP},
		"name",
	)
	if not name:
		return

	current = frappe.db.get_value("Admission Checklist Item", name, "status")
	if only_from and current not in only_from:
		return
	if current in ("Approved", "Rejected") and status not in ("Approved", "Rejected"):
		return  # a decision already made is not walked back by a later send

	frappe.db.set_value(
		"Admission Checklist Item",
		name,
		{"status": status, "updated_by": frappe.session.user, "updated_on": now_datetime()},
		update_modified=False,
	)


@frappe.whitelist()
def decide(request, outcome, approved_amount=0, monthly_discount=0, remarks=None):
	"""Approve or reject one scholarship request. Registrar's action."""
	doc = frappe.get_doc("Scholarship Request", request)
	doc.check_permission("write")

	if outcome not in ("Approved", "Rejected"):
		frappe.throw(_("Outcome must be Approved or Rejected."))

	if outcome == "Approved":
		approved = flt(approved_amount)
		cap = program_cap(doc.program)
		if approved <= 0:
			frappe.throw(_("Enter the amount awarded."), title=_("Nothing Awarded"))
		if cap and approved > cap:
			frappe.throw(
				_("{0} is above the {1} cap of {2}.").format(
					frappe.utils.fmt_money(approved, currency="INR"),
					doc.program,
					frappe.utils.fmt_money(cap, currency="INR"),
				),
				title=_("Above the Cap"),
			)
		doc.approved_amount = approved
		doc.monthly_discount = flt(monthly_discount)
	else:
		doc.approved_amount = 0
		doc.monthly_discount = 0

	doc.status = outcome
	doc.approved_by = frappe.session.user
	doc.approved_on = today()
	doc.flags.ignore_permissions = True
	doc.save(ignore_permissions=True)

	if doc.application:
		_mark_step(doc.application, outcome)
		if remarks:
			frappe.db.set_value(
				"Admission Checklist Item",
				{
					"parent": doc.application,
					"parenttype": "Admission Application",
					"step_no": STEP,
				},
				"remarks",
				remarks,
				update_modified=False,
			)

	return {"request": doc.name, "status": doc.status, "approved": doc.approved_amount}


# ---------------------------------------------------------------------------
# Desk and guest endpoints
# ---------------------------------------------------------------------------


@frappe.whitelist()
def send(application):
	doc = frappe.get_doc("Admission Application", application)
	doc.check_permission("write")

	report = send_form(application)

	lines = []
	if report["emailed"]:
		lines.append(_("Scholarship form sent to <b>{0}</b>.").format(report["emailed"]))
	if report["link"]:
		lines.append(_("Their link: {0}").format(report["link"]))
	for warning in report["warnings"]:
		lines.append(f"<span style='color:var(--orange-600)'>{warning}</span>")

	frappe.msgprint(
		"<br>".join(lines),
		title=_("Scholarship Form"),
		indicator="orange" if report["warnings"] else "green",
	)
	return report


@frappe.whitelist(allow_guest=True, methods=["POST"])
def submit_form(token, statement, signature=None):
	try:
		return submit(token, statement, signature)
	except TokenError:
		raise
	except frappe.ValidationError:
		raise
	except Exception:
		frappe.log_error(title="Scholarship form submission failed")
		frappe.throw(_("Could not save your form. Please try again."))
