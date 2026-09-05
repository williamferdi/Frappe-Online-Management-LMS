# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""One test per rule about bringing LMS records across.

The rule worth most is the one an importer is most likely to flatten: Pass
becomes full marks, Fail becomes zero, and **Not Graded stays unscored**. A
zero for work nobody marked is the failure the whole grade pipeline is built
to avoid, and an import is where it would arrive silently.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.academic import lms_import
from sibbcs.academic.doctype.academic_term.test_academic_term import make_term
from sibbcs.academic.doctype.course.test_course import make_course
from sibbcs.academic.doctype.course_offering.test_course_offering import make_offering
from sibbcs.academic.doctype.program_enrollment.test_program_enrollment import (
	make_enrollment,
	make_student,
)
from sibbcs.academic.test_gradebook import make_assignment, make_scheme


class TestLmsImport(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.term = make_term(
			f"TST-IM-{frappe.generate_hash(length=6)}", status="Open"
		).name

	def setUp(self):
		frappe.set_user("Administrator")
		suffix = frappe.generate_hash(length=6)
		self.course = make_course(f"TIM {suffix[:4]}").name
		self.offering = make_offering(self.course, self.term, status="Published").name
		make_scheme(self.offering, [{"component": "Assignment", "weight_pct": 100}])
		self.assignment = make_assignment(
			self.offering, title=f"Essay {suffix[:4]}", points_possible=20
		).name

		email = f"imp.{suffix}@example.invalid"
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": "Import",
					"user_type": "System User",
					"send_welcome_email": 0,
					"roles": [{"role": "Student"}],
				}
			).insert(ignore_permissions=True)
		self.email = email
		self.student = make_student(f"Import {suffix}", user=email).name
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

	def _entry(self, status):
		return {
			"submission": "whatever",
			"assignment": self.assignment,
			"course_registration": self.registration,
			"status": status,
			"comments": "Their words",
		}

	# --- the mapping that matters -----------------------------------------

	def test_a_pass_becomes_full_marks(self):
		"""Pass/Fail carries no more information than that, so inventing a
		number between them would be inventing a mark."""
		name = lms_import._import_submission(self._entry("Pass"))

		doc = frappe.get_doc("Assignment Submission", name)
		self.assertEqual(doc.score, 20)
		self.assertTrue(doc.scored)

	def test_a_fail_becomes_zero_and_is_marked(self):
		name = lms_import._import_submission(self._entry("Fail"))

		doc = frappe.get_doc("Assignment Submission", name)
		self.assertEqual(doc.score, 0)
		self.assertTrue(doc.scored, "a fail is a mark somebody gave")

	def test_not_graded_stays_unscored_rather_than_becoming_zero(self):
		"""The distinction the whole grade pipeline rests on. A zero here would
		put a fail on a transcript for an essay nobody read."""
		name = lms_import._import_submission(self._entry("Not Graded"))

		doc = frappe.get_doc("Assignment Submission", name)
		self.assertFalse(doc.scored)
		self.assertEqual(doc.status, "Submitted")

	def test_an_unscored_import_does_not_move_the_grade(self):
		lms_import._import_submission(self._entry("Not Graded"))

		registration = frappe.get_doc("Course Registration", self.registration)
		self.assertFalse(registration.grade)

	def test_the_students_own_words_are_kept(self):
		name = lms_import._import_submission(self._entry("Pass"))
		self.assertEqual(
			frappe.db.get_value("Assignment Submission", name, "body"), "Their words"
		)

	# --- the survey --------------------------------------------------------

	def test_the_survey_writes_nothing(self):
		before = frappe.db.count("Assignment Submission")
		lms_import.survey()
		self.assertEqual(frappe.db.count("Assignment Submission"), before)

	def test_run_writes_nothing_without_apply(self):
		"""A migration you can start by accident is a migration you will."""
		before = frappe.db.count("Module Item Progress")
		lms_import.run()
		self.assertEqual(frappe.db.count("Module Item Progress"), before)

	def test_the_survey_says_why_a_row_cannot_be_placed(self):
		"""A count of what did not move is useless without the reason; the
		commonest one is a lesson nobody has put in a module yet."""
		result = lms_import.survey()

		self.assertIn("progress", result)
		self.assertIn("skipped", result["progress"])
		self.assertIsInstance(result["progress"]["skipped"], dict)

	def test_importing_twice_does_not_duplicate(self):
		lms_import._import_submission(self._entry("Pass"))
		before = frappe.db.count(
			"Assignment Submission",
			{"assignment": self.assignment, "course_registration": self.registration},
		)

		lms_import.run(apply=True)

		self.assertEqual(
			frappe.db.count(
				"Assignment Submission",
				{"assignment": self.assignment, "course_registration": self.registration},
			),
			before,
		)

	def test_nothing_is_written_back_to_the_lms(self):
		"""The app is vendored: the next `bench update` replaces it, so a write
		would be lost and a schema change would take our data with it."""
		import ast
		import inspect

		tree = ast.parse(inspect.getsource(lms_import))
		writes = []
		for node in ast.walk(tree):
			if not isinstance(node, ast.Call):
				continue
			target = ast.unparse(node.func)
			if target.endswith(("new_doc", "set_value", "delete_doc", "insert", "save")):
				writes.append(ast.unparse(node)[:90])

		for call in writes:
			for lms_doctype in ("LMS ", "Course Lesson", "Course Chapter"):
				self.assertNotIn(
					lms_doctype, call, f"this writes to the vendored LMS: {call}"
				)
