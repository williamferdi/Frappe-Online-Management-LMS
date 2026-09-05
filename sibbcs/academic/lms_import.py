# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""Bring what the LMS already knows into the records this app keeps.

    bench --site online.sibbc.org execute sibbcs.academic.lms_import.survey
    bench --site online.sibbc.org execute sibbcs.academic.lms_import.run

Survey first, then apply -- the same shape as `lms_copy`, because a migration
you cannot read before running is a migration you find out about afterwards.
`run()` does nothing without `apply=True`.

Two things exist to bring across:

**Lesson progress.** `LMS Course Progress` says which lessons a student has
finished. Phase 3 keeps the same fact as `Module Item Progress`, against the
module item that points at the lesson -- so a student who reads a course in
this app is not asked to re-read what they already did in the LMS.

**Assignment submissions.** `LMS Assignment Submission` is Pass/Fail with a
comment. Pass becomes full marks, Fail becomes zero, and **Not Graded stays
unscored rather than becoming zero** -- the distinction the whole grade
pipeline is built around, and the one an importer is most likely to flatten.

**Nothing is deleted and nothing is written back to the LMS.** The app is
vendored; the next `bench update` replaces it. This reads.

**The entrance exam is deliberately not here.** It is three essay questions
marked by a person, sat by candidates who have no Course Registration to
attach anything to -- see `admissions/entrance_exam.py`. It is an admissions
artefact rather than coursework, and the Phase 4 quiz engine marks objective
questions. Moving it is a decision about admissions, not a data migration.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

# What a Pass is worth. Full marks, because Pass/Fail carries no more
# information than that and inventing a number would be inventing a mark.
PASS = "Pass"
FAIL = "Fail"


def _offering_for_lms_course(lms_course):
	"""Our Course Offering(s) for one LMS course.

	A Course links to one LMS Course and may run in several terms, so this is
	a list.
	"""
	course = frappe.db.get_value("Course", {"lms_course": lms_course}, "name")
	if not course:
		return []
	return frappe.get_all("Course Offering", filters={"course": course}, pluck="name")


def _registration_for(user, offerings):
	"""The registration this LMS member holds on one of these offerings."""
	if not user or not offerings:
		return None
	student = frappe.db.get_value("Student", {"user": user}, "name")
	if not student:
		return None
	return frappe.db.get_value(
		"Course Registration",
		{"student": student, "course_offering": ("in", offerings)},
		"name",
	)


def _module_item_for(lesson, offerings):
	"""The module item that points at this lesson, if somebody has added it."""
	if not lesson or not offerings:
		return None
	return frappe.db.get_value(
		"Course Module Item",
		{"item_type": "Lesson", "lesson": lesson, "course_offering": ("in", offerings)},
		"name",
	)


# ---------------------------------------------------------------------------
# reading first
# ---------------------------------------------------------------------------


def survey():
	"""What an import would move, and what it could not place.

	Prints rather than returns, because this is read by a person before they
	decide to run the thing.
	"""
	progress = _survey_progress()
	submissions = _survey_submissions()

	print("--- lesson progress ---")
	print(f"  {progress['total']} row(s) in the LMS")
	print(f"  {len(progress['ready'])} would be brought across")
	for reason, rows in progress["skipped"].items():
		print(f"  {len(rows)} skipped: {reason}")

	print("--- assignment submissions ---")
	print(f"  {submissions['total']} row(s) in the LMS")
	print(f"  {len(submissions['ready'])} would be brought across")
	for reason, rows in submissions["skipped"].items():
		print(f"  {len(rows)} skipped: {reason}")

	return {"progress": progress, "submissions": submissions}


def _survey_progress():
	rows = frappe.get_all(
		"LMS Course Progress",
		fields=["name", "member", "lesson", "course", "status"],
	)

	ready, skipped = [], {}

	def skip(reason, row):
		skipped.setdefault(reason, []).append(row.name)

	for row in rows:
		if row.status != "Complete":
			skip("not complete in the LMS", row)
			continue

		offerings = _offering_for_lms_course(row.course)
		if not offerings:
			skip("no Course Offering for that LMS course", row)
			continue

		registration = _registration_for(row.member, offerings)
		if not registration:
			skip("that member is not registered on the course here", row)
			continue

		item = _module_item_for(row.lesson, offerings)
		if not item:
			# The commonest case, and not an error: nobody has put the lesson
			# into a module yet, so there is no item to record progress
			# against. Build the modules, then run this again.
			skip("the lesson is not in any module yet", row)
			continue

		ready.append(
			{"progress": row.name, "module_item": item, "course_registration": registration}
		)

	return {"total": len(rows), "ready": ready, "skipped": skipped}


def _survey_submissions():
	if not frappe.db.exists("DocType", "LMS Assignment Submission"):
		return {"total": 0, "ready": [], "skipped": {}}

	rows = frappe.get_all(
		"LMS Assignment Submission",
		fields=["name", "member", "assignment", "status", "comments"],
	)

	ready, skipped = [], {}

	def skip(reason, row):
		skipped.setdefault(reason, []).append(row.name)

	for row in rows:
		lms_course = frappe.db.get_value("LMS Assignment", row.assignment, "course")
		offerings = _offering_for_lms_course(lms_course) if lms_course else []
		if not offerings:
			skip("no Course Offering for that LMS course", row)
			continue

		registration = _registration_for(row.member, offerings)
		if not registration:
			skip("that member is not registered on the course here", row)
			continue

		title = frappe.db.get_value("LMS Assignment", row.assignment, "title")
		assignment = frappe.db.get_value(
			"Course Assignment",
			{"course_offering": ("in", offerings), "title": title},
			"name",
		)
		if not assignment:
			skip("no Course Assignment of that name here", row)
			continue

		ready.append(
			{
				"submission": row.name,
				"assignment": assignment,
				"course_registration": registration,
				"status": row.status,
				"comments": row.comments,
			}
		)

	return {"total": len(rows), "ready": ready, "skipped": skipped}


# ---------------------------------------------------------------------------
# then writing
# ---------------------------------------------------------------------------


def run(apply=False):
	"""Bring across everything the survey says it can place.

	Idempotent: a row already recorded here is left alone, so running it twice
	moves nothing the second time and running it after building more modules
	picks up what could not be placed before.
	"""
	if not apply:
		print("Nothing written. Run with apply=True once the survey reads right.")
		return survey()

	moved = {"progress": 0, "submissions": 0}

	for entry in _survey_progress()["ready"]:
		if frappe.db.exists(
			"Module Item Progress",
			{
				"module_item": entry["module_item"],
				"course_registration": entry["course_registration"],
			},
		):
			continue
		from sibbcs.academic import modules

		modules.record_progress(
			entry["module_item"], entry["course_registration"], status="Complete"
		)
		moved["progress"] += 1

	for entry in _survey_submissions()["ready"]:
		if frappe.db.exists(
			"Assignment Submission",
			{
				"assignment": entry["assignment"],
				"course_registration": entry["course_registration"],
			},
		):
			continue
		_import_submission(entry)
		moved["submissions"] += 1

	frappe.db.commit()
	print(f"Brought across: {moved['progress']} progress row(s), "
		  f"{moved['submissions']} submission(s).")
	return moved


def _import_submission(entry):
	"""One LMS submission, with Pass/Fail turned into a mark.

	Not Graded stays unscored. `scored` is what the grade pipeline reads, and
	setting it on work nobody marked would put a zero on a transcript for an
	essay a teacher never saw.
	"""
	possible = flt(
		frappe.db.get_value("Course Assignment", entry["assignment"], "points_possible")
	)

	doc = frappe.new_doc("Assignment Submission")
	doc.assignment = entry["assignment"]
	doc.course_registration = entry["course_registration"]
	doc.attempt = 1
	doc.submitted_on = now_datetime()
	doc.body = entry.get("comments")

	if entry["status"] == PASS:
		doc.score = possible
		doc.scored = 1
		doc.status = "Graded"
	elif entry["status"] == FAIL:
		doc.score = 0
		doc.scored = 1
		doc.status = "Graded"
	else:
		# Not Graded. Left unscored on purpose.
		doc.scored = 0
		doc.status = "Submitted"

	doc.insert(ignore_permissions=True)
	return doc.name
