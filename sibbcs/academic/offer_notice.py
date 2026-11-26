# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""Telling students that a course they can take is open for registration.

Registration has always been a pull: the student signs in, opens Register, and
finds out. Which means they find out if they happen to look, inside a window
that is a fortnight wide. The college asked to be able to push it instead --
"email notified when courses are offered with associated student levels, so
they can register" -- and the level is the whole point of the request. A
Level 1 student should hear about the Level 1 and Level 2 courses and about
nothing else.

**Who is asked is `eligibility.evaluate`, not a level comparison.** The same
engine the Register page runs, so the letter can never point somebody at a
course the page will then refuse them: a prerequisite they have not passed, a
course they have already taken, a full offering, a closed term. The level rule
is one gate of several, and re-stating it here is how the two would drift.

That costs a handful of queries per student per offering. It is a daily job
over a college of two hundred, and the alternative -- a cheap level filter and
a letter that is sometimes wrong -- is the one that generates email to the
Registrar.

**`students_notified_on` is the whole of the idempotency.** The hook fires on
every save of a published offering and the sweep runs every day; the stamp is
what makes the second one quiet. It is stamped even when nobody was eligible,
because "nobody yet" is an answer, and a sweep that retried it would ask the
same question of the same students every morning for the rest of the term.
Clearing the field is the supported way to send it again.

**One letter per offering, not a digest.** A term published course by course
reads as a course at a time, and each letter is about one thing the student
can act on. Publishing a whole catalogue in one afternoon would send a handful
at once; if the college finds that noisy, the grouping belongs here, in
`announce_open_offerings`, which already has every offering in hand.
"""

import frappe
from frappe import _
from frappe.utils import formatdate, getdate, now_datetime, today

from sibbcs.academic.eligibility import check_level, evaluate
from sibbcs.finance.gateway import public_url

TEMPLATE = "course_offered"

# A course is worth writing about once it is open to register for. `Running`
# is deliberately not here: a course that has started is not news a student
# can act on, and an offering that goes Published -> Running in one afternoon
# has already been announced under the stamp.
ANNOUNCEABLE = ("Published",)

# Terms whose registration a student could still act on.
OPEN_TERM_STATUS = ("Open", "Active")

FALLBACK = (
	"Open for registration: {{ course_code }} — {{ term }}",
	"<p>Dear {{ student_name }},</p>"
	"<p><b>{{ course_title }}</b> ({{ course_code }}) is running in "
	"{{ term }} and is open to you to register for. It is a Level "
	"{{ course_level }} course and carries {{ credits }} credits."
	"{% if closes %} Registration closes on {{ closes }}.{% endif %}</p>"
	"<p>Register here:<br>"
	'<a href="{{ register_url }}">{{ register_url }}</a></p>'
	"<p>A place is not held for you until you register.</p>"
	"<p>Office of the Registrar</p>",
)


def _term_is_open(term):
	"""Could a student still register in this term?

	Status first, because it is the college's own decision. A
	`registration_closes` already past means the window has shut even though
	the term itself is Open, and writing to somebody about a course they can
	no longer take is worse than not writing at all.
	"""
	row = frappe.db.get_value(
		"Academic Term", term, ["status", "registration_closes"], as_dict=True
	)
	if not row or row.status not in OPEN_TERM_STATUS:
		return False
	if row.registration_closes and getdate(row.registration_closes) < getdate(today()):
		return False
	return True


def _offering_context(offering):
	"""What the letter says about the course, read once for every recipient."""
	row = frappe.db.get_value(
		"Course Offering",
		offering,
		["name", "course", "course_title", "term", "format", "credits"],
		as_dict=True,
	)
	if not row:
		return None

	course = (
		frappe.db.get_value("Course", row.course, ["level", "course_title"], as_dict=True) or {}
	)
	closes = frappe.db.get_value("Academic Term", row.term, "registration_closes")

	return {
		"offering": row.name,
		"course_code": row.course,
		"course_title": row.course_title or course.get("course_title") or row.course,
		"course_level": course.get("level") or "",
		"term": row.term,
		"format": row.format or "",
		"credits": row.credits or 0,
		"closes": formatdate(closes) if closes else "",
		"register_url": public_url("/portal/courses/register"),
	}


def recipients(offering):
	"""Active enrollments that could register for this offering today.

	Returns a list of `{enrollment, student, name, email, level}`. A student
	with no address is left out here rather than failing later: there is
	nothing to send to, and it is the registrar's record to fix, not this
	job's.
	"""
	course = frappe.db.get_value("Course Offering", offering, "course")
	course_level = frappe.db.get_value("Course", course, "level") if course else None

	# Only the programmes this course counts toward. A course with none listed
	# is universal -- `Course.counts_toward` reads an empty list the same way,
	# so a partly-seeded catalogue does not silently write to nobody.
	programs = frappe.get_all(
		"Course Program Link",
		filters={"parent": course, "parenttype": "Course"},
		pluck="program",
	)
	filters = {"status": "Active"}
	if programs:
		filters["program"] = ("in", programs)

	rows = frappe.get_all(
		"Program Enrollment",
		filters=filters,
		fields=["name", "student", "current_level"],
	)
	# The level rule first, because it is pure and the college's question is
	# about levels: it throws out most of the roll without touching the
	# database at all. `evaluate` checks it again, which is the point -- this
	# is a filter, not the decision.
	rows = [row for row in rows if check_level(row.current_level, course_level)]
	if not rows:
		return []

	# Then the students, in one query rather than one per enrollment. The
	# expensive part is `evaluate` below, at six queries each, so everything
	# that can be thrown out before it is worth throwing out first.
	people = {
		person.name: person
		for person in frappe.get_all(
			"Student",
			filters={"name": ("in", [row.student for row in rows]), "status": "Active"},
			fields=["name", "full_name", "email"],
		)
		if person.email
	}

	found = []
	for row in rows:
		person = people.get(row.student)
		if not person:
			continue

		decision, _warnings = evaluate(row.name, offering)
		if not decision:
			continue

		found.append(
			{
				"enrollment": row.name,
				"student": row.student,
				"name": person.full_name or row.student,
				"email": person.email,
				"level": row.current_level or "",
			}
		)

	return found


def announce(offering, force=False):
	"""Email every eligible student that this course is open. Idempotent.

	Returns a report: who it went to, or why nobody did. Never raises -- it
	runs from a hook and from a nightly sweep, and neither has anybody to tell.
	"""
	from sibbcs.admissions.notifications import render_template

	report = {"offering": offering, "sent": [], "skipped": None}

	row = frappe.db.get_value(
		"Course Offering", offering, ["status", "term", "students_notified_on"], as_dict=True
	)
	if not row:
		report["skipped"] = "no such offering"
		return report
	if row.status not in ANNOUNCEABLE:
		report["skipped"] = f"status is {row.status}"
		return report
	if row.students_notified_on and not force:
		report["skipped"] = "already announced"
		return report
	if not _term_is_open(row.term):
		# Deliberately not stamped: the term may open later, and the sweep
		# should find this offering again when it does.
		report["skipped"] = "registration is not open in this term"
		return report

	context = _offering_context(offering)
	if not context:
		report["skipped"] = "no such offering"
		return report

	for person in recipients(offering):
		payload = dict(context, student_name=person["name"], student_level=person["level"])
		try:
			subject, message = render_template(TEMPLATE, payload, *FALLBACK)
			frappe.sendmail(
				recipients=[person["email"]],
				subject=subject,
				message=message,
				header=[_("Registration Open"), "blue"],
				now=False,
			)
		except Exception:
			frappe.log_error(title="Course offered email failed")
			continue
		report["sent"].append(person["student"])

	# Stamped even when nobody was eligible. "Nobody, yet" is an answer, and a
	# sweep that retried it would ask the same question of the same students
	# every morning until the term closed.
	frappe.db.set_value(
		"Course Offering", offering, "students_notified_on", now_datetime(), update_modified=False
	)
	return report


def announce_open_offerings():
	"""Nightly: announce anything published that nobody has been told about.

	The hook below is the usual way this runs, and this is what catches what a
	hook cannot: an offering published while mail was down, one created by a
	script that bypassed the document API, and -- the common one -- a course
	published into a term whose registration had not opened yet.
	"""
	if not frappe.db.has_column("Course Offering", "students_notified_on"):
		return []

	pending = frappe.get_all(
		"Course Offering",
		filters={"status": ("in", ANNOUNCEABLE), "students_notified_on": ("is", "not set")},
		pluck="name",
	)
	return [announce(offering) for offering in pending]


def on_offering_change(doc, method=None):
	"""Queue the announcement when an offering is published.

	Queued rather than sent inline for the reason every other outbound hook
	here is: the Registrar pressing Save must not wait on a mail server, nor
	have a save refused because one is down.
	"""
	if doc.status not in ANNOUNCEABLE:
		return
	if doc.get("students_notified_on"):
		return
	if frappe.flags.sibbcs_import:
		return

	frappe.enqueue(
		"sibbcs.academic.offer_notice.announce",
		queue="long",
		enqueue_after_commit=True,
		offering=doc.name,
	)


@frappe.whitelist()
def announce_now(offering, force=False):
	"""Desk-callable: tell the eligible students about this course now.

	`force` writes again to everybody still eligible -- which is what the
	Registrar wants after correcting a course level, and is the only way past
	the stamp short of clearing the field by hand.
	"""
	frappe.only_for(("Registrar", "Academic Coordinator", "System Manager"))
	frappe.get_doc("Course Offering", offering).check_permission("write")
	if isinstance(force, str):
		force = force.lower() not in ("", "0", "false", "none")
	return announce(offering, force=force)
