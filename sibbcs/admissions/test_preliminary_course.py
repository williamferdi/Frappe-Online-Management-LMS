# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""The manual step delivered as an LMS course.

Onboarding is gated on this step, so "acknowledged" has to mean the course was
actually finished. These tests are mostly about the gate refusing.

**The course is Campus LMS Lite's now.** Phase 7 removed the lesson counting on
this side, so there is no progress to arrange by inserting rows: what these
tests arrange is what that system would answer, through `lms_says`. The fixture
still builds a course in the bundled app because `Reading Manual.lms_course` is
a Link to it, and that is the last thing holding that app in place.
"""

import itertools
from contextlib import contextmanager
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.admissions import manuals
from sibbcs.admissions.checklist import NO, set_status, status_of
from sibbcs.admissions.test_scholarship import png_data_url
from sibbcs.integrations import campus_lms

COURSE_TITLE = "Test Orientation Course"
MANUAL = "Test Course Manual"
LESSONS = 3
EXTERNAL = "ADMISSIONS-ORIENTATION"
LIVE_LMS = {"campus_lms_url": "https://lms.example.invalid", "campus_lms_token": "t"}


@contextmanager
def lms_says(done=0, total=LESSONS, external=EXTERNAL, enrol=True):
	"""Treat the fixture course as moved, and say how far along the candidate is.

	`course_for` is patched rather than naming a real moved slug, so these
	tests do not depend on which courses happen to be in `MOVED_COURSES`.
	`enrol=False` makes it an unmapped course, which is the configuration error
	the gate has to fail closed on.
	"""
	resolved = external if enrol else None
	answer = {
		"required": total,
		"completed": done,
		"complete": bool(total) and done >= total,
	}
	with patch.dict(frappe.conf, LIVE_LMS):
		with patch.object(campus_lms, "course_for", return_value=resolved):
			with patch.object(campus_lms, "progress", return_value=answer):
				with patch.object(campus_lms, "enrol_in_course", return_value={}) as enrolled:
					yield enrolled

_seq = itertools.count(1)


def make_course():
	"""The course slug a Reading Manual names.

	It used to build a real course in the bundled `lms` app, because
	`Reading Manual.lms_course` was a Link to it. Phase 7 uninstalled that app
	and the field is Data now -- a slug that `campus_lms.MOVED_COURSES`
	resolves -- so there is nothing to build. `lms_says` patches `course_for`,
	so the slug only has to be stable.
	"""
	return "test-orientation-course"


def make_manual(course):
	if frappe.db.exists("Reading Manual", MANUAL):
		frappe.db.set_value(
			"Reading Manual",
			MANUAL,
			{"is_active": 1, "delivery": "LMS Course", "lms_course": course},
			update_modified=False,
		)
		return MANUAL

	frappe.get_doc(
		{
			"doctype": "Reading Manual",
			"manual_title": MANUAL,
			"version": "1",
			"is_active": 1,
			"require_scroll": 0,
			"delivery": "LMS Course",
			"lms_course": course,
			"content": "<p>Orientation.</p>",
		}
	).insert(ignore_permissions=True)
	return MANUAL


def make_application(**overrides):
	values = {
		"doctype": "Admission Application",
		"full_name": "Course Reader",
		"dob": "1992-12-12",
		"gender": "Male",
		"mobile": "9000000918",
		"email": f"course.reader{next(_seq)}@example.com",
		"program": frappe.db.get_value("Program", {}, "name"),
	}
	values.update(overrides)
	doc = frappe.get_doc(values)
	doc.insert(ignore_permissions=True)
	return doc


def admit(app):
	# Step 6 records a sent email, so the fixture sends one: the guard in
	# checklist.EVIDENCE refuses the status on trust, which is the whole
	# reason it exists.
	app.db_set("exam_link_sent_on", frappe.utils.now_datetime(), update_modified=False)
	app.reload()
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


# `complete_lessons` inserted LMS Course Progress rows to arrange how far a
# candidate had got. Progress is read from Campus LMS Lite now, so what gets
# arranged is that system's answer -- see `lms_says` above.


class TestPreliminaryCourse(FrappeTestCase):
	def setUp(self):
		for name in frappe.get_all("Reading Manual", pluck="name"):
			frappe.db.set_value("Reading Manual", name, "is_active", 0)
		self.course = make_course()
		make_manual(self.course)

	def _send(self, app):
		with patch(
			"sibbcs.admissions.notifications.outgoing_configured", return_value=True
		), patch("frappe.sendmail") as sendmail:
			report = manuals.send_manuals(app.name)
		return report, sendmail

	# -- which delivery -----------------------------------------------------

	def test_a_course_backed_manual_reports_its_course(self):
		with lms_says():
			self.assertEqual(manuals.manual_course(MANUAL), self.course)

	def test_a_document_manual_reports_no_course(self):
		frappe.db.set_value("Reading Manual", MANUAL, "delivery", "Document")
		self.assertIsNone(manuals.manual_course(MANUAL))

	def test_a_course_we_cannot_find_over_there_is_not_a_course(self):
		"""An unmapped manual must not silently become an ungated one.

		This used to ask whether the bundled LMS still had the course. Once
		that app goes the answer is False for every manual, so it asks whether
		the course can be found in Campus LMS Lite instead."""
		with lms_says(enrol=False):
			self.assertIsNone(manuals.manual_course(MANUAL))

	# -- sending ------------------------------------------------------------

	def test_sending_enrolls_the_applicant_in_the_course(self):
		app = admit(make_application())
		with lms_says() as enrolled:
			self._send(app)

		app.reload()
		self.assertTrue(app.applicant_user)
		self.assertTrue(
			enrolled.called,
			"the candidate was told to take a course they are not enrolled in",
		)
		self.assertEqual(enrolled.call_args.args[0], app.name)
		self.assertEqual(enrolled.call_args.args[1], EXTERNAL)

	def test_the_email_carries_both_the_course_and_the_signing_link(self):
		app = admit(make_application())
		with lms_says():
			_report, sendmail = self._send(app)

		body = sendmail.call_args.kwargs["message"]
		self.assertIn("/manual-reading?token=", body)
		self.assertNotIn(":8000", body)
		self.assertNotIn("{{", body)

	def test_enrolling_twice_is_harmless(self):
		"""The sync endpoints upsert on externalId, so a second enrolment finds
		the first rather than making another. What this pins is that we do call
		again rather than deciding for ourselves that we need not."""
		app = admit(make_application())
		with lms_says() as enrolled:
			self._send(app)
			app.reload()
			manuals.enroll_in_course(app, self.course)

		keys = {call.args[0] for call in enrolled.call_args_list}
		self.assertEqual(keys, {app.name})
		self.assertGreaterEqual(enrolled.call_count, 2)

	# -- progress -----------------------------------------------------------

	def test_progress_is_what_the_lms_reports(self):
		app = admit(make_application())
		with lms_says():
			self._send(app)
		app.reload()

		with lms_says(done=0):
			progress = manuals.course_progress(app.name, self.course)
			self.assertEqual(progress["total"], LESSONS)
			self.assertEqual(progress["done"], 0)
			self.assertFalse(progress["complete"])

		with lms_says(done=2):
			progress = manuals.course_progress(app.name, self.course)
			self.assertEqual(progress["done"], 2)
			self.assertFalse(progress["complete"])

		with lms_says(done=LESSONS):
			self.assertTrue(manuals.course_progress(app.name, self.course)["complete"])

	def test_a_course_we_cannot_find_is_never_complete(self):
		"""Not an error, and not complete either: a signature must never be let
		through on an absence of evidence."""
		app = admit(make_application())
		with lms_says(enrol=False):
			progress = manuals.course_progress(app.name, self.course)

		self.assertEqual(progress["total"], 0)
		self.assertFalse(progress["complete"])

	def test_an_applicant_the_lms_has_not_heard_of_has_no_progress(self):
		app = make_application()
		with patch.dict(frappe.conf, LIVE_LMS):
			with patch.object(campus_lms, "course_for", return_value=EXTERNAL):
				# What `/sync/progress` answers for an unknown person: a 404,
				# which `_get` turns into None rather than raising.
				with patch.object(campus_lms, "progress", return_value=None):
					progress = manuals.course_progress(app.name, self.course)

		self.assertEqual(progress["done"], 0)
		self.assertFalse(progress["complete"])

	# -- the gate ------------------------------------------------------------

	def _token(self, app):
		app.reload()
		return app.manual_acknowledgements[0].token

	def test_signing_is_refused_until_every_lesson_is_done(self):
		app = admit(make_application())
		with lms_says():
			self._send(app)
		app.reload()

		with lms_says(done=LESSONS - 1):
			with self.assertRaises(frappe.ValidationError):
				manuals.acknowledge(self._token(app), "Course Reader", 1, png_data_url())

		app.reload()
		self.assertNotEqual(status_of(app, NO["manual_reading"]), "Acknowledged")

	def test_signing_works_once_the_course_is_complete(self):
		app = admit(make_application())
		with lms_says():
			self._send(app)
		app.reload()

		with lms_says(done=LESSONS):
			manuals.acknowledge(self._token(app), "Course Reader", 1, png_data_url())

		app.reload()
		row = app.manual_acknowledgements[0]
		self.assertTrue(row.acknowledged_on)
		self.assertEqual(row.acknowledged_name, "Course Reader")
		self.assertTrue(row.signature, "the signature was not stored")
		self.assertEqual(status_of(app, NO["manual_reading"]), "Acknowledged")

	def test_the_signature_is_stored_privately(self):
		app = admit(make_application())
		with lms_says():
			self._send(app)
		app.reload()
		with lms_says(done=LESSONS):
			manuals.acknowledge(self._token(app), "Course Reader", 1, png_data_url())

		app.reload()
		signature = app.manual_acknowledgements[0].signature
		self.assertEqual(
			frappe.db.get_value("File", {"file_url": signature}, "is_private"), 1
		)

	def test_a_refused_course_gate_leaves_no_signature_behind(self):
		app = admit(make_application())
		with lms_says():
			self._send(app)
		app.reload()

		with lms_says(done=0):
			try:
				manuals.acknowledge(self._token(app), "Course Reader", 1, png_data_url())
			except frappe.ValidationError:
				pass

		app.reload()
		self.assertFalse(app.manual_acknowledgements[0].signature)
		self.assertFalse(app.manual_acknowledgements[0].acknowledged_on)

	def test_onboarding_stays_blocked_while_the_course_is_unfinished(self):
		from sibbcs.admissions.checklist import blocked_reason

		app = admit(make_application())
		with lms_says():
			self._send(app)
		app.reload()

		self.assertIsNotNone(blocked_reason(app, NO["onboarding"]))

		with lms_says(done=LESSONS):
			manuals.acknowledge(self._token(app), "Course Reader", 1, png_data_url())
		app.reload()

		self.assertIsNone(blocked_reason(app, NO["onboarding"]))


class TestTheMovedCourseEnrolsInCampusLms(FrappeTestCase):
	"""The orientation course lives in Campus LMS Lite now, and progress is
	read from over there. An applicant enrolled only in the bundled app is a
	person that system has never heard of, which reads as nothing done --
	forever -- so their signature could never be let through."""

	LIVE = {"campus_lms_url": "https://lms.example.invalid", "campus_lms_token": "t"}
	MOVED = "m-div-preliminary-orientation"

	def setUp(self):
		for name in frappe.get_all("Reading Manual", pluck="name"):
			frappe.db.set_value("Reading Manual", name, "is_active", 0)
		self.course = make_course()
		make_manual(self.course)

	def test_the_enrolment_goes_to_campus_lms_not_the_bundled_app(self):
		app = admit(make_application())
		with patch.dict(frappe.conf, self.LIVE):
			with patch("sibbcs.integrations.campus_lms.enrol_in_course") as enrol:
				manuals.enroll_in_course(app, self.MOVED)

		self.assertTrue(enrol.called)
		args = enrol.call_args.args
		self.assertEqual(args[0], app.name)
		self.assertEqual(args[1], "ADMISSIONS-ORIENTATION")

	def test_it_is_filed_under_the_application(self):
		"""The applicant has no student number yet; the application number is
		how they are known over there until they are converted."""
		app = admit(make_application())
		with patch.dict(frappe.conf, self.LIVE):
			with patch("sibbcs.integrations.campus_lms._post") as post:
				post.return_value = {}
				manuals.enroll_in_course(app, self.MOVED)

		enrolment = [c for c in post.call_args_list if c.args[0] == "/sync/enrollments"]
		self.assertEqual(len(enrolment), 1)
		sent = enrolment[0].args[1]
		self.assertEqual(sent["personExternalId"], app.name)
		self.assertEqual(sent["courseExternalId"], "ADMISSIONS-ORIENTATION")
		self.assertEqual(sent["externalId"], f"ADMISSIONS-ORIENTATION-{app.name}")
		self.assertEqual(sent["role"], "student")

	def test_the_exam_keeps_its_own_enrolment_key(self):
		"""Every candidate who has sat one already has an `EXAM-` row over
		there; reusing this key shape for the exam would add a second rather
		than find the first."""
		from sibbcs.integrations import campus_lms

		with patch.dict(frappe.conf, self.LIVE):
			with patch("sibbcs.integrations.campus_lms._post") as post:
				post.return_value = {}
				campus_lms.enrol_applicant("APP-0001", "a@example.invalid", "A")

		keys = [c.args[1]["externalId"] for c in post.call_args_list if c.args[0] == "/sync/enrollments"]
		self.assertEqual(keys, ["EXAM-APP-0001"])

	def test_a_course_that_did_not_move_is_reported_not_enrolled_anywhere(self):
		"""Stage B still fell back to the bundled app here. Stage C removed
		that: nobody is taught there, so an unmapped course is a configuration
		problem rather than somewhere to enrol."""
		app = admit(make_application())
		with patch.dict(frappe.conf, self.LIVE):
			with patch("sibbcs.integrations.campus_lms.enrol_in_course") as enrol:
				result = manuals.enroll_in_course(app, self.course)

		self.assertIsNone(result)
		self.assertFalse(enrol.called)
