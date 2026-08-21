# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.admissions import interview
from sibbcs.admissions.checklist import NO, set_status, status_of

EVENT = "https://calendly.com/admissions-online-sibbc/30min"
# What a link actually looks like when copied out of a browser.
EVENT_WITH_VIEW_STATE = f"{EVENT}?month=2026-08&date=2026-08-28"


def make_application(**overrides):
	values = {
		"doctype": "Admission Application",
		"full_name": "Interview Candidate",
		"dob": "1991-07-07",
		"gender": "Male",
		"mobile": "9000000915",
		"email": "interview.candidate@example.com",
		"program": frappe.db.get_value("Program", {}, "name"),
	}
	values.update(overrides)
	doc = frappe.get_doc(values)
	doc.insert(ignore_permissions=True)
	return doc


class TestInterviewBooking(FrappeTestCase):
	# -- the configured event ---------------------------------------------

	def test_no_event_configured_gives_no_link(self):
		with patch.dict(frappe.conf, {"calendly_interview_url": ""}):
			self.assertIsNone(interview.event_url())
			self.assertFalse(interview.configured())

	def test_the_browsers_view_state_is_stripped(self):
		"""month= and date= pin the widget to a day that will be in the past."""
		with patch.dict(frappe.conf, {"calendly_interview_url": EVENT_WITH_VIEW_STATE}):
			self.assertEqual(interview.event_url(), EVENT)

	def test_a_trailing_slash_is_dropped(self):
		with patch.dict(frappe.conf, {"calendly_interview_url": EVENT + "/"}):
			self.assertEqual(interview.event_url(), EVENT)

	def test_something_that_is_not_a_url_is_refused(self):
		with patch.dict(frappe.conf, {"calendly_interview_url": "admissions/30min"}):
			self.assertIsNone(interview.event_url())

	# -- the candidate's link ----------------------------------------------

	def test_the_link_prefills_the_candidate_and_carries_the_application(self):
		app = make_application()
		with patch.dict(frappe.conf, {"calendly_interview_url": EVENT_WITH_VIEW_STATE}):
			link = interview.booking_url(app)

		parts = urlsplit(link)
		query = parse_qs(parts.query)

		self.assertEqual(f"{parts.scheme}://{parts.netloc}{parts.path}", EVENT)
		self.assertEqual(query["name"], ["Interview Candidate"])
		self.assertEqual(query["email"], ["interview.candidate@example.com"])
		self.assertEqual(query["utm_content"], [app.name])
		self.assertNotIn("date", query)
		self.assertNotIn("month", query)

	def test_no_link_without_an_event(self):
		app = make_application()
		with patch.dict(frappe.conf, {"calendly_interview_url": ""}):
			self.assertIsNone(interview.booking_url(app))

	# -- sending -------------------------------------------------------------

	def _send(self, app, event=EVENT):
		with patch.dict(frappe.conf, {"calendly_interview_url": event}), patch(
			"sibbcs.admissions.notifications.outgoing_configured", return_value=True
		), patch("frappe.sendmail") as sendmail:
			report = interview.send_invite(app.name)
		return report, sendmail

	def test_sending_stores_the_link_and_stamps_the_application(self):
		app = make_application()
		report, sendmail = self._send(app)

		self.assertEqual(report["emailed"], app.email)
		self.assertEqual(report["warnings"], [])
		self.assertTrue(sendmail.called)

		app.reload()
		self.assertIn("utm_content=", app.interview_booking_url)
		self.assertTrue(app.interview_link_sent_on)

	def test_the_email_carries_the_link_and_no_dev_port(self):
		app = make_application()
		_report, sendmail = self._send(app)

		body = sendmail.call_args.kwargs["message"]
		self.assertIn("calendly.com/admissions-online-sibbc/30min", body)
		self.assertNotIn(":8000", body)
		self.assertNotIn("{{", body)

	def test_the_step_says_invite_sent_not_scheduled(self):
		"""A sent link is not a booking; nobody here knows they booked yet."""
		app = make_application()
		self.assertEqual(status_of(app, NO["interview"]), "Awaiting")

		self._send(app)
		app.reload()
		self.assertEqual(status_of(app, NO["interview"]), "Invite Sent")

	def test_resending_does_not_undo_an_officers_decision(self):
		app = make_application()
		self._send(app)
		app.reload()
		set_status(app, NO["interview"], "Scheduled")
		app.reload()

		self._send(app)
		app.reload()
		self.assertEqual(status_of(app, NO["interview"]), "Scheduled")

	def test_without_an_event_nothing_is_sent_and_the_step_stays_put(self):
		app = make_application()
		with patch.dict(frappe.conf, {"calendly_interview_url": ""}), patch(
			"frappe.sendmail"
		) as sendmail:
			report = interview.send_invite(app.name)

		self.assertFalse(sendmail.called)
		self.assertIsNone(report["emailed"])
		self.assertTrue(report["warnings"])

		app.reload()
		self.assertEqual(status_of(app, NO["interview"]), "Awaiting")

	def test_a_missing_mail_account_is_a_warning_not_an_exception(self):
		app = make_application()
		with patch.dict(frappe.conf, {"calendly_interview_url": EVENT}), patch(
			"sibbcs.admissions.notifications.outgoing_configured", return_value=False
		), patch("frappe.sendmail") as sendmail:
			report = interview.send_invite(app.name)

		self.assertFalse(sendmail.called)
		self.assertTrue(any("outgoing email" in w for w in report["warnings"]))
		# The link is still stored, so an officer can send it by hand.
		app.reload()
		self.assertTrue(app.interview_booking_url)

	def test_the_interview_step_is_not_gated(self):
		"""Nothing has to happen before an interview can be booked."""
		from sibbcs.admissions.checklist import blocked_reason

		self.assertIsNone(blocked_reason(make_application(), NO["interview"]))
