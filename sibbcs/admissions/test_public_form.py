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

	# --- the payment gate ----------------------------------------------

	def test_application_is_not_placed_until_the_fee_is_paid(self):
		"""The college's rule: fee first, then the application counts."""
		result = submit_application(**payload(email="gate1@example.invalid"))
		doc = frappe.get_doc("Admission Application", result["application"])

		self.assertFalse(doc.application_fee_paid)
		self.assertIn((doc.workflow_state or "Draft"), ("Draft", None, ""))
		self.assertTrue(result["payment_pending"])

	def test_application_fee_invoice_is_raised(self):
		from sibbcs.finance.fees import application_fee_invoice

		result = submit_application(**payload(email="gate2@example.invalid"))
		invoice = application_fee_invoice(result["application"])

		self.assertIsNotNone(invoice)
		self.assertEqual(invoice.net_amount, 350)
		self.assertEqual(invoice.status, "Unpaid")
		# no Student exists yet -- the invoice belongs to the application
		self.assertFalse(invoice.student)
		self.assertEqual(invoice.admission_application, result["application"])

	def test_fee_invoice_is_not_raised_twice(self):
		from sibbcs.finance.fees import raise_application_fee

		result = submit_application(**payload(email="gate3@example.invalid"))
		raise_application_fee(result["application"])
		self.assertEqual(
			frappe.db.count(
				"Fee Invoice", {"admission_application": result["application"]}
			),
			1,
		)

	def test_paying_the_fee_places_the_application(self):
		from sibbcs.finance.fees import mark_application_fee_paid

		result = submit_application(**payload(email="gate4@example.invalid"))
		state = mark_application_fee_paid(result["application"])

		doc = frappe.get_doc("Admission Application", result["application"])
		self.assertTrue(doc.application_fee_paid)
		self.assertEqual(state, "In Review")
		self.assertEqual(doc.workflow_state, "In Review")

	def test_marking_paid_twice_is_harmless(self):
		"""Razorpay retries webhooks."""
		from sibbcs.finance.fees import mark_application_fee_paid

		result = submit_application(**payload(email="gate5@example.invalid"))
		mark_application_fee_paid(result["application"])
		state = mark_application_fee_paid(result["application"])
		self.assertEqual(state, "In Review")

	def test_payment_status_reports_the_gate(self):
		from sibbcs.admissions.public_form import payment_status

		result = submit_application(**payload(email="gate6@example.invalid"))
		before = payment_status(result["application"])
		self.assertTrue(before["found"])
		self.assertFalse(before["paid"])
		self.assertEqual(before["amount"], 350)

	def test_payment_status_for_unknown_application(self):
		from sibbcs.admissions.public_form import payment_status

		self.assertFalse(payment_status("APP-DOES-NOT-EXIST")["found"])

	def test_saved_even_when_the_gateway_is_unavailable(self):
		"""A gateway problem must not lose a filled-in application."""
		result = submit_application(**payload(email="gate7@example.invalid"))
		self.assertTrue(frappe.db.exists("Admission Application", result["application"]))
		# no keys configured in tests, so no link -- but the record survives
		self.assertIsNone(result["payment_url"])
		self.assertEqual(result["payment_error"], "gateway_not_configured")

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


class TestRequestDispatch(FrappeTestCase):
	"""Referee and mentor requests must actually be sent, to a usable link."""

	def test_token_links_are_externally_reachable(self):
		"""frappe.utils.get_url() appends the dev port outside production mode,
		which would have made every referee link unopenable."""
		from sibbcs.admissions.doctype.admission_application.admission_application import (
			token_url,
		)

		link = token_url("reference", "SAMPLE")
		self.assertNotIn(":8000", link)
		self.assertTrue(link.startswith("http"))
		self.assertIn("/reference?token=SAMPLE", link)

	def test_dispatch_is_skipped_and_reported_without_a_mail_account(self):
		"""Never raise at whoever triggered the save -- report it instead."""
		from sibbcs.admissions.notifications import dispatch_requests

		result = submit_application(**payload(email="disp1@example.invalid"))
		report = dispatch_requests(result["application"])

		self.assertEqual(report["referees"], [])
		self.assertIn("no outgoing email account", report["skipped"])

	def test_draft_applications_are_not_dispatched(self):
		"""An abandoned, unpaid application must not email its referees."""
		from sibbcs.admissions.notifications import dispatch_on_placement

		result = submit_application(**payload(email="disp2@example.invalid"))
		doc = frappe.get_doc("Admission Application", result["application"])
		self.assertEqual(doc.workflow_state or "Draft", "Draft")
		# Draft short-circuits before any send is attempted
		self.assertIsNone(dispatch_on_placement(doc))

	def test_requests_are_dispatched_once_the_application_is_placed(self):
		"""With mail configured, placing the application sends the requests."""
		from unittest.mock import patch

		from sibbcs.admissions import notifications
		from sibbcs.finance.fees import mark_application_fee_paid

		result = submit_application(**payload(email="disp3@example.invalid"))

		sent = []
		with patch.object(notifications, "outgoing_configured", return_value=True), patch.object(
			frappe, "sendmail", side_effect=lambda **kw: sent.append(kw["recipients"][0])
		):
			mark_application_fee_paid(result["application"])

		# two referees and one mentor from the standard payload
		self.assertEqual(len(sent), 3)

		doc = frappe.get_doc("Admission Application", result["application"])
		for row in doc.reference_requests:
			self.assertTrue(row.sent_on, "referee row was never stamped as sent")
		self.assertTrue(doc.mentor_consents[0].sent_on)

	def test_dispatch_does_not_resend(self):
		from unittest.mock import patch

		from sibbcs.admissions import notifications

		result = submit_application(**payload(email="disp4@example.invalid"))
		frappe.db.set_value(
			"Admission Application", result["application"], "workflow_state", "In Review"
		)

		sent = []
		with patch.object(notifications, "outgoing_configured", return_value=True), patch.object(
			frappe, "sendmail", side_effect=lambda **kw: sent.append(kw["recipients"][0])
		):
			notifications.dispatch_requests(result["application"])
			first = len(sent)
			notifications.dispatch_requests(result["application"])

		self.assertEqual(len(sent), first, "requests were sent twice")
