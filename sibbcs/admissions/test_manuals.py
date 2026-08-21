# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.admissions import manuals
from sibbcs.admissions.checklist import NO, blocked_reason, set_status, status_of
from sibbcs.admissions.tokens import TokenError, resolve

UNIVERSAL = "Test Universal Manual"
SCOPED = "Test Scoped Manual"


def a_program():
	return frappe.db.get_value("Program", {}, "name")


def another_program():
	names = frappe.get_all("Program", pluck="name", limit=2)
	return names[1] if len(names) > 1 else None


def make_manual(title, programs=None, active=1):
	if frappe.db.exists("Reading Manual", title):
		frappe.delete_doc("Reading Manual", title, force=True, ignore_permissions=True)

	doc = frappe.get_doc(
		{
			"doctype": "Reading Manual",
			"manual_title": title,
			"version": "1",
			"is_active": active,
			"require_scroll": 1,
			"content": "<p>Read me.</p>",
		}
	)
	for program in programs or []:
		doc.append("applies_to_programs", {"program": program})
	doc.insert(ignore_permissions=True)
	return doc.name


def make_application(**overrides):
	values = {
		"doctype": "Admission Application",
		"full_name": "Manual Reader",
		"dob": "1994-02-02",
		"gender": "Female",
		"mobile": "9000000912",
		"email": "manual.reader@example.com",
		"program": a_program(),
	}
	values.update(overrides)
	doc = frappe.get_doc(values)
	doc.insert(ignore_permissions=True)
	return doc


def admit(app):
	"""Take an application to where the manual step becomes reachable.

	Manuals follow the admission decision, so: the LMS account, the exam, the
	fee, then the decision itself.
	"""
	set_status(app, NO["lms_account"], "Link Sent")
	app.reload()
	set_status(app, NO["entrance_exam"], "Passed")
	app.reload()
	app.db_set("admission_fee_paid", 1)
	app.reload()
	set_status(app, NO["admission_fee"], "Paid")
	app.reload()
	set_status(app, NO["decision"], "Admitted")
	app.reload()
	return app


class TestReadingManuals(FrappeTestCase):
	def setUp(self):
		# Reading Manuals are global and this suite leaks records between tests
		# (User inserts commit, which is why every test here uses its own
		# email). Start each test from a known empty set so that what applies
		# to an application is decided by the test, not by the one before it.
		for name in frappe.get_all("Reading Manual", pluck="name"):
			frappe.db.set_value("Reading Manual", name, "is_active", 0)

	# -- which manuals apply ---------------------------------------------

	def test_a_manual_with_no_programs_is_universal(self):
		make_manual(UNIVERSAL)
		self.assertIn(UNIVERSAL, manuals.applicable_manuals(a_program()))

	def test_a_scoped_manual_only_reaches_its_own_programs(self):
		other = another_program()
		if not other:
			self.skipTest("only one Program in the catalog")

		make_manual(SCOPED, programs=[other])
		self.assertNotIn(SCOPED, manuals.applicable_manuals(a_program()))
		self.assertIn(SCOPED, manuals.applicable_manuals(other))

	def test_an_inactive_manual_is_never_applicable(self):
		make_manual(UNIVERSAL, active=0)
		self.assertNotIn(UNIVERSAL, manuals.applicable_manuals(a_program()))

	# -- the gate ---------------------------------------------------------

	def test_manuals_cannot_be_sent_before_the_admission_decision(self):
		make_manual(UNIVERSAL)
		app = make_application()

		self.assertIsNotNone(blocked_reason(app, NO["manual_reading"]))
		with self.assertRaises(frappe.ValidationError):
			manuals.send_manuals(app.name)

	def test_being_admitted_opens_the_step(self):
		make_manual(UNIVERSAL)
		app = admit(make_application())
		self.assertIsNone(blocked_reason(app, NO["manual_reading"]))

	# -- sending ----------------------------------------------------------

	def _send(self, app, force=False):
		with patch(
			"sibbcs.admissions.notifications.outgoing_configured", return_value=True
		), patch("frappe.sendmail") as sendmail:
			report = manuals.send_manuals(app.name, force=force)
		return report, sendmail

	def test_sending_attaches_a_row_per_applicable_manual(self):
		make_manual(UNIVERSAL)
		app = admit(make_application())

		report, sendmail = self._send(app)

		self.assertIn(UNIVERSAL, report["attached"])
		self.assertIn(UNIVERSAL, report["sent"])
		self.assertTrue(sendmail.called)

		app.reload()
		self.assertEqual(len(app.manual_acknowledgements), 1)
		self.assertTrue(app.manual_acknowledgements[0].sent_on)
		self.assertTrue(app.manual_acknowledgements[0].token)

	def test_the_link_is_openable_and_carries_no_dev_port(self):
		make_manual(UNIVERSAL)
		app = admit(make_application())
		_report, sendmail = self._send(app)

		body = sendmail.call_args.kwargs["message"]
		self.assertIn("/manual-reading?token=", body)
		self.assertNotIn(":8000", body)
		self.assertNotIn("{{", body)

	def test_sending_twice_does_not_email_twice(self):
		make_manual(UNIVERSAL)
		app = admit(make_application())

		self._send(app)
		app.reload()
		report, sendmail = self._send(app)

		self.assertEqual(report["sent"], [])
		self.assertFalse(sendmail.called)

	def test_force_resends(self):
		make_manual(UNIVERSAL)
		app = admit(make_application())

		self._send(app)
		app.reload()
		report, sendmail = self._send(app, force=True)

		self.assertIn(UNIVERSAL, report["sent"])
		self.assertTrue(sendmail.called)

	def test_no_applicable_manual_is_a_warning_not_a_crash(self):
		for title in (UNIVERSAL, SCOPED):
			if frappe.db.exists("Reading Manual", title):
				frappe.db.set_value("Reading Manual", title, "is_active", 0)

		app = admit(make_application())
		with patch("frappe.sendmail") as sendmail:
			report = manuals.send_manuals(app.name)

		self.assertFalse(sendmail.called)
		self.assertTrue(report["warnings"])
		self.assertEqual(status_of(app, NO["manual_reading"]), "Awaiting")

	def test_the_step_moves_to_sent(self):
		make_manual(UNIVERSAL)
		app = admit(make_application())
		self._send(app)

		app.reload()
		self.assertEqual(status_of(app, NO["manual_reading"]), "Sent")

	# -- acknowledging -----------------------------------------------------

	def _acknowledge(self, app, index=0, name="Manual Reader"):
		app.reload()
		token = app.manual_acknowledgements[index].token
		return manuals.acknowledge(token, name, 1)

	def test_acknowledging_records_the_name_they_typed(self):
		make_manual(UNIVERSAL)
		app = admit(make_application())
		self._send(app)

		# Deliberately different from full_name: what they typed is the record.
		self._acknowledge(app, name="M. Reader")

		app.reload()
		row = app.manual_acknowledgements[0]
		self.assertTrue(row.acknowledged_on)
		self.assertEqual(row.acknowledged_name, "M. Reader")

	def test_an_unticked_box_is_refused(self):
		make_manual(UNIVERSAL)
		app = admit(make_application())
		self._send(app)
		app.reload()
		token = app.manual_acknowledgements[0].token

		with self.assertRaises(frappe.ValidationError):
			manuals.acknowledge(token, "Manual Reader", 0)

	def test_a_name_that_is_not_a_name_is_refused(self):
		make_manual(UNIVERSAL)
		app = admit(make_application())
		self._send(app)
		app.reload()
		token = app.manual_acknowledgements[0].token

		with self.assertRaises(frappe.ValidationError):
			manuals.acknowledge(token, "  x ", 1)

	def test_a_token_is_spent_on_use(self):
		make_manual(UNIVERSAL)
		app = admit(make_application())
		self._send(app)
		app.reload()
		token = app.manual_acknowledgements[0].token

		manuals.acknowledge(token, "Manual Reader", 1)
		with self.assertRaises(TokenError):
			manuals.acknowledge(token, "Manual Reader", 1)

	def test_a_reference_token_cannot_open_a_manual(self):
		make_manual(UNIVERSAL)
		app = admit(
			make_application(
				reference_requests=[
					{"referee_name": "Ref One", "referee_email": "ref.one@example.com"}
				]
			)
		)
		app.reload()
		foreign = app.reference_requests[0].token

		with self.assertRaises(TokenError):
			resolve("manual-reading", foreign)

	def test_step_12_reaches_acknowledged_only_when_every_manual_is_in(self):
		other = another_program()
		make_manual(UNIVERSAL)
		make_manual(SCOPED, programs=[a_program()] if other else None)

		app = admit(make_application())
		self._send(app)
		app.reload()
		self.assertEqual(len(app.manual_acknowledgements), 2)

		self._acknowledge(app, index=0)
		app.reload()
		self.assertEqual(
			status_of(app, NO["manual_reading"]), "Sent", "one manual out of two counted as read"
		)

		self._acknowledge(app, index=1)
		app.reload()
		self.assertEqual(status_of(app, NO["manual_reading"]), "Acknowledged")

	def test_the_step_does_not_walk_backwards(self):
		make_manual(UNIVERSAL)
		app = admit(make_application())
		self._send(app)
		self._acknowledge(app)
		app.reload()
		self.assertEqual(status_of(app, NO["manual_reading"]), "Acknowledged")

		# A manual added afterwards must not undo the recorded acknowledgement.
		manuals._set_step(app.name)
		self.assertEqual(status_of(app, NO["manual_reading"]), "Acknowledged")
