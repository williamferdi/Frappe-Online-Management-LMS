# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.admissions.doctype.admission_application.test_admission_application import (
	make_application,
)
from sibbcs.admissions.doctype.qualifying_exam_result.qualifying_exam_result import has_passed


def make_result(application, **scores):
	defaults = {
		"doctype": "Qualifying Exam Result",
		"application": application,
		"english_score": 70,
		"bible_score": 70,
		"theology_score": 70,
		"ministry_score": 70,
		"conducted_on": "2026-03-01",
	}
	defaults.update(scores)
	return frappe.get_doc(defaults).insert(ignore_permissions=True)


class TestQualifyingExamResult(FrappeTestCase):
	def test_total_is_the_mean_of_four_sections(self):
		app = make_application(email="qer1@example.com")
		result = make_result(
			app.name, english_score=80, bible_score=60, theology_score=70, ministry_score=90
		)
		self.assertEqual(result.total, 75)

	def test_pass_at_or_above_the_pass_mark(self):
		"""The rule, not the figure: the college has moved the pass mark once
		already, from 60 to 70, and will again."""
		app = make_application(email="qer2@example.com")
		result = make_result(
			app.name,
			pass_mark=60,
			english_score=60,
			bible_score=60,
			theology_score=60,
			ministry_score=60,
		)
		self.assertEqual(result.result, "Pass")

	def test_fail_below_the_pass_mark(self):
		app = make_application(email="qer3@example.com")
		result = make_result(
			app.name,
			pass_mark=60,
			english_score=59,
			bible_score=59,
			theology_score=59,
			ministry_score=59,
		)
		self.assertEqual(result.result, "Fail")

	def test_the_pass_mark_now_defaults_to_forty(self):
		meta = frappe.get_meta("Qualifying Exam Result")
		field = next(df for df in meta.fields if df.fieldname == "pass_mark")
		self.assertEqual(float(field.default), 40.0)

	def test_negative_score_rejected(self):
		app = make_application(email="qer4@example.com")
		with self.assertRaises(frappe.ValidationError):
			make_result(app.name, english_score=-1)

	def test_score_above_hundred_rejected(self):
		app = make_application(email="qer5@example.com")
		with self.assertRaises(frappe.ValidationError):
			make_result(app.name, bible_score=101)

	def test_score_is_mirrored_onto_the_application(self):
		"""The workflow gates on the application's copy of the score."""
		app = make_application(email="qer6@example.com")
		make_result(
			app.name, english_score=80, bible_score=80, theology_score=80, ministry_score=80
		)
		app.reload()
		self.assertEqual(app.qualifying_exam_score, 80)

	def test_has_passed_helper(self):
		app = make_application(email="qer7@example.com")
		make_result(app.name, english_score=90, bible_score=90, theology_score=90, ministry_score=90)
		self.assertTrue(has_passed(app.name))

	def test_has_passed_is_false_without_a_result(self):
		app = make_application(email="qer8@example.com")
		self.assertFalse(has_passed(app.name))
