# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""Role permissions -- architecture doc §7.

These exist because of a real escalation. The builders passed only the flags
they meant to grant; frappe's DocPerm defaults filled the rest with 1, so
`read("Student")` came back with create=1. Students could create Courses,
Programs, Academic Terms, Course Offerings -- and Level Promotions, meaning a
student could promote themselves to Level 4 and unlock Level 4 courses.

Nothing in the earlier suites caught it: every rule engine test ran as
Administrator, who is allowed to do all of it.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.setup.permissions import FORBIDDEN_CREATE, MATRIX, apply_all, audit


def creators(doctype):
	meta = frappe.get_meta(doctype)
	return {p.role for p in meta.permissions if p.permlevel == 0 and p.create}


def writers(doctype, permlevel=0):
	meta = frappe.get_meta(doctype)
	return {p.role for p in meta.permissions if p.permlevel == permlevel and p.write}


class TestPermissionMatrix(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		apply_all()

	def test_audit_is_clean(self):
		self.assertEqual(audit(), [])

	def test_students_cannot_create_academic_masters(self):
		for doctype in ("Program", "Course", "Academic Term", "Course Offering", "Grade Scale"):
			self.assertNotIn("Student", creators(doctype), doctype)

	def test_students_cannot_promote_themselves(self):
		"""The worst case: self-service Level Promotion unlocks Level 4 courses."""
		self.assertNotIn("Student", creators("Level Promotion"))
		self.assertNotIn("Student", writers("Level Promotion"))

	def test_students_cannot_edit_their_own_level(self):
		self.assertNotIn("Student", writers("Program Enrollment", permlevel=1))

	def test_students_cannot_create_registrations_directly(self):
		"""Registration must go through portal.register so the rule engine runs."""
		self.assertNotIn("Student", creators("Course Registration"))

	def test_students_cannot_write_grades(self):
		self.assertNotIn("Student", writers("Course Registration", permlevel=1))

	def test_students_cannot_create_invoices_or_payments(self):
		for doctype in ("Fee Invoice", "Payment Entry"):
			self.assertNotIn("Student", creators(doctype), doctype)

	def test_faculty_cannot_create_students_or_enrollments(self):
		for doctype in ("Student", "Program Enrollment", "Level Promotion"):
			self.assertNotIn("Faculty", creators(doctype), doctype)

	def test_facilitators_cannot_write_grades(self):
		"""§7: facilitators handle forums and attendance, never final grades."""
		self.assertNotIn("Facilitator", writers("Course Registration", permlevel=1))

	def test_faculty_can_write_grades(self):
		self.assertIn("Faculty", writers("Course Registration", permlevel=1))

	def test_only_registrar_and_coordinator_move_levels(self):
		allowed = writers("Program Enrollment", permlevel=1)
		self.assertIn("Registrar", allowed)
		self.assertIn("Academic Coordinator", allowed)
		self.assertNotIn("Faculty", allowed)
		self.assertNotIn("Admissions Officer", allowed)

	def test_admissions_officer_has_no_grade_access(self):
		"""§7: Admissions Officer has no access to grades or finance."""
		self.assertNotIn("Admissions Officer", writers("Course Registration", permlevel=1))
		for doctype in ("Fee Invoice", "Payment Entry"):
			self.assertNotIn("Admissions Officer", creators(doctype), doctype)

	def test_accounts_has_no_grade_access(self):
		self.assertNotIn("Accounts", writers("Course Registration", permlevel=1))

	def test_coordinator_owns_the_catalog(self):
		for doctype in ("Course", "Academic Term", "Course Offering", "Instructor"):
			self.assertIn("Academic Coordinator", creators(doctype), doctype)

	def test_every_matrix_doctype_exists(self):
		for doctype in MATRIX:
			self.assertTrue(frappe.db.exists("DocType", doctype), doctype)

	def test_read_only_roles_really_are_read_only(self):
		"""A `read` row must not carry create, write or delete."""
		for doctype, forbidden in FORBIDDEN_CREATE.items():
			meta = frappe.get_meta(doctype)
			for perm in meta.permissions:
				if perm.permlevel or perm.role not in forbidden:
					continue
				self.assertFalse(perm.create, f"{doctype}/{perm.role} create")
				self.assertFalse(perm.delete, f"{doctype}/{perm.role} delete")
