# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""Every door from this site to the learning site, and where it opens.

There are four, and on 20 Nov 2026 two of them were shut. The orientation
email sent an admitted candidate to `/lms/courses/...` on this site -- the
bundled lms app, which Phase 7 removed -- while the enrolment in the same
letter had gone to Campus LMS Lite. The acknowledgement page carried the same
address. The other two worked but landed everybody on the front door, because
the registrar knew the LMS by our name for a course and not by its own.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.academic.doctype.academic_term.test_academic_term import make_term
from sibbcs.academic.doctype.course.test_course import make_course
from sibbcs.academic.doctype.course_offering.test_course_offering import make_offering
from sibbcs.api import session as session_api
from sibbcs.api import student as student_api
from sibbcs.integrations import campus_lms

LIVE = {"campus_lms_url": "https://lms.example.invalid", "campus_lms_token": "t"}
DARK = {"campus_lms_url": "", "campus_lms_token": ""}


class TestCourseUrl(FrappeTestCase):
	def test_the_front_door_without_an_id(self):
		"""A real answer, not a shrug: the LMS shows a person their courses."""
		with patch.dict(frappe.conf, LIVE):
			self.assertEqual(campus_lms.course_url(), "https://lms.example.invalid")

	def test_the_course_itself_with_one(self):
		with patch.dict(frappe.conf, LIVE):
			self.assertEqual(
				campus_lms.course_url("abc-123"),
				"https://lms.example.invalid/courses/abc-123",
			)

	def test_nothing_at_all_when_no_learning_site_is_configured(self):
		"""None, so a caller writes no link rather than a link to nowhere."""
		with patch.dict(frappe.conf, DARK):
			self.assertIsNone(campus_lms.course_url())
			self.assertIsNone(campus_lms.course_url("abc-123"))

	def test_it_never_points_at_this_site(self):
		"""The bug this was written for: `/lms/courses/...` on online.sibbc.org
		is an address the bundled lms app served, and that app is gone."""
		with patch.dict(frappe.conf, LIVE):
			self.assertNotIn("/lms/courses/", campus_lms.course_url("abc-123"))


class TestRememberingTheCourseId(FrappeTestCase):
	"""The id comes back in what `/sync/courses` answers; keeping it is the
	only way a link can open the course rather than the front door."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.term = make_term(f"TST-DOOR-{frappe.generate_hash(length=6)}").name

	def setUp(self):
		# A fresh course per test: an offering is named `{course}-{term}`, so
		# two on one course in one term are the same document.
		frappe.set_user("Administrator")
		course = make_course(f"TDR {frappe.generate_hash(length=4)[:4]}").name
		self.offering = make_offering(course, self.term).name

	def test_the_id_is_kept(self):
		campus_lms._remember_course_id(
			self.offering, {"created": False, "course": {"id": "uuid-1"}}
		)

		self.assertEqual(
			frappe.db.get_value("Course Offering", self.offering, "lms_course_id"), "uuid-1"
		)

	def test_an_answer_with_no_course_in_it_changes_nothing(self):
		"""`onlyIfPresent` answers `{"created": false, "found": false,
		"course": null}`, and that is not a reason to blank what we knew."""
		campus_lms._remember_course_id(self.offering, {"course": {"id": "uuid-1"}})
		campus_lms._remember_course_id(self.offering, {"created": False, "course": None})

		self.assertEqual(
			frappe.db.get_value("Course Offering", self.offering, "lms_course_id"), "uuid-1"
		)

	def test_an_answer_of_the_wrong_shape_is_passed_over(self):
		"""Another system's answer, and what it sends is what would end up in
		a link handed to a student."""
		for answer in (None, "nope", {"course": "nope"}, {"course": {"id": 7}}):
			campus_lms._remember_course_id(self.offering, answer)

		self.assertIsNone(
			frappe.db.get_value("Course Offering", self.offering, "lms_course_id") or None
		)

	def test_it_does_not_stamp_the_offering_as_edited(self):
		"""This runs inside the push job. Touching `modified` would make every
		offering look edited by the sync it had just set off -- and re-fire
		`on_update`, which enqueues the push again."""
		before = frappe.db.get_value("Course Offering", self.offering, "modified")

		campus_lms._remember_course_id(self.offering, {"course": {"id": "uuid-2"}})

		self.assertEqual(
			frappe.db.get_value("Course Offering", self.offering, "modified"), before
		)

	def test_the_push_keeps_what_the_sync_answered(self):
		with patch.dict(frappe.conf, LIVE):
			with patch.object(
				campus_lms, "_post", return_value={"course": {"id": "uuid-3"}}
			):
				campus_lms.push("Course Offering", self.offering)

		self.assertEqual(
			frappe.db.get_value("Course Offering", self.offering, "lms_course_id"), "uuid-3"
		)


class TestWhereAStudentOpensTheirCourse(FrappeTestCase):
	"""`api.student._lms_links` decides how deep the Open course button goes."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.term = make_term(f"TST-DOOR2-{frappe.generate_hash(length=6)}").name

	def setUp(self):
		frappe.set_user("Administrator")
		course = make_course(f"TDS {frappe.generate_hash(length=4)[:4]}").name
		self.offering = make_offering(course, self.term).name

	def test_straight_to_the_course_once_the_id_is_known(self):
		frappe.db.set_value(
			"Course Offering", self.offering, "lms_course_id", "uuid-9", update_modified=False
		)
		rows = [{"name": "REG-1", "course_offering": self.offering}]

		with patch.dict(frappe.conf, LIVE):
			student_api._lms_links(rows)

		self.assertEqual(rows[0]["lms_url"], "https://lms.example.invalid/courses/uuid-9")

	def test_the_front_door_until_it_is(self):
		"""Blank on every offering until it has been pushed once since this
		landed, and the front door is still somewhere useful to arrive."""
		rows = [{"name": "REG-1", "course_offering": self.offering}]

		with patch.dict(frappe.conf, LIVE):
			student_api._lms_links(rows)

		self.assertEqual(rows[0]["lms_url"], "https://lms.example.invalid")

	def test_no_link_at_all_where_there_is_no_learning_site(self):
		rows = [{"name": "REG-1", "course_offering": self.offering}]

		with patch.dict(frappe.conf, DARK):
			student_api._lms_links(rows)

		self.assertIsNone(rows[0]["lms_url"])

	def test_one_query_however_many_courses_are_on_the_screen(self):
		"""The obvious version reads the offering per row. A student with a
		full term has eight, and this is drawn on every visit to My Courses."""
		rows = [
			{"name": f"REG-{n}", "course_offering": self.offering} for n in range(8)
		]

		with patch.dict(frappe.conf, LIVE):
			with patch.object(
				frappe, "get_all", wraps=frappe.get_all
			) as get_all:
				student_api._lms_links(rows)

		offering_reads = [
			call for call in get_all.call_args_list if call.args and call.args[0] == "Course Offering"
		]
		self.assertEqual(len(offering_reads), 1, offering_reads)


class TestTheShellKnowsWhereTheLearningSiteIs(FrappeTestCase):
	def test_the_session_carries_it(self):
		with patch.dict(frappe.conf, LIVE):
			self.assertEqual(
				session_api.session_payload()["lms_url"], "https://lms.example.invalid"
			)

	def test_it_is_empty_where_none_is_configured(self):
		"""Empty rather than missing: the front end draws no link on '' and
		would have to guard a missing key everywhere instead."""
		with patch.dict(frappe.conf, DARK):
			self.assertEqual(session_api.session_payload()["lms_url"], "")
