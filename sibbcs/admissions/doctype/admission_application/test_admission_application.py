# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from sibbcs.admissions.doctype.admission_application.admission_application import (
	REQUIRED_DOCUMENTS,
)
from sibbcs.admissions.tokens import TokenError, get_context_for, mark_submitted, resolve


def make_application(**kw):
	docs = kw.pop("documents", None)
	refs = kw.pop("references", None)
	mentors = kw.pop("mentors", None)

	defaults = {
		"doctype": "Admission Application",
		"full_name": kw.pop("full_name", "Test Applicant"),
		"email": kw.pop("email", "applicant@example.com"),
		"mobile": kw.pop("mobile", "9000000001"),
		"program": kw.pop("program", "MDIV"),
		"dob": kw.pop("dob", "1995-06-15"),
	}
	defaults.update(kw)

	doc = frappe.get_doc(defaults)
	for row in docs or []:
		doc.append("application_documents", row)
	for row in refs or []:
		doc.append("reference_requests", row)
	for row in mentors or []:
		doc.append("mentor_consents", row)

	return doc.insert(ignore_permissions=True)


def all_documents_verified():
	return [
		{"document_type": d, "file": f"/files/{d}.pdf", "verified": 1}
		for d in REQUIRED_DOCUMENTS
	]


class TestAdmissionApplication(FrappeTestCase):
	def test_naming_series_is_app_year(self):
		app = make_application()
		self.assertRegex(app.name, r"^APP-\d{4}-\d{5}$")

	def test_age_is_derived_from_dob(self):
		app = make_application(dob="2000-01-01")
		expected = int(frappe.utils.date_diff(nowdate(), "2000-01-01") // 365.25)
		self.assertEqual(app.age, expected)

	def test_future_dob_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			make_application(dob=add_days(nowdate(), 1))

	def test_email_is_lower_cased(self):
		app = make_application(email="Mixed.Case@Example.COM")
		self.assertEqual(app.email, "mixed.case@example.com")

	def test_docs_verified_false_when_documents_missing(self):
		app = make_application()
		self.assertFalse(app.docs_verified)

	def test_docs_verified_false_when_one_is_unverified(self):
		docs = all_documents_verified()
		docs[0]["verified"] = 0
		app = make_application(documents=docs)
		self.assertFalse(app.docs_verified)
		self.assertIn(REQUIRED_DOCUMENTS[0], app.unverified_documents())

	def test_docs_verified_true_when_all_present_and_verified(self):
		app = make_application(documents=all_documents_verified())
		self.assertTrue(app.docs_verified)
		self.assertEqual(app.missing_documents(), [])

	def test_duplicate_referee_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			make_application(
				references=[
					{"referee_name": "A", "referee_email": "same@x.com", "referee_type": "Pastor-Mentor"},
					{"referee_name": "B", "referee_email": "same@x.com", "referee_type": "Professor-Employer"},
				]
			)

	def test_applicant_cannot_be_their_own_referee(self):
		with self.assertRaises(frappe.ValidationError):
			make_application(
				email="self@example.com",
				references=[
					{
						"referee_name": "Self",
						"referee_email": "self@example.com",
						"referee_type": "Pastor-Mentor",
					}
				],
			)

	def test_tokens_issued_to_referees_and_mentors(self):
		app = make_application(
			references=[
				{"referee_name": "Pastor A", "referee_email": "a@x.com", "referee_type": "Pastor-Mentor"}
			],
			mentors=[{"mentor_name": "Mentor M", "mentor_email": "m@x.com"}],
		)
		self.assertTrue(app.reference_requests[0].token)
		self.assertTrue(app.mentor_consents[0].token)

	def test_tokens_are_unique_and_long(self):
		app = make_application(
			references=[
				{"referee_name": "A", "referee_email": "a@x.com", "referee_type": "Pastor-Mentor"},
				{"referee_name": "B", "referee_email": "b@x.com", "referee_type": "Professor-Employer"},
			]
		)
		first, second = (r.token for r in app.reference_requests)
		self.assertNotEqual(first, second)
		self.assertGreaterEqual(len(first), 32)

	def test_pending_references_tracks_outstanding(self):
		app = make_application(
			references=[
				{"referee_name": "A", "referee_email": "a@x.com", "referee_type": "Pastor-Mentor"}
			]
		)
		self.assertEqual(app.pending_references(), ["A"])


class TestTokenController(FrappeTestCase):
	def setUp(self):
		super().setUp()
		self.app = make_application(
			email="tokentest@example.com",
			references=[
				{"referee_name": "Pastor A", "referee_email": "a@x.com", "referee_type": "Pastor-Mentor"}
			],
			mentors=[{"mentor_name": "Mentor M", "mentor_email": "m@x.com"}],
		)
		self.ref_token = self.app.reference_requests[0].token
		self.mentor_token = self.app.mentor_consents[0].token

	def test_resolve_finds_the_row(self):
		resolved = resolve("reference", self.ref_token)
		self.assertEqual(resolved["parent"], self.app.name)

	def test_unknown_token_rejected(self):
		with self.assertRaises(TokenError):
			resolve("reference", "x" * 40)

	def test_empty_token_rejected(self):
		with self.assertRaises(TokenError):
			resolve("reference", "")

	def test_short_token_rejected(self):
		with self.assertRaises(TokenError):
			resolve("reference", "abc")

	def test_unknown_form_key_rejected(self):
		with self.assertRaises(TokenError):
			resolve("not-a-form", self.ref_token)

	def test_reference_token_is_not_valid_for_mentor_form(self):
		"""Tokens must not be interchangeable between form types."""
		with self.assertRaises(TokenError):
			resolve("mentor-consent", self.ref_token)

	def test_context_exposes_only_safe_fields(self):
		context = get_context_for("reference", self.ref_token)
		self.assertEqual(context["applicant_name"], "Test Applicant")
		self.assertEqual(context["program"], "MDIV")
		# the applicant's contact details must not leak to a referee
		self.assertNotIn("tokentest@example.com", json.dumps(context, default=str))

	def test_submission_records_answers(self):
		mark_submitted(
			"reference",
			self.ref_token,
			{"recommendation": "Strong", "response_json": '{"capacity": "Pastor"}'},
		)
		self.app.reload()
		row = self.app.reference_requests[0]
		self.assertEqual(row.recommendation, "Strong")
		self.assertTrue(row.submitted_on)

	def test_token_cannot_be_reused(self):
		mark_submitted("reference", self.ref_token, {"recommendation": "Positive"})
		with self.assertRaises(TokenError):
			mark_submitted("reference", self.ref_token, {"recommendation": "Negative"})

	def test_submission_cannot_write_arbitrary_fields(self):
		"""A crafted payload must not reach fields outside the row's meta."""
		mark_submitted(
			"reference",
			self.ref_token,
			{"recommendation": "Strong", "parent": "EVIL", "token": "hijack"},
		)
		self.app.reload()
		row = self.app.reference_requests[0]
		self.assertEqual(row.parent, self.app.name)
		self.assertEqual(row.token, self.ref_token)

	def test_mentor_consent_submission(self):
		mark_submitted(
			"mentor-consent",
			self.mentor_token,
			{"mentor_name": "Mentor M", "church": "Grace Church", "mentor_mobile": "9000000002"},
		)
		self.app.reload()
		row = self.app.mentor_consents[0]
		self.assertEqual(row.church, "Grace Church")
		self.assertTrue(row.consented_on)
		self.assertTrue(self.app.has_mentor_consent())
