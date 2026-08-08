# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""The conversion point -- architecture doc §4."""

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.admissions.conversion import convert
from sibbcs.admissions.doctype.admission_application.test_admission_application import (
	all_documents_verified,
	make_application,
)


def ready_application(**kw):
	"""An application that has cleared every gate up to the fee."""
	kw.setdefault("documents", all_documents_verified())
	kw.setdefault("admission_fee_paid", 1)
	kw.setdefault("application_fee_paid", 1)
	return make_application(**kw)


class TestConversion(FrappeTestCase):
	def test_refuses_when_admission_fee_unpaid(self):
		app = make_application(admission_fee_paid=0)
		with self.assertRaises(frappe.ValidationError):
			convert(app.name)

	def test_creates_student(self):
		app = ready_application(email="convert1@example.com", full_name="Grace Kumar")
		report = convert(app.name)

		student = frappe.get_doc("Student", report["created"]["student"])
		self.assertEqual(student.full_name, "Grace Kumar")
		self.assertEqual(student.admission_application, app.name)
		self.assertEqual(student.status, "Active")

	def test_student_id_uses_sib_series(self):
		app = ready_application(email="convert2@example.com")
		report = convert(app.name)
		self.assertRegex(report["created"]["student"], r"^SIB-\d{4}-\d{4}$")

	def test_creates_user_with_student_role(self):
		app = ready_application(email="convert3@example.com")
		report = convert(app.name)

		self.assertEqual(report["created"]["user"], "convert3@example.com")
		user = frappe.get_doc("User", "convert3@example.com")
		self.assertIn("Student", [r.role for r in user.roles])

	def test_student_is_linked_to_its_user(self):
		app = ready_application(email="convert4@example.com")
		report = convert(app.name)
		student = frappe.get_doc("Student", report["created"]["student"])
		self.assertEqual(student.user, "convert4@example.com")

	def test_reuses_an_existing_user(self):
		"""Re-applicants and staff-turned-students already have a login."""
		email = "existing@example.com"
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": "Already Here",
					"user_type": "Website User",
					"send_welcome_email": 0,
				}
			).insert(ignore_permissions=True)

		app = ready_application(email=email)
		report = convert(app.name)
		self.assertEqual(report["created"]["user"], email)

	def test_two_students_may_share_a_phone_number(self):
		"""frappe's User.mobile_no is UNIQUE, but shared handsets are ordinary
		here -- a married couple, a family phone, a church office number. The
		second enrollment must still succeed."""
		shared = "9000000123"
		first = ready_application(email="shared1@example.com", mobile=shared)
		second = ready_application(email="shared2@example.com", mobile=shared)

		convert(first.name)
		report = convert(second.name)

		self.assertEqual(report["created"]["user"], "shared2@example.com")
		# both students keep the real number on their own record
		for name in (first.name, second.name):
			student = frappe.db.get_value(
				"Student", {"admission_application": name}, "mobile"
			)
			self.assertEqual(student, shared)

	def test_creates_program_enrollment_at_level_one(self):
		app = ready_application(email="convert5@example.com", program="MDIV")
		report = convert(app.name)

		enrollment = frappe.get_doc(
			"Program Enrollment", report["created"]["program_enrollment"]
		)
		self.assertEqual(enrollment.program, "MDIV")
		self.assertEqual(enrollment.current_level, "1")
		self.assertEqual(enrollment.status, "Active")

	def test_entry_level_does_not_override_level_one(self):
		"""entry_level on the application is advisory; enrollment starts at 1."""
		app = ready_application(email="convert6@example.com", entry_level="3")
		report = convert(app.name)
		enrollment = frappe.get_doc(
			"Program Enrollment", report["created"]["program_enrollment"]
		)
		self.assertEqual(enrollment.current_level, "1")

	def test_application_records_the_student(self):
		app = ready_application(email="convert7@example.com")
		report = convert(app.name)
		app.reload()
		self.assertEqual(app.student, report["created"]["student"])
		self.assertTrue(app.enrolled_on)

	def test_conversion_is_idempotent(self):
		app = ready_application(email="convert8@example.com")
		first = convert(app.name)
		second = convert(app.name)

		self.assertTrue(second["already_converted"])
		self.assertEqual(first["created"]["student"], second["created"]["student"])
		self.assertEqual(frappe.db.count("Student", {"admission_application": app.name}), 1)

	def test_later_phase_steps_are_reported_as_deferred(self):
		"""Never silently skip -- Phase 3/4/6 work must show up in the report."""
		app = ready_application(email="convert9@example.com", program="MDIV")
		report = convert(app.name)
		deferred = {d["step"] for d in report["deferred"]}

		# Course Registration (Phase 3) and Fee Invoice (Phase 4) do not exist yet
		self.assertIn("orientation", deferred)
		self.assertIn("ata_invoice", deferred)

	def test_ata_invoice_not_raised_for_non_mdiv(self):
		app = ready_application(email="convert10@example.com", program="MACS")
		report = convert(app.name)
		self.assertNotIn("ata_invoice", {d["step"] for d in report["deferred"]})


class TestConversionScholarship(FrappeTestCase):
	def _approved_scholarship(self, app, monthly, total):
		scholarship = frappe.get_doc(
			{
				"doctype": "Scholarship Request",
				"application": app.name,
				"program": app.program,
				"requested_amount": total,
				"approved_amount": total,
				"monthly_discount": monthly,
				"status": "Approved",
			}
		).insert(ignore_permissions=True)
		app.reload()
		return scholarship

	def test_approved_scholarship_lands_on_enrollment(self):
		app = ready_application(email="sch1@example.com")
		self._approved_scholarship(app, monthly=800, total=24000)

		report = convert(app.name)
		enrollment = frappe.get_doc(
			"Program Enrollment", report["created"]["program_enrollment"]
		)
		self.assertEqual(enrollment.scholarship_monthly_discount, 800)
		self.assertEqual(enrollment.scholarship_total_cap, 24000)
		self.assertEqual(enrollment.scholarship_used_to_date, 0)

	def test_unapproved_scholarship_is_ignored(self):
		app = ready_application(email="sch2@example.com")
		frappe.get_doc(
			{
				"doctype": "Scholarship Request",
				"application": app.name,
				"program": app.program,
				"requested_amount": 20000,
				"status": "Submitted",
			}
		).insert(ignore_permissions=True)
		app.reload()

		report = convert(app.name)
		enrollment = frappe.get_doc(
			"Program Enrollment", report["created"]["program_enrollment"]
		)
		self.assertEqual(enrollment.scholarship_monthly_discount, 0)

	def test_discount_is_clipped_to_the_cap(self):
		"""The cap is what stops a monthly discount running forever."""
		app = ready_application(email="sch3@example.com")
		self._approved_scholarship(app, monthly=800, total=2000)

		report = convert(app.name)
		enrollment = frappe.get_doc(
			"Program Enrollment", report["created"]["program_enrollment"]
		)
		# 3 months at 800 = 2400 wanted, but only 2000 remains
		self.assertEqual(enrollment.discount_for_months(3), 2000)
		self.assertEqual(enrollment.discount_for_months(2), 1600)
