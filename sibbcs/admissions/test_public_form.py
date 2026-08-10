# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""The public application form.

This is the only endpoint an anonymous stranger can write to, so most of these
tests are about what it refuses.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.admissions.public_form import APPLICANT_FIELDS, submit_application


def payload(**overrides):
	values = {
		"full_name": "Public Applicant",
		"email": "public1@example.invalid",
		"mobile": "9000001111",
		"program": "MDIV",
		"dob": "1994-03-02",
		"church_name": "Grace Baptist",
		"referee1_name": "Pastor A",
		"referee1_email": "ref.a@example.invalid",
		"referee1_type": "Pastor-Mentor",
		"referee2_name": "Prof B",
		"referee2_email": "ref.b@example.invalid",
		"referee2_type": "Professor-Employer",
		"mentor_name": "Mentor M",
		"mentor_email": "mentor.m@example.invalid",
	}
	values.update(overrides)
	return values


class TestPublicApplication(FrappeTestCase):
	def test_creates_a_draft_application(self):
		result = submit_application(**payload())
		doc = frappe.get_doc("Admission Application", result["application"])
		self.assertEqual(doc.full_name, "Public Applicant")
		self.assertEqual(doc.program, "MDIV")

	def test_email_is_lower_cased(self):
		result = submit_application(**payload(email="MiXeD@Example.Invalid"))
		doc = frappe.get_doc("Admission Application", result["application"])
		self.assertEqual(doc.email, "mixed@example.invalid")

	def test_referees_and_mentor_are_attached_with_tokens(self):
		result = submit_application(**payload(email="public2@example.invalid"))
		doc = frappe.get_doc("Admission Application", result["application"])

		self.assertEqual(len(doc.reference_requests), 2)
		self.assertEqual(len(doc.mentor_consents), 1)
		for row in doc.reference_requests:
			self.assertTrue(row.token)
		self.assertTrue(doc.mentor_consents[0].token)

	# --- what it must refuse -------------------------------------------

	def test_gates_cannot_be_set_from_the_form(self):
		"""The whole point of the whitelist: no self-service admission."""
		result = submit_application(
			**payload(
				email="public3@example.invalid",
				application_fee_paid=1,
				admission_fee_paid=1,
				docs_verified=1,
				qualifying_exam_score=99,
				interview_outcome="Recommend",
				workflow_state="Enrolled",
				student="SIB-2026-0001",
			)
		)
		doc = frappe.get_doc("Admission Application", result["application"])

		self.assertFalse(doc.application_fee_paid)
		self.assertFalse(doc.admission_fee_paid)
		self.assertFalse(doc.docs_verified)
		self.assertFalse(doc.qualifying_exam_score)
		self.assertFalse(doc.interview_outcome)
		self.assertFalse(doc.student)

	def test_whitelist_excludes_every_gate(self):
		for field in (
			"application_fee_paid", "admission_fee_paid", "docs_verified",
			"qualifying_exam_score", "interview_outcome", "offer_sent_on",
			"student", "workflow_state", "scholarship_request", "notes",
		):
			self.assertNotIn(field, APPLICANT_FIELDS, field)

	def test_honeypot_blocks_submission(self):
		with self.assertRaises(frappe.ValidationError):
			submit_application(**payload(email="bot@example.invalid", website="http://spam"))

	def test_missing_required_fields_refused(self):
		with self.assertRaises(frappe.ValidationError):
			submit_application(**payload(email="public4@example.invalid", full_name=""))

	def test_unknown_program_refused(self):
		with self.assertRaises(frappe.ValidationError):
			submit_application(**payload(email="public5@example.invalid", program="NOT-A-PROGRAM"))

	def test_invalid_email_refused(self):
		with self.assertRaises(Exception):
			submit_application(**payload(email="not-an-email"))

	def test_future_dob_refused(self):
		with self.assertRaises(frappe.ValidationError):
			submit_application(
				**payload(email="public6@example.invalid", dob=frappe.utils.add_days(frappe.utils.nowdate(), 5))
			)

	def test_applicant_cannot_be_their_own_referee(self):
		with self.assertRaises(frappe.ValidationError):
			submit_application(
				**payload(email="self@example.invalid", referee1_email="self@example.invalid")
			)

	def test_duplicate_referees_refused(self):
		with self.assertRaises(frappe.ValidationError):
			submit_application(
				**payload(
					email="public7@example.invalid",
					referee1_email="same@example.invalid",
					referee2_email="same@example.invalid",
				)
			)

	def test_second_open_application_refused(self):
		submit_application(**payload(email="twice@example.invalid"))
		with self.assertRaises(frappe.ValidationError):
			submit_application(**payload(email="twice@example.invalid"))

	def test_reapplying_allowed_after_rejection(self):
		"""A rejected candidate may apply again in a later intake."""
		result = submit_application(**payload(email="again@example.invalid"))
		frappe.db.set_value(
			"Admission Application", result["application"], "workflow_state", "Rejected"
		)
		second = submit_application(**payload(email="again@example.invalid"))
		self.assertNotEqual(second["application"], result["application"])

	def test_no_internal_message_leaks_to_the_applicant(self):
		"""With no outgoing mail account, frappe.sendmail pushes
		"Please setup default outgoing Email Account…" onto the message log,
		which then rides back to the anonymous applicant in the API response.
		"""
		frappe.clear_messages()
		submit_application(**payload(email="quiet@example.invalid"))

		leaked = " ".join(str(m) for m in (frappe.get_message_log() or []))
		self.assertNotIn("Email Account", leaked)
		self.assertNotIn("default outgoing", leaked.lower())

	def test_long_values_are_capped(self):
		result = submit_application(
			**payload(email="public8@example.invalid", full_name="x" * 400)
		)
		doc = frappe.get_doc("Admission Application", result["application"])
		self.assertLessEqual(len(doc.full_name), 140)
