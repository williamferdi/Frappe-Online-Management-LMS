# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""The entrance exam, from where it is sat to where it is recorded.

The candidate sits it in the LMS: three open-ended essays in the Entrance Exam
course, marked there by whoever reads them. The admissions side has its own
`Qualifying Exam Result`, because the college's pass mark is its own rule and
the workflow gates on `Admission Application.qualifying_exam_score`.

Nothing joined the two. An essay marked 20/25 in the LMS stayed in the LMS, and
the application went on saying the score was 0 -- which is what the college
saw. This module is that join, in one direction only: **the LMS is where the
marking happens, and a Qualifying Exam Result is what we make of it.**

Two things it deliberately does not do:

* It does not mark essays. The rubric is in the course and the marks belong to
  whoever read the answers.
* It does not decide the outcome. `pass_mark` on the result does that -- the
  college's 70%, not the quiz's own passing percentage, which the LMS sets for
  its own purposes and which is not the college's rule.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from sibbcs.admissions import checklist
from sibbcs.admissions.doctype.qualifying_exam_result.qualifying_exam_result import (
	ESSAY_MAX,
	ESSAYS,
	latest_for,
)

# The quiz the college sets. Found by title rather than hard-coded name so a
# rebuilt quiz is still recognised -- `phase2m_entrance_exam.py` owns the title.
QUIZ_TITLE = "Entrance Exam — Essays"

# The three essays, in the order the quiz asks them. `ESSAYS` is the same order
# on the result doctype, so the mapping is positional and stated once.
ESSAY_ORDER = ESSAYS


def quiz_names():
	return frappe.get_all("LMS Quiz", filters={"title": QUIZ_TITLE}, pluck="name")


def _application(name, permission="read"):
	doc = frappe.get_doc("Admission Application", name)
	doc.check_permission(permission)
	return doc


def submission_for(application):
	"""The candidate's own attempt at the entrance exam, or None.

	Keyed on `applicant_user`, which `lms_account.create_account` sets when it
	makes their login. A submission by anyone else is not this candidate's exam
	whatever else it may be.
	"""
	user = frappe.db.get_value("Admission Application", application, "applicant_user")
	if not user:
		return None

	quizzes = quiz_names()
	if not quizzes:
		return None

	name = frappe.db.get_value(
		"LMS Quiz Submission",
		{"quiz": ("in", quizzes), "member": user},
		"name",
		order_by="creation desc",
	)
	return frappe.get_doc("LMS Quiz Submission", name) if name else None


def _essays_from(submission):
	"""The three marks, in the order the result doctype keeps them.

	Positional, because an open-ended question carries no key we could match on
	and the quiz asks them in a fixed order. A submission that does not have
	exactly three answers is not the paper we know how to record, so it is
	reported rather than guessed at.
	"""
	rows = submission.result or []
	if len(rows) != len(ESSAY_ORDER):
		return None

	marks = {}
	for field, row in zip(ESSAY_ORDER, rows):
		out_of = int(row.marks_out_of or ESSAY_MAX)
		mark = flt(row.marks)
		# Marked out of something other than 25 is still a fraction of the
		# essay; scaling it is more honest than storing 8 as if it were 8/25.
		marks[field] = flt(mark / out_of * ESSAY_MAX, 2) if out_of and out_of != ESSAY_MAX else mark
	return marks


def _marked(submission):
	"""Has anybody actually read these yet?

	The LMS creates a submission the moment the candidate presses submit, with
	every open-ended answer at zero. Recording that as a result would tell the
	college the candidate scored nothing, which is a different statement from
	"nobody has marked this yet".
	"""
	rows = submission.result or []
	return any(flt(row.marks) > 0 for row in rows)


def state(application):
	"""Where this candidate's exam stands, from both sides."""
	submission = submission_for(application)
	result = latest_for(application)

	answers = []
	if submission:
		answers = [
			{
				"question": row.question,
				"answer": row.answer,
				"marks": flt(row.marks),
				"marks_out_of": int(row.marks_out_of or ESSAY_MAX),
			}
			for row in (submission.result or [])
		]

	return {
		"application": application,
		"quiz_exists": bool(quiz_names()),
		"submission": {
			"name": submission.name,
			"member": submission.member,
			"submitted_on": str(submission.creation),
			"score": flt(submission.score),
			"score_out_of": flt(submission.score_out_of),
			"marked": _marked(submission),
			"answers": answers,
		}
		if submission
		else None,
		"result": {
			"name": result.name,
			"conducted_on": str(result.conducted_on) if result.conducted_on else None,
			"pass_mark": flt(result.pass_mark),
			"total": flt(result.total),
			"result": result.result,
			**{field: flt(result.get(field)) for field in ESSAY_ORDER},
		}
		if result
		else None,
		"essay_max": ESSAY_MAX,
		"essays": list(ESSAY_ORDER),
	}


def _save_result(application, marks, conducted_on=None):
	"""Write the marks onto this application's exam result, making one if needed.

	Saved through the document: `QualifyingExamResult.validate` computes the
	total against the pass mark and `on_update` pushes the score onto the
	application. Writing the fields around it would record marks that nothing
	acted on.
	"""
	result = latest_for(application)
	if not result:
		result = frappe.get_doc(
			{
				"doctype": "Qualifying Exam Result",
				"application": application,
				"applicant_name": frappe.db.get_value(
					"Admission Application", application, "full_name"
				),
			}
		)

	for field, value in marks.items():
		result.set(field, value)
	if conducted_on:
		result.conducted_on = getdate(conducted_on)
	elif not result.conducted_on:
		result.conducted_on = frappe.utils.today()

	result.flags.ignore_permissions = True
	result.save(ignore_permissions=True)
	return result


@frappe.whitelist()
def exam(application):
	"""What the console draws: the attempt, the marks and the verdict."""
	_application(application)
	return state(application)


@frappe.whitelist(methods=["POST"])
def pull(application):
	"""Bring the marks the LMS holds across onto the admissions record."""
	_application(application, "write")

	submission = submission_for(application)
	if not submission:
		frappe.throw(
			_("This candidate has not sat the entrance exam yet."),
			title=_("Nothing to Pull"),
		)

	if not _marked(submission):
		frappe.throw(
			_(
				"The candidate has sat the exam but nobody has marked it yet. "
				"Mark the three essays in the Entrance Exam course, or enter the "
				"marks here."
			),
			title=_("Not Marked Yet"),
		)

	marks = _essays_from(submission)
	if marks is None:
		frappe.throw(
			_(
				"That submission has {0} answers, not {1}. Enter the marks by hand."
			).format(len(submission.result or []), len(ESSAY_ORDER)),
			title=_("Unexpected Paper"),
		)

	_save_result(application, marks, conducted_on=submission.creation)
	return state(application)


@frappe.whitelist(methods=["POST"])
def record(application, **marks):
	"""Enter or correct the three marks by hand.

	For the paper sat away from the LMS, and for a re-mark. Each essay is out
	of `ESSAY_MAX`; the document refuses anything outside that.
	"""
	_application(application, "write")

	values = {}
	for field in ESSAY_ORDER:
		if field in marks and marks[field] not in (None, ""):
			values[field] = flt(marks[field])

	if not values:
		frappe.throw(_("Enter at least one mark."))

	_save_result(application, values, conducted_on=marks.get("conducted_on"))
	return state(application)


def on_quiz_submission(doc, method=None):
	"""An entrance exam was submitted or marked in the LMS.

	Hooked rather than polled: a mark entered in the course reaches the
	admissions record on the same save, which is the whole complaint this
	answers. Everything is best-effort -- an admissions bookkeeping problem
	must never stop somebody submitting or marking a quiz.
	"""
	try:
		if doc.quiz not in quiz_names():
			return

		if not _marked(doc):
			return  # sat, not yet marked

		application = frappe.db.get_value(
			"Admission Application", {"applicant_user": doc.member}, "name"
		)
		if not application:
			return

		marks = _essays_from(doc)
		if marks is None:
			return

		_save_result(application, marks, conducted_on=doc.creation)
	except Exception:
		frappe.log_error(title="Entrance exam sync failed")


def backfill():
	"""Pull every marked entrance exam that has never been recorded.

	For the exams sat before the two sides were joined. Returns what it did so
	the patch can print it.
	"""
	done, skipped = [], []
	for name in frappe.get_all(
		"LMS Quiz Submission", filters={"quiz": ("in", quiz_names() or [""])}, pluck="name"
	):
		submission = frappe.get_doc("LMS Quiz Submission", name)
		application = frappe.db.get_value(
			"Admission Application", {"applicant_user": submission.member}, "name"
		)
		if not application:
			skipped.append((submission.member, "no application"))
			continue
		if not _marked(submission):
			skipped.append((application, "not marked"))
			continue
		marks = _essays_from(submission)
		if marks is None:
			skipped.append((application, "unexpected paper"))
			continue

		_save_result(application, marks, conducted_on=submission.creation)
		done.append(application)

	return {"recorded": done, "skipped": skipped}


def sync_step(application, result):
	"""Move the checklist to say what the result says.

	Recorded as a fact, not as a decision: `checklist.record_fact` writes the
	row directly rather than going through `set_status`, whose gates guard an
	officer's *choice* to advance a step. The candidate sat the exam and passed
	it; that is true whether or not the LMS account step was ever ticked.
	"""
	if not result or not result.result:
		return
	checklist.record_fact(
		application,
		checklist.NO["entrance_exam"],
		"Passed" if result.result == "Pass" else "Failed",
	)
