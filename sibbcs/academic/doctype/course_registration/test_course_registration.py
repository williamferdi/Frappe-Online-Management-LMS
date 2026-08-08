# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from sibbcs.academic.doctype.academic_term.test_academic_term import make_term
from sibbcs.academic.doctype.course.test_course import make_course
from sibbcs.academic.doctype.course_offering.test_course_offering import make_offering
from sibbcs.academic.doctype.course_registration.course_registration import (
	compute_cgpa,
	completed_registrations,
	credits_earned,
	refresh_enrollment_progress,
)
from sibbcs.academic.doctype.program_enrollment.test_program_enrollment import (
	make_enrollment,
	make_student,
)


def make_registration(enrollment, offering, **kw):
	defaults = {
		"doctype": "Course Registration",
		"program_enrollment": enrollment,
		"course_offering": offering,
		"registration_date": today(),
		"status": "Registered",
	}
	defaults.update(kw)
	return frappe.get_doc(defaults).insert(ignore_permissions=True)


class TestCourseRegistration(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.term = make_term("TST-REG-TERM", status="Open").name

	def _setup(self, email, level="1", course_level="1", code=None, **offering_kw):
		student = make_student(full_name=f"Reg {email}", email=email)
		enrollment = make_enrollment(student.name)
		frappe.db.set_value(
			"Program Enrollment", enrollment.name, "current_level", level, update_modified=False
		)
		course = make_course(code or f"TST R{abs(hash(email)) % 900 + 100}", level=course_level)
		offering = make_offering(course.name, self.term, status="Published", **offering_kw)
		return enrollment, offering

	def test_registration_is_named_enrollment_dash_offering(self):
		enrollment, offering = self._setup("reg1@example.com", code="TST R300")
		registration = make_registration(enrollment.name, offering.name)
		self.assertEqual(registration.name, f"{enrollment.name}-{offering.name}")

	def test_fetches_course_term_and_credits(self):
		enrollment, offering = self._setup("reg2@example.com", code="TST R310")
		registration = make_registration(enrollment.name, offering.name)
		registration.reload()
		self.assertEqual(registration.term, self.term)
		self.assertEqual(registration.credits, 3)

	def test_records_the_level_at_registration(self):
		"""Kept for audit -- the student's level may move later."""
		enrollment, offering = self._setup("reg3@example.com", level="2", code="TST R320")
		registration = make_registration(enrollment.name, offering.name)
		self.assertEqual(registration.level_at_registration, "2")

	def test_blocked_registration_raises(self):
		enrollment, offering = self._setup(
			"reg4@example.com", level="2", course_level="3", code="TST R330"
		)
		with self.assertRaises(frappe.ValidationError):
			make_registration(enrollment.name, offering.name)

	def test_override_allows_a_soft_block(self):
		enrollment, offering = self._setup(
			"reg5@example.com", level="2", course_level="3", code="TST R340"
		)
		registration = make_registration(
			enrollment.name, offering.name, override_reason="Coordinator approved early entry"
		)
		self.assertEqual(registration.override_by, frappe.session.user)

	def test_override_cannot_clear_the_3_4_rule(self):
		enrollment, offering = self._setup(
			"reg6@example.com", level="3", course_level="4", code="TST R350"
		)
		with self.assertRaises(frappe.ValidationError):
			make_registration(
				enrollment.name, offering.name, override_reason="please let me through"
			)

	def test_registration_updates_the_offering_count(self):
		enrollment, offering = self._setup("reg7@example.com", code="TST R360")
		make_registration(enrollment.name, offering.name)
		self.assertEqual(
			frappe.db.get_value("Course Offering", offering.name, "enrolled_count"), 1
		)

	def test_withdrawn_registration_frees_the_seat(self):
		enrollment, offering = self._setup("reg8@example.com", code="TST R370")
		registration = make_registration(enrollment.name, offering.name)
		registration.status = "Withdrawn"
		registration.save(ignore_permissions=True)
		self.assertEqual(
			frappe.db.get_value("Course Offering", offering.name, "enrolled_count"), 0
		)


class TestGrading(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.term = make_term("TST-GRADE-TERM", status="Open").name

	def _registration(self, email, code, credits=3):
		student = make_student(full_name=f"Grade {email}", email=email)
		enrollment = make_enrollment(student.name)
		course = make_course(code, level="1", credits=credits)
		offering = make_offering(course.name, self.term, status="Published")
		return enrollment, make_registration(enrollment.name, offering.name)

	def test_weighted_score_per_component(self):
		_enrollment, registration = self._registration("grade1@example.com", "TST G100")
		registration.append(
			"grade_components",
			{"component": "Assignment", "weight_pct": 40, "max_marks": 100, "obtained_marks": 80},
		)
		registration.append(
			"grade_components",
			{"component": "Final Paper", "weight_pct": 60, "max_marks": 100, "obtained_marks": 70},
		)
		registration.save(ignore_permissions=True)

		self.assertEqual(registration.grade_components[0].weighted_score, 32)
		self.assertEqual(registration.grade_components[1].weighted_score, 42)
		self.assertEqual(registration.final_marks, 74)

	def test_partial_marks_do_not_produce_a_grade(self):
		"""A half-marked registration must not show a misleading low score."""
		_enrollment, registration = self._registration("grade2@example.com", "TST G110")
		registration.append(
			"grade_components",
			{"component": "Assignment", "weight_pct": 50, "max_marks": 100, "obtained_marks": 90},
		)
		registration.append(
			"grade_components",
			{"component": "Final Paper", "weight_pct": 50, "max_marks": 100},
		)
		registration.save(ignore_permissions=True)
		self.assertFalse(registration.final_marks)

	def test_pass_mark_is_sixty_without_a_grade_scale(self):
		"""Grade bands are an open decision; fall back to the confirmed 60%."""
		_enrollment, registration = self._registration("grade3@example.com", "TST G120")
		registration.append(
			"grade_components",
			{"component": "Final Paper", "weight_pct": 100, "max_marks": 100, "obtained_marks": 65},
		)
		registration.save(ignore_permissions=True)
		self.assertEqual(registration.final_marks, 65)
		self.assertTrue(registration.passed)

	def test_below_sixty_fails(self):
		_enrollment, registration = self._registration("grade4@example.com", "TST G130")
		registration.append(
			"grade_components",
			{"component": "Final Paper", "weight_pct": 100, "max_marks": 100, "obtained_marks": 55},
		)
		registration.save(ignore_permissions=True)
		self.assertFalse(registration.passed)

	def test_credits_earned_counts_only_passes(self):
		enrollment, registration = self._registration("grade5@example.com", "TST G140", credits=4)
		frappe.db.set_value(
			"Course Registration", registration.name, "passed", 1, update_modified=False
		)
		self.assertEqual(credits_earned(enrollment.name), 4)

	def test_cgpa_is_credit_weighted(self):
		student = make_student(full_name="CGPA Student", email="grade6@example.com")
		enrollment = make_enrollment(student.name)

		for code, credits, points in (("TST G150", 2, 4.0), ("TST G151", 4, 3.0)):
			course = make_course(code, level="1", credits=credits)
			offering = make_offering(course.name, self.term, status="Published")
			registration = make_registration(enrollment.name, offering.name)
			frappe.db.set_value(
				"Course Registration",
				registration.name,
				{"passed": 1, "grade_points": points, "status": "Completed"},
				update_modified=False,
			)

		# (2*4 + 4*3) / 6 = 3.33
		self.assertEqual(compute_cgpa(enrollment.name), 3.33)

	def test_cgpa_is_zero_with_no_passes(self):
		student = make_student(full_name="No Pass", email="grade7@example.com")
		enrollment = make_enrollment(student.name)
		self.assertEqual(compute_cgpa(enrollment.name), 0.0)

	def test_transcript_lists_completed_registrations(self):
		enrollment, registration = self._registration("grade8@example.com", "TST G160")
		frappe.db.set_value(
			"Course Registration",
			registration.name,
			{"status": "Completed", "passed": 1},
			update_modified=False,
		)
		transcript = completed_registrations(enrollment.name)
		self.assertEqual(len(transcript), 1)

	def test_refresh_writes_progress_onto_the_enrollment(self):
		enrollment, registration = self._registration("grade9@example.com", "TST G170", credits=3)
		frappe.db.set_value(
			"Course Registration",
			registration.name,
			{"passed": 1, "grade_points": 4.0},
			update_modified=False,
		)
		refresh_enrollment_progress(enrollment.name)
		enrollment.reload()
		self.assertEqual(enrollment.credits_earned, 3)
		self.assertEqual(enrollment.cgpa, 4.0)
