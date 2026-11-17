# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""One test per gap the audit of 2026-09-11 found: a teacher reaching into a
course they do not teach.

Two teachers, one course each, and every test asks whether "mine" can reach
"theirs". The teacher's own course is tested alongside wherever it is not
already covered elsewhere, because a guard that also stops the legitimate case
is not a guard.

**Most of this file went with Phase 7.** It covered the scoping of pages,
files, rubrics, question banks, quizzes, assignments, overrides, groups,
discussions and module items -- all of which are now Campus LMS Lite's, and it
scopes its own. What is still this system's to narrow is the registrar's own
record: who a teacher may see, and the grade scheme a released mark lands in.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.academic.doctype.academic_term.test_academic_term import make_term
from sibbcs.academic.doctype.course.test_course import make_course
from sibbcs.academic.doctype.course_offering.test_course_offering import (
	make_instructor,
	make_offering,
)
from sibbcs.academic.doctype.program_enrollment.test_program_enrollment import (
	make_enrollment,
	make_student,
)
from sibbcs.academic.test_gradebook import make_scheme
from sibbcs.academic.test_permissions import make_user
from sibbcs.api import academic_api


class TestCourseScoping(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		suffix = frappe.generate_hash(length=6)
		cls.suffix = suffix
		cls.term = make_term(f"TST-CSC-{suffix}", status="Open").name

		cls.mine_user = make_user(f"csc.mine.{suffix}@example.invalid", ["Faculty"])
		cls.theirs_user = make_user(f"csc.theirs.{suffix}@example.invalid", ["Faculty"])
		cls.office_user = make_user(
			f"csc.office.{suffix}@example.invalid", ["Academic Coordinator"]
		)

		mine_instructor = make_instructor(f"CSC Mine {suffix}", user=cls.mine_user).name
		theirs_instructor = make_instructor(
			f"CSC Theirs {suffix}", user=cls.theirs_user
		).name

		cls.mine_course = make_course(f"TSC CM{suffix[:3]}").name
		cls.theirs_course = make_course(f"TSC CT{suffix[:3]}").name
		cls.mine_offering = make_offering(
			cls.mine_course, cls.term, instructor=mine_instructor, status="Published"
		).name
		cls.theirs_offering = make_offering(
			cls.theirs_course, cls.term, instructor=theirs_instructor, status="Published"
		).name

		# One student on each course, and one on both.
		cls.mine_student, _ = cls._student_on([cls.mine_offering])
		cls.theirs_student, theirs_registrations = cls._student_on([cls.theirs_offering])
		cls.both_student, _ = cls._student_on([cls.mine_offering, cls.theirs_offering])
		cls.theirs_registration = theirs_registrations[cls.theirs_offering]

		for offering in (cls.mine_offering, cls.theirs_offering):
			make_scheme(offering, [{"component": "Coursework", "weight_pct": 100}])

	@staticmethod
	def _student_on(offerings):
		student = make_student(f"CSC Student {frappe.generate_hash(length=6)}").name
		enrollment = make_enrollment(student).name
		registrations = {
			offering: frappe.get_doc(
				{
					"doctype": "Course Registration",
					"program_enrollment": enrollment,
					"course_offering": offering,
					"status": "Registered",
				}
			).insert(ignore_permissions=True).name
			for offering in offerings
		}
		return student, registrations

	def setUp(self):
		frappe.set_user("Administrator")
		# The scoping answers are memoised per request, and a whole test run is
		# one request. Start each test from what the database says.
		frappe.local.sibbcs_scope_cache = {}

	def tearDown(self):
		frappe.set_user("Administrator")

	# --- the endpoints that went with the teaching screens ----------------

	def test_the_teaching_endpoints_are_gone(self):
		"""Phase 7 removed them. A name coming back is a module somebody
		restored without restoring its scoping, which is how a teacher reaches
		another course's material again."""
		import importlib

		for module in (
			"sibbcs.api.marking",
			"sibbcs.api.coursework",
			"sibbcs.api.collaboration",
			"sibbcs.api.syllabus",
			"sibbcs.api.player",
			"sibbcs.api.content",
			"sibbcs.academic.modules",
			"sibbcs.academic.overrides",
		):
			with self.assertRaises(ModuleNotFoundError, msg=module):
				importlib.import_module(module)

	def test_the_course_api_keeps_only_the_grade_scheme(self):
		from sibbcs.api import course as course_api

		for name in ("save_scheme", "delete_scheme", "choices", "courses", "course"):
			self.assertTrue(hasattr(course_api, name), name)
		for name in ("save_assignment", "delete_assignment", "set_published", "content_space"):
			self.assertFalse(hasattr(course_api, name), name)

	# --- students ---------------------------------------------------------

	def test_a_teachers_roll_is_their_own_students(self):
		frappe.set_user(self.mine_user)
		names = [row["name"] for row in academic_api.students(limit=500)["rows"]]

		self.assertIn(self.mine_student, names)
		self.assertIn(self.both_student, names)
		self.assertNotIn(self.theirs_student, names)

	def test_a_teacher_cannot_open_a_student_they_do_not_teach(self):
		frappe.set_user(self.mine_user)
		with self.assertRaises(frappe.PermissionError):
			academic_api.student(self.theirs_student)

	def test_a_students_record_shows_a_teacher_only_their_own_courses(self):
		frappe.set_user(self.mine_user)
		offerings = [
			row["course_offering"]
			for row in academic_api.student(self.both_student)["registrations"]
		]

		self.assertEqual(offerings, [self.mine_offering])

	def test_the_office_still_sees_every_course_on_a_students_record(self):
		frappe.set_user(self.office_user)
		offerings = {
			row["course_offering"]
			for row in academic_api.student(self.both_student)["registrations"]
		}

		self.assertEqual(offerings, {self.mine_offering, self.theirs_offering})

	def test_the_demographics_describe_a_teachers_own_students(self):
		frappe.set_user(self.mine_user)
		self.assertEqual(academic_api.demographics()["total"], 2)

	def test_desk_shows_a_teacher_only_their_own_students(self):
		frappe.set_user(self.mine_user)
		names = frappe.get_list("Student", pluck="name", limit_page_length=0)

		self.assertIn(self.mine_student, names)
		self.assertNotIn(self.theirs_student, names)
		self.assertFalse(frappe.has_permission("Student", "read", doc=self.theirs_student))
		self.assertEqual(
			frappe.get_list(
				"Program Enrollment", filters={"student": self.theirs_student}, pluck="name"
			),
			[],
		)

	# --- the grade scheme, which is where a released LMS mark lands --------

	def test_a_teacher_sees_only_their_own_courses_scheme(self):
		frappe.set_user(self.mine_user)
		names = frappe.get_list("Course Grade Scheme", pluck="name", limit_page_length=0)

		self.assertIn(self.mine_offering, names)
		self.assertNotIn(self.theirs_offering, names)

	def test_a_teacher_cannot_write_another_courses_scheme(self):
		from sibbcs.api import course as course_api

		frappe.set_user(self.mine_user)
		with self.assertRaises(frappe.PermissionError):
			course_api.save_scheme(
				self.theirs_offering, [{"component": "Coursework", "weight_pct": 100}]
			)

	def test_a_teacher_still_writes_their_own(self):
		"""A guard that also stops the legitimate case is not a guard."""
		from sibbcs.api import course as course_api

		frappe.set_user(self.mine_user)
		saved = course_api.save_scheme(
			self.mine_offering, [{"component": "Coursework", "weight_pct": 100}]
		)
		self.assertTrue(saved)

	def test_the_office_is_not_narrowed(self):
		frappe.set_user(self.office_user)

		self.assertIn(
			self.theirs_student, frappe.get_list("Student", pluck="name", limit_page_length=0)
		)
		self.assertTrue(
			frappe.has_permission("Course Grade Scheme", "write", doc=self.theirs_offering)
		)
