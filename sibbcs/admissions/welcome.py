# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""The letter that says somebody is now a student.

Until 20 Nov 2026 nothing was sent. A candidate was written to at nearly every
step -- documents, references, the exam, the interview, the scholarship form,
the orientation course -- and then, at the one step that changes what they
are, the system went quiet. They were given a Student number, a programme and
a level, and told none of it. Nobody had the address of the portal, and nobody
had a password for it.

**Password, not credentials.** The college asked for "credentials in email".
What goes out is the login address and a link the student uses to set a
password of their own; the password itself is never written down, here or
anywhere. A password in an inbox is a password in an inbox for ever, and it
would make the Admissions Office the keeper of every student's.

**A link, because there is no password yet.** The Frappe account is made at
step 6, silently and with no role, so that the candidate keeps one login for
life -- see `lms_account`. Nobody ever sets a password on it: the one the
candidate chose when they applied is Campus LMS Lite's, a different system. So
at this point every student is new to this site, whether their User record is
or not, and the link is what gets them in.

**It never raises.** This runs at the end of `conversion.convert`, inside the
transaction that creates the Student. A mail server that is down must not undo
an enrolment the Registrar has just accepted, so a failure is logged and
reported in the conversion report, and the office can send it again.
"""

import frappe
from frappe import _

from sibbcs.finance.gateway import public_url
from sibbcs.integrations import campus_lms

TEMPLATE = "student_welcome"

FALLBACK = (
	"Your student portal — {{ student_id }}",
	"<p>Dear {{ student_name }},</p>"
	"<p>Your enrolment at South India Baptist Bible College &amp; Seminary "
	"(Online) is complete. You are student <b>{{ student_id }}</b>, reading "
	"for the {{ program_name }} at Level {{ level }}.</p>"
	"<p>The student portal is where you register for courses, see what you "
	"owe and read your results:<br>"
	'<a href="{{ portal_url }}">{{ portal_url }}</a></p>'
	"<p>Sign in as <b>{{ login_email }}</b>. Set your password here:<br>"
	'<a href="{{ password_url }}">{{ password_url }}</a></p>'
	"<p>Office of the Registrar</p>",
)


def password_link(user):
	"""A fresh set-your-password link for this login.

	`User._reset_password` is overridden in `sibbcs.overrides.user`, so the
	address this returns is the public one and not `online.sibbc.org:8000`.
	`send_email=False`: the link travels in our letter, which says what it is
	for, rather than in Frappe's generic one alongside it.
	"""
	return frappe.get_doc("User", user)._reset_password(send_email=False)


def context_for(student, enrollment, user):
	"""Everything the letter needs, read once."""
	row = (
		frappe.db.get_value(
			"Program Enrollment", enrollment, ["program", "current_level"], as_dict=True
		)
		or {}
	)
	program = row.get("program")

	return {
		"student_id": student.name,
		"student_name": student.full_name,
		"program": program,
		"program_name": frappe.db.get_value("Program", program, "program_name") or program,
		"level": row.get("current_level") or "1",
		"login_email": user,
		"portal_url": public_url("/portal"),
		"password_url": password_link(user),
		# Omitted rather than guessed at when the learning site is not
		# configured: a paragraph pointing at nothing is worse than no
		# paragraph, and the template is written to leave it out.
		"lms_url": campus_lms.base_url() if campus_lms.configured() else None,
	}


def send(student, enrollment, user):
	"""Email a new student their portal address and a password link.

	Returns the address written to, or None. Never raises.
	"""
	from sibbcs.admissions.notifications import render_template

	if not user or not student.email:
		return None

	try:
		subject, message = render_template(TEMPLATE, context_for(student, enrollment, user), *FALLBACK)
		frappe.sendmail(
			recipients=[student.email],
			subject=subject,
			message=message,
			header=[_("Welcome"), "green"],
			now=False,
		)
	except Exception:
		frappe.log_error(title=f"Student welcome email failed for {student.name}")
		return None

	return student.email
