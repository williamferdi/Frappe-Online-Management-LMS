# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""The academic console.

Grade entry is the one place this layer writes, so most of these tests are
about that: that a blank mark is not a zero, that the letter comes from the
Grade Scale rather than from here, and that the permlevel on the grade fields
is still doing its job because nothing passes `ignore_permissions`.
"""

import ast
import inspect

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.academic.doctype.academic_term.test_academic_term import make_term
from sibbcs.academic.doctype.course.test_course import make_course
from sibbcs.academic.doctype.course_offering.test_course_offering import make_offering
from sibbcs.academic.doctype.course_registration.test_course_registration import (
	make_registration,
)
from sibbcs.api import academic_api as api
from sibbcs.api.test_student_api import make_student


def a_registration():
	"""A live registration of our own.

	Built rather than found: grading the first Registered row on the site
	moves it to Completed, so a test that borrows one leaves the next run
	with nothing to borrow and quietly skips.
	"""
	tag = frappe.generate_hash(length=6)
	term = make_term(f"GRD-{tag}", status="Open").name
	course = make_course(f"GRD{tag}", level="1", credits=3).name
	# make_offering leaves an offering in Draft, which the rule engine
	# correctly refuses to register anyone onto.
	offering = make_offering(course, term, status="Published").name

	student, enrollment, _ = make_student()
	return make_registration(enrollment.name, offering).name


class TestAccess(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_a_student_is_refused_the_academic_console(self):
		"""Students hold read on Student and Course Registration -- they must,
		to see their own. These endpoints list everybody."""
		_, _, email = make_student()
		frappe.set_user(email)

		for endpoint, kwargs in (
			(api.students, {}),
			(api.offerings, {}),
		):
			with self.subTest(endpoint=endpoint.__name__):
				with self.assertRaises(frappe.PermissionError):
					endpoint(**kwargs)

	def test_a_guest_is_refused(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			api.students()

	def test_save_grades_never_ignores_permissions(self):
		"""The grade fields sit at permlevel 1, so an ordinary save is already
		the permission check, and `ignore_permissions` would quietly remove it.

		Read from the syntax tree, not the text: the first version of this
		test grepped the source and matched the docstring explaining the rule.
		"""
		tree = ast.parse(inspect.getsource(api.save_grades).lstrip())
		offenders = [
			node
			for node in ast.walk(tree)
			if isinstance(node, ast.Call)
			for kw in node.keywords
			if kw.arg == "ignore_permissions"
		]
		self.assertEqual(offenders, [], "save_grades bypasses the permlevel check")
		self.assertIn('check_permission("write")', inspect.getsource(api.save_grades))


class TestStudents(FrappeTestCase):
	def test_the_roll_carries_each_enrolment(self):
		result = api.students()
		self.assertIn("rows", result)
		for row in result["rows"]:
			self.assertIn("enrollment", row)

	def test_search_matches_a_fragment(self):
		"""A bare value in or_filters means `=`; the operator has to be
		spelled out or the box silently matches nothing.

		Searched on the unique part of the name, not the shared prefix: every
		student this suite makes is a Portal Student, and matching all of them
		runs into the row cap rather than testing the LIKE.
		"""
		student, _, _ = make_student()
		frappe.db.commit()

		fragment = student.full_name.split()[-1]
		names = [row.name for row in api.students(search=fragment)["rows"]]
		self.assertIn(student.name, names)

	def test_a_capped_list_says_it_was_capped(self):
		"""Two hundred results with no sign there are four hundred is a
		Registrar reading a truncated list and believing it."""
		page = api.students(limit=1)
		self.assertIn("truncated", page)
		if frappe.db.count("Student") > 1:
			self.assertTrue(page["truncated"])
			self.assertEqual(len(page["rows"]), 1)

	def test_a_missing_student_is_reported_not_returned_empty(self):
		with self.assertRaises(frappe.ValidationError):
			api.student("SIB-does-not-exist")


class TestGradeEntry(FrappeTestCase):
	def setUp(self):
		self.registration = a_registration()

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_a_blank_mark_is_not_a_zero(self):
		"""compute_grade holds the letter back until every component is marked.
		Storing a blank as 0 would award a fail on unfinished marking."""
		result = api.save_grades(
			self.registration,
			[
				{"component": "Assignment", "weight_pct": 40, "max_marks": 100, "obtained_marks": 82},
				{"component": "Final Paper", "weight_pct": 60, "max_marks": 100, "obtained_marks": None},
			],
		)

		self.assertFalse(result["marks_complete"])
		self.assertIsNone(result["grade"])
		blank = next(c for c in result["components"] if c["component"] == "Final Paper")
		self.assertIn(blank["obtained_marks"], (None, 0.0))
		self.assertIsNone(blank["obtained_marks"], "a blank mark was stored as a number")

	def test_a_complete_sheet_produces_a_letter_from_the_scale(self):
		result = api.save_grades(
			self.registration,
			[
				{"component": "Assignment", "weight_pct": 40, "max_marks": 100, "obtained_marks": 90},
				{"component": "Final Paper", "weight_pct": 60, "max_marks": 100, "obtained_marks": 90},
			],
		)

		self.assertTrue(result["marks_complete"])
		self.assertEqual(result["final_marks"], 90.0)
		self.assertTrue(result["grade"], "no grade came back from the scale")

	def test_the_weighted_score_is_computed_not_accepted(self):
		"""A caller could send any weighted_score it liked; the document
		recomputes from the raw marks."""
		result = api.save_grades(
			self.registration,
			[
				{
					"component": "Assignment",
					"weight_pct": 50,
					"max_marks": 100,
					"obtained_marks": 60,
					"weighted_score": 999,
				},
				{"component": "Final Paper", "weight_pct": 50, "max_marks": 100, "obtained_marks": 60},
			],
		)
		for component in result["components"]:
			self.assertEqual(component["weighted_score"], 30.0)

	def test_marks_out_of_something_other_than_a_hundred(self):
		result = api.save_grades(
			self.registration,
			[
				{"component": "Assignment", "weight_pct": 100, "max_marks": 50, "obtained_marks": 25},
			],
		)
		self.assertEqual(result["final_marks"], 50.0)

	def test_saving_marks_updates_the_credits_and_cgpa(self):
		enrollment = frappe.db.get_value(
			"Course Registration", self.registration, "program_enrollment"
		)
		api.save_grades(
			self.registration,
			[
				{"component": "Assignment", "weight_pct": 100, "max_marks": 100, "obtained_marks": 85},
			],
			status="Completed",
		)
		frappe.db.commit()

		row = frappe.db.get_value(
			"Program Enrollment", enrollment, ["credits_earned", "cgpa"], as_dict=True
		)
		self.assertGreater(row.credits_earned, 0)

	def test_components_may_arrive_as_a_json_string(self):
		"""Frappe hands whitelisted methods form-encoded arguments, so a list
		arrives as text."""
		import json

		result = api.save_grades(
			self.registration,
			json.dumps(
				[{"component": "Assignment", "weight_pct": 100, "max_marks": 100, "obtained_marks": 70}]
			),
		)
		self.assertEqual(result["final_marks"], 70.0)

	def test_something_that_is_not_a_list_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			api.save_grades(self.registration, {"component": "Assignment"})

	def test_a_row_with_no_component_named_is_skipped(self):
		result = api.save_grades(
			self.registration,
			[
				{"component": "Assignment", "weight_pct": 100, "max_marks": 100, "obtained_marks": 70},
				{"component": "", "weight_pct": 0, "max_marks": 100, "obtained_marks": None},
			],
		)
		self.assertEqual(len(result["components"]), 1)


class TestRoster(FrappeTestCase):
	def test_the_component_choices_come_from_the_doctype(self):
		"""Hard-coding them here is how the sheet ends up offering a component
		the Select refuses on save."""
		meta = frappe.get_meta("Grade Component")
		options = [c for c in (meta.get_field("component").options or "").split("\n") if c]
		self.assertEqual(api._component_choices(), options)

	def test_the_statuses_come_from_the_doctype(self):
		meta = frappe.get_meta("Course Registration")
		options = [c for c in (meta.get_field("status").options or "").split("\n") if c]
		self.assertEqual(api._registration_statuses(), options)

	def test_marks_complete_is_false_when_a_component_is_blank(self):
		self.assertFalse(api._marks_complete([]))
		self.assertFalse(
			api._marks_complete([{"obtained_marks": 10}, {"obtained_marks": None}])
		)
		self.assertTrue(api._marks_complete([{"obtained_marks": 10}, {"obtained_marks": 0}]))

	def test_a_missing_offering_is_reported(self):
		with self.assertRaises(frappe.ValidationError):
			api.roster("does-not-exist")


class TestPromotions(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_the_board_says_whether_the_caller_may_act(self):
		result = api.promotions()
		self.assertIn("may_approve", result)
		self.assertIn("rows", result)

	def test_every_blocked_row_gives_a_reason(self):
		"""A greyed button with no explanation is what the office rings about."""
		for row in api.promotions()["rows"]:
			if not row["eligible"]:
				self.assertTrue(row["blocked"], f"{row['student_name']} blocked with no reason")

	def test_a_student_cannot_see_the_promotion_board(self):
		_, _, email = make_student()
		frappe.set_user(email)
		with self.assertRaises(frappe.PermissionError):
			api.promotions()
