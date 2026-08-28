# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""The entrance exam: three essays out of 75, pass at 40%."""

import itertools

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.admissions.doctype.qualifying_exam_result.qualifying_exam_result import (
	ESSAY_MAX,
	ESSAY_TOTAL,
	ESSAYS,
)
from sibbcs.setup import phase2m_entrance_exam as exam

PASS = 40


_seq = itertools.count(1)


def make_result(**scores):
	"""`application` is mandatory on this DocType, so every result needs one."""
	from sibbcs.admissions.doctype.admission_application.test_admission_application import (
		make_application,
	)

	values = {
		"doctype": "Qualifying Exam Result",
		"applicant_name": "Exam Candidate",
		"conducted_on": frappe.utils.today(),
		"pass_mark": PASS,
	}
	values.update(scores)
	if not values.get("application"):
		values["application"] = make_application(
			email=f"examcand{next(_seq)}@example.com"
		).name
	doc = frappe.get_doc(values)
	doc.insert(ignore_permissions=True)
	return doc


class TestEssayScoring(FrappeTestCase):
	def test_the_paper_is_three_essays_of_twenty_five(self):
		self.assertEqual(len(ESSAYS), 3)
		self.assertEqual(ESSAY_MAX, 25)
		self.assertEqual(ESSAY_TOTAL, 75)

	def test_the_total_reads_as_a_percentage_of_seventy_five(self):
		doc = make_result(essay_gospel=20, essay_calling=20, essay_motivation=20)
		self.assertEqual(doc.total, 80.0)  # 60 of 75

	def test_the_pass_mark_decides_the_verdict(self):
		"""40% of 75 is 30 marks."""
		passing = make_result(essay_gospel=10, essay_calling=10, essay_motivation=10)
		self.assertEqual(passing.total, 40.0)
		self.assertEqual(passing.result, "Pass")

		failing = make_result(essay_gospel=10, essay_calling=10, essay_motivation=9)
		self.assertEqual(failing.total, 38.67)
		self.assertEqual(failing.result, "Fail")

	def test_a_full_paper_is_a_hundred_percent(self):
		doc = make_result(essay_gospel=25, essay_calling=25, essay_motivation=25)
		self.assertEqual(doc.total, 100.0)

	def test_an_essay_mark_above_twenty_five_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			make_result(essay_gospel=26)

	def test_a_negative_essay_mark_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			make_result(essay_gospel=-1)

	def test_one_marked_essay_is_enough_to_use_the_essay_rule(self):
		"""Half-marked scripts must not fall back to the four-subject mean."""
		doc = make_result(essay_gospel=25)
		self.assertEqual(doc.total, 33.33)  # 25 of 75, not a mean of four

	# -- the paper that came before ----------------------------------------

	def test_a_four_subject_result_is_still_averaged(self):
		"""Results recorded against the old paper keep the answer they had."""
		doc = make_result(
			bible_score=75, theology_score=75, ministry_score=75, english_score=75
		)
		self.assertEqual(doc.total, 75.0)

	def test_the_old_paper_is_only_used_when_no_essay_is_marked(self):
		doc = make_result(
			bible_score=100,
			theology_score=100,
			ministry_score=100,
			english_score=100,
			essay_gospel=10,
			essay_calling=10,
			essay_motivation=10,
		)
		self.assertEqual(doc.total, 40.0)  # 30 of 75, not the mean of 100s

	def test_the_score_reaches_the_application(self):
		from sibbcs.admissions.doctype.admission_application.test_admission_application import (
			make_application,
		)

		app = make_application(email="examresult@example.com")
		make_result(
			application=app.name,
			essay_gospel=20,
			essay_calling=20,
			essay_motivation=20,
		)
		self.assertEqual(
			frappe.db.get_value("Admission Application", app.name, "qualifying_exam_score"),
			80.0,
		)


class TestExamCourseBuilder(FrappeTestCase):
	def test_the_pass_mark_matches_the_desk_record(self):
		"""Two places carry the figure; they must not drift apart."""
		from sibbcs.setup import phase2n_exam_fields

		self.assertEqual(exam.PASSING_PERCENTAGE, PASS)
		self.assertEqual(phase2n_exam_fields.PASS_MARK, PASS)

	def test_the_paper_is_worth_seventy_five(self):
		self.assertEqual(exam.MARKS_PER_ESSAY * len(exam.ESSAYS), 75)

	def test_every_essay_states_its_marks(self):
		for _title, prompt in exam.ESSAYS:
			self.assertIn("25 marks", prompt)

	def test_every_essay_states_the_word_count(self):
		for _title, prompt in exam.ESSAYS:
			self.assertIn("200", prompt)
			self.assertIn("300", prompt)

	def test_the_rubrics_are_not_in_the_candidates_questions(self):
		"""A candidate reading the mark scheme is not sitting the same exam."""
		for _title, prompt in exam.ESSAYS:
			self.assertNotIn("rubric", prompt.lower())
			self.assertNotIn("0–10", prompt)
			self.assertNotIn("Doctrinal soundness", prompt)

		# and the rubric text must never reach the lesson body either
		self.assertNotIn("0–10", exam.LESSON_BODY)

	def test_the_rubrics_cover_every_essay(self):
		text = " ".join(entry[1] for entry in exam.RUBRIC_BLOCKS)
		for fragment in (
			"Understanding of the Gospel",
			"Calling to Ministry",
			"Motivation to Study",
		):
			self.assertIn(fragment, text)

	def test_the_rubrics_say_they_are_not_for_the_candidate(self):
		text = " ".join(entry[1] for entry in exam.RUBRIC_BLOCKS)
		self.assertIn("not shown to the candidate", text)

	def test_the_rubrics_are_valid_editorjs_json(self):
		"""Lesson.vue calls JSON.parse on this inside the template, unguarded.
		Anything that is not JSON throws during render and the lesson comes out
		blank -- which is what HTML in this field did."""
		import json

		document = json.loads(exam.rubric_json())
		self.assertIn("blocks", document)
		self.assertGreater(
			len(document["blocks"]),
			1,
			"the template hides instructor content with one block or fewer",
		)
		for block in document["blocks"]:
			self.assertIn(block["type"], ("header", "paragraph"))
			self.assertTrue(block["data"].get("text"))
			self.assertTrue(block.get("id"))

	def test_the_exam_is_sat_once(self):
		self.assertEqual(exam.MAX_ATTEMPTS, 1)


class TestExamTidy(FrappeTestCase):
	"""Rebuilding after somebody edits the quiz by hand.

	Building a quiz through the LMS UI is easy to get wrong -- the rubric bands
	read like separate questions, and deleting a quiz leaves the lesson
	pointing at nothing. tidy() finds that wreckage; the one thing it must
	never remove is a candidate's answers.
	"""

	def test_survey_reports_the_four_things_that_go_wrong(self):
		found = exam.survey()
		for key in (
			"stray_questions",
			"loose_quizzes",
			"dangling_lessons",
			"empty_lessons",
		):
			self.assertIn(key, found)
			self.assertIsInstance(found[key], list)

	def test_a_dry_run_removes_nothing(self):
		before = {
			"quizzes": frappe.db.count("LMS Quiz"),
			"questions": frappe.db.count("LMS Question"),
			"lessons": frappe.db.count("Course Lesson"),
		}
		exam.tidy(apply=False)
		self.assertEqual(before["quizzes"], frappe.db.count("LMS Quiz"))
		self.assertEqual(before["questions"], frappe.db.count("LMS Question"))
		self.assertEqual(before["lessons"], frappe.db.count("Course Lesson"))

	def test_our_own_quiz_is_never_called_loose(self):
		"""It has a course and a lesson, so it must never be swept up."""
		found = exam.survey()
		for name in found["loose_quizzes"]:
			self.assertNotEqual(
				frappe.db.get_value("LMS Quiz", name, "title"), exam.QUIZ_TITLE
			)

	def test_a_quiz_with_submissions_is_kept(self):
		"""A candidate's answers are the one thing here that cannot be rebuilt."""
		from unittest.mock import patch

		with patch.object(exam, "survey", return_value={
			"loose_quizzes": ["some-quiz"],
			"stray_questions": [],
			"dangling_lessons": [],
			"empty_lessons": [],
		}), patch.object(exam, "_has_submissions", return_value=True):
			found = exam.tidy(apply=False)

		self.assertEqual(found["loose_quizzes"], [])
