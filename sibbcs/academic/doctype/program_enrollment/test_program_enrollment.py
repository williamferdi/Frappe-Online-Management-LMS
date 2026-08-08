# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today


def make_student(full_name="Enrollment Test Student", **kw):
	defaults = {"doctype": "Student", "full_name": full_name, "status": "Active"}
	defaults.update(kw)
	return frappe.get_doc(defaults).insert(ignore_permissions=True)


def make_enrollment(student, program="MDIV", **kw):
	defaults = {
		"doctype": "Program Enrollment",
		"student": student,
		"program": program,
		"enrollment_date": today(),
		"current_level": "1",
		"status": "Active",
	}
	defaults.update(kw)
	return frappe.get_doc(defaults).insert(ignore_permissions=True)


class TestProgramEnrollment(FrappeTestCase):
	def test_named_student_dash_program(self):
		student = make_student(email="pe1@example.com")
		enrollment = make_enrollment(student.name)
		self.assertEqual(enrollment.name, f"{student.name}-MDIV")

	def test_duplicate_enrollment_rejected(self):
		student = make_student(email="pe2@example.com")
		make_enrollment(student.name)
		with self.assertRaises((frappe.ValidationError, frappe.DuplicateEntryError)):
			make_enrollment(student.name)

	def test_same_student_may_enroll_in_a_second_program(self):
		student = make_student(email="pe3@example.com")
		make_enrollment(student.name, program="MDIV")
		second = make_enrollment(student.name, program="MACS")
		self.assertEqual(second.program, "MACS")

	def test_negative_scholarship_rejected(self):
		student = make_student(email="pe4@example.com")
		with self.assertRaises(frappe.ValidationError):
			make_enrollment(student.name, scholarship_monthly_discount=-100)

	def test_used_cannot_exceed_cap(self):
		student = make_student(email="pe5@example.com")
		with self.assertRaises(frappe.ValidationError):
			make_enrollment(
				student.name, scholarship_total_cap=1000, scholarship_used_to_date=2000
			)

	def test_completion_must_follow_enrollment(self):
		student = make_student(email="pe6@example.com")
		with self.assertRaises(frappe.ValidationError):
			make_enrollment(student.name, expected_completion="2020-01-01")

	def test_remaining_scholarship(self):
		student = make_student(email="pe7@example.com")
		enrollment = make_enrollment(
			student.name, scholarship_total_cap=24000, scholarship_used_to_date=9000
		)
		self.assertEqual(enrollment.scholarship_remaining(), 15000)

	def test_discount_for_months_respects_the_cap(self):
		"""Architecture doc §5: the cap is what makes a flexible award safe."""
		student = make_student(email="pe8@example.com")
		enrollment = make_enrollment(
			student.name,
			scholarship_monthly_discount=800,
			scholarship_total_cap=24000,
			scholarship_used_to_date=23000,
		)
		# 2 months at 800 = 1600 wanted, only 1000 left
		self.assertEqual(enrollment.discount_for_months(2), 1000)

	def test_current_level_is_permlevel_gated(self):
		"""Only Registrar / Academic Coordinator may move a student's level."""
		meta = frappe.get_meta("Program Enrollment")
		self.assertEqual(meta.get_field("current_level").permlevel, 1)

		roles = {p.role for p in meta.permissions if p.permlevel == 1 and p.write}
		self.assertIn("Registrar", roles)
		self.assertIn("Academic Coordinator", roles)
		self.assertNotIn("Faculty", roles)


class TestStudent(FrappeTestCase):
	def test_student_id_series(self):
		student = make_student(email="st1@example.com")
		self.assertRegex(student.name, r"^SIB-\d{4}-\d{4}$")

	def test_duplicate_email_rejected(self):
		make_student(email="dupe@example.com")
		with self.assertRaises(frappe.ValidationError):
			make_student(full_name="Someone Else", email="dupe@example.com")

	def test_email_lower_cased(self):
		student = make_student(email="Upper.Case@Example.com")
		self.assertEqual(student.email, "upper.case@example.com")

	def test_future_dob_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			make_student(email="st2@example.com", dob=frappe.utils.add_days(today(), 1))

	def test_active_enrollment_lookup(self):
		student = make_student(email="st3@example.com")
		enrollment = make_enrollment(student.name)
		student.reload()
		self.assertEqual(student.active_enrollment().name, enrollment.name)
