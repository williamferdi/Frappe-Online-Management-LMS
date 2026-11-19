# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""The emails admissions sends to people who are not the candidate.

Two of them are new, and both exist because something was arriving in silence:
a mentor was asked to commit to a student without being shown what that means,
and a candidate could send every certificate we had asked for without anybody
in the office being told.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.admissions import notifications
from sibbcs.admissions.public_form import submit_application
from sibbcs.admissions.test_public_form import payload


def _application():
	"""One application through the public form, with a mentor row on it."""
	result = submit_application(
		**payload(email=f"notify-{frappe.generate_hash(length=10)}@example.invalid")
	)
	return frappe.get_doc("Admission Application", result["application"])


class TestTheMentorHandbookTravelsWithTheRequest(FrappeTestCase):
	"""A mentor is a stranger with no login, asked on the strength of one email
	to take on a student for the length of a degree. The handbook is the
	document that says what they would be agreeing to.
	"""

	def setUp(self):
		self.original = frappe.conf.get(notifications.MENTOR_HANDBOOK_CONFIG)

	def tearDown(self):
		frappe.conf[notifications.MENTOR_HANDBOOK_CONFIG] = self.original

	def test_nothing_is_attached_when_the_site_has_no_handbook(self):
		frappe.conf[notifications.MENTOR_HANDBOOK_CONFIG] = None
		self.assertEqual(notifications.mentor_handbook_attachment(), [])

	def test_a_handbook_that_has_been_deleted_is_left_off_rather_than_raised(self):
		"""The consent request must still go. A mentor can answer without the
		handbook; they cannot answer an email that was never sent.
		"""
		frappe.conf[notifications.MENTOR_HANDBOOK_CONFIG] = "/private/files/not-here-at-all.pdf"
		self.assertEqual(notifications.mentor_handbook_attachment(), [])

	def test_a_real_file_is_attached_by_url(self):
		# Deliberately not a .pdf. Frappe scans an uploaded PDF for embedded
		# JavaScript, and pypdf refuses a stub that only starts with %PDF --
		# which has nothing to do with what is being tested here. The real
		# handbook is a real PDF and passes that scan.
		handbook = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": f"handbook-{frappe.generate_hash(length=8)}.txt",
				"content": b"stand-in for the Mentor Handbook",
				"decode": False,
				"is_private": 1,
			}
		)
		handbook.flags.ignore_permissions = True
		handbook.insert(ignore_permissions=True)

		frappe.conf[notifications.MENTOR_HANDBOOK_CONFIG] = handbook.file_url
		self.assertEqual(
			notifications.mentor_handbook_attachment(), [{"file_url": handbook.file_url}]
		)

	def test_the_consent_email_carries_it(self):
		from unittest.mock import patch

		doc = _application()
		sent = []

		with patch.object(
			notifications, "mentor_handbook_attachment", return_value=[{"file_url": "/x.pdf"}]
		), patch.object(
			notifications.frappe, "sendmail", side_effect=lambda **kw: sent.append(kw)
		):
			notifications.send_mentor_row(doc, doc.mentor_consents[0])

		self.assertEqual(len(sent), 1)
		self.assertEqual(sent[0]["attachments"], [{"file_url": "/x.pdf"}])

	def test_the_wording_tells_the_mentor_it_is_there(self):
		"""An attachment nobody is told about is an attachment nobody opens."""
		self.assertIn("Mentor Handbook is attached", notifications.FALLBACK_MENTOR[1])


class TestTheOfficeIsToldDocumentsArrived(FrappeTestCase):
	"""The resubmit request goes out from the console; until now the answer to
	it came back in silence, and an officer had to think to go and look.
	"""

	def setUp(self):
		frappe.cache().delete_keys("sibbcs:documents-alert:")

	def _send(self, application):
		from unittest.mock import patch

		sent = []
		with patch.object(
			notifications, "outgoing_configured", return_value=True
		), patch.object(
			notifications, "officer_emails", return_value=["officer@example.invalid"]
		), patch.object(
			notifications.frappe, "sendmail", side_effect=lambda **kw: sent.append(kw)
		):
			notifications.notify_officers_of_documents(application)
		return sent

	def test_it_names_the_candidate_and_links_to_the_application(self):
		doc = _application()
		sent = self._send(doc.name)

		self.assertEqual(len(sent), 1)
		self.assertIn(doc.full_name, sent[0]["subject"])
		self.assertIn(f"/staff/admissions/{doc.name}", sent[0]["message"])

	def test_the_link_is_one_a_browser_can_reach(self):
		"""public_url, never get_url -- the latter appends :8000 here."""
		doc = _application()
		self.assertNotIn(":8000", self._send(doc.name)[0]["message"])

	def test_six_documents_in_a_row_are_one_email_and_not_six(self):
		"""A candidate sends every certificate one after another. Six emails
		about one application is how a useful alert becomes one an officer
		filters away. Each email lists everything outstanding, never a diff,
		so a throttled one costs the officer nothing.
		"""
		doc = _application()
		self.assertEqual(len(self._send(doc.name)), 1)
		self.assertEqual(len(self._send(doc.name)), 0)
		self.assertEqual(len(self._send(doc.name)), 0)

	def test_one_application_does_not_silence_another(self):
		first = _application()
		second = _application()
		self.assertEqual(len(self._send(first.name)), 1)
		self.assertEqual(len(self._send(second.name)), 1)

	def test_nothing_is_sent_with_no_outgoing_account(self):
		from unittest.mock import patch

		doc = _application()
		with patch.object(notifications, "outgoing_configured", return_value=False):
			self.assertIsNone(notifications.notify_officers_of_documents(doc.name))

	def test_nobody_holding_the_role_is_reported_rather_than_raised(self):
		from unittest.mock import patch

		doc = _application()
		with patch.object(
			notifications, "outgoing_configured", return_value=True
		), patch.object(notifications, "officer_emails", return_value=[]):
			self.assertIsNone(notifications.notify_officers_of_documents(doc.name))

	def test_an_application_that_has_gone_is_not_an_error(self):
		from unittest.mock import patch

		with patch.object(
			notifications, "outgoing_configured", return_value=True
		), patch.object(
			notifications, "officer_emails", return_value=["officer@example.invalid"]
		):
			self.assertIsNone(
				notifications.notify_officers_of_documents("APP-DOES-NOT-EXIST")
			)


class TestWhoCountsAsAnAdmissionsOfficer(FrappeTestCase):
	def test_only_addresses_come_back(self):
		"""`Has Role.parent` is a User name, which is usually an address and on
		`Administrator` and `Guest` is not.
		"""
		for email in notifications.officer_emails():
			self.assertIn("@", email)

	def test_administrator_and_guest_are_not_in_the_list(self):
		listed = notifications.officer_emails()
		self.assertNotIn("Administrator", listed)
		self.assertNotIn("Guest", listed)
