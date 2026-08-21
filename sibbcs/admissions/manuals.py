"""Manual Reading Review: sending the manuals, and recording that they were read.

A candidate who has been admitted is sent the manuals they must read. They open
a link, read the manual, type their name and confirm. The step reaches
**Acknowledged** only when every manual that applies to them has been confirmed
-- not the first one.

No login, by design. The candidate does have an account by this point (LMS
Account Creation made one), but requiring a sign-in to acknowledge a document is friction that
buys nothing: the token already identifies exactly one manual for exactly one
applicant, and is spent on use.

What is recorded is deliberately thin but legally useful: who typed their
name, when, and from which address. `Manual Acknowledgement.acknowledged_name`
is what the candidate typed, not what the office believes their name to be --
if those differ, that difference is evidence, and overwriting it would destroy
the only thing the record is for.

Which manuals apply is a property of the manual, not of this code: a Reading
Manual with no programs listed is universal, one with programs listed applies
to those programs only.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime

from sibbcs.admissions.checklist import NO
from sibbcs.admissions.doctype.admission_application.admission_application import token_url
from sibbcs.finance.gateway import public_url

STEP = NO["manual_reading"]
FORM_KEY = "manual-reading"


# ---------------------------------------------------------------------------
# which manuals apply
# ---------------------------------------------------------------------------


def applicable_manuals(program=None):
	"""Active manuals for a program. No programs listed means universal."""
	names = frappe.get_all(
		"Reading Manual",
		filters={"is_active": 1},
		pluck="name",
		ignore_permissions=True,
	)

	applicable = []
	for name in names:
		scoped = frappe.get_all(
			"Reading Manual Program",
			filters={"parent": name, "parenttype": "Reading Manual"},
			pluck="program",
			ignore_permissions=True,
		)
		if not scoped or (program and program in scoped):
			applicable.append(name)

	return sorted(applicable)


# ---------------------------------------------------------------------------
# course-backed manuals
# ---------------------------------------------------------------------------


def manual_course(manual):
	"""The LMS course a manual is delivered through, or None.

	A manual can be a document to read or a course to complete. The course
	form is what makes "acknowledged" mean something: a PDF acknowledgement is
	one click, whereas a course records a lesson at a time.
	"""
	if not manual:
		return None
	row = frappe.db.get_value(
		"Reading Manual", manual, ["delivery", "lms_course"], as_dict=True
	)
	if not row or row.delivery != "LMS Course" or not row.lms_course:
		return None
	if not frappe.db.exists("LMS Course", row.lms_course):
		frappe.log_error(
			title="Reading Manual points at a course that does not exist",
			message=f"{manual} -> {row.lms_course}",
		)
		return None
	return row.lms_course


def course_progress(application, course):
	"""How far this applicant has got. Counted from lessons, not a percentage.

	`LMS Enrollment.progress` is maintained by the LMS and would be simpler to
	read, but it is a rounded figure kept up to date by the LMS's own hooks --
	so a course whose last lesson is skipped can still round to 100. Counting
	completed lessons against the lessons that exist cannot.
	"""
	user = frappe.db.get_value("Admission Application", application, "applicant_user")
	total = frappe.db.count("Course Lesson", {"course": course})

	if not user or not total:
		return {"user": user, "total": total, "done": 0, "complete": False}

	done = frappe.db.count(
		"LMS Course Progress",
		{"member": user, "course": course, "status": "Complete"},
	)
	return {
		"user": user,
		"total": total,
		"done": min(done, total),
		"complete": done >= total,
	}


def enroll_in_course(doc, course):
	"""Put the applicant into the course. Idempotent.

	They already have a login from LMS Account Creation; ensure_user adopts it
	rather than making a second, and covers the case where that step was
	skipped.
	"""
	from sibbcs.admissions import lms_account

	user = doc.applicant_user
	if not user:
		user, _created = lms_account.ensure_user(doc)
		doc.db_set("applicant_user", user, update_modified=False)

	if not frappe.db.exists("LMS Enrollment", {"member": user, "course": course}):
		try:
			frappe.get_doc(
				{
					"doctype": "LMS Enrollment",
					"member": user,
					"course": course,
					"member_type": "Student",
					"role": "Member",
				}
			).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(title=f"Preliminary course enrollment failed for {doc.name}")
			return None

	return user


def attach_manuals(doc):
	"""Give the application a row per applicable manual. Idempotent.

	Sets tokens here rather than in issue_tokens() because the rows do not
	exist until the manuals are sent.
	"""
	from sibbcs.admissions.tokens import generate_token

	held = {r.manual for r in doc.get("manual_acknowledgements") or []}
	added = []

	for manual in applicable_manuals(doc.program):
		if manual in held:
			continue
		doc.append("manual_acknowledgements", {"manual": manual, "token": generate_token()})
		added.append(manual)

	return added


# ---------------------------------------------------------------------------
# sending
# ---------------------------------------------------------------------------


FALLBACK_MANUAL = (
	"Please read: {{ manual_title }}",
	"<p>Dear {{ applicant_name }},</p>"
	"<p>Congratulations on your admission to South India Baptist Bible College "
	"&amp; Seminary. Before your enrolment can be completed, please read "
	"<b>{{ manual_title }}</b> and confirm that you have done so.</p>"
	"<p>Open it here:<br>"
	'<a href="{{ link }}">{{ link }}</a></p>'
	"<p>Admissions Office</p>",
)


FALLBACK_COURSE = (
	"Complete your orientation course -- {{ manual_title }}",
	"<p>Dear {{ applicant_name }},</p>"
	"<p>Congratulations on your admission to South India Baptist Bible College "
	"&amp; Seminary. Before your enrolment can be completed, please work through "
	"the orientation course. It carries no credit and every lesson must be "
	"finished.</p>"
	"<p>Sign in as <b>{{ login_email }}</b> and open the course:<br>"
	'<a href="{{ course_url }}">{{ course_url }}</a></p>'
	"<p>When you have finished every lesson, sign the acknowledgement here:<br>"
	'<a href="{{ link }}">{{ link }}</a></p>'
	"<p>Admissions Office</p>",
)


def send_manual_row(doc, row):
	"""Email one manual link. Returns the address, or None."""
	from sibbcs.admissions.notifications import render_template

	if not doc.email:
		return None

	title, version = frappe.db.get_value(
		"Reading Manual", row.manual, ["manual_title", "version"]
	)

	# A course-backed manual has to be enrolled before the link is any use.
	course = manual_course(row.manual)
	course_url = None
	if course:
		enroll_in_course(doc, course)
		course_url = public_url(f"/lms/courses/{course}")

	context = {
		"applicant_name": doc.full_name,
		"manual_title": title,
		"manual_version": version,
		"program": doc.program,
		"link": token_url(FORM_KEY, row.token),
		"course_url": course_url,
		"login_email": doc.applicant_user or doc.email,
		"application_id": doc.name,
	}
	template = "preliminary_course" if course else "manual_reading"
	fallback = FALLBACK_COURSE if course else FALLBACK_MANUAL
	subject, message = render_template(template, context, *fallback)

	frappe.sendmail(
		recipients=[doc.email],
		subject=subject,
		message=message,
		header=[_("Reading Manual"), "blue"],
		now=False,
	)
	frappe.db.set_value(
		"Manual Acknowledgement", row.name, "sent_on", now_datetime(), update_modified=False
	)
	return doc.email


def send_manuals(application, force=False):
	"""Attach any missing manual rows and email the outstanding ones.

	`force` re-sends rows already stamped `sent_on`. A manual already
	acknowledged is never re-sent: its token is spent.
	"""
	from sibbcs.admissions.checklist import blocked_reason
	from sibbcs.admissions.notifications import outgoing_configured

	doc = frappe.get_doc("Admission Application", application)

	reason = blocked_reason(doc, STEP)
	if reason:
		frappe.throw(reason, title=_("Step Blocked"))

	report = {
		"application": doc.name,
		"attached": [],
		"sent": [],
		"warnings": [],
	}

	report["attached"] = attach_manuals(doc)
	if report["attached"]:
		doc.flags.ignore_permissions = True
		doc.save(ignore_permissions=True)
		doc.reload()

	if not doc.get("manual_acknowledgements"):
		report["warnings"].append(
			"No active reading manual applies to this program, so nothing was sent."
		)
		return report

	if not outgoing_configured():
		report["warnings"].append(
			"No outgoing email account is configured, so nothing was sent."
		)
		return report

	for row in doc.manual_acknowledgements:
		if row.acknowledged_on:
			continue
		if row.sent_on and not force:
			continue
		try:
			if send_manual_row(doc, row):
				report["sent"].append(row.manual)
		except Exception:
			frappe.log_error(title=f"Manual link failed for {doc.name}")
			report["warnings"].append(f"{row.manual} could not be emailed.")

	if report["sent"]:
		_set_step(doc.name)

	return report


# ---------------------------------------------------------------------------
# acknowledging
# ---------------------------------------------------------------------------


def acknowledge(token, reader_name, confirmed, signature=None):
	"""Record that one manual was read. Called from the guest endpoint."""
	from sibbcs.admissions.scholarship import _decode_signature, _store_signature
	from sibbcs.admissions.tokens import mark_submitted, resolve

	if str(confirmed) not in ("1", "true", "on", "yes", "True"):
		frappe.throw(
			_("Please tick the box to confirm you have read the manual."),
			title=_("Not Confirmed"),
		)

	reader_name = (reader_name or "").strip()
	if len(reader_name) < 3:
		frappe.throw(_("Please type your full name."), title=_("Name Needed"))

	resolved = resolve(FORM_KEY, token)
	row = frappe.db.get_value(
		"Manual Acknowledgement", resolved["row_name"], "manual"
	)

	# A course-backed manual is not "read" until the course is finished. The
	# page hides the button, but the button is not the rule.
	course = manual_course(row)
	if course:
		progress = course_progress(resolved["parent"], course)
		if not progress["complete"]:
			frappe.throw(
				_("Please finish the course first — {0} of {1} lessons done.").format(
					progress["done"], progress["total"]
				),
				title=_("Course Not Complete"),
			)

	# Validated before anything is written, so a bad signature cannot leave a
	# half-recorded acknowledgement. Same rule as the scholarship form.
	raw_signature = _decode_signature(signature) if signature else None

	result = mark_submitted(
		FORM_KEY,
		token,
		{
			# What they typed, not what we think their name is.
			"acknowledged_name": reader_name[:140],
			"ip_address": frappe.local.request_ip or "",
		},
	)

	if raw_signature:
		file_url = _store_signature(
			raw_signature, resolved["parent"], reader_name, doctype="Admission Application"
		)
		if file_url:
			frappe.db.set_value(
				"Manual Acknowledgement",
				resolved["row_name"],
				"signature",
				file_url,
				update_modified=False,
			)

	_set_step(resolved["parent"])
	return result


def _set_step(application):
	"""Sent while any manual is outstanding; Acknowledged once all are in."""
	rows = frappe.get_all(
		"Manual Acknowledgement",
		filters={"parent": application, "parenttype": "Admission Application"},
		fields=["name", "acknowledged_on"],
		ignore_permissions=True,
	)
	if not rows:
		return None

	status = "Acknowledged" if all(r.acknowledged_on for r in rows) else "Sent"

	name = frappe.db.get_value(
		"Admission Checklist Item",
		{"parent": application, "parenttype": "Admission Application", "step_no": STEP},
		"name",
	)
	if not name:
		return status

	current = frappe.db.get_value("Admission Checklist Item", name, "status")
	if current == "Acknowledged":
		return current  # never walk the step backwards

	frappe.db.set_value(
		"Admission Checklist Item",
		name,
		{"status": status, "updated_by": frappe.session.user, "updated_on": now_datetime()},
		update_modified=False,
	)
	return status


# ---------------------------------------------------------------------------
# Desk
# ---------------------------------------------------------------------------


@frappe.whitelist()
def send(application, force=0):
	doc = frappe.get_doc("Admission Application", application)
	doc.check_permission("write")

	report = send_manuals(application, force=int(force or 0) == 1)

	lines = []
	if report["sent"]:
		lines.append(_("Sent: {0}").format(", ".join(report["sent"])))
	elif not report["warnings"]:
		lines.append(_("Every manual has already been sent."))
	for warning in report["warnings"]:
		lines.append(f"<span style='color:var(--orange-600)'>{warning}</span>")

	frappe.msgprint(
		"<br>".join(lines),
		title=_("Reading Manuals"),
		indicator="orange" if report["warnings"] else "green",
	)
	return report


@frappe.whitelist()
def status(application):
	"""What the Desk button needs: one line per manual."""
	doc = frappe.get_doc("Admission Application", application)
	doc.check_permission("read")

	rows = []
	for row in doc.get("manual_acknowledgements") or []:
		rows.append(
			{
				"manual": row.manual,
				"sent_on": str(row.sent_on) if row.sent_on else None,
				"acknowledged_on": str(row.acknowledged_on) if row.acknowledged_on else None,
				"acknowledged_name": row.acknowledged_name,
			}
		)

	return {
		"application": doc.name,
		"rows": rows,
		"outstanding": [r["manual"] for r in rows if not r["acknowledged_on"]],
		"applicable": applicable_manuals(doc.program),
	}
