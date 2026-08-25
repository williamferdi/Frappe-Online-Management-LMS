# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from sibbcs.academic.doctype.academic_term.test_academic_term import make_term
from sibbcs.academic.doctype.course.test_course import make_course
from sibbcs.academic.doctype.course_offering.test_course_offering import make_offering
from sibbcs.academic.doctype.level_promotion.level_promotion import outstanding_level_three
from sibbcs.academic.doctype.program_enrollment.test_program_enrollment import (
	make_enrollment,
	make_student,
)


def make_promotion(enrollment, from_level, to_level, **kw):
	defaults = {
		"doctype": "Level Promotion",
		"program_enrollment": enrollment,
		"from_level": str(from_level),
		"to_level": str(to_level),
	}
	defaults.update(kw)
	return frappe.get_doc(defaults).insert(ignore_permissions=True)


class TestLevelPromotion(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.term = make_term("TST-PROMO-TERM", status="Open").name

	def setUp(self):
		# These test the mechanics of moving a level -- the one-at-a-time rule,
		# the Level 4 gate, the audit trail. The eight-course requirement is
		# tested in test_registration_payment.py; switching it off here keeps
		# each test about one rule.
		for program in frappe.get_all("Program", pluck="name"):
			frappe.db.set_value(
				"Program", program, "courses_per_level", 0, update_modified=False
			)
		self.addCleanup(self._restore_course_counts)

	def _restore_course_counts(self):
		for program in frappe.get_all("Program", pluck="name"):
			frappe.db.set_value(
				"Program", program, "courses_per_level", 8, update_modified=False
			)

	def _enrollment(self, email, level="1"):
		student = make_student(full_name=f"Promo {email}", email=email)
		enrollment = make_enrollment(student.name)
		frappe.db.set_value(
			"Program Enrollment", enrollment.name, "current_level", level, update_modified=False
		)
		enrollment.reload()
		return enrollment

	def _pass_course(self, enrollment, code, level):
		course = make_course(code, level=level)
		offering = make_offering(course.name, self.term, status="Published")
		registration = frappe.get_doc(
			{
				"doctype": "Course Registration",
				"program_enrollment": enrollment.name,
				"course_offering": offering.name,
				"registration_date": today(),
				"status": "Registered",
				"override_reason": "test setup",
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value(
			"Course Registration",
			registration.name,
			{"passed": 1, "status": "Completed"},
			update_modified=False,
		)
		return course

	def test_promotion_moves_the_enrollment_level(self):
		enrollment = self._enrollment("promo1@example.com", level="1")
		make_promotion(enrollment.name, 1, 2)
		enrollment.reload()
		self.assertEqual(enrollment.current_level, "2")

	def test_promotion_records_who_approved_it(self):
		enrollment = self._enrollment("promo2@example.com", level="1")
		promotion = make_promotion(enrollment.name, 1, 2)
		self.assertTrue(promotion.approved_by)
		self.assertTrue(promotion.approved_on)

	def test_from_level_must_match_the_enrollment(self):
		enrollment = self._enrollment("promo3@example.com", level="1")
		with self.assertRaises(frappe.ValidationError):
			make_promotion(enrollment.name, 2, 3)

	def test_same_level_rejected(self):
		enrollment = self._enrollment("promo4@example.com", level="1")
		with self.assertRaises(frappe.ValidationError):
			make_promotion(enrollment.name, 1, 1)

	def test_skipping_a_level_rejected(self):
		enrollment = self._enrollment("promo5@example.com", level="1")
		with self.assertRaises(frappe.ValidationError):
			make_promotion(enrollment.name, 1, 3)

	def test_level_4_blocked_while_level_3_courses_outstanding(self):
		"""§3: all Level 3 courses must be completed and passed first."""
		enrollment = self._enrollment("promo6@example.com", level="3")
		make_course("TST P400", level="3")  # exists, never passed

		with self.assertRaises(frappe.ValidationError):
			make_promotion(enrollment.name, 3, 4)

	def test_outstanding_level_three_lists_unpassed_courses(self):
		enrollment = self._enrollment("promo7@example.com", level="3")
		make_course("TST P410", level="3")
		outstanding = outstanding_level_three(enrollment.name)
		self.assertIn("TST P410", outstanding)

	def test_passed_level_three_course_drops_off_the_outstanding_list(self):
		enrollment = self._enrollment("promo8@example.com", level="3")
		course = self._pass_course(enrollment, "TST P420", "3")
		outstanding = outstanding_level_three(enrollment.name)
		self.assertNotIn(course.name, outstanding)

	def test_promotion_captures_credit_evidence(self):
		enrollment = self._enrollment("promo9@example.com", level="1")
		self._pass_course(enrollment, "TST P430", "1")
		promotion = make_promotion(enrollment.name, 1, 2)
		self.assertEqual(promotion.courses_passed, 1)
		self.assertEqual(promotion.credits_at_promotion, 3)
