# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""Sitting a quiz: start, answer, submit -- and the staff side that builds one.

Every endpoint here that a student reaches resolves the registration from the
session and compares the server's clock. Nothing about timing, shuffling,
attempt count or correctness is decided by, or disclosed to, the browser.

`seconds_remaining` is sent so the page can show a countdown, but the countdown
is decoration: the server refuses a late answer whatever the page believes, and
a student who edits the number in devtools has edited a picture of a clock.
"""

import json

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, flt, get_datetime, now_datetime

from sibbcs.academic import overrides, quizzes
from sibbcs.academic import permissions as academic_permissions
from sibbcs.academic.portal import get_student
from sibbcs.api.academic_api import ACADEMIC_ROLES


def _require_teaching():
	if not set(frappe.get_roles()).intersection(ACADEMIC_ROLES):
		frappe.throw(
			_("You do not have access to academic records."), frappe.PermissionError
		)


def _my_registration(course_registration):
	student = get_student()
	if not student:
		frappe.throw(_("No student record for your account."), frappe.PermissionError)

	row = frappe.db.get_value(
		"Course Registration",
		course_registration,
		["name", "student", "course_offering"],
		as_dict=True,
	)
	if not row or row.student != student:
		frappe.throw(_("Registration not found."), frappe.PermissionError)
	return row


def _assignment_for(assignment, registration):
	row = frappe.db.get_value(
		"Course Assignment",
		assignment,
		["name", "title", "course_offering", "course_quiz", "submission_type",
		 "published", "points_possible", "due_date", "available_from", "available_until"],
		as_dict=True,
	)
	if not row or not cint(row.published):
		frappe.throw(_("Assignment not found."))
	if row.course_offering != registration.course_offering:
		frappe.throw(_("That is not on your course."), frappe.PermissionError)
	if row.submission_type != "Quiz" or not row.course_quiz:
		frappe.throw(_("That assignment is not a quiz."))
	return row


def _seconds_left(attempt):
	if not attempt.expires_at:
		return None
	remaining = (get_datetime(attempt.expires_at) - now_datetime()).total_seconds()
	return max(int(remaining), 0)


def _open_attempt(assignment, registration):
	rows = frappe.get_all(
		"Quiz Attempt",
		filters={
			"assignment": assignment,
			"course_registration": registration,
			"status": "In progress",
		},
		pluck="name",
		order_by="creation desc",
		limit=1,
	)
	return frappe.get_doc("Quiz Attempt", rows[0]) if rows else None


# ---------------------------------------------------------------------------
# sitting it
# ---------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def start(course_registration, assignment):
	"""Begin an attempt, or hand back the one already open.

	The paper is drawn and the clock is set here, once. Reconnecting returns
	the same attempt with the same questions and the same expiry -- a student
	whose browser crashed has not been given more time, and one who reloads
	has not been given a different paper.
	"""
	registration = _my_registration(course_registration)
	row = _assignment_for(assignment, registration)
	quiz = frappe.get_doc("Course Quiz", row.course_quiz)

	# A quiz window is an assignment window, so an extension moves it too.
	overrides.apply_to(row, registration.name)

	now = now_datetime()
	if row.available_from and now < get_datetime(row.available_from):
		frappe.throw(_("This has not opened yet."))
	if row.available_until and now > get_datetime(row.available_until):
		frappe.throw(_("This has closed."))

	open_already = _open_attempt(assignment, registration.name)
	if open_already:
		if open_already.expires_at and get_datetime(open_already.expires_at) < now:
			# The sweep has not caught it yet; close it now rather than let a
			# reload become extra time.
			_close(open_already, auto=True)
			frappe.db.commit()
		else:
			return _attempt_payload(open_already, quiz)

	taken = frappe.db.count(
		"Quiz Attempt",
		{"assignment": assignment, "course_registration": registration.name},
	)
	allowed = cint(quiz.allowed_attempts)
	if allowed and taken >= allowed:
		frappe.throw(
			_("You have used all {0} attempt(s) for this quiz.").format(allowed)
		)

	questions = quizzes.draw_questions(quiz)
	if not questions:
		frappe.throw(_("This quiz has no questions yet."))

	attempt = frappe.new_doc("Quiz Attempt")
	attempt.assignment = assignment
	attempt.quiz = quiz.name
	attempt.course_registration = registration.name
	attempt.attempt = taken + 1
	attempt.started_at = now
	# The clock, set by the server and never touched again.
	attempt.expires_at = (
		add_to_date(now, minutes=cint(quiz.time_limit_minutes))
		if cint(quiz.time_limit_minutes)
		else None
	)
	attempt.question_order = json.dumps(questions)
	attempt.status = "In progress"
	attempt.insert(ignore_permissions=True)
	frappe.db.commit()

	return _attempt_payload(attempt, quiz)


def _attempt_payload(attempt, quiz):
	"""The attempt as its own student may see it: no answers, no marks."""
	questions = json.loads(attempt.question_order or "[]")
	given = {row.question: row.answer for row in attempt.answers}

	return {
		"attempt": attempt.name,
		"status": attempt.status,
		"started_at": attempt.started_at,
		"expires_at": attempt.expires_at,
		"seconds_remaining": _seconds_left(attempt),
		"one_question_at_a_time": cint(quiz.one_question_at_a_time),
		"title": quiz.title,
		"description": quiz.description,
		"questions": [
			{
				**(quizzes.question_payload(question, quiz, seed=attempt.name) or {}),
				"given": _decode(given.get(question)),
			}
			for question in questions
		],
	}


def _decode(answer):
	if answer in (None, ""):
		return None
	try:
		return json.loads(answer)
	except (ValueError, TypeError):
		return answer


@frappe.whitelist(methods=["POST"])
def answer(course_registration, attempt, question, value):
	"""Record one answer.

	Saved as it is given rather than all at once at the end, so a browser that
	dies mid-quiz loses one answer rather than the paper.
	"""
	registration = _my_registration(course_registration)
	doc = _mine_or_throw(attempt, registration.name)

	if doc.status != "In progress":
		frappe.throw(_("This attempt is finished."))

	if doc.expires_at:
		overdue = (now_datetime() - get_datetime(doc.expires_at)).total_seconds()
		if overdue > quizzes.GRACE_SECONDS:
			# Close it here as well: the sweep runs on a schedule, and an
			# answer arriving late is the moment we know the time is up.
			_close(doc, auto=True)
			frappe.db.commit()
			frappe.throw(_("Your time is up."))

	if question not in json.loads(doc.question_order or "[]"):
		frappe.throw(_("That question is not on your paper."))

	stored = json.dumps(value)
	for row in doc.answers:
		if row.question == question:
			row.answer = stored
			break
	else:
		doc.append("answers", {"question": question, "answer": stored})

	doc.save(ignore_permissions=True)
	frappe.db.commit()

	return {"question": question, "seconds_remaining": _seconds_left(doc)}


@frappe.whitelist(methods=["POST"])
def submit(course_registration, attempt):
	"""Hand the paper in."""
	registration = _my_registration(course_registration)
	doc = _mine_or_throw(attempt, registration.name)

	if doc.status != "In progress":
		frappe.throw(_("This attempt is already finished."))

	_close(doc, auto=False)
	frappe.db.commit()

	return result(course_registration, attempt)


def _close(attempt, auto):
	"""Score it, close it, and write the one submission a quiz produces."""
	attempt.status = "Expired" if auto else "Submitted"
	attempt.auto_submitted = int(auto)
	attempt.submitted_at = attempt.expires_at if auto else now_datetime()
	quizzes.score_attempt(attempt)
	attempt.save(ignore_permissions=True)
	quizzes.submission_for(attempt)
	return attempt


def _mine_or_throw(attempt, registration):
	doc = frappe.get_doc("Quiz Attempt", attempt)
	if doc.course_registration != registration:
		frappe.throw(_("That attempt is not yours."), frappe.PermissionError)
	return doc


@frappe.whitelist()
def result(course_registration, attempt):
	"""What a student may see afterwards, which the quiz's own policy decides.

	"Never" means never -- not "hidden by the page". A payload that carries
	the answers and trusts the front end to hide them is a payload that gives
	them away.
	"""
	registration = _my_registration(course_registration)
	doc = _mine_or_throw(attempt, registration.name)
	quiz = frappe.get_doc("Course Quiz", doc.quiz)

	payload = {
		"attempt": doc.name,
		"status": doc.status,
		"auto_submitted": cint(doc.auto_submitted),
		"submitted_at": doc.submitted_at,
		"score": flt(doc.score),
		"points_possible": flt(doc.points_possible),
	}

	if not _may_reveal(quiz, doc):
		return payload

	payload["questions"] = []
	for row in doc.answers:
		question = frappe.db.get_value(
			"Bank Question", row.question, ["question", "question_type", "explanation"],
			as_dict=True,
		)
		payload["questions"].append(
			{
				"name": row.question,
				"question": question.question if question else None,
				"explanation": question.explanation if question else None,
				"given": _decode(row.answer),
				"is_correct": cint(row.is_correct),
				"points_awarded": flt(row.points_awarded),
				"correct": sorted(quizzes._correct_options(row.question)),
			}
		)
	return payload


def _may_reveal(quiz, attempt):
	policy = quiz.reveal_answers or "Never"
	if policy == "Never":
		return False
	if attempt.status == "In progress":
		# Nothing is revealed while the paper is still open, whatever the
		# policy says about afterwards.
		return False
	if policy == "After the attempt":
		return True

	due = frappe.db.get_value("Course Assignment", attempt.assignment, "due_date")
	return bool(due) and now_datetime() > get_datetime(due)


# ---------------------------------------------------------------------------
# building one
# ---------------------------------------------------------------------------


def _bank_course(bank):
	"""A bank's course, or None when it is shared. A bank that does not exist
	is said so, rather than read as a shared one."""
	if not bank or not frappe.db.exists("Question Bank", bank):
		frappe.throw(_("Bank not found."))
	return frappe.db.get_value("Question Bank", bank, "course")


@frappe.whitelist()
def banks(course=None):
	"""The banks this user may use: their own courses', and the shared ones.

	Scoped since 2026-09-11. A bank carries its answers, so a list of every
	course's banks was a directory of other people's exams.
	"""
	_require_teaching()
	return {
		"rows": frappe.get_all(
			"Question Bank",
			or_filters=academic_permissions.course_record_filters(course),
			fields=["name", "title", "course", "question_count", "description"],
			order_by="title asc",
		)
	}


@frappe.whitelist()
def bank(name):
	"""One bank with its questions -- and their answers, so only for the
	teachers of its course, or for anyone who teaches when it is shared."""
	_require_teaching()
	academic_permissions.assert_may_see(_bank_course(name))

	row = frappe.db.get_value(
		"Question Bank", name, ["name", "title", "course", "description"], as_dict=True
	)
	if not row:
		frappe.throw(_("Bank not found."))

	questions = frappe.get_all(
		"Bank Question",
		filters={"bank": name},
		fields=["name", "question", "question_type", "points", "position", "explanation"],
		order_by="position asc, creation asc",
	)
	for question in questions:
		question["options"] = frappe.get_all(
			"Bank Question Option",
			filters={"parent": question.name, "parenttype": "Bank Question"},
			fields=["idx", "option_text", "is_correct"],
			order_by="idx asc",
		)

	row["questions"] = questions
	return row


@frappe.whitelist(methods=["POST"])
def save_bank(title, course=None, description=None, name=None):
	"""A course's bank is its teachers'; a shared one the office's. Where it
	is now and where it would go are both checked, or a bank could be carried
	off another course."""
	_require_teaching()
	if name:
		academic_permissions.assert_may_change(_bank_course(name), _("question bank"))
	academic_permissions.assert_may_change(course or None, _("question bank"))

	doc = frappe.get_doc("Question Bank", name) if name else frappe.new_doc("Question Bank")
	doc.title = title
	doc.course = course or None
	doc.description = description
	doc.save()
	frappe.db.commit()
	return {"bank": doc.name}


@frappe.whitelist(methods=["POST"])
def save_question(bank, values, question=None):
	_require_teaching()
	academic_permissions.assert_may_change(_bank_course(bank), _("question bank"))
	if question and frappe.db.get_value("Bank Question", question, "bank") != bank:
		# Moving a question in would take it out of another bank -- possibly
		# another course's live quiz.
		frappe.throw(_("That question is in another bank."), frappe.PermissionError)

	if isinstance(values, str):
		values = frappe.parse_json(values)
	if not isinstance(values, dict):
		frappe.throw(_("A question must be a set of fields."))

	doc = (
		frappe.get_doc("Bank Question", question)
		if question
		else frappe.new_doc("Bank Question")
	)
	doc.bank = bank
	for field in ("question", "question_type", "points", "position", "explanation"):
		if field in values:
			doc.set(field, values[field])

	if "options" in values:
		doc.set("options", [])
		for option in values["options"] or []:
			doc.append(
				"options",
				{
					"option_text": option.get("option_text"),
					"is_correct": cint(option.get("is_correct")),
				},
			)

	doc.save()
	frappe.db.commit()
	return {"question": doc.name}


@frappe.whitelist(methods=["POST"])
def delete_question(question):
	_require_teaching()
	bank = frappe.db.get_value("Bank Question", question, "bank")
	if not bank:
		frappe.throw(_("Question not found."))
	academic_permissions.assert_may_change(_bank_course(bank), _("question bank"))

	frappe.delete_doc("Bank Question", question)
	frappe.db.commit()
	return {"deleted": question}


@frappe.whitelist()
def quizzes_for(course):
	_require_teaching()
	academic_permissions.assert_may_teach_course(course)
	return {
		"rows": frappe.get_all(
			"Course Quiz",
			filters={"course": course},
			fields=["name", "title", "time_limit_minutes", "allowed_attempts",
					"total_points", "reveal_answers"],
			order_by="title asc",
		)
	}


@frappe.whitelist(methods=["POST"])
def save_quiz(course, values, name=None):
	"""A quiz is its course's and stays there: changed by that course's
	teachers, never carried to another, and drawing only on its own course's
	banks or shared ones."""
	_require_teaching()
	academic_permissions.assert_may_teach_course(course)
	if name:
		where = frappe.db.get_value("Course Quiz", name, "course")
		if not where:
			frappe.throw(_("Quiz not found."))
		if where != course:
			frappe.throw(_("That quiz belongs to another course."), frappe.PermissionError)

	if isinstance(values, str):
		values = frappe.parse_json(values)
	if not isinstance(values, dict):
		frappe.throw(_("A quiz must be a set of fields."))

	doc = frappe.get_doc("Course Quiz", name) if name else frappe.new_doc("Course Quiz")
	doc.course = course
	for field in (
		"title", "time_limit_minutes", "allowed_attempts", "shuffle_questions",
		"shuffle_options", "reveal_answers", "one_question_at_a_time", "description",
	):
		if field in values:
			doc.set(field, values[field])

	if "sources" in values:
		doc.set("sources", [])
		for source in values["sources"] or []:
			owner = _bank_course(source.get("bank"))
			if owner and owner != course:
				# Drawing on it would put another course's exam questions in
				# this one's paper.
				frappe.throw(
					_("{0} belongs to another course.").format(source.get("bank")),
					frappe.PermissionError,
				)
			doc.append(
				"sources",
				{"bank": source.get("bank"), "pick": cint(source.get("pick")) or 1},
			)

	doc.save()
	frappe.db.commit()
	return {"quiz": doc.name}


@frappe.whitelist()
def attempts(assignment):
	"""Who has sat this, and how they did."""
	_require_teaching()
	offering = frappe.db.get_value("Course Assignment", assignment, "course_offering")
	if not offering:
		frappe.throw(_("Assignment not found."))
	academic_permissions.assert_may_teach(offering)

	return {
		"rows": frappe.get_all(
			"Quiz Attempt",
			filters={"assignment": assignment},
			fields=[
				"name", "student_name", "attempt", "status", "started_at",
				"submitted_at", "auto_submitted", "score", "points_possible",
			],
			order_by="student_name asc, attempt asc",
		)
	}
