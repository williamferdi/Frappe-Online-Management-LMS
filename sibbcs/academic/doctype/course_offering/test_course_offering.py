# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.academic.doctype.academic_term.test_academic_term import make_term
from sibbcs.academic.doctype.course.test_course import make_course


def make_instructor(full_name, **kw):
	existing = frappe.db.get_value("Instructor", {"full_name": full_name})
	if existing:
		return frappe.get_doc("Instructor", existing)

	defaults = {"doctype": "Instructor", "full_name": full_name, "is_active": 1}
	defaults.update(kw)
	return frappe.get_doc(defaults).insert(ignore_permissions=True)


def make_offering(course, term, **kw):
	defaults = {
		"doctype": "Course Offering",
		"course": course,
		"term": term,
		"format": kw.pop("format", "Pre-Recorded"),
	}
	defaults.update(kw)
	return frappe.get_doc(defaults).insert(ignore_permissions=True)


class TestCourseOffering(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.course = make_course("TST O200").name
		cls.term = make_term("TST-TERM-OFF").name

	def test_offering_is_named_course_dash_term(self):
		offering = make_offering(self.course, self.term)
		self.assertEqual(offering.name, f"{self.course}-{self.term}")

	def test_fetches_credits_and_level_from_course(self):
		course = make_course("TST O201", credits=4, level="2")
		offering = make_offering(course.name, self.term)
		offering.reload()
		self.assertEqual(offering.credits, 4)
		self.assertEqual(offering.course_level, "2")

	def test_duplicate_course_and_term_rejected(self):
		course = make_course("TST O210")
		make_offering(course.name, self.term)
		with self.assertRaises((frappe.ValidationError, frappe.DuplicateEntryError)):
			make_offering(course.name, self.term)

	def test_zoom_live_requires_days(self):
		course = make_course("TST O220")
		with self.assertRaises(frappe.ValidationError):
			make_offering(course.name, self.term, format="Zoom Live", zoom_time="19:00:00")

	def test_time_fields_are_never_empty_on_insert(self):
		"""Regression guard for a Frappe behaviour that traps validation code.

		frappe/model/create_new.py fills every Time field with nowtime() during
		Document.insert() -> _set_defaults(), unconditionally. So zoom_time is
		always populated and "zoom_time is required" can never be enforced by
		checking emptiness. If this test ever fails, that behaviour changed and
		CourseOffering.validate_format_requirements can be tightened.
		"""
		course = make_course("TST O221")
		offering = make_offering(
			course.name,
			self.term,
			format="Zoom Live",
			zoom_days=[{"weekday": "Monday"}],
		)
		self.assertTrue(offering.zoom_time, "Frappe no longer defaults Time fields")

	def test_zoom_live_with_full_schedule_saves(self):
		course = make_course("TST O222")
		offering = make_offering(
			course.name,
			self.term,
			format="Zoom Live",
			zoom_days=[{"weekday": "Monday"}, {"weekday": "Thursday"}],
			zoom_time="19:00:00",
		)
		self.assertEqual(len(offering.zoom_days), 2)

	def test_negative_capacity_rejected(self):
		course = make_course("TST O230")
		with self.assertRaises(frappe.ValidationError):
			make_offering(course.name, self.term, capacity=-1)

	def test_zero_capacity_means_unlimited(self):
		course = make_course("TST O231")
		offering = make_offering(course.name, self.term, capacity=0)
		self.assertTrue(offering.has_seats_available())

	def test_seats_run_out_at_capacity(self):
		course = make_course("TST O232")
		offering = make_offering(course.name, self.term, capacity=2)
		offering.db_set("enrolled_count", 2, update_modified=False)
		offering.reload()
		self.assertFalse(offering.has_seats_available())

	def test_capacity_cannot_drop_below_enrolled(self):
		course = make_course("TST O233")
		offering = make_offering(course.name, self.term, capacity=10)
		offering.db_set("enrolled_count", 5, update_modified=False)
		offering.reload()
		offering.capacity = 3
		with self.assertRaises(frappe.ValidationError):
			offering.save(ignore_permissions=True)

	def test_inactive_instructor_rejected(self):
		course = make_course("TST O240")
		instructor = make_instructor("Test Retired Instructor", is_active=0)
		with self.assertRaises(frappe.ValidationError):
			make_offering(course.name, self.term, instructor=instructor.name)

	def test_non_facilitator_rejected_as_facilitator(self):
		course = make_course("TST O241")
		instructor = make_instructor("Test Plain Instructor", is_facilitator=0)
		with self.assertRaises(frappe.ValidationError):
			make_offering(course.name, self.term, facilitator=instructor.name)

	def test_facilitator_accepted_when_flagged(self):
		course = make_course("TST O242")
		instructor = make_instructor("Test Real Facilitator", is_facilitator=1)
		offering = make_offering(course.name, self.term, facilitator=instructor.name)
		self.assertEqual(offering.facilitator, instructor.name)

	def test_closed_term_rejects_new_offerings(self):
		course = make_course("TST O250")
		closed = make_term("TST-TERM-CLOSED", status="Closed")
		with self.assertRaises(frappe.ValidationError):
			make_offering(course.name, closed.name)
