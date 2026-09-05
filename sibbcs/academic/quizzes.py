# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""Sitting a quiz, with every decision made by the server.

The vendored LMS runs its timer, its shuffle and its attempt limit in the
browser, which means all three can be edited in devtools. Here:

    expires_at      set when the attempt starts, from the quiz's own limit,
                    and never accepted or recomputed from anything a client
                    sends
    question_order  drawn and stored once, so reloading cannot re-roll a
                    shuffle until an easier paper appears
    attempts        counted in the database
    correctness     never leaves the server while an attempt is open

**Scoring writes an Assignment Submission**, which is the same record a
hand-marked essay produces. A quiz has no route to a transcript of its own, so
the gradebook, the Grade Scale and CGPA need to know nothing about quizzes.

**The clock is the server's clock.** Every check compares `now_datetime()`
against the stored `expires_at`; nothing is trusted about when the browser
thinks it is. A late answer is refused rather than silently kept, because a
quiz that accepts answers after time is a quiz with no time limit.
"""

import json
import random

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, flt, now_datetime, get_datetime

# How long after expiry an answer is still accepted, to cover the round trip
# of a submit that left the browser just in time. Small enough to be worth
# nothing to somebody trying to use it.
GRACE_SECONDS = 5


def _plain(html):
	"""A question without its markup, for lists and titles."""
	import re

	return re.sub(r"<[^>]+>", " ", html or "").replace("&nbsp;", " ").strip()[:140]


# ---------------------------------------------------------------------------
# drawing a paper
# ---------------------------------------------------------------------------


def draw_questions(quiz):
	"""Choose the questions for one attempt.

	Drawn once per attempt and stored. A bank with fewer questions than the
	quiz asks for gives what it has rather than failing -- a short paper is
	better than no exam, and the shortfall is the author's to notice.
	"""
	doc = frappe.get_doc("Course Quiz", quiz) if isinstance(quiz, str) else quiz

	chosen = []
	for source in doc.sources:
		available = frappe.get_all(
			"Bank Question",
			filters={"bank": source.bank},
			pluck="name",
			order_by="position asc, creation asc",
		)
		wanted = min(cint(source.pick), len(available))
		chosen.extend(random.sample(available, wanted) if wanted else [])

	if cint(doc.shuffle_questions):
		random.shuffle(chosen)

	return chosen


def points_for(questions):
	if not questions:
		return 0.0
	rows = frappe.get_all(
		"Bank Question", filters={"name": ("in", questions)}, fields=["name", "points"]
	)
	return flt(sum(flt(row.points) for row in rows), 2)


# ---------------------------------------------------------------------------
# the paper a student is allowed to see
# ---------------------------------------------------------------------------


def question_payload(question, quiz, seed=None):
	"""One question with its options, and nothing about which is right.

	`is_correct` is dropped here rather than in the front end, so a student
	reading the network tab learns no more than one reading the page.
	"""
	row = frappe.db.get_value(
		"Bank Question", question, ["name", "question", "question_type", "points"],
		as_dict=True,
	)
	if not row:
		return None

	options = frappe.get_all(
		"Bank Question Option",
		filters={"parent": question, "parenttype": "Bank Question"},
		fields=["idx", "option_text"],
		order_by="idx asc",
	)

	if row.question_type == "Short answer":
		# The accepted answers are the options; sending them would be sending
		# the answer.
		options = []
	elif quiz and cint(quiz.get("shuffle_options")):
		# Seeded per attempt and question, so the order is stable when the
		# student reloads but different between students.
		shuffler = random.Random(f"{seed}:{question}")
		shuffler.shuffle(options)

	return {
		"name": row.name,
		"question": row.question,
		"question_type": row.question_type,
		"points": flt(row.points),
		"options": [{"idx": option.idx, "text": option.option_text} for option in options],
	}


# ---------------------------------------------------------------------------
# marking
# ---------------------------------------------------------------------------


def _correct_options(question):
	return {
		row.idx
		for row in frappe.get_all(
			"Bank Question Option",
			filters={"parent": question, "parenttype": "Bank Question"},
			fields=["idx", "is_correct"],
		)
		if cint(row.is_correct)
	}


def _accepted_texts(question):
	return {
		(row.option_text or "").strip().lower()
		for row in frappe.get_all(
			"Bank Question Option",
			filters={"parent": question, "parenttype": "Bank Question"},
			fields=["option_text", "is_correct"],
		)
		if cint(row.is_correct)
	}


def mark_answer(question, answer):
	"""Whether one answer is right, and what it earns.

	All or nothing per question, including "multiple answers": a partial tick
	list is not a partially correct answer to "which of these are true", and
	half marks for guessing everything would reward exactly that.
	"""
	row = frappe.db.get_value(
		"Bank Question", question, ["question_type", "points"], as_dict=True
	)
	if not row:
		return False, 0.0

	given = answer
	if isinstance(given, str):
		try:
			given = json.loads(given)
		except (ValueError, TypeError):
			given = given

	if row.question_type == "Short answer":
		text = (given if isinstance(given, str) else "").strip().lower()
		correct = bool(text) and text in _accepted_texts(question)
	else:
		chosen = {cint(value) for value in given} if isinstance(given, list) else set()
		correct = bool(chosen) and chosen == _correct_options(question)

	return correct, flt(row.points) if correct else 0.0


def score_attempt(attempt):
	"""Mark every answer and total the attempt.

	Deterministic arithmetic over answers already stored -- no judgement -- so
	it is safe to run from the expiry sweep as well as from a submit.
	"""
	doc = frappe.get_doc("Quiz Attempt", attempt) if isinstance(attempt, str) else attempt

	total = 0.0
	for row in doc.answers:
		correct, points = mark_answer(row.question, row.answer)
		row.is_correct = int(correct)
		row.points_awarded = points
		total += points

	doc.score = flt(total, 2)
	doc.points_possible = points_for(json.loads(doc.question_order or "[]"))
	return doc


def submission_for(attempt):
	"""Write the attempt's score onto the assignment's submission.

	This is the only place a quiz reaches a grade, and it reaches it through
	the record every other kind of work uses. `posted` is left to the marking
	API and the scheme's posting policy, so an auto-closed attempt does not
	put a mark in front of a student that nobody has released.
	"""
	doc = frappe.get_doc("Quiz Attempt", attempt) if isinstance(attempt, str) else attempt

	possible = flt(
		frappe.db.get_value("Course Assignment", doc.assignment, "points_possible")
	)
	# The quiz is marked out of its own questions; the assignment says what it
	# is worth. Scaling here keeps a bank edit from changing what the course
	# is out of.
	earned = (
		flt(doc.score) * possible / flt(doc.points_possible)
		if flt(doc.points_possible)
		else 0.0
	)

	existing = frappe.get_all(
		"Assignment Submission",
		filters={
			"assignment": doc.assignment,
			"course_registration": doc.course_registration,
		},
		fields=["name", "attempt"],
		order_by="attempt desc",
		limit=1,
	)

	if existing:
		submission = frappe.get_doc("Assignment Submission", existing[0].name)
	else:
		submission = frappe.new_doc("Assignment Submission")
		submission.assignment = doc.assignment
		submission.course_registration = doc.course_registration
		submission.attempt = 1

	submission.submitted_on = doc.submitted_at or now_datetime()
	submission.status = "Graded"
	submission.score = flt(earned, 2)
	submission.scored = 1
	submission.body = _("Quiz attempt {0}").format(doc.name)
	submission.flags.ignore_permissions = True
	submission.save(ignore_permissions=True)

	return submission.name


# ---------------------------------------------------------------------------
# the sweep
# ---------------------------------------------------------------------------


def close_expired():
	"""Close attempts whose time has run out.

	Runs on the scheduler. It scores, because a quiz score is arithmetic over
	answers already given rather than a judgement -- leaving them unscored
	would strand every student whose time ran out until somebody noticed.

	What it does *not* do is release the mark: `posted` is untouched, so the
	scheme's posting policy still decides when a student sees it. That is the
	line worth holding for a job that runs as Administrator and is therefore
	exempt from the permlevel that protects grade fields everywhere else.

	Idempotent: an attempt already Submitted or Expired is not looked at
	again.
	"""
	now = now_datetime()
	# A list, not a dict: a dict cannot carry two conditions on `expires_at`
	# and would silently keep only the last one.
	stale = frappe.get_all(
		"Quiz Attempt",
		filters=[
			["status", "=", "In progress"],
			["expires_at", "is", "set"],
			["expires_at", "<", now],
		],
		pluck="name",
	)

	closed = 0
	for name in stale:
		doc = frappe.get_doc("Quiz Attempt", name)
		if doc.status != "In progress" or not doc.expires_at:
			continue
		if get_datetime(doc.expires_at) >= now:
			continue

		doc.status = "Expired"
		doc.auto_submitted = 1
		doc.submitted_at = doc.expires_at
		score_attempt(doc)
		doc.save(ignore_permissions=True)
		submission_for(doc)
		closed += 1

	if closed:
		frappe.db.commit()
	return closed
