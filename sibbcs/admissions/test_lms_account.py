# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.admissions import lms_account
from sibbcs.admissions.checklist import status_of

APPLICANT_EMAIL = "step7.applicant@example.com"
EXAM_URL = "https://exam.example.com/entrance"


def make_application(email=APPLICANT_EMAIL, **overrides):
	values = {
		"doctype": "Admission Application",
		"full_name": "Step Seven Applicant",
		"dob": "1995-04-01",
		"gender": "Male",
		"mobile": "9000000701",
		"email": email,
		"program": frappe.db.get_value("Program", {}, "name"),
	}
	values.update(overrides)
	doc = frappe.get_doc(values)
	doc.insert(ignore_permissions=True)
	return doc


class TestLMSAccount(FrappeTestCase):
	def setUp(self):
		for email in (APPLICANT_EMAIL, "other.applicant@example.com"):
			if frappe.db.exists("User", email):
				frappe.delete_doc("User", email, force=True, ignore_permissions=True)

	# -- the exam link ---------------------------------------------------

	def test_no_exam_configured_gives_no_link(self):
		with patch.dict(frappe.conf, {"entrance_exam_url": "", "entrance_exam_lms_course": ""}):
			self.assertIsNone(lms_account.exam_link())
			self.assertFalse(lms_account.exam_configured())

	def test_explicit_url_wins_over_the_lms_course(self):
		with patch.dict(
			frappe.conf,
			{"entrance_exam_url": EXAM_URL, "entrance_exam_lms_course": "anything"},
		):
			self.assertEqual(lms_account.exam_link(), EXAM_URL)

	def test_a_course_that_does_not_exist_is_not_a_link(self):
		"""A typo in the config must not send applicants to a 404."""
		with patch.dict(
			frappe.conf,
			{"entrance_exam_url": "", "entrance_exam_lms_course": "no-such-course"},
		):
			self.assertIsNone(lms_account.exam_course())
			self.assertIsNone(lms_account.exam_link())

	# -- the account -----------------------------------------------------

	def test_creates_a_website_user_with_the_lms_role(self):
		app = make_application()
		name, created = lms_account.ensure_user(app)

		self.assertTrue(created)
		self.assertEqual(name, APPLICANT_EMAIL)

		user = frappe.get_doc("User", name)
		self.assertEqual(user.user_type, "Website User")
		self.assertIn(lms_account.LMS_ROLE, [r.role for r in user.roles])

	def test_the_applicant_does_not_get_the_student_role_yet(self):
		"""They are an applicant. The Student role is granted at conversion."""
		app = make_application()
		name, _created = lms_account.ensure_user(app)
		roles = [r.role for r in frappe.get_doc("User", name).roles]
		self.assertNotIn("Student", roles)

	def test_an_existing_user_is_adopted_not_duplicated(self):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": APPLICANT_EMAIL,
				"first_name": "Already Here",
				"user_type": "Website User",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)

		app = make_application()
		name, created = lms_account.ensure_user(app)

		self.assertFalse(created)
		self.assertEqual(name, APPLICANT_EMAIL)
		self.assertEqual(
			frappe.db.count("User", {"email": APPLICANT_EMAIL}),
			1,
			"a second account was made for an email that already had one",
		)

	def test_a_disabled_account_is_reported_not_silently_reopened(self):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": APPLICANT_EMAIL,
				"first_name": "Disabled",
				"user_type": "Website User",
				"send_welcome_email": 0,
			}
		)
		user.insert(ignore_permissions=True)
		user.db_set("enabled", 0)

		app = make_application()
		with self.assertRaises(frappe.ValidationError):
			lms_account.ensure_user(app)

	def test_an_application_without_an_email_cannot_get_an_account(self):
		app = make_application()
		app.db_set("email", "")
		app.reload()
		with self.assertRaises(frappe.ValidationError):
			lms_account.ensure_user(app)

	def test_two_applicants_may_share_a_phone_number(self):
		"""Same rule as conversion: User.mobile_no is UNIQUE, handsets are shared."""
		first = make_application()
		lms_account.ensure_user(first)

		second = make_application(email="other.applicant@example.com")
		name, created = lms_account.ensure_user(second)

		self.assertTrue(created)
		self.assertEqual(name, "other.applicant@example.com")

	# -- the password link -----------------------------------------------

	def test_password_link_never_carries_the_dev_port(self):
		"""User._reset_password builds with get_url(), which appends :8000."""
		app = make_application()
		name, _created = lms_account.ensure_user(app)
		link = lms_account.set_password_link(name)

		self.assertNotIn(":8000", link)
		self.assertIn("/update-password?key=", link)

	def test_each_send_issues_a_fresh_password_key(self):
		app = make_application()
		name, _created = lms_account.ensure_user(app)

		first = lms_account.set_password_link(name)
		second = lms_account.set_password_link(name)
		self.assertNotEqual(first, second, "the same reset key was handed out twice")

	# -- the whole step --------------------------------------------------

	def _run(self, app, send=True):
		with patch.dict(
			frappe.conf, {"entrance_exam_url": EXAM_URL, "entrance_exam_lms_course": ""}
		), patch(
			"sibbcs.admissions.notifications.outgoing_configured", return_value=True
		), patch(
			"frappe.sendmail"
		) as sendmail:
			report = lms_account.create_and_send(app.name, send=send)
		return report, sendmail

	def test_the_step_records_the_account_and_the_link(self):
		app = make_application()
		report, sendmail = self._run(app)

		self.assertEqual(report["user"], APPLICANT_EMAIL)
		self.assertEqual(report["exam_link"], EXAM_URL)
		self.assertEqual(report["emailed"], APPLICANT_EMAIL)
		self.assertEqual(report["warnings"], [])
		self.assertTrue(sendmail.called)

		app.reload()
		self.assertEqual(app.applicant_user, APPLICANT_EMAIL)
		self.assertEqual(app.entrance_exam_link, EXAM_URL)
		self.assertTrue(app.lms_account_created_on)
		self.assertTrue(app.exam_link_sent_on)

	def test_the_invitation_carries_the_exam_link_and_no_password(self):
		app = make_application()
		_report, sendmail = self._run(app)

		body = sendmail.call_args.kwargs["message"]
		self.assertIn(EXAM_URL, body)
		self.assertIn("/update-password?key=", body)
		self.assertNotIn(":8000", body)

	def test_step_7_moves_to_link_sent(self):
		app = make_application()
		self.assertEqual(status_of(app, 7), "Awaiting")

		self._run(app)
		app.reload()
		self.assertEqual(status_of(app, 7), "Link Sent")

	def test_without_an_exam_link_the_account_is_still_made_but_nothing_is_sent(self):
		app = make_application()
		with patch.dict(
			frappe.conf, {"entrance_exam_url": "", "entrance_exam_lms_course": ""}
		), patch("frappe.sendmail") as sendmail:
			report = lms_account.create_and_send(app.name)

		self.assertEqual(report["user"], APPLICANT_EMAIL)
		self.assertIsNone(report["emailed"])
		self.assertFalse(sendmail.called)
		self.assertTrue(report["warnings"])

		app.reload()
		self.assertEqual(status_of(app, 7), "Created")
		self.assertFalse(app.exam_link_sent_on)

	def test_a_missing_mail_account_is_a_warning_not_an_exception(self):
		app = make_application()
		with patch.dict(
			frappe.conf, {"entrance_exam_url": EXAM_URL, "entrance_exam_lms_course": ""}
		), patch(
			"sibbcs.admissions.notifications.outgoing_configured", return_value=False
		), patch(
			"frappe.sendmail"
		) as sendmail:
			report = lms_account.create_and_send(app.name)

		self.assertFalse(sendmail.called)
		self.assertIsNone(report["emailed"])
		self.assertTrue(any("outgoing email" in w for w in report["warnings"]))

	def test_running_it_twice_makes_one_account(self):
		app = make_application()
		self._run(app)
		report, _sendmail = self._run(app)

		self.assertFalse(report["user_created"])
		self.assertEqual(frappe.db.count("User", {"email": APPLICANT_EMAIL}), 1)

	def test_the_step_does_not_walk_backwards(self):
		"""Link Sent must not fall back to Created on a later run."""
		app = make_application()
		self._run(app)
		self._run(app, send=False)

		app.reload()
		self.assertEqual(status_of(app, 7), "Link Sent")

	# -- the gate it opens ------------------------------------------------

	def test_step_7_unblocks_the_entrance_exam(self):
		from sibbcs.admissions.checklist import blocked_reason

		app = make_application()
		self.assertIsNotNone(
			blocked_reason(app, 8), "the exam was sittable before an account existed"
		)

		self._run(app)
		app.reload()
		self.assertIsNone(blocked_reason(app, 8))

	# -- the account survives into studenthood ----------------------------

	def test_conversion_reuses_the_applicant_account(self):
		"""The applicant keeps one login: no second User at conversion."""
		from sibbcs.admissions import conversion

		app = make_application()
		self._run(app)

		app.db_set("admission_fee_paid", 1)
		app.reload()
		report = conversion.convert(app.name)

		self.assertEqual(report["created"]["user"], APPLICANT_EMAIL)
		self.assertEqual(frappe.db.count("User", {"email": APPLICANT_EMAIL}), 1)

		roles = [r.role for r in frappe.get_doc("User", APPLICANT_EMAIL).roles]
		self.assertIn("Student", roles)
		self.assertIn(lms_account.LMS_ROLE, roles)
