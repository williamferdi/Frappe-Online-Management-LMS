# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.admissions.doctype.admission_application.test_admission_application import (
	make_application,
)


def make_scholarship(**kw):
	defaults = {
		"doctype": "Scholarship Request",
		"program": "MDIV",
		"requested_amount": 24000,
		"justification": "Bi-vocational pastor supporting a family.",
		"status": "Draft",
	}
	defaults.update(kw)
	return frappe.get_doc(defaults).insert(ignore_permissions=True)


class TestScholarshipRequest(FrappeTestCase):
	def test_needs_an_application_or_a_student(self):
		with self.assertRaises(frappe.ValidationError):
			make_scholarship()

	def test_program_defaults_from_the_application(self):
		app = make_application(email="sr1@example.com", program="MACS")
		scholarship = frappe.get_doc(
			{
				"doctype": "Scholarship Request",
				"application": app.name,
				"requested_amount": 1000,
				"status": "Draft",
			}
		).insert(ignore_permissions=True)
		self.assertEqual(scholarship.program, "MACS")

	def test_negative_amount_rejected(self):
		app = make_application(email="sr2@example.com")
		with self.assertRaises(frappe.ValidationError):
			make_scholarship(application=app.name, requested_amount=-1)

	def test_approval_requires_an_approved_total(self):
		app = make_application(email="sr3@example.com")
		with self.assertRaises(frappe.ValidationError):
			make_scholarship(application=app.name, status="Approved", monthly_discount=800)

	def test_approval_requires_a_monthly_discount(self):
		app = make_application(email="sr4@example.com")
		with self.assertRaises(frappe.ValidationError):
			make_scholarship(application=app.name, status="Approved", approved_amount=24000)

	def test_monthly_discount_cannot_exceed_the_total(self):
		app = make_application(email="sr5@example.com")
		with self.assertRaises(frappe.ValidationError):
			make_scholarship(
				application=app.name,
				status="Approved",
				approved_amount=1000,
				monthly_discount=5000,
			)

	def test_approval_is_stamped(self):
		app = make_application(email="sr6@example.com")
		scholarship = make_scholarship(
			application=app.name,
			status="Approved",
			approved_amount=24000,
			monthly_discount=800,
		)
		self.assertTrue(scholarship.approved_by)
		self.assertTrue(scholarship.approved_on)

	def test_stamp_is_cleared_if_approval_is_withdrawn(self):
		app = make_application(email="sr7@example.com")
		scholarship = make_scholarship(
			application=app.name,
			status="Approved",
			approved_amount=24000,
			monthly_discount=800,
		)
		scholarship.status = "Rejected"
		scholarship.save(ignore_permissions=True)
		self.assertIsNone(scholarship.approved_by)

	def test_request_links_itself_back_to_the_application(self):
		app = make_application(email="sr8@example.com")
		scholarship = make_scholarship(application=app.name)
		app.reload()
		self.assertEqual(app.scholarship_request, scholarship.name)
