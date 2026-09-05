# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""One test per claim made about the quiz engine.

The claims worth testing are the ones the vendored LMS cannot make: the clock,
the shuffle, the attempt count and the answer key are all the server's, and a
student who edits the page learns nothing and gains nothing.
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from sibbcs.academic import quizzes
from sibbcs.academic.doctype.academic_term.test_academic_term import make_term
from sibbcs.academic.doctype.course.test_course import make_course
from sibbcs.academic.doctype.course_offering.test_course_offering import make_offering
from sibbcs.academic.doctype.program_enrollment.test_program_enrollment import (
	make_enrollment,
	make_student,
)
from sibbcs.academic.test_gradebook import make_scheme
from sibbcs.api import quiz as quiz_api


def make_bank(title, course=None):
	return frappe.get_doc(
		{"doctype": "Question Bank", "title": title, "course": course}
	).insert(ignore_permissions=True)


def make_question(bank, text="What is 2 + 2?", correct="4", wrong=("3", "5"), **kw):
	options = [{"option_text": correct, "is_correct": 1}]
	options += [{"option_text": value, "is_correct": 0} for value in wrong]

	values = {
		"doctype": "Bank Question",
		"bank": bank,
		"question": f"<p>{text}</p>",
		"question_type": kw.pop("question_type", "Choice"),
		"points": kw.pop("points", 1),
		"options": kw.pop("options", options),
	}
	values.update(kw)
	return frappe.get_doc(values).insert(ignore_permissions=True)


class TestQuizzes(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.term = make_term(
			f"TST-QZ-{frappe.generate_hash(length=6)}", status="Open"
		).name

	def setUp(self):
		frappe.set_user("Administrator")
		suffix = frappe.generate_hash(length=6)
		self.course = make_course(f"TQZ {suffix[:4]}").name
		self.offering = make_offering(self.course, self.term, status="Published").name
		make_scheme(self.offering, [{"component": "Quiz", "weight_pct": 100}])

		self.bank = make_bank(f"Bank {suffix}", self.course).name
		self.questions = [
			make_question(self.bank, f"Question {index}") for index in range(4)
		]

		self.quiz = frappe.get_doc(
			{
				"doctype": "Course Quiz",
				"course": self.course,
				"title": f"Quiz {suffix}",
				"time_limit_minutes": 30,
				"allowed_attempts": 1,
				"sources": [{"bank": self.bank, "pick": 4}],
			}
		).insert(ignore_permissions=True)

		self.assignment = frappe.get_doc(
			{
				"doctype": "Course Assignment",
				"course_offering": self.offering,
				"title": f"Sit the quiz {suffix[:4]}",
				"component": "Quiz",
				"points_possible": 20,
				"submission_type": "Quiz",
				"course_quiz": self.quiz.name,
				"late_policy": "Accept",
				"published": 1,
			}
		).insert(ignore_permissions=True).name

		email = f"quiz.{suffix}@example.invalid"
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": "Quiz Student",
					"user_type": "System User",
					"send_welcome_email": 0,
					"roles": [{"role": "Student"}],
				}
			).insert(ignore_permissions=True)
		self.email = email
		self.student = make_student(f"Quiz Student {suffix}", user=email).name
		self.registration = frappe.get_doc(
			{
				"doctype": "Course Registration",
				"program_enrollment": make_enrollment(self.student).name,
				"course_offering": self.offering,
				"status": "Registered",
			}
		).insert(ignore_permissions=True).name

	def tearDown(self):
		frappe.set_user("Administrator")

	def _start(self):
		frappe.set_user(self.email)
		return quiz_api.start(self.registration, self.assignment)

	# --- the clock ---------------------------------------------------------

	def test_the_clock_is_set_by_the_server(self):
		"""Nothing about the deadline comes from the browser."""
		started = self._start()

		attempt = frappe.get_doc("Quiz Attempt", started["attempt"])
		expected = add_to_date(attempt.started_at, minutes=30)

		self.assertAlmostEqual(
			(expected - attempt.expires_at).total_seconds(), 0, delta=2
		)
		self.assertGreater(started["seconds_remaining"], 1700)

	def test_an_answer_after_time_is_refused(self):
		"""A quiz that takes late answers has no time limit."""
		started = self._start()
		attempt = started["attempt"]

		frappe.db.set_value(
			"Quiz Attempt", attempt, "expires_at", add_to_date(now_datetime(), minutes=-1)
		)

		with self.assertRaises(frappe.ValidationError):
			quiz_api.answer(self.registration, attempt, self.questions[0].name, [1])

	def test_a_late_answer_closes_the_attempt_rather_than_leaving_it_open(self):
		started = self._start()
		attempt = started["attempt"]
		frappe.db.set_value(
			"Quiz Attempt", attempt, "expires_at", add_to_date(now_datetime(), minutes=-1)
		)

		try:
			quiz_api.answer(self.registration, attempt, self.questions[0].name, [1])
		except frappe.ValidationError:
			pass

		frappe.set_user("Administrator")
		doc = frappe.get_doc("Quiz Attempt", attempt)
		self.assertEqual(doc.status, "Expired")
		self.assertTrue(doc.auto_submitted)

	def test_reconnecting_does_not_buy_more_time(self):
		"""The same attempt, the same paper, the same deadline."""
		first = self._start()
		second = quiz_api.start(self.registration, self.assignment)

		self.assertEqual(first["attempt"], second["attempt"])
		self.assertEqual(first["expires_at"], second["expires_at"])
		self.assertEqual(
			[q["name"] for q in first["questions"]],
			[q["name"] for q in second["questions"]],
		)

	def test_the_sweep_closes_and_scores_an_abandoned_attempt(self):
		"""A student whose time ran out is not left unscored forever."""
		started = self._start()
		attempt = started["attempt"]
		quiz_api.answer(self.registration, attempt, self.questions[0].name, [1])

		frappe.set_user("Administrator")
		frappe.db.set_value(
			"Quiz Attempt", attempt, "expires_at", add_to_date(now_datetime(), minutes=-1)
		)

		closed = quizzes.close_expired()

		doc = frappe.get_doc("Quiz Attempt", attempt)
		self.assertGreaterEqual(closed, 1)
		self.assertEqual(doc.status, "Expired")
		self.assertTrue(doc.auto_submitted)
		self.assertIsNotNone(doc.score)

	def test_the_sweep_leaves_a_live_attempt_alone(self):
		started = self._start()

		frappe.set_user("Administrator")
		quizzes.close_expired()

		self.assertEqual(
			frappe.db.get_value("Quiz Attempt", started["attempt"], "status"),
			"In progress",
		)

	def test_the_sweep_does_not_release_the_mark(self):
		"""It runs as Administrator, which is exempt from the permlevel that
		protects grades everywhere else. So it scores, and stops."""
		started = self._start()
		quiz_api.answer(self.registration, started["attempt"], self.questions[0].name, [1])

		frappe.set_user("Administrator")
		frappe.db.set_value(
			"Quiz Attempt",
			started["attempt"],
			"expires_at",
			add_to_date(now_datetime(), minutes=-1),
		)
		quizzes.close_expired()

		submission = frappe.get_all(
			"Assignment Submission",
			filters={"assignment": self.assignment, "course_registration": self.registration},
			fields=["posted", "scored"],
		)[0]
		self.assertTrue(submission.scored)
		self.assertFalse(submission.posted, "nobody has released this yet")

	# --- what the browser is told -----------------------------------------

	def test_the_paper_never_says_which_answer_is_right(self):
		"""A student reading the network tab learns no more than one reading
		the page."""
		started = self._start()

		# frappe.as_json, because that is the encoder the real response uses.
		body = frappe.as_json(started)
		for question in started["questions"]:
			for option in question["options"]:
				self.assertNotIn("is_correct", option)
		self.assertNotIn("is_correct", body)

	def test_a_short_answer_question_sends_no_options_at_all(self):
		"""The accepted answers are the options, so sending them would be
		sending the answer."""
		question = make_question(
			self.bank,
			"Name the first book",
			question_type="Short answer",
			options=[{"option_text": "Genesis", "is_correct": 1}],
		)

		payload = quizzes.question_payload(
			question.name, frappe.get_doc("Course Quiz", self.quiz.name)
		)
		self.assertEqual(payload["options"], [])

	def test_results_are_withheld_when_the_quiz_says_never(self):
		started = self._start()
		quiz_api.answer(self.registration, started["attempt"], self.questions[0].name, [1])
		quiz_api.submit(self.registration, started["attempt"])

		result = quiz_api.result(self.registration, started["attempt"])

		self.assertNotIn("questions", result)
		self.assertIn("score", result)

	def test_results_are_shown_when_the_quiz_says_after_the_attempt(self):
		frappe.db.set_value(
			"Course Quiz", self.quiz.name, "reveal_answers", "After the attempt"
		)

		started = self._start()
		quiz_api.answer(self.registration, started["attempt"], self.questions[0].name, [1])
		quiz_api.submit(self.registration, started["attempt"])

		result = quiz_api.result(self.registration, started["attempt"])
		self.assertIn("questions", result)
		self.assertIn("correct", result["questions"][0])

	# --- attempts ----------------------------------------------------------

	def test_the_attempt_limit_is_counted_in_the_database(self):
		started = self._start()
		quiz_api.submit(self.registration, started["attempt"])

		with self.assertRaises(frappe.ValidationError):
			quiz_api.start(self.registration, self.assignment)

	def test_an_attempt_is_not_somebody_elses_to_answer(self):
		started = self._start()

		other = make_student(f"Other {frappe.generate_hash(length=6)}", user=None).name
		other_registration = frappe.get_doc(
			{
				"doctype": "Course Registration",
				"program_enrollment": make_enrollment(other).name,
				"course_offering": self.offering,
				"status": "Registered",
			}
		).insert(ignore_permissions=True).name

		frappe.set_user(self.email)
		with self.assertRaises(frappe.PermissionError):
			quiz_api.answer(
				other_registration, started["attempt"], self.questions[0].name, [1]
			)

	def test_a_question_not_on_the_paper_is_refused(self):
		"""Drawn papers differ, so "answer question X" has to be checked
		against this attempt's own list."""
		started = self._start()
		stranger = make_question(make_bank("Elsewhere").name, "Not yours")

		with self.assertRaises(frappe.ValidationError):
			quiz_api.answer(self.registration, started["attempt"], stranger.name, [1])

	# --- marking -----------------------------------------------------------

	def test_a_right_answer_scores_and_a_wrong_one_does_not(self):
		question = self.questions[0]
		correct_index = next(
			row.idx for row in question.options if row.is_correct
		)

		self.assertEqual(quizzes.mark_answer(question.name, [correct_index]), (True, 1.0))
		self.assertEqual(
			quizzes.mark_answer(question.name, [correct_index + 1])[0], False
		)

	def test_multiple_answers_are_all_or_nothing(self):
		"""Half marks for ticking everything would reward ticking everything."""
		question = make_question(
			self.bank,
			"Which are true?",
			question_type="Multiple answers",
			options=[
				{"option_text": "A", "is_correct": 1},
				{"option_text": "B", "is_correct": 1},
				{"option_text": "C", "is_correct": 0},
			],
		)

		self.assertEqual(quizzes.mark_answer(question.name, [1, 2])[0], True)
		self.assertEqual(quizzes.mark_answer(question.name, [1])[0], False)
		self.assertEqual(quizzes.mark_answer(question.name, [1, 2, 3])[0], False)

	def test_a_short_answer_is_matched_without_case_or_padding(self):
		question = make_question(
			self.bank,
			"First book?",
			question_type="Short answer",
			options=[{"option_text": "Genesis", "is_correct": 1}],
		)

		self.assertEqual(quizzes.mark_answer(question.name, "  genesis ")[0], True)
		self.assertEqual(quizzes.mark_answer(question.name, "Exodus")[0], False)
		self.assertEqual(quizzes.mark_answer(question.name, "")[0], False)

	def test_submitting_writes_one_assignment_submission(self):
		"""The whole point of routing quizzes through an assignment: a quiz has
		no path to a transcript of its own."""
		started = self._start()
		for question in started["questions"]:
			quiz_api.answer(self.registration, started["attempt"], question["name"], [1])
		quiz_api.submit(self.registration, started["attempt"])

		frappe.set_user("Administrator")
		submissions = frappe.get_all(
			"Assignment Submission",
			filters={"assignment": self.assignment, "course_registration": self.registration},
			fields=["name", "score", "scored"],
		)

		self.assertEqual(len(submissions), 1)
		self.assertTrue(submissions[0].scored)

	def test_the_score_is_scaled_to_what_the_assignment_is_worth(self):
		"""The quiz is out of its own questions; the assignment says what it is
		worth to the course. Editing a bank must not change the course total."""
		started = self._start()
		for question in started["questions"]:
			correct = next(
				row.idx
				for row in frappe.get_doc("Bank Question", question["name"]).options
				if row.is_correct
			)
			quiz_api.answer(
				self.registration, started["attempt"], question["name"], [correct]
			)
		quiz_api.submit(self.registration, started["attempt"])

		frappe.set_user("Administrator")
		score = frappe.get_all(
			"Assignment Submission",
			filters={"assignment": self.assignment, "course_registration": self.registration},
			pluck="score",
		)[0]

		# Four questions worth 1 each, all right, on an assignment out of 20.
		self.assertEqual(score, 20.0)

	# --- authoring ---------------------------------------------------------

	def test_a_question_with_no_correct_answer_is_refused(self):
		"""Caught when it is written, not when a student gets it wrong."""
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Bank Question",
					"bank": self.bank,
					"question": "<p>Unanswerable</p>",
					"question_type": "Choice",
					"points": 1,
					"options": [
						{"option_text": "A", "is_correct": 0},
						{"option_text": "B", "is_correct": 0},
					],
				}
			).insert(ignore_permissions=True)

	def test_a_single_choice_question_cannot_have_two_right_answers(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Bank Question",
					"bank": self.bank,
					"question": "<p>Ambiguous</p>",
					"question_type": "Choice",
					"points": 1,
					"options": [
						{"option_text": "A", "is_correct": 1},
						{"option_text": "B", "is_correct": 1},
					],
				}
			).insert(ignore_permissions=True)

	def test_the_bank_counts_its_own_questions(self):
		self.assertEqual(
			frappe.db.get_value("Question Bank", self.bank, "question_count"),
			len(self.questions),
		)

	def test_a_bank_shorter_than_the_draw_gives_what_it_has(self):
		"""A short paper beats no exam; the shortfall is the author's to see."""
		quiz = frappe.get_doc(
			{
				"doctype": "Course Quiz",
				"course": self.course,
				"title": "Greedy",
				"sources": [{"bank": self.bank, "pick": 99}],
			}
		).insert(ignore_permissions=True)

		self.assertEqual(len(quizzes.draw_questions(quiz)), len(self.questions))
