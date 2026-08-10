"""The public application form -- architecture doc §2.1, §4.

A prospective student fills this in at `/apply` with no login and no account.
It creates an Admission Application in **Draft**, which is where the Admissions
Officer picks it up.

Security shape, because this is the one endpoint an anonymous stranger can
write to:

* **Field whitelist, not blacklist.** Only `APPLICANT_FIELDS` is ever copied off
  the request. Every gate (`application_fee_paid`, `docs_verified`,
  `admission_fee_paid`), the workflow state, the exam score, the interview
  outcome and the `student` link are unreachable by construction -- a crafted
  payload cannot set them because they are not in the list.
* **Rate limited per IP**, so the form cannot be used to bulk-create records.
* **Honeypot field** that real people never fill in.
* **Duplicate guard**: one open application per email address.
* No file uploads. Guest file upload is a large attack surface for very little
  gain -- documents are collected after Submitted, during Documents Under
  Review, where the officer can already see who is asking.
"""

import frappe
from frappe import _
from frappe.utils import getdate, nowdate, validate_email_address

# The only fields a candidate may set. Everything else on the DocType --
# gates, workflow state, scores, outcomes, the student link -- is unreachable.
APPLICANT_FIELDS = (
	"full_name",
	"dob",
	"gender",
	"mobile",
	"whatsapp",
	"email",
	"address",
	"church_name",
	"current_role",
	"years_of_ministry",
	"has_bachelors",
	"program",
	"intake_term",
)

MAX_LEN = {
	"full_name": 140,
	"mobile": 20,
	"whatsapp": 20,
	"email": 140,
	"address": 500,
	"church_name": 140,
	"current_role": 140,
}


def open_programs():
	return frappe.get_all(
		"Program",
		filters={"is_active": 1},
		fields=["name", "program_name"],
		order_by="program_name",
	)


def open_intakes():
	"""Terms still accepting applications."""
	terms = frappe.get_all(
		"Academic Term",
		filters={"status": ("in", ("Planned", "Open"))},
		fields=["name", "term_name", "application_deadline", "start_date"],
		order_by="start_date",
	)
	today = getdate(nowdate())
	return [
		t
		for t in terms
		if not t.application_deadline or getdate(t.application_deadline) >= today
	]


def _clean(values):
	"""Copy only whitelisted fields, trimmed and length-capped."""
	cleaned = {}
	for field in APPLICANT_FIELDS:
		value = values.get(field)
		if value in (None, ""):
			continue
		if isinstance(value, str):
			value = value.strip()
			cap = MAX_LEN.get(field)
			if cap:
				value = value[:cap]
		cleaned[field] = value

	cleaned["email"] = (cleaned.get("email") or "").lower()
	cleaned["has_bachelors"] = 1 if str(values.get("has_bachelors")) in ("1", "true", "on", "yes") else 0
	return cleaned


def _validate(cleaned, referees):
	missing = [f for f in ("full_name", "email", "mobile", "program") if not cleaned.get(f)]
	if missing:
		frappe.throw(
			_("Please fill in: {0}").format(", ".join(frappe.unscrub(m) for m in missing))
		)

	validate_email_address(cleaned["email"], throw=True)

	if not frappe.db.exists("Program", cleaned["program"]):
		frappe.throw(_("Please choose a programme from the list."))

	if cleaned.get("intake_term"):
		valid = {t.name for t in open_intakes()}
		if cleaned["intake_term"] not in valid:
			frappe.throw(_("That intake is no longer accepting applications."))

	if cleaned.get("dob") and getdate(cleaned["dob"]) >= getdate(nowdate()):
		frappe.throw(_("Date of birth must be in the past."))

	seen = set()
	for referee in referees:
		email = (referee.get("referee_email") or "").strip().lower()
		if not (referee.get("referee_name") and email):
			continue
		validate_email_address(email, throw=True)
		if email == cleaned["email"]:
			frappe.throw(_("You cannot list yourself as a referee."))
		if email in seen:
			frappe.throw(_("The same referee is listed twice."))
		seen.add(email)


def _existing_open_application(email):
	"""One live application per email address."""
	return frappe.db.exists(
		"Admission Application",
		{
			"email": email,
			"workflow_state": ("not in", ("Rejected", "Withdrawn", "Orientation Registered")),
		},
	)


def _referees_from(values):
	rows = []
	for index in (1, 2):
		name = (values.get(f"referee{index}_name") or "").strip()
		email = (values.get(f"referee{index}_email") or "").strip().lower()
		kind = values.get(f"referee{index}_type") or "Pastor-Mentor"
		if name and email:
			rows.append(
				{"referee_name": name[:140], "referee_email": email[:140], "referee_type": kind}
			)
	return rows


def _mentor_from(values):
	name = (values.get("mentor_name") or "").strip()
	email = (values.get("mentor_email") or "").strip().lower()
	if not (name and email):
		return []
	return [
		{
			"mentor_name": name[:140],
			"mentor_email": email[:140],
			"mentor_mobile": (values.get("mentor_mobile") or "").strip()[:20],
			"church": (values.get("mentor_church") or "").strip()[:140],
		}
	]


@frappe.whitelist(allow_guest=True, methods=["POST"])
def submit_application(**values):
	"""Create a Draft Admission Application from the public form."""
	values.pop("cmd", None)

	# Honeypot: a hidden field no human ever completes.
	if (values.get("website") or "").strip():
		frappe.throw(_("Your application could not be submitted."))

	_rate_limit()

	cleaned = _clean(values)
	referees = _referees_from(values)
	mentor = _mentor_from(values)

	_validate(cleaned, referees)

	existing = _existing_open_application(cleaned["email"])
	if existing:
		frappe.throw(
			_(
				"An application already exists for {0} (reference {1}). "
				"Please contact the Admissions Office rather than applying twice."
			).format(cleaned["email"], existing),
			title=_("Already Applied"),
		)

	doc = frappe.get_doc({"doctype": "Admission Application", **cleaned})
	for referee in referees:
		doc.append("reference_requests", referee)
	for row in mentor:
		doc.append("mentor_consents", row)

	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)

	_notify(doc)

	return {
		"application": doc.name,
		"full_name": doc.full_name,
		"program": doc.program,
	}


def _rate_limit():
	"""Cap submissions per IP. Best-effort -- never blocks a real applicant
	because the cache is unavailable."""
	try:
		ip = frappe.local.request_ip or "unknown"
		key = f"sibbcs:apply:{ip}"
		cache = frappe.cache()
		count = cache.get_value(key) or 0
		if int(count) >= 5:
			frappe.throw(
				_("Too many applications from this connection. Please try again later."),
				title=_("Slow Down"),
			)
		cache.set_value(key, int(count) + 1, expires_in_sec=3600)
	except frappe.ValidationError:
		raise
	except Exception:
		pass


def outgoing_mail_configured():
	# Email Account has no `enabled` field; the outgoing switch is `enable_outgoing`.
	return bool(
		frappe.db.get_value(
			"Email Account", {"default_outgoing": 1, "enable_outgoing": 1}, "name"
		)
	)


def _notify(doc):
	"""Acknowledge to the applicant and alert the Admissions Officers.

	Queued, never inline: a mail failure must not lose an application that has
	already been accepted.

	Two guards, both learned the hard way. We check for an outgoing account
	first, because frappe.sendmail with none configured raises *and* pushes
	"Please setup default outgoing Email Account from Tools > Email Account"
	onto the message log -- which then travels back to the anonymous applicant
	in the API response. And we clear the message log afterwards regardless, so
	no internal mail plumbing can ever surface on the public form.
	"""
	if not outgoing_mail_configured():
		frappe.logger("sibbcs").info(
			f"{doc.name}: no outgoing email account, acknowledgement skipped"
		)
		return

	try:
		if doc.email:
			frappe.sendmail(
				recipients=[doc.email],
				subject=_("We have received your application — {0}").format(doc.name),
				message=_(
					"<p>Dear {0},</p>"
					"<p>Thank you for applying to South India Baptist Bible College &amp; "
					"Seminary (Online). Your application reference is <b>{1}</b>.</p>"
					"<p>Our Admissions Office will contact you about the application fee "
					"and the documents we need next. Please quote your reference in any "
					"correspondence.</p>"
				).format(doc.full_name, doc.name),
				now=False,
			)

		officers = frappe.get_all(
			"Has Role", filters={"role": "Admissions Officer", "parenttype": "User"}, pluck="parent"
		)
		officers = [e for e in officers if "@" in (e or "")]
		if officers:
			frappe.sendmail(
				recipients=officers,
				subject=_("New application: {0} — {1}").format(doc.full_name, doc.program),
				message=_("<p>{0} has applied for {1}. Reference <b>{2}</b>.</p>").format(
					doc.full_name, doc.program, doc.name
				),
				now=False,
			)
	except Exception:
		frappe.log_error(title=f"Application acknowledgement failed for {doc.name}")
	finally:
		# Never let mail plumbing reach the applicant's screen.
		frappe.clear_messages()
