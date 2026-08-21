# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""The manual step delivered as an LMS course.

Onboarding is gated on this step, so "acknowledged" has to mean the course was
actually finished. These tests are mostly about the gate refusing.
"""

import itertools
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.admissions import manuals
from sibbcs.admissions.checklist import NO, set_status, status_of
from sibbcs.admissions.test_scholarship import png_data_url

COURSE_TITLE = "Test Orientation Course"
MANUAL = "Test Course Manual"
LESSONS = 3

_seq = itertools.count(1)


def make_course():
	course = frappe.db.get_value("LMS Course", {"title": COURSE_TITLE}, "name")
	if not course:
		from sibbcs.academic.lms_sync import _default_instructor

		doc = frappe.get_doc(
			{
				"doctype": "LMS Course",
				"title": COURSE_TITLE,
				"short_introduction": "For tests.",
				"description": "For tests.",
				"published": 1,
				"instructors": [{"instructor": _default_instructor()}],
			}
		)
		doc.insert(ignore_permissions=True)
		course = doc.name

	chapter = frappe.db.get_value(
		"Course Chapter", {"course": course, "title": "Chapter"}, "name"
	)
	if not chapter:
		chapter_doc = frappe.get_doc(
			{"doctype": "Course Chapter", "course": course, "title": "Chapter"}
		)
		chapter_doc.insert(ignore_permissions=True)
		chapter = chapter_doc.name

	have = frappe.db.count("Course Lesson", {"course": course})
	for index in range(have, LESSONS):
		frappe.get_doc(
			{
				"doctype": "Course Lesson",
				"course": course,
				"chapter": chapter,
				"title": f"Lesson {index + 1}",
				"body": "Read this.",
			}
		).insert(ignore_permissions=True)

	return course


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


def complete_lessons(user, course, count):
	chapter = frappe.db.get_value("Course Chapter", {"course": course}, "name")
	lessons = frappe.get_all(
		"Course Lesson", filters={"course": course}, pluck="name", order_by="creation"
	)
	for lesson in lessons[:count]:
		if frappe.db.exists(
			"LMS Course Progress", {"member": user, "course": course, "lesson": lesson}
		):
			continue
		frappe.get_doc(
			{
				"doctype": "LMS Course Progress",
				"member": user,
				"course": course,
				"chapter": chapter,
				"lesson": lesson,
				"status": "Complete",
			}
		).insert(ignore_permissions=True)


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
		self.assertEqual(manuals.manual_course(MANUAL), self.course)

	def test_a_document_manual_reports_no_course(self):
		frappe.db.set_value("Reading Manual", MANUAL, "delivery", "Document")
		self.assertIsNone(manuals.manual_course(MANUAL))

	def test_a_course_that_has_been_deleted_is_not_a_course(self):
		"""A dangling link must not silently become an ungated manual."""
		frappe.db.set_value("Reading Manual", MANUAL, "lms_course", "no-such-course")
		self.assertIsNone(manuals.manual_course(MANUAL))

	# -- sending ------------------------------------------------------------

	def test_sending_enrolls_the_applicant_in_the_course(self):
		app = admit(make_application())
		self._send(app)

		app.reload()
		self.assertTrue(app.applicant_user)
		self.assertTrue(
			frappe.db.exists(
				"LMS Enrollment", {"member": app.applicant_user, "course": self.course}
			),
			"the candidate was told to take a course they are not enrolled in",
		)

	def test_the_email_carries_both_the_course_and_the_signing_link(self):
		app = admit(make_application())
		_report, sendmail = self._send(app)

		body = sendmail.call_args.kwargs["message"]
		self.assertIn(f"/lms/courses/{self.course}", body)
		self.assertIn("/manual-reading?token=", body)
		self.assertNotIn(":8000", body)
		self.assertNotIn("{{", body)

	def test_enrolling_twice_makes_one_enrollment(self):
		app = admit(make_application())
		self._send(app)
		app.reload()
		manuals.enroll_in_course(app, self.course)

		self.assertEqual(
			frappe.db.count(
				"LMS Enrollment", {"member": app.applicant_user, "course": self.course}
			),
			1,
		)

	# -- progress -----------------------------------------------------------

	def test_progress_counts_completed_lessons(self):
		app = admit(make_application())
		self._send(app)
		app.reload()

		progress = manuals.course_progress(app.name, self.course)
		self.assertEqual(progress["total"], LESSONS)
		self.assertEqual(progress["done"], 0)
		self.assertFalse(progress["complete"])

		complete_lessons(app.applicant_user, self.course, 2)
		progress = manuals.course_progress(app.name, self.course)
		self.assertEqual(progress["done"], 2)
		self.assertFalse(progress["complete"])

		complete_lessons(app.applicant_user, self.course, LESSONS)
		self.assertTrue(manuals.course_progress(app.name, self.course)["complete"])

	def test_an_applicant_with_no_account_has_no_progress(self):
		app = make_application()
		progress = manuals.course_progress(app.name, self.course)
		self.assertEqual(progress["done"], 0)
		self.assertFalse(progress["complete"])

	# -- the gate ------------------------------------------------------------

	def _token(self, app):
		app.reload()
		return app.manual_acknowledgements[0].token

	def test_signing_is_refused_until_every_lesson_is_done(self):
		app = admit(make_application())
		self._send(app)
		app.reload()
		complete_lessons(app.applicant_user, self.course, LESSONS - 1)

		with self.assertRaises(frappe.ValidationError):
			manuals.acknowledge(self._token(app), "Course Reader", 1, png_data_url())

		app.reload()
		self.assertNotEqual(status_of(app, NO["manual_reading"]), "Acknowledged")

	def test_signing_works_once_the_course_is_complete(self):
		app = admit(make_application())
		self._send(app)
		app.reload()
		complete_lessons(app.applicant_user, self.course, LESSONS)

		manuals.acknowledge(self._token(app), "Course Reader", 1, png_data_url())

		app.reload()
		row = app.manual_acknowledgements[0]
		self.assertTrue(row.acknowledged_on)
		self.assertEqual(row.acknowledged_name, "Course Reader")
		self.assertTrue(row.signature, "the signature was not stored")
		self.assertEqual(status_of(app, NO["manual_reading"]), "Acknowledged")

	def test_the_signature_is_stored_privately(self):
		app = admit(make_application())
		self._send(app)
		app.reload()
		complete_lessons(app.applicant_user, self.course, LESSONS)
		manuals.acknowledge(self._token(app), "Course Reader", 1, png_data_url())

		app.reload()
		signature = app.manual_acknowledgements[0].signature
		self.assertEqual(
			frappe.db.get_value("File", {"file_url": signature}, "is_private"), 1
		)

	def test_a_refused_course_gate_leaves_no_signature_behind(self):
		app = admit(make_application())
		self._send(app)
		app.reload()

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
		self._send(app)
		app.reload()

		self.assertIsNotNone(blocked_reason(app, NO["onboarding"]))

		complete_lessons(app.applicant_user, self.course, LESSONS)
		manuals.acknowledge(self._token(app), "Course Reader", 1, png_data_url())
		app.reload()

		self.assertIsNone(blocked_reason(app, NO["onboarding"]))
