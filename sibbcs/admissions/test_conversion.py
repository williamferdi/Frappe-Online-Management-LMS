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

	def test_steps_are_reported_never_silently_skipped(self):
		"""Every step must land in `created` or `deferred` with a reason."""
		app = ready_application(email="convert9@example.com", program="MDIV")
		report = convert(app.name)

		accounted = set(report["created"]) | {d["step"] for d in report["deferred"]}
		self.assertIn("student", accounted)
		self.assertIn("program_enrollment", accounted)
		# Mentor is Phase 6 and still absent
		self.assertIn("mentor", {d["step"] for d in report["deferred"]})
		for item in report["deferred"]:
			self.assertTrue(item["reason"], item["step"])

	def test_ata_invoice_raised_for_mdiv_now_that_finance_exists(self):
		"""The deferred step completes itself once Phase 4 lands."""
		app = ready_application(email="convert12@example.com", program="MDIV")
		report = convert(app.name)

		self.assertIn("ata_invoice", report["created"])
		invoice = frappe.get_doc("Fee Invoice", report["created"]["ata_invoice"])
		self.assertEqual(invoice.fee_type, "ATA Registration")
		self.assertEqual(invoice.net_amount, 2000)

	def test_ata_invoice_not_raised_for_non_mdiv(self):
		app = ready_application(email="convert10@example.com", program="MACS")
		report = convert(app.name)
		self.assertNotIn("ata_invoice", report["created"])


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


class TestTheLevelIsSettledAtConversion(FrappeTestCase):
	"""`onboard_level` decides the level once, and then stops deciding anything.

	On 21 Nov 2026 two live applications read Level 2 while the students they
	had created sat at Level 1. Both had been edited the day after conversion,
	and nothing on screen said the edit could not reach the student.
	"""

	def test_a_blank_onboard_level_lands_the_student_at_level_one(self):
		"""The reported cause: nobody had decided, so the fallback decided."""
		app = ready_application(email="level1@example.com", onboard_level="")
		report = convert(app.name)

		self.assertEqual(
			frappe.db.get_value(
				"Program Enrollment", report["created"]["program_enrollment"], "current_level"
			),
			"1",
		)

	def test_an_onboard_level_is_honoured_when_it_is_set_in_time(self):
		app = ready_application(email="level2@example.com", onboard_level="2")
		report = convert(app.name)

		self.assertEqual(
			frappe.db.get_value(
				"Program Enrollment", report["created"]["program_enrollment"], "current_level"
			),
			"2",
		)

	def test_changing_it_afterwards_is_refused_and_says_where_to_go(self):
		app = ready_application(email="level3@example.com", onboard_level="1")
		report = convert(app.name)

		doc = frappe.get_doc("Admission Application", app.name)
		doc.onboard_level = "2"
		with self.assertRaises(frappe.ValidationError) as caught:
			doc.save(ignore_permissions=True)

		message = str(caught.exception)
		self.assertIn("Level Promotion", message)
		self.assertIn(report["created"]["student"], message)

		# And the refusal left the enrolment exactly where it was.
		self.assertEqual(
			frappe.db.get_value(
				"Program Enrollment", report["created"]["program_enrollment"], "current_level"
			),
			"1",
		)

	def test_the_advisory_entry_level_is_still_free_to_edit(self):
		"""It records what was asked for, is never read by conversion, and so
		cannot mislead anybody about where a student is."""
		app = ready_application(email="level4@example.com", onboard_level="1")
		convert(app.name)

		doc = frappe.get_doc("Admission Application", app.name)
		doc.entry_level = "3"
		doc.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Admission Application", app.name, "entry_level"), "3")

	def test_before_conversion_the_level_is_still_the_registrar_s_to_set(self):
		app = ready_application(email="level5@example.com", onboard_level="1")

		doc = frappe.get_doc("Admission Application", app.name)
		doc.onboard_level = "3"
		doc.save(ignore_permissions=True)
		self.assertEqual(
			frappe.db.get_value("Admission Application", app.name, "onboard_level"), "3"
		)
