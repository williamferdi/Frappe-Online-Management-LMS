# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""One test per rule about who may see whose marks.

The three ways into a Course Registration are tested separately on purpose,
because closing one has never closed the others: a filtered list still hands
the record over by name, and both are irrelevant to a /staff endpoint reading
through `frappe.get_all`.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.academic import permissions
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
from sibbcs.api import academic_api


def make_user(email, roles, name="Scope Test"):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": name,
				"user_type": "System User",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
	user = frappe.get_doc("User", email)
	user.set("roles", [])
	for role in roles:
		user.append("roles", {"role": role})
	user.save(ignore_permissions=True)
	return email


class TestAcademicScoping(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		suffix = frappe.generate_hash(length=6)
		cls.term = make_term(f"TST-SCOPE-{suffix}", status="Open").name

		# Two teachers, one course each. The point of every test below is that
		# neither can reach into the other's.
		cls.mine_user = make_user(f"mine.{suffix}@example.invalid", ["Faculty"])
		cls.theirs_user = make_user(f"theirs.{suffix}@example.invalid", ["Faculty"])

		cls.mine_instructor = make_instructor(
			f"Scope Mine {suffix}", user=cls.mine_user
		).name
		cls.theirs_instructor = make_instructor(
			f"Scope Theirs {suffix}", user=cls.theirs_user
		).name

		cls.mine_offering = make_offering(
			make_course(f"TSC M{suffix[:3]}").name, cls.term, instructor=cls.mine_instructor, status="Published"
		).name
		cls.theirs_offering = make_offering(
			make_course(f"TSC T{suffix[:3]}").name, cls.term, instructor=cls.theirs_instructor, status="Published"
		).name

		# A student on each offering.
		cls.student = make_student(f"Scope Student {suffix}").name
		cls.enrollment = make_enrollment(cls.student).name
		cls.mine_registration = cls._register(cls.enrollment, cls.mine_offering)
		cls.theirs_registration = cls._register(cls.enrollment, cls.theirs_offering)

	@staticmethod
	def _register(enrollment, offering):
		return frappe.get_doc(
			{
				"doctype": "Course Registration",
				"program_enrollment": enrollment,
				"course_offering": offering,
				"status": "Registered",
			}
		).insert(ignore_permissions=True).name

	def tearDown(self):
		frappe.set_user("Administrator")

	# --- the helpers ------------------------------------------------------

	def test_a_teacher_is_found_through_their_instructor_record(self):
		self.assertEqual(
			permissions.offerings_for(self.mine_user), [self.mine_offering]
		)

	def test_a_teacher_with_no_instructor_record_teaches_nothing(self):
		"""Fails closed. The tempting fallback -- show everything when no
		Instructor row names the user -- makes a missing record a master key."""
		stranger = make_user("stranger.scope@example.invalid", ["Faculty"])

		self.assertEqual(permissions.offerings_for(stranger), [])
		self.assertEqual(permissions.offering_scope(stranger), [])

	def test_the_registrar_is_not_scoped_at_all(self):
		"""None and [] are different answers: the whole register, versus a
		teacher who has been given no course."""
		registrar = make_user("registrar.scope@example.invalid", ["Registrar"])

		self.assertIsNone(permissions.offering_scope(registrar))

	# --- the list ---------------------------------------------------------

	def test_a_list_shows_only_the_teachers_own_registrations(self):
		frappe.set_user(self.mine_user)

		names = frappe.get_list("Course Registration", pluck="name")

		self.assertIn(self.mine_registration, names)
		self.assertNotIn(self.theirs_registration, names)

	def test_a_student_sees_only_their_own_registrations(self):
		other = make_student("Scope Other Student")
		other_enrollment = make_enrollment(other.name, program="MDIV")
		other_registration = self._register(other_enrollment.name, self.mine_offering)

		email = make_user("scope.student@example.invalid", ["Student"])
		frappe.db.set_value("Student", self.student, "user", email)

		frappe.set_user(email)
		names = frappe.get_list("Course Registration", pluck="name")

		self.assertIn(self.mine_registration, names)
		self.assertNotIn(other_registration, names)

	# --- the same record by name -----------------------------------------

	def test_a_filtered_list_does_not_make_the_url_safe(self):
		"""The query condition hides a row from a list and does nothing at all
		about `/api/resource/Course Registration/<name>`."""
		frappe.set_user(self.mine_user)

		self.assertTrue(
			frappe.has_permission(
				"Course Registration", "read", doc=self.mine_registration
			)
		)
		self.assertFalse(
			frappe.has_permission(
				"Course Registration", "read", doc=self.theirs_registration
			)
		)

	def test_a_teacher_cannot_write_marks_on_another_teachers_course(self):
		frappe.set_user(self.mine_user)

		self.assertFalse(
			frappe.has_permission(
				"Course Registration", "write", doc=self.theirs_registration
			)
		)

	def test_save_grades_refuses_another_teachers_registration(self):
		"""`save_grades` calls check_permission and saves without
		ignore_permissions, so the hook is what that check consults."""
		frappe.set_user(self.mine_user)

		with self.assertRaises(frappe.PermissionError):
			academic_api.save_grades(
				self.theirs_registration,
				[{"component": "Assignment", "weight_pct": 100, "max_marks": 100,
				  "obtained_marks": 99}],
			)

	def test_save_grades_still_works_on_the_teachers_own_course(self):
		"""A guard that also stops the legitimate case is not a guard."""
		frappe.set_user(self.mine_user)

		result = academic_api.save_grades(
			self.mine_registration,
			[{"component": "Assignment", "weight_pct": 100, "max_marks": 100,
			  "obtained_marks": 80}],
		)

		self.assertEqual(result["final_marks"], 80)

	# --- the /staff API ---------------------------------------------------

	def test_the_roster_refuses_an_offering_the_teacher_does_not_teach(self):
		"""`roster` reads with frappe.get_all, which bypasses permissions
		entirely; without its own guard the DocType hooks never see it."""
		frappe.set_user(self.mine_user)

		with self.assertRaises(frappe.PermissionError):
			academic_api.roster(self.theirs_offering)

	def test_the_roster_still_answers_for_the_teachers_own_offering(self):
		frappe.set_user(self.mine_user)

		result = academic_api.roster(self.mine_offering)

		self.assertEqual(result["offering"]["name"], self.mine_offering)

	def test_the_offering_list_is_narrowed_to_what_the_teacher_teaches(self):
		frappe.set_user(self.mine_user)

		# This class's own term. `offerings()` pages at 200 rows ordered by
		# term, and a test site carries every term every earlier run made --
		# without this the answer depends on how much rubbish is lying about.
		names = [row["name"] for row in academic_api.offerings(term=self.term)["rows"]]

		self.assertIn(self.mine_offering, names)
		self.assertNotIn(self.theirs_offering, names)

	def test_the_registrar_still_sees_every_offering(self):
		registrar = make_user("registrar2.scope@example.invalid", ["Registrar"])
		frappe.set_user(registrar)

		names = [row["name"] for row in academic_api.offerings(term=self.term)["rows"]]

		self.assertIn(self.mine_offering, names)
		self.assertIn(self.theirs_offering, names)

	# --- the student directory -------------------------------------------

	def test_a_student_cannot_read_the_whole_student_directory(self):
		email = make_user("directory.scope@example.invalid", ["Student"])
		mine = make_student("Scope Directory Mine")
		theirs = make_student("Scope Directory Theirs")
		frappe.db.set_value("Student", mine.name, "user", email)

		frappe.set_user(email)
		names = frappe.get_list("Student", pluck="name")

		self.assertIn(mine.name, names)
		self.assertNotIn(theirs.name, names)

	def test_a_teacher_may_still_look_up_their_own_students(self):
		"""This student is on the teacher's course, which since 2026-09-11 is
		exactly what a teacher's roll is: their own students."""
		frappe.set_user(self.mine_user)

		self.assertIn(self.student, frappe.get_list("Student", pluck="name"))

	def test_a_teacher_cannot_look_up_a_student_they_do_not_teach(self):
		"""Once left open -- "looking a student up is teaching work" -- until
		the college decided a teacher holds no personal details for a student
		they never teach."""
		stranger = make_student(f"Scope Stranger {frappe.generate_hash(length=5)}").name
		make_enrollment(stranger)

		frappe.set_user(self.mine_user)

		self.assertNotIn(stranger, frappe.get_list("Student", pluck="name"))
		self.assertFalse(frappe.has_permission("Student", "read", doc=stranger))

	def test_a_teacher_with_no_course_gets_an_empty_list_not_an_error(self):
		"""The live configuration today: every Instructor record has a null
		`user`, so every Faculty user scopes to []. That becomes
		`filters["name"] = ("in", [])`, and an empty IN list is a SQL syntax
		error in the hands of the wrong query builder. It must return nothing
		rather than break the offerings screen."""
		stranger = make_user("nocourse.scope@example.invalid", ["Faculty"])
		frappe.set_user(stranger)

		result = academic_api.offerings()

		self.assertEqual(result["rows"], [])

	def test_a_teacher_with_no_course_sees_no_registrations_either(self):
		"""The same empty scope, through the query condition rather than the
		endpoint."""
		stranger = make_user("nocourse2.scope@example.invalid", ["Faculty"])
		frappe.set_user(stranger)

		self.assertEqual(frappe.get_list("Course Registration", pluck="name"), [])
