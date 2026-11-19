# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

import ast
import inspect
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.admissions import lms_account
from sibbcs.admissions.checklist import NO, status_of

APPLICANT_EMAIL = "step7.applicant@example.com"
EXAM_URL = "https://exam.example.com/entrance"
ACTIVATION_URL = "https://lms.example.invalid/activate?token=fixture"


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
		# No role at all. `LMS Student` was granted here and belonged to the
		# bundled lms app, which Phase 7 removed; an applicant needs nothing on
		# this site to sit the exam, because that happens in Campus LMS Lite
		# under its own account.
		self.assertEqual([r.role for r in user.roles], [])

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

	# -- no Frappe password link lives here any more ----------------------

	def test_the_frappe_password_link_builder_is_gone(self):
		"""The exam is sat in Campus LMS Lite. This module used to mint a
		Frappe `/update-password` link and email it, so a candidate set a
		password on a portal where they hold no roles and nothing to read --
		while the LMS activation link they actually needed went into the
		officer's report and was never sent.

		Asserted on the module rather than on its source text: a grep for
		"update-password" matches the paragraph above it, which is how this
		codebase has fooled itself before.
		"""
		self.assertFalse(hasattr(lms_account, "set_password_link"))

		calls = [
			node
			for node in ast.walk(ast.parse(inspect.getsource(lms_account)))
			if isinstance(node, ast.Attribute) and node.attr == "_reset_password"
		]
		self.assertEqual(calls, [], "something here still resets a Frappe password")

	# -- the whole step --------------------------------------------------

	def _run(self, app, send=True, activation=ACTIVATION_URL):
		"""The step as it runs with a working LMS behind it.

		`reissue_activation_link` is what supplies the link here: these
		fixtures do not stand up a Campus LMS, and the step now refuses to send
		half an invitation without one.
		"""
		with patch.dict(
			frappe.conf, {"entrance_exam_url": EXAM_URL, "entrance_exam_lms_course": ""}
		), patch.object(
			lms_account.campus_lms,
			"reissue_activation_link",
			return_value={"url": activation} if activation else {"error": "no account"},
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

	def test_the_invitation_carries_the_exam_link_and_the_lms_activation(self):
		app = make_application()
		_report, sendmail = self._run(app)

		body = sendmail.call_args.kwargs["message"]
		self.assertIn(EXAM_URL, body)
		self.assertIn(ACTIVATION_URL, body)
		self.assertNotIn("/update-password", body)
		self.assertNotIn(":8000", body)

	def test_the_step_moves_to_link_sent(self):
		app = make_application()
		self.assertEqual(status_of(app, NO["lms_account"]), "Awaiting")

		self._run(app)
		app.reload()
		self.assertEqual(status_of(app, NO["lms_account"]), "Link Sent")

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
		self.assertEqual(status_of(app, NO["lms_account"]), "Created")
		self.assertFalse(app.exam_link_sent_on)

	def test_a_missing_mail_account_is_a_warning_not_an_exception(self):
		app = make_application()
		with patch.dict(
			frappe.conf, {"entrance_exam_url": EXAM_URL, "entrance_exam_lms_course": ""}
		), patch.object(
			lms_account.campus_lms,
			"reissue_activation_link",
			return_value={"url": ACTIVATION_URL},
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
		self.assertEqual(status_of(app, NO["lms_account"]), "Link Sent")

	# -- the gate it opens ------------------------------------------------

	def test_step_7_unblocks_the_entrance_exam(self):
		from sibbcs.admissions.checklist import blocked_reason

		app = make_application()
		self.assertIsNotNone(
			blocked_reason(app, NO["entrance_exam"]), "the exam was sittable before an account existed"
		)

		self._run(app)
		app.reload()
		self.assertIsNone(blocked_reason(app, NO["entrance_exam"]))

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


class TestTheExamAccountInCampusLms(FrappeTestCase):
	"""The exam moved, so the account an applicant needs is over there.

	The Frappe user is still made: conversion adopts it when they are admitted,
	so one person keeps one login either side.
	"""

	def setUp(self):
		frappe.set_user("Administrator")

	def _application(self):
		from sibbcs.admissions.doctype.admission_application.test_admission_application import (
			make_application,
		)

		tag = frappe.generate_hash(length=6)
		return make_application(full_name=f"Campus {tag}", email=f"campus.{tag}@example.invalid")

	def test_the_applicant_is_filed_under_their_application(self):
		"""Not under an email or a student number they do not have yet. It is
		how the exam result finds its way back to this record."""
		doc = self._application()
		sent = []
		with patch.object(lms_account.campus_lms, "configured", return_value=True):
			with patch.object(lms_account.campus_lms, "_post", side_effect=lambda path, body: sent.append((path, body)) or {"activationUrl": "https://lms.test/activate?token=x"}):
				report = lms_account.create_and_send(doc.name, send=False)

		people = [body for path, body in sent if path == "/sync/people"]
		enrolments = [body for path, body in sent if path == "/sync/enrollments"]
		self.assertEqual(people[0]["externalId"], doc.name)
		self.assertEqual(people[0]["role"], "student")
		self.assertEqual(enrolments[0]["courseExternalId"], lms_account.campus_lms.EXAM_COURSE)
		self.assertEqual(report["enrolled_in"], lms_account.campus_lms.EXAM_COURSE)

	def test_the_activation_link_comes_back_for_the_invitation(self):
		"""The LMS sends no email, so the invitation goes out from here -- and
		an officer can pass the link on if it does not arrive."""
		doc = self._application()
		with patch.object(lms_account.campus_lms, "configured", return_value=True):
			with patch.object(lms_account.campus_lms, "_post", return_value={"activationUrl": "https://lms.test/activate?token=abc"}):
				report = lms_account.create_and_send(doc.name, send=False)

		self.assertEqual(report["activation_link"], "https://lms.test/activate?token=abc")

	def test_an_lms_that_is_down_does_not_cost_the_applicant_their_account(self):
		doc = self._application()
		with patch.object(lms_account.campus_lms, "configured", return_value=True):
			with patch.object(lms_account.campus_lms, "_post", side_effect=OSError("unreachable")):
				report = lms_account.create_and_send(doc.name, send=False)

		self.assertTrue(report["user"], "the Frappe account must still be made")
		self.assertIsNone(report["enrolled_in"])

	def test_the_exam_link_is_the_lms_itself(self):
		"""No course address: they sign in and the only course they are on is
		the exam."""
		with patch.object(lms_account.campus_lms, "configured", return_value=True):
			with patch.object(lms_account.campus_lms, "base_url", return_value="https://lms.test"):
				self.assertEqual(lms_account.exam_link(), "https://lms.test")


class TestTheInvitationOpensTheAccountItNames(FrappeTestCase):
	"""Until 19 Nov 2026 this email sent a candidate to Frappe to set a
	password for an account with no roles on it, and pointed them at an LMS
	account they had no way to open. The activation link existed -- it went
	into the officer's report and nowhere else.
	"""

	def setUp(self):
		frappe.set_user("Administrator")

	def _application(self):
		from sibbcs.admissions.doctype.admission_application.test_admission_application import (
			make_application,
		)

		tag = frappe.generate_hash(length=6)
		return make_application(full_name=f"Invite {tag}", email=f"invite.{tag}@example.invalid")

	def _send(self, doc, activation="https://lms.test/activate?token=abc", reissue=None):
		sent = []
		posts = {"activationUrl": activation}
		with patch.dict(frappe.conf, {"entrance_exam_url": EXAM_URL}), patch.object(
			lms_account.campus_lms, "configured", return_value=True
		), patch.object(
			lms_account.campus_lms, "_post", return_value=posts
		), patch.object(
			lms_account.campus_lms,
			"reissue_activation_link",
			return_value=reissue if reissue is not None else {"error": "not asked"},
		), patch(
			"sibbcs.admissions.notifications.outgoing_configured", return_value=True
		), patch(
			"frappe.sendmail", side_effect=lambda **kw: sent.append(kw)
		):
			report = lms_account.create_and_send(doc.name, send=True)
		return report, sent

	def test_the_button_opens_the_lms_account(self):
		report, sent = self._send(self._application())

		self.assertEqual(len(sent), 1)
		self.assertIn("https://lms.test/activate?token=abc", sent[0]["message"])
		self.assertEqual(report["activation_link"], "https://lms.test/activate?token=abc")

	def test_no_frappe_password_link_goes_out(self):
		_report, sent = self._send(self._application())
		self.assertNotIn("/update-password", sent[0]["message"])

	def test_the_exam_link_is_still_there(self):
		_report, sent = self._send(self._application())
		self.assertIn(EXAM_URL, sent[0]["message"])

	def test_it_says_the_link_expires(self):
		"""Seven days, and after that the candidate has no self-service route:
		Campus LMS Lite's Forgot password serves an account that is already
		active, not one that was never opened.
		"""
		_report, sent = self._send(self._application())
		self.assertIn("7 days", sent[0]["message"])

	def test_a_repeat_asks_the_lms_for_a_fresh_link(self):
		"""`/sync/people` issues one only on creation -- a second token
		invalidates the first, so a routine re-sync would break the link the
		candidate was about to use.
		"""
		doc = self._application()
		report, sent = self._send(
			doc, activation=None, reissue={"url": "https://lms.test/activate?token=second"}
		)

		self.assertEqual(report["activation_link"], "https://lms.test/activate?token=second")
		self.assertIn("token=second", sent[0]["message"])

	def test_half_an_invitation_is_not_sent(self):
		"""Telling somebody to sit an exam and giving them no way into the
		account it is sat under is worse than sending nothing.
		"""
		doc = self._application()
		report, sent = self._send(
			doc, activation=None, reissue={"error": "Campus LMS has no account for this applicant yet."}
		)

		self.assertEqual(sent, [])
		self.assertIsNone(report["emailed"])
		self.assertIn(
			"Campus LMS has no account for this applicant yet.", report["warnings"]
		)
		self.assertIn(
			"No Campus LMS activation link, so the invitation was not sent.",
			report["warnings"],
		)

	def test_the_frappe_account_is_still_made(self):
		"""Conversion adopts it at onboarding, so one person keeps one login
		either side. It is simply never emailed about.
		"""
		doc = self._application()
		report, _sent = self._send(doc)
		self.assertTrue(report["user"])
		self.assertTrue(frappe.db.exists("User", report["user"]))


class TestTheInvitationRendersWithNothingLeftOver(FrappeTestCase):
	"""`render_template` leaves an unknown variable as literal text rather than
	failing, so an Email Template naming a variable the code stopped passing
	sends `{{ password_link }}` to the candidate in place of their link. That
	is exactly what `lms_account_invite` would have done, and nothing would
	have said so until somebody read a delivered email.
	"""

	def setUp(self):
		frappe.set_user("Administrator")

	def test_no_variable_is_left_unreplaced(self):
		from sibbcs.admissions.doctype.admission_application.test_admission_application import (
			make_application,
		)

		tag = frappe.generate_hash(length=6)
		app = make_application(full_name=f"Render {tag}", email=f"render.{tag}@example.invalid")

		sent = []
		with patch.dict(frappe.conf, {"entrance_exam_url": EXAM_URL}), patch.object(
			lms_account.campus_lms,
			"reissue_activation_link",
			return_value={"url": ACTIVATION_URL},
		), patch(
			"sibbcs.admissions.notifications.outgoing_configured", return_value=True
		), patch(
			"frappe.sendmail", side_effect=lambda **kw: sent.append(kw)
		):
			lms_account.create_and_send(app.name, send=True)

		self.assertEqual(len(sent), 1)
		body = sent[0]["message"]
		self.assertNotIn("{{", body)
		self.assertNotIn("}}", body)
		self.assertIn(ACTIVATION_URL, body)
