"""Step 7: the applicant's LMS account, and the entrance exam link.

Step 8 (Entrance Exam Review) is gated on this step, and the reason is
practical rather than bureaucratic: the entrance exam is sat inside the LMS,
so an applicant with no account cannot sit it.

Three decisions worth recording.

**One account, kept for life.** The login created here is the same one the
applicant keeps as a student. `conversion._create_user` links an existing User
by email rather than making a second, so an admitted applicant never has to
learn a new address, and their exam attempt stays attached to them.

**No password is ever emailed.** We send a set-your-own-password link -- the
same `/update-password?key=` mechanism Frappe uses for a forgotten password.
A password in an inbox is a password in an inbox forever, and the office would
end up knowing every applicant's.

**The applicant is not yet a Student.** They get `LMS Student`, which opens the
LMS, and nothing else. The `Student` role is granted at conversion, when it is
true.

Two settings, neither hardcoded:

    bench --site online.sibbc.org set-config entrance_exam_lms_course "<lms course>"
    bench --site online.sibbc.org set-config entrance_exam_url "<full url>"

`entrance_exam_url` wins if both are set, for an exam that lives outside the
LMS. With the course set we also enroll the applicant, so it appears on their
dashboard rather than only in an email they have to keep.
"""

from urllib.parse import urlsplit

import frappe
from frappe import _
from frappe.utils import now_datetime

from sibbcs.finance.gateway import public_url

LMS_ROLE = "LMS Student"
STEP = 7


# ---------------------------------------------------------------------------
# the exam
# ---------------------------------------------------------------------------


def exam_course():
	"""The LMS Course the entrance exam lives in, if it lives in the LMS."""
	name = (frappe.conf.get("entrance_exam_lms_course") or "").strip()
	if not name:
		return None
	if not frappe.db.exists("LMS Course", name):
		frappe.log_error(
			title="Entrance exam course not found",
			message=f"entrance_exam_lms_course is set to {name!r}, which does not exist.",
		)
		return None
	return name


def exam_link():
	"""Where the applicant sits the exam, or None if nobody has said."""
	override = (frappe.conf.get("entrance_exam_url") or "").strip()
	if override:
		return override

	course = exam_course()
	if course:
		return public_url(f"/lms/courses/{course}")

	return None


def exam_configured():
	return bool(exam_link())


# ---------------------------------------------------------------------------
# the account
# ---------------------------------------------------------------------------


def ensure_user(doc):
	"""Create or adopt the User for this applicant. Returns (name, created)."""
	email = (doc.email or "").strip().lower()
	if not email:
		frappe.throw(
			_("This application has no email address, so no account can be made."),
			title=_("No Email"),
		)

	created = False

	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
		# An existing-but-disabled account is somebody's decision, not an
		# accident. Re-enabling it silently would undo that decision.
		if not user.enabled:
			frappe.throw(
				_(
					"A disabled account already exists for {0}. Enable it first, or "
					"correct the email on this application."
				).format(email),
				title=_("Account Disabled"),
			)
	else:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": doc.full_name or email,
				"user_type": "Website User",
				# Our own invite carries the exam link and is the only mail the
				# applicant should get; Frappe's welcome mail would arrive
				# alongside it saying something different.
				"send_welcome_email": 0,
			}
		)
		# User.mobile_no is UNIQUE and shared handsets are ordinary here, so
		# only claim a number nobody holds. See conversion._create_user.
		if doc.mobile and not frappe.db.exists("User", {"mobile_no": doc.mobile}):
			user.mobile_no = doc.mobile
		user.flags.ignore_permissions = True
		user.insert(ignore_permissions=True)
		created = True

	if not any(r.role == LMS_ROLE for r in user.roles):
		user.append("roles", {"role": LMS_ROLE})
		user.save(ignore_permissions=True)

	return user.name, created


def set_password_link(user_name):
	"""A link that lets the applicant choose their own password.

	`User._reset_password` builds its URL with frappe.utils.get_url(), which
	appends the dev webserver port on this deployment -- the same trap that
	poisoned the referee links. We keep its key and rebuild the address.
	"""
	user = frappe.get_doc("User", user_name)
	raw = user._reset_password(send_email=False)
	parts = urlsplit(raw)
	tail = parts.path + (f"?{parts.query}" if parts.query else "")
	return public_url(tail)


def enroll_in_exam(user_name):
	"""Put the applicant into the exam course, if there is one. Idempotent."""
	course = exam_course()
	if not course:
		return None

	if frappe.db.exists("LMS Enrollment", {"member": user_name, "course": course}):
		return course

	try:
		frappe.get_doc(
			{
				"doctype": "LMS Enrollment",
				"member": user_name,
				"course": course,
				"member_type": "Student",
				"role": "Member",
			}
		).insert(ignore_permissions=True)
	except Exception:
		# A misconfigured LMS must not cost the applicant their account.
		frappe.log_error(title=f"Entrance exam enrollment failed for {user_name}")
		return None

	return course


# ---------------------------------------------------------------------------
# the invitation
# ---------------------------------------------------------------------------


FALLBACK_INVITE = (
	"Your SIBBCS account and entrance exam",
	"<p>Dear {{ applicant_name }},</p>"
	"<p>An account has been created for you at South India Baptist Bible College "
	"&amp; Seminary (Online). Your username is <b>{{ login_email }}</b>.</p>"
	"<p>First, set your password:<br>"
	'<a href="{{ password_link }}">{{ password_link }}</a></p>'
	"{% if exam_link %}"
	"<p>Then sit the entrance exam here:<br>"
	'<a href="{{ exam_link }}">{{ exam_link }}</a></p>'
	"{% endif %}"
	"<p>Admissions Office</p>",
)


def send_invite(doc, user_name, link):
	"""Email the applicant their login and the exam link."""
	from sibbcs.admissions.notifications import render_template

	context = {
		"applicant_name": doc.full_name,
		"login_email": user_name,
		"program": doc.program,
		"password_link": set_password_link(user_name),
		"exam_link": link,
		"application_id": doc.name,
	}
	subject, message = render_template("lms_account_invite", context, *FALLBACK_INVITE)

	frappe.sendmail(
		recipients=[doc.email],
		subject=subject,
		message=message,
		header=[_("Your Account"), "blue"],
		now=False,
	)
	return doc.email


# ---------------------------------------------------------------------------
# the whole step
# ---------------------------------------------------------------------------


def create_and_send(application, send=True):
	"""Do step 7 for one application. Idempotent; safe to press twice.

	Returns a report rather than throwing on a half-configured system: the
	account is worth having even when nobody has yet said where the exam is.
	"""
	from sibbcs.admissions.notifications import outgoing_configured

	doc = frappe.get_doc("Admission Application", application)

	report = {
		"application": doc.name,
		"user": None,
		"user_created": False,
		"exam_link": None,
		"enrolled_in": None,
		"emailed": None,
		"warnings": [],
	}

	user_name, created = ensure_user(doc)
	report["user"] = user_name
	report["user_created"] = created

	if doc.applicant_user != user_name:
		doc.db_set("applicant_user", user_name, update_modified=False)
	if not doc.lms_account_created_on:
		doc.db_set("lms_account_created_on", now_datetime(), update_modified=False)

	report["enrolled_in"] = enroll_in_exam(user_name)

	link = exam_link()
	report["exam_link"] = link
	if link:
		doc.db_set("entrance_exam_link", link, update_modified=False)
	else:
		report["warnings"].append(
			"No entrance exam link is configured, so the invitation was not sent. "
			"Set entrance_exam_lms_course or entrance_exam_url."
		)

	if send and link:
		if not outgoing_configured():
			report["warnings"].append(
				"No outgoing email account is configured, so nothing was sent."
			)
		else:
			try:
				report["emailed"] = send_invite(doc, user_name, link)
				doc.db_set("exam_link_sent_on", now_datetime(), update_modified=False)
			except Exception:
				frappe.log_error(title=f"LMS invite failed for {doc.name}")
				report["warnings"].append("The invitation email could not be sent.")

	_mark_step(doc.name, report)
	return report


def _mark_step(application, report):
	"""Move step 7 to Created, or Link Sent once the email is away.

	Written straight to the child row: this is called from an action that has
	already written to the parent, and checklist.set_status() would save the
	parent again for a field it has just stamped.
	"""
	status = "Link Sent" if report.get("emailed") else "Created"

	name = frappe.db.get_value(
		"Admission Checklist Item",
		{"parent": application, "parenttype": "Admission Application", "step_no": STEP},
		"name",
	)
	if not name:
		return

	current = frappe.db.get_value("Admission Checklist Item", name, "status")
	if current == "Link Sent":
		return  # never walk the step backwards

	frappe.db.set_value(
		"Admission Checklist Item",
		name,
		{"status": status, "updated_by": frappe.session.user, "updated_on": now_datetime()},
		update_modified=False,
	)


# ---------------------------------------------------------------------------
# Desk
# ---------------------------------------------------------------------------


@frappe.whitelist()
def create_account(application, send=1):
	doc = frappe.get_doc("Admission Application", application)
	doc.check_permission("write")

	report = create_and_send(application, send=int(send or 0) == 1)

	lines = []
	if report["user_created"]:
		lines.append(_("Account created: <b>{0}</b>").format(report["user"]))
	else:
		lines.append(_("Existing account used: <b>{0}</b>").format(report["user"]))
	if report["enrolled_in"]:
		lines.append(_("Enrolled in the entrance exam course."))
	if report["emailed"]:
		lines.append(_("Login and exam link sent to <b>{0}</b>.").format(report["emailed"]))
	for warning in report["warnings"]:
		lines.append(f"<span style='color:var(--orange-600)'>{warning}</span>")

	frappe.msgprint(
		"<br>".join(lines),
		title=_("LMS Account"),
		indicator="orange" if report["warnings"] else "green",
	)
	return report


@frappe.whitelist()
def resend_exam_link(application):
	"""Send the login and exam link again -- a fresh password link each time."""
	doc = frappe.get_doc("Admission Application", application)
	doc.check_permission("write")

	if not doc.applicant_user:
		frappe.throw(
			_("No account has been created for this applicant yet."),
			title=_("Nothing to Resend"),
		)
	return create_account(application, send=1)
