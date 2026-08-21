# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

from unittest.mock import patch

import itertools

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.admissions import conversion, manuals
from sibbcs.admissions.checklist import blocked_reason, set_status, status_of

MANUAL = "Test Onboarding Manual"


def a_program():
	return frappe.db.get_value("Program", {}, "name")


_seq = itertools.count(1)


def make_application(**overrides):
	"""A fresh applicant each time.

	Student.validate_unique_email refuses a second Student on the same address,
	and records survive between tests in this suite (User inserts commit), so a
	shared address would make the second onboarding test fail on the first one's
	leftovers.
	"""
	values = {
		"doctype": "Admission Application",
		"full_name": "Onboard Candidate",
		"dob": "1993-03-03",
		"gender": "Male",
		"mobile": "9000000913",
		"email": f"onboard.candidate{next(_seq)}@example.com",
		"program": a_program(),
	}
	values.update(overrides)
	doc = frappe.get_doc(values)
	doc.insert(ignore_permissions=True)
	return doc


def ready_to_onboard(app, level=None, fee="Paid"):
	"""Walk an application through the steps that gate 13."""
	# Only this manual, so acknowledging it really does complete step 12 --
	# an active manual left behind by another test file would leave a second
	# row outstanding and the gate shut.
	for name in frappe.get_all("Reading Manual", pluck="name"):
		frappe.db.set_value("Reading Manual", name, "is_active", 0)

	if frappe.db.exists("Reading Manual", MANUAL):
		frappe.db.set_value("Reading Manual", MANUAL, "is_active", 1)
	else:
		frappe.get_doc(
			{
				"doctype": "Reading Manual",
				"manual_title": MANUAL,
				"version": "1",
				"is_active": 1,
				"content": "<p>Read me.</p>",
			}
		).insert(ignore_permissions=True)

	set_status(app, 7, "Link Sent")
	app.reload()
	set_status(app, 8, "Passed")
	app.reload()

	if fee == "Paid":
		app.db_set("admission_fee_paid", 1)
		app.reload()
	set_status(app, 10, fee)
	app.reload()
	set_status(app, 11, "Admitted")
	app.reload()

	with patch(
		"sibbcs.admissions.notifications.outgoing_configured", return_value=True
	), patch("frappe.sendmail"):
		manuals.send_manuals(app.name)
	app.reload()
	manuals.acknowledge(app.manual_acknowledgements[0].token, "Onboard Candidate", 1)
	app.reload()

	if level:
		app.db_set("onboard_level", level)
		app.reload()

	return app


class TestOnboarding(FrappeTestCase):
	# -- the gates --------------------------------------------------------

	def test_onboarding_is_blocked_before_the_admission_decision(self):
		app = make_application()
		self.assertIsNotNone(blocked_reason(app, 13))
		with self.assertRaises(frappe.ValidationError):
			conversion.onboard(app.name)

	def test_onboarding_is_blocked_while_a_manual_is_unread(self):
		app = make_application()
		set_status(app, 7, "Link Sent")
		app.reload()
		set_status(app, 8, "Passed")
		app.reload()
		app.db_set("admission_fee_paid", 1)
		app.reload()
		set_status(app, 10, "Paid")
		app.reload()
		set_status(app, 11, "Admitted")
		app.reload()

		self.assertIsNotNone(blocked_reason(app, 13))
		with self.assertRaises(frappe.ValidationError):
			conversion.onboard(app.name)

	def test_no_student_is_created_by_a_blocked_attempt(self):
		"""The gate is checked before the Student exists, not after."""
		app = make_application()
		try:
			conversion.onboard(app.name)
		except frappe.ValidationError:
			pass
		self.assertFalse(frappe.db.exists("Student", {"admission_application": app.name}))

	# -- the level --------------------------------------------------------

	def test_the_enrollment_is_created_at_the_chosen_level(self):
		app = ready_to_onboard(make_application(), level="3")
		report = conversion.onboard(app.name)

		enrollment = report["created"]["program_enrollment"]
		self.assertEqual(
			frappe.db.get_value("Program Enrollment", enrollment, "current_level"), "3"
		)
		self.assertEqual(report["level"], "3")

	def test_level_1_is_the_fallback_when_nobody_chose(self):
		app = ready_to_onboard(make_application())
		report = conversion.onboard(app.name)

		enrollment = report["created"]["program_enrollment"]
		self.assertEqual(
			frappe.db.get_value("Program Enrollment", enrollment, "current_level"), "1"
		)

	# -- a waived fee ------------------------------------------------------

	def test_a_waived_admission_fee_can_still_be_onboarded(self):
		"""A waiver is a decision, not a payment; the checkbox stays false."""
		app = ready_to_onboard(make_application(), fee="Waived")
		self.assertFalse(app.admission_fee_paid)

		report = conversion.onboard(app.name)
		self.assertTrue(report["created"]["student"])

	# -- the step ----------------------------------------------------------

	def test_onboarding_completes_step_13_and_the_overall_state(self):
		app = ready_to_onboard(make_application(), level="2")
		conversion.onboard(app.name)

		app.reload()
		self.assertEqual(status_of(app, 13), "Onboarded")
		self.assertEqual(app.workflow_state, "Onboarded")
		self.assertTrue(app.student)

	def test_onboarding_twice_makes_one_student(self):
		app = ready_to_onboard(make_application())
		first = conversion.onboard(app.name)
		second = conversion.onboard(app.name)

		self.assertTrue(second["already_converted"])
		self.assertEqual(first["created"]["student"], second["created"]["student"])
		self.assertEqual(
			frappe.db.count("Student", {"admission_application": app.name}), 1
		)

	def test_the_applicant_keeps_the_login_from_step_7(self):
		from sibbcs.admissions import lms_account

		app = ready_to_onboard(make_application())
		lms_account.ensure_user(app)

		report = conversion.onboard(app.name)
		self.assertEqual(report["created"]["user"], app.email)
		self.assertEqual(frappe.db.count("User", {"email": app.email}), 1)
