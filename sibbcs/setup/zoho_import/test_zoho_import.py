# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""The Zoho import: what must not happen while it loads, and the read side.

Every fixture here is invented. Real Zoho data never goes into a test.
"""

from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from sibbcs.academic import offer_notice
from sibbcs.academic.doctype.academic_term.test_academic_term import make_term
from sibbcs.academic.doctype.course.test_course import make_course
from sibbcs.academic.doctype.course_offering.test_course_offering import make_offering
from sibbcs.academic.doctype.program_enrollment.test_program_enrollment import (
	make_enrollment,
	make_student,
)
from sibbcs.finance import fees, hooks_handlers
from sibbcs.integrations import campus_lms
from sibbcs.setup.zoho_import import quiet
from sibbcs.setup.zoho_import.client import Client, ZohoError, file_references
from sibbcs.setup.zoho_import.extract import _emails, onboarded


class TestQuiet(FrappeTestCase):
	def test_it_sets_and_restores_the_flags(self):
		self.assertFalse(frappe.flags.sibbcs_import)
		with quiet():
			self.assertTrue(frappe.flags.sibbcs_import)
			self.assertTrue(frappe.flags.mute_emails)
		self.assertFalse(frappe.flags.sibbcs_import)

	def test_it_restores_them_after_an_error(self):
		with self.assertRaises(RuntimeError):
			with quiet():
				raise RuntimeError("load failed")
		self.assertFalse(frappe.flags.sibbcs_import)

	def test_nothing_is_pushed_to_the_lms_while_importing(self):
		with mock.patch.object(campus_lms, "configured", return_value=True), mock.patch(
			"frappe.enqueue"
		) as enqueue:
			with quiet():
				campus_lms.queue("Student", "SIB-X")
				campus_lms.queue_payload("/sync/people", {"externalId": "SIB-X"})
			self.assertFalse(enqueue.called)

			# and outside the block it works as it always did
			campus_lms.queue("Student", "SIB-X")
			self.assertTrue(enqueue.called)

	def test_no_registration_open_mail_is_queued_while_importing(self):
		offering = frappe._dict(name="X-T", status="Published", students_notified_on=None)

		with mock.patch("frappe.enqueue") as enqueue:
			with quiet():
				offer_notice.on_offering_change(offering)
			self.assertFalse(enqueue.called)


class TestCarriedOverRegistrationsAreNeverBilled(FrappeTestCase):
	"""Without this the nightly sweep would raise a Rs350 fee for every course
	every imported student ever took."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.term = make_term("TST-ZOHO-TERM", status="Open").name

	def _registration(self, email, code, **kw):
		student = make_student(full_name=f"Zoho {email}", email=email)
		enrollment = make_enrollment(student.name)
		course = make_course(code, level="1")
		offering = make_offering(course.name, self.term, status="Published")
		values = {
			"doctype": "Course Registration",
			"program_enrollment": enrollment.name,
			"course_offering": offering.name,
			"registration_date": today(),
			"status": "Completed",
		}
		values.update(kw)
		return frappe.get_doc(values).insert(ignore_permissions=True)

	def _invoices(self, registration):
		return frappe.db.count("Fee Invoice", {"course_registration": registration.name})

	def test_a_carried_over_registration_raises_no_fee(self):
		registration = self._registration("zoho1@example.com", "TST Z100", legacy_source="3000001")

		registration.reload()
		self.assertFalse(registration.registration_fee_invoice)
		self.assertEqual(self._invoices(registration), 0)
		self.assertIsNone(fees.raise_registration_fee(registration.name))

	def test_the_nightly_sweep_passes_it_by(self):
		legacy = self._registration("zoho2@example.com", "TST Z110", legacy_source="3000002")
		with quiet():
			# Loaded quietly and *not* carried over: the sweep should still
			# catch this one, which proves the sweep ran.
			fresh = self._registration("zoho3@example.com", "TST Z120", status="Registered")
		self.assertEqual(self._invoices(fresh), 0)

		hooks_handlers.sweep_missing_registration_fees(limit=100000)

		self.assertEqual(self._invoices(legacy), 0)
		self.assertEqual(self._invoices(fresh), 1)

	def test_nothing_is_billed_while_importing(self):
		with quiet():
			registration = self._registration("zoho4@example.com", "TST Z130", status="Registered")
		self.assertEqual(self._invoices(registration), 0)

	def test_an_ordinary_registration_is_still_billed(self):
		registration = self._registration("zoho5@example.com", "TST Z140", status="Registered")
		self.assertEqual(self._invoices(registration), 1)


class FakeResponse:
	def __init__(self, body=None, status=200, headers=None, content=b""):
		self._body = body or {}
		self.status_code = status
		self.headers = headers or {}
		self.content = content

	def json(self):
		return self._body


class FakeSession:
	def __init__(self, pages):
		self.pages = list(pages)
		self.gets = []

	def post(self, url, params=None, timeout=None):
		return FakeResponse({"access_token": "a", "expires_in": 3600})

	def get(self, url, params=None, headers=None, timeout=None, stream=False):
		self.gets.append({"url": url, "params": params, "headers": headers})
		return self.pages.pop(0)


CREDENTIALS = {"dc": "in", "client_id": "c", "client_secret": "S3cret-Value", "refresh_token": "R3fresh-Value"}


class TestTheZohoClient(FrappeTestCase):
	def test_it_follows_the_cursor_to_the_end(self):
		session = FakeSession(
			[
				FakeResponse({"code": 3000, "data": [{"ID": "1"}, {"ID": "2"}]}, headers={"record_cursor": "next"}),
				FakeResponse({"code": 3000, "data": [{"ID": "3"}]}),
			]
		)

		rows = Client(CREDENTIALS, session=session).records("courses_Report")

		self.assertEqual([r["ID"] for r in rows], ["1", "2", "3"])
		self.assertEqual(session.gets[1]["headers"]["record_cursor"], "next")
		self.assertEqual(session.gets[0]["params"]["field_config"], "all")

	def test_an_empty_report_is_an_empty_list(self):
		session = FakeSession([FakeResponse({"code": 3100, "message": "No records exist"})])
		self.assertEqual(Client(CREDENTIALS, session=session).records("x"), [])

	def test_an_error_code_is_not_mistaken_for_no_records(self):
		session = FakeSession([FakeResponse({"code": 2945, "message": "No such report"})])
		with self.assertRaises(ZohoError):
			Client(CREDENTIALS, session=session).records("x")

	def test_a_refused_token_says_why_and_not_the_secret(self):
		session = FakeSession([])
		session.post = lambda *a, **k: FakeResponse({"error": "invalid_client"})
		with self.assertRaises(ZohoError) as caught:
			Client(CREDENTIALS, session=session).records("x")
		self.assertIn("invalid_client", str(caught.exception))
		self.assertNotIn("S3cret-Value", str(caught.exception))
		self.assertNotIn("R3fresh-Value", str(caught.exception))

	def test_file_references_are_found_in_every_shape_creator_uses(self):
		one = "/api/v2.1/o/a/report/r/1/photo/download?filepath=/1700_me.jpg"
		many = [
			"/api/v2.1/o/a/report/r/1/Docs/download?filepath=a.pdf",
			{"value": "/api/v2.1/o/a/report/r/1/Docs/download?filepath=b.pdf"},
		]

		self.assertEqual(file_references(one), ["/1700_me.jpg"])
		self.assertEqual(file_references(many), ["a.pdf", "b.pdf"])
		self.assertEqual(file_references("Awaiting Review"), [])
		self.assertEqual(file_references(None), [])


class TestWhoIsExtracted(FrappeTestCase):
	def test_only_onboarded_students_whatever_shape_the_status_comes_in(self):
		rows = [
			{"ID": "1", "Onboarding_Status": "Onboarded"},
			{"ID": "2", "Onboarding_Status": {"display_value": "Onboarded"}},
			{"ID": "3", "Onboarding_Status": "Awaiting Onboarding"},
			{"ID": "4"},
		]
		self.assertEqual([r["ID"] for r in onboarded(rows)], ["1", "2"])

	def test_emails_are_matched_case_blind(self):
		self.assertEqual(
			_emails({"Student_Email": " Ruth@Example.COM ", "Name": "x@y.z"}), {"ruth@example.com"}
		)
