# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

import base64
import itertools
import zlib
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.admissions import scholarship
from sibbcs.admissions.checklist import NO, status_of
from sibbcs.admissions.tokens import TokenError

_seq = itertools.count(1)


def png_data_url():
	"""A real one-pixel PNG, so the magic-byte check is exercised honestly."""

	def chunk(kind, payload):
		body = kind + payload
		return (
			len(payload).to_bytes(4, "big")
			+ body
			+ (zlib.crc32(body) & 0xFFFFFFFF).to_bytes(4, "big")
		)

	raw = (
		b"\x89PNG\r\n\x1a\n"
		+ chunk(b"IHDR", (1).to_bytes(4, "big") + (1).to_bytes(4, "big") + bytes([8, 0, 0, 0, 0]))
		+ chunk(b"IDAT", zlib.compress(b"\x00\x00"))
		+ chunk(b"IEND", b"")
	)
	return "data:image/png;base64," + base64.b64encode(raw).decode()


def make_application(program="MDIV", **overrides):
	values = {
		"doctype": "Admission Application",
		"full_name": "Scholarship Candidate",
		"dob": "1990-01-01",
		"gender": "Female",
		"mobile": "9000000916",
		"email": f"scholar{next(_seq)}@example.com",
		"program": program if frappe.db.exists("Program", program) else frappe.db.get_value("Program", {}, "name"),
	}
	values.update(overrides)
	doc = frappe.get_doc(values)
	doc.insert(ignore_permissions=True)
	return doc


class TestScholarship(FrappeTestCase):
	def setUp(self):
		for program, cap in (("MDIV", 24000), ("MACS", 16000), ("GDCS", 8000)):
			if frappe.db.exists("Program", program):
				frappe.db.set_value(
					"Program", program, "scholarship_max", cap, update_modified=False
				)

	# -- the caps ---------------------------------------------------------

	def test_the_cap_comes_from_the_program_not_from_code(self):
		if not frappe.db.exists("Program", "MDIV"):
			self.skipTest("MDIV is not in the catalog")

		self.assertEqual(scholarship.program_cap("MDIV"), 24000)
		frappe.db.set_value("Program", "MDIV", "scholarship_max", 30000, update_modified=False)
		self.assertEqual(scholarship.program_cap("MDIV"), 30000)

	def test_an_undeclared_cap_is_zero(self):
		self.assertEqual(scholarship.program_cap(None), 0)

	def test_the_intro_quotes_the_cap_for_this_program(self):
		if not frappe.db.exists("Program", "GDCS"):
			self.skipTest("GDCS is not in the catalog")

		text = scholarship.intro("GDCS")
		self.assertEqual(text["program_cap"], 8000)
		self.assertIn("financial need", text["body"])

	# -- word counting -----------------------------------------------------

	def test_words_are_counted_by_whitespace_not_characters(self):
		self.assertEqual(scholarship.word_count("  one   two\nthree  "), 3)
		self.assertEqual(scholarship.word_count(""), 0)
		self.assertEqual(scholarship.word_count(None), 0)

	# -- the link -----------------------------------------------------------

	def _send(self, app):
		with patch(
			"sibbcs.admissions.notifications.outgoing_configured", return_value=True
		), patch("frappe.sendmail") as sendmail:
			report = scholarship.send_form(app.name)
		return report, sendmail

	def test_sending_issues_a_token_and_stores_the_link(self):
		app = make_application()
		report, sendmail = self._send(app)

		self.assertEqual(report["emailed"], app.email)
		self.assertTrue(sendmail.called)

		app.reload()
		self.assertTrue(app.scholarship_token)
		self.assertIn("/scholarship?token=", app.scholarship_form_url)
		self.assertNotIn(":8000", app.scholarship_form_url)
		self.assertTrue(app.scholarship_form_sent_on)

	def test_the_step_leaves_not_applicable_once_the_form_goes_out(self):
		app = make_application()
		self.assertEqual(status_of(app, NO["scholarship"]), "Not Applicable")

		self._send(app)
		app.reload()
		self.assertEqual(status_of(app, NO["scholarship"]), "Form Sent")

	def test_resending_keeps_the_same_token(self):
		app = make_application()
		self._send(app)
		app.reload()
		first = app.scholarship_token

		self._send(app)
		app.reload()
		self.assertEqual(app.scholarship_token, first)

	# -- resolving ----------------------------------------------------------

	def test_a_short_or_missing_token_is_refused(self):
		for bad in (None, "", "abc", 12345):
			with self.assertRaises(TokenError):
				scholarship.resolve(bad)

	def test_an_unknown_token_is_refused(self):
		with self.assertRaises(TokenError):
			scholarship.resolve("k" * 40)

	# -- submitting ----------------------------------------------------------

	def _submit(self, app, statement="We have no income beyond my ministry stipend."):
		app.reload()
		return scholarship.submit(app.scholarship_token, statement, png_data_url())

	def test_submitting_creates_a_linked_request_with_the_signature(self):
		app = make_application()
		self._send(app)
		result = self._submit(app)

		request = frappe.get_doc("Scholarship Request", result["request"])
		self.assertEqual(request.application, app.name)
		self.assertEqual(request.program, app.program)
		self.assertEqual(request.status, "Submitted")
		self.assertIn("no income", request.justification)
		self.assertTrue(request.submitted_on)
		self.assertTrue(request.signature, "the drawn signature was not stored")

		app.reload()
		self.assertEqual(app.scholarship_request, request.name)
		self.assertEqual(status_of(app, NO["scholarship"]), "Received")

	def test_the_signature_is_stored_privately(self):
		app = make_application()
		self._send(app)
		result = self._submit(app)

		signature = frappe.db.get_value("Scholarship Request", result["request"], "signature")
		self.assertEqual(
			frappe.db.get_value("File", {"file_url": signature}, "is_private"), 1
		)

	def test_an_empty_statement_is_refused(self):
		app = make_application()
		self._send(app)
		app.reload()
		with self.assertRaises(frappe.ValidationError):
			scholarship.submit(app.scholarship_token, "   ", png_data_url())

	def test_over_the_word_limit_is_refused(self):
		app = make_application()
		self._send(app)
		app.reload()
		too_long = " ".join(["need"] * (scholarship.WORD_LIMIT + 1))
		with self.assertRaises(frappe.ValidationError):
			scholarship.submit(app.scholarship_token, too_long, png_data_url())

	def test_an_unsigned_form_is_refused(self):
		app = make_application()
		self._send(app)
		app.reload()
		with self.assertRaises(frappe.ValidationError):
			scholarship.submit(app.scholarship_token, "Genuine need.", None)

	def test_something_that_is_not_a_png_is_refused(self):
		"""The pad produces PNG; anything else did not come from the pad."""
		app = make_application()
		self._send(app)
		app.reload()
		with self.assertRaises(frappe.ValidationError):
			scholarship.submit(
				app.scholarship_token,
				"Genuine need.",
				"data:image/png;base64," + base64.b64encode(b"<script>").decode(),
			)

	def test_a_refused_signature_leaves_no_request_behind(self):
		app = make_application()
		self._send(app)
		app.reload()
		try:
			scholarship.submit(app.scholarship_token, "Genuine need.", "data:image/png;base64,bm90YXBuZw==")
		except frappe.ValidationError:
			pass
		self.assertFalse(
			frappe.db.exists("Scholarship Request", {"application": app.name}),
			"a request was created for a signature that was then refused",
		)

	def test_the_token_is_spent_on_submission(self):
		app = make_application()
		self._send(app)
		self._submit(app)

		app.reload()
		with self.assertRaises(TokenError):
			scholarship.resolve(app.scholarship_token)

	def test_a_second_form_cannot_be_sent_once_one_is_in(self):
		app = make_application()
		self._send(app)
		self._submit(app)
		app.reload()

		report, sendmail = self._send(app)
		self.assertFalse(sendmail.called)
		self.assertTrue(report["warnings"])

	# -- the review ----------------------------------------------------------

	def _submitted_request(self, program="MDIV"):
		app = make_application(program=program)
		self._send(app)
		result = self._submit(app)
		return app, result["request"]

	def test_approving_stamps_the_decision_and_moves_the_step(self):
		app, request = self._submitted_request()
		scholarship.decide(request, "Approved", approved_amount=12000, monthly_discount=1000)

		doc = frappe.get_doc("Scholarship Request", request)
		self.assertEqual(doc.status, "Approved")
		self.assertEqual(doc.approved_amount, 12000)
		self.assertEqual(doc.monthly_discount, 1000)
		self.assertEqual(doc.approved_by, frappe.session.user)
		self.assertTrue(doc.approved_on)

		app.reload()
		self.assertEqual(status_of(app, NO["scholarship"]), "Approved")

	def test_an_award_above_the_program_cap_is_refused(self):
		if not frappe.db.exists("Program", "MDIV"):
			self.skipTest("MDIV is not in the catalog")

		_app, request = self._submitted_request()
		with self.assertRaises(frappe.ValidationError):
			scholarship.decide(request, "Approved", approved_amount=24001, monthly_discount=1000)

	def test_approving_nothing_is_refused(self):
		_app, request = self._submitted_request()
		with self.assertRaises(frappe.ValidationError):
			scholarship.decide(request, "Approved", approved_amount=0)

	def test_rejecting_clears_the_amounts_and_records_the_reason(self):
		app, request = self._submitted_request()
		scholarship.decide(request, "Rejected", remarks="Household income above the threshold.")

		doc = frappe.get_doc("Scholarship Request", request)
		self.assertEqual(doc.status, "Rejected")
		self.assertEqual(doc.approved_amount, 0)
		self.assertEqual(doc.monthly_discount, 0)

		app.reload()
		self.assertEqual(status_of(app, NO["scholarship"]), "Rejected")
		row = next(r for r in app.checklist if int(r.step_no) == NO["scholarship"])
		self.assertIn("threshold", row.remarks)

	def test_an_outcome_that_is_neither_is_refused(self):
		_app, request = self._submitted_request()
		with self.assertRaises(frappe.ValidationError):
			scholarship.decide(request, "Maybe", approved_amount=1000)

	# -- what the award is for ------------------------------------------------

	def test_an_approved_award_reaches_the_program_enrollment(self):
		"""The cap only works if conversion copies it onto the enrollment."""
		from sibbcs.admissions import conversion

		app, request = self._submitted_request()
		scholarship.decide(request, "Approved", approved_amount=12000, monthly_discount=1000)

		app.db_set("admission_fee_paid", 1)
		app.reload()
		report = conversion.convert(app.name)

		enrollment = frappe.get_doc(
			"Program Enrollment", report["created"]["program_enrollment"]
		)
		self.assertEqual(enrollment.scholarship_total_cap, 12000)
		self.assertEqual(enrollment.scholarship_monthly_discount, 1000)
		self.assertEqual(enrollment.scholarship_used_to_date, 0)
