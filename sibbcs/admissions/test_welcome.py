# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""The letter a new student gets, and the link in it that has to work.

Two faults, reported together on 20 Nov 2026. Onboarding emailed nobody, so a
candidate admitted on Tuesday was given a Student number, a programme and a
level and told none of it. And every password link this site sends carried
`:8000`, the dev webserver's port, which nothing outside the box answers on --
so the one link that would have let them in timed out in the browser.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.admissions import welcome
from sibbcs.overrides.user import external

HOST = {"host_name": "https://online.example.invalid"}
# The live site exactly: a host_name that is right, and a webserver_port that
# `get_url` appends to it regardless -- which it does unless bench is run by
# supervisor or systemd, and this one is neither.
PORTED = {
	"host_name": "https://online.example.invalid",
	"webserver_port": 8000,
	"restart_supervisor_on_update": False,
	"restart_systemd_on_update": False,
}


def _user(email):
	if frappe.db.exists("User", email):
		return frappe.get_doc("User", email)
	return frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": "Welcome Test",
			"user_type": "Website User",
			"send_welcome_email": 0,
		}
	).insert(ignore_permissions=True)


class TestThePasswordLinkResolves(FrappeTestCase):
	"""`sibbcs.overrides.user` -- the one method all three password mails
	pass through."""

	def test_the_host_is_the_one_the_college_publishes(self):
		with patch.dict(frappe.conf, HOST):
			self.assertEqual(
				external("https://online.example.invalid:8000/update-password?key=abc"),
				"https://online.example.invalid/update-password?key=abc",
			)

	def test_the_key_is_carried_over_untouched(self):
		"""Only the host is replaced. The key is Frappe's, and a link whose
		key was mangled is the same dead end by a different route."""
		with patch.dict(frappe.conf, HOST):
			link = external("http://localhost:8000/update-password?key=a.b-c_d&x=1")

		self.assertIn("key=a.b-c_d", link)
		self.assertIn("x=1", link)

	def test_an_expired_password_keeps_its_flag(self):
		with patch.dict(frappe.conf, HOST):
			link = external(
				"https://x:8000/update-password?key=abc&password_expired=true"
			)

		self.assertIn("password_expired=true", link)

	def test_nothing_in_gives_nothing_out(self):
		self.assertIsNone(external(None))
		self.assertEqual(external(""), "")

	def test_a_reset_link_carries_no_port(self):
		"""End to end, with the site configured the way the live one is: a
		host_name that is right and a webserver_port that `get_url` appends to
		it anyway."""
		user = _user(f"pw.{frappe.generate_hash(length=6)}@example.invalid")

		with patch.dict(frappe.conf, PORTED):
			link = user._reset_password(send_email=False)

		self.assertNotIn(":8000", link)
		self.assertTrue(link.startswith("https://online.example.invalid/update-password?key="))

	def test_the_class_frappe_builds_is_ours(self):
		"""`override_doctype_class` in hooks. Without it everything above is
		tested on a class nothing instantiates."""
		from sibbcs.overrides.user import SIBBCSUser

		self.assertIsInstance(
			_user(f"cls.{frappe.generate_hash(length=6)}@example.invalid"), SIBBCSUser
		)

	def test_the_mail_carries_the_corrected_link(self):
		"""Not just the return value: the forgot-password form never sees it,
		and the mail is the whole of what the student gets."""
		user = _user(f"mail.{frappe.generate_hash(length=6)}@example.invalid")

		with patch.dict(frappe.conf, PORTED):
			with patch.object(type(user), "password_reset_mail") as mail:
				user._reset_password(send_email=True)

		mail.assert_called_once()
		self.assertNotIn(":8000", mail.call_args.args[0])


class TestTheWelcomeLetter(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.email = f"new.{frappe.generate_hash(length=6)}@example.invalid"
		cls.user = _user(cls.email).name
		cls.student = frappe.get_doc(
			{
				"doctype": "Student",
				"full_name": "Welcome Test Student",
				"email": cls.email,
				"user": cls.user,
				"status": "Active",
			}
		).insert(ignore_permissions=True)
		cls.enrollment = frappe.get_doc(
			{
				"doctype": "Program Enrollment",
				"student": cls.student.name,
				"program": "MDIV",
				"enrollment_date": frappe.utils.today(),
				"current_level": "2",
				"status": "Active",
			}
		).insert(ignore_permissions=True).name

	def _context(self):
		with patch.dict(frappe.conf, PORTED):
			return welcome.context_for(self.student, self.enrollment, self.user)

	def test_it_names_the_portal(self):
		"""The college asked for `online.sibbc.org/portal` by name. Desk is
		not where a student goes."""
		self.assertEqual(
			self._context()["portal_url"], "https://online.example.invalid/portal"
		)

	def test_it_carries_a_password_link_and_never_a_password(self):
		context = self._context()

		self.assertIn("/update-password?key=", context["password_url"])
		# A password in an inbox is a password in an inbox for ever, and it
		# would make the Admissions Office the keeper of every student's.
		self.assertNotIn("password", context)

	def test_no_address_in_it_carries_the_dev_port(self):
		for key in ("portal_url", "password_url"):
			self.assertNotIn(":8000", self._context()[key], key)

	def test_it_says_who_they_now_are(self):
		context = self._context()

		self.assertEqual(context["student_id"], self.student.name)
		self.assertEqual(context["level"], "2")
		self.assertEqual(context["login_email"], self.user)

	def test_the_learning_site_paragraph_is_left_out_when_there_is_none(self):
		with patch.dict(frappe.conf, {"campus_lms_url": "", "campus_lms_token": ""}):
			self.assertIsNone(self._context()["lms_url"])

	def test_it_is_sent(self):
		with patch.dict(frappe.conf, PORTED):
			with patch.object(frappe, "sendmail") as sendmail:
				sent = welcome.send(self.student, self.enrollment, self.user)

		self.assertEqual(sent, self.email)
		self.assertEqual(sendmail.call_args.kwargs["recipients"], [self.email])

	def test_a_mail_server_that_is_down_does_not_undo_an_enrolment(self):
		"""This runs inside the transaction that creates the Student. It
		reports the failure and returns; it never raises."""
		with patch.dict(frappe.conf, PORTED):
			with patch.object(frappe, "sendmail", side_effect=Exception("no smtp")):
				with patch.object(frappe, "log_error") as log:
					self.assertIsNone(welcome.send(self.student, self.enrollment, self.user))

		log.assert_called_once()

	def test_a_student_with_no_address_is_not_written_to(self):
		student = frappe.get_doc(
			{"doctype": "Student", "full_name": "No Address", "status": "Active"}
		).insert(ignore_permissions=True)

		with patch.object(frappe, "sendmail") as sendmail:
			self.assertIsNone(welcome.send(student, self.enrollment, self.user))

		sendmail.assert_not_called()


class TestOnboardingSendsIt(FrappeTestCase):
	"""The gap the college reported: somebody admitted was told nothing."""

	def test_conversion_writes_to_the_new_student(self):
		from sibbcs.admissions.conversion import convert
		from sibbcs.admissions.test_conversion import ready_application

		email = f"welcomed.{frappe.generate_hash(length=6)}@example.invalid"
		app = ready_application(email=email, program="MDIV")

		with patch.dict(frappe.conf, PORTED):
			with patch.object(frappe, "sendmail") as sendmail:
				report = convert(app.name)

		self.assertEqual(report["welcomed"], email)
		recipients = [
			call.kwargs.get("recipients") for call in sendmail.call_args_list
		]
		self.assertIn([email], recipients)

	def test_frappe_does_not_send_its_own_welcome_alongside(self):
		"""Two letters saying different things, and a second password link
		that invalidates the first."""
		from sibbcs.admissions.conversion import convert
		from sibbcs.admissions.test_conversion import ready_application

		email = f"single.{frappe.generate_hash(length=6)}@example.invalid"
		app = ready_application(email=email, program="MDIV")

		with patch.dict(frappe.conf, PORTED):
			with patch.object(frappe, "sendmail"):
				report = convert(app.name)

		self.assertEqual(
			frappe.db.get_value("User", report["created"]["user"], "send_welcome_email"), 0
		)
