"""Bring across the exams already sat, and the verdicts already reached.

Two gaps closed at once, both of which left the college looking at a checklist
that disagreed with what had actually happened:

* An entrance exam marked in the LMS never reached the admissions record, so
  the application went on saying the score was zero.
* A `Qualifying Exam Result` or an `Interview Record` moved nothing on the
  checklist, because only the officer's own button did.

Both are now wired at the source -- `on_quiz_submission`, and each DocType's
`on_update`. This is for what happened before that.

Reports rather than guesses: a submission nobody has marked is left alone, and
a step an officer has already decided is not walked back.
"""

import frappe

from sibbcs.admissions import entrance_exam
from sibbcs.admissions.checklist import NO, record_fact
from sibbcs.admissions.doctype.interview_record.interview_record import OUTCOMES


def execute():
	pulled = entrance_exam.backfill()
	for application in pulled["recorded"]:
		print(f"Entrance exam recorded from the LMS: {application}")
	for who, why in pulled["skipped"]:
		print(f"Entrance exam left alone: {who} ({why})")

	# Results recorded by hand before the step was wired.
	moved = 0
	for row in frappe.get_all(
		"Qualifying Exam Result",
		filters={"application": ("is", "set")},
		fields=["application", "result"],
	):
		if not row.result:
			continue
		if record_fact(
			row.application,
			NO["entrance_exam"],
			"Passed" if row.result == "Pass" else "Failed",
		):
			moved += 1

	interviews = 0
	for row in frappe.get_all(
		"Interview Record",
		filters={"application": ("is", "set")},
		fields=["application", "outcome", "scheduled_on"],
	):
		status = OUTCOMES.get(row.outcome) if row.outcome else None
		if not status and row.scheduled_on:
			status = "Scheduled"
		if status and record_fact(row.application, NO["interview"], status):
			interviews += 1

	print(
		f"Checklist caught up: {moved} exam steps, {interviews} interview steps, "
		f"{len(pulled['recorded'])} exams pulled from the LMS."
	)
