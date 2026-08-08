# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""The eligibility rule engine -- architecture doc §3."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from sibbcs.academic.doctype.academic_term.test_academic_term import make_term
from sibbcs.academic.doctype.course.test_course import make_course
from sibbcs.academic.doctype.course_offering.test_course_offering import make_offering
from sibbcs.academic.doctype.program_enrollment.test_program_enrollment import (
	make_enrollment,
	make_student,
)
from sibbcs.academic.eligibility import (
	check_duplicate,
	check_level,
	check_prerequisites,
	evaluate,
)


class TestLevelRules(FrappeTestCase):
	"""Rules 1-4 as pure functions -- no database involved."""

	def test_rule_1_same_level_always_allowed(self):
		for lvl in (1, 2, 3, 4):
			self.assertTrue(check_level(lvl, lvl), f"level {lvl}")

	def test_rule_2_level_1_student_may_take_level_2(self):
		decision = check_level(1, 2)
		self.assertTrue(decision)
		self.assertEqual(decision.code, "level_1_2_interchangeable")

	def test_rule_2_level_2_student_may_take_level_1(self):
		self.assertTrue(check_level(2, 1))

	def test_rule_3_level_3_student_blocked_from_level_4(self):
		decision = check_level(3, 4)
		self.assertFalse(decision)
		self.assertTrue(decision.hard, "levels 3/4 must be a hard block")
		self.assertEqual(decision.code, "level_3_4_never")

	def test_rule_3_level_4_student_blocked_from_level_3(self):
		decision = check_level(4, 3)
		self.assertFalse(decision)
		self.assertTrue(decision.hard)

	def test_rule_3_is_not_overridable(self):
		"""No override clears the 3/4 rule -- that is the point of `hard`."""
		decision = check_level(3, 4)
		self.assertFalse(decision.needs_override)

	def test_level_2_student_cannot_take_level_3_course(self):
		"""Confirmed decision #5: blocked, override required."""
		decision = check_level(2, 3)
		self.assertFalse(decision)
		self.assertTrue(decision.needs_override)
		self.assertFalse(decision.hard)
		self.assertEqual(decision.code, "level_needs_override")

	def test_level_1_student_cannot_take_level_3_course(self):
		decision = check_level(1, 3)
		self.assertFalse(decision)
		self.assertTrue(decision.needs_override)

	def test_level_1_student_cannot_take_level_4_course(self):
		self.assertFalse(check_level(1, 4))

	def test_level_4_student_may_take_level_1_or_2(self):
		"""{4,1} and {4,2} fall through to rule 4, so they need an override."""
		for course_level in (1, 2):
			decision = check_level(4, course_level)
			self.assertFalse(decision)
			self.assertTrue(decision.needs_override)

	def test_missing_level_is_blocked(self):
		self.assertFalse(check_level(None, 2))
		self.assertFalse(check_level(2, None))

	def test_every_pair_is_decided(self):
		"""No level combination may fall through undecided."""
		for student in (1, 2, 3, 4):
			for course in (1, 2, 3, 4):
				decision = check_level(student, course)
				self.assertIsNotNone(decision.code, f"{student}->{course}")


class TestEligibilityGates(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.term = make_term("TST-ELIG-TERM", status="Open").name

	def _enrollment(self, email, level="1"):
		student = make_student(full_name=f"Elig {email}", email=email)
		enrollment = make_enrollment(student.name)
		frappe.db.set_value(
			"Program Enrollment", enrollment.name, "current_level", level, update_modified=False
		)
		enrollment.reload()
		return enrollment

	def _offering(self, code, level="1", **kw):
		course = make_course(code, level=level)
		kw.setdefault("status", "Published")
		return make_offering(course.name, self.term, **kw)

	def test_allows_a_clean_same_level_registration(self):
		enrollment = self._enrollment("elig1@example.com", level="1")
		offering = self._offering("TST E100", level="1")
		decision, _warnings = evaluate(enrollment.name, offering.name)
		self.assertTrue(decision, decision.reason)

	def test_blocks_level_2_student_from_level_3_offering(self):
		enrollment = self._enrollment("elig2@example.com", level="2")
		offering = self._offering("TST E110", level="3")
		decision, _warnings = evaluate(enrollment.name, offering.name)
		self.assertFalse(decision)
		self.assertTrue(decision.needs_override)

	def test_override_clears_a_soft_level_block(self):
		enrollment = self._enrollment("elig3@example.com", level="2")
		offering = self._offering("TST E111", level="3")
		# Administrator holds an override role in tests
		decision, warnings = evaluate(enrollment.name, offering.name, has_override=True)
		self.assertTrue(decision, decision.reason)
		self.assertTrue(any("Overridden" in w for w in warnings))

	def test_override_does_not_clear_the_3_4_rule(self):
		enrollment = self._enrollment("elig4@example.com", level="3")
		offering = self._offering("TST E120", level="4")
		decision, _warnings = evaluate(enrollment.name, offering.name, has_override=True)
		self.assertFalse(decision, "levels 3/4 must stay blocked even with an override")

	def test_draft_offering_is_not_open(self):
		enrollment = self._enrollment("elig5@example.com")
		offering = self._offering("TST E130", status="Draft")
		decision, _warnings = evaluate(enrollment.name, offering.name)
		self.assertFalse(decision)
		self.assertEqual(decision.code, "offering_not_open")

	def test_full_offering_is_blocked(self):
		enrollment = self._enrollment("elig6@example.com")
		offering = self._offering("TST E140", capacity=1)
		frappe.db.set_value(
			"Course Offering", offering.name, "enrolled_count", 1, update_modified=False
		)
		decision, _warnings = evaluate(enrollment.name, offering.name)
		self.assertFalse(decision)
		self.assertEqual(decision.code, "offering_full")

	def test_closed_term_is_blocked(self):
		enrollment = self._enrollment("elig7@example.com")
		closed = make_term("TST-ELIG-CLOSED", status="Open")
		course = make_course("TST E150", level="1")
		offering = make_offering(course.name, closed.name, status="Published")
		frappe.db.set_value("Academic Term", closed.name, "status", "Closed", update_modified=False)

		decision, _warnings = evaluate(enrollment.name, offering.name)
		self.assertFalse(decision)
		self.assertEqual(decision.code, "term_closed")

	def test_inactive_enrollment_is_blocked(self):
		enrollment = self._enrollment("elig8@example.com")
		frappe.db.set_value(
			"Program Enrollment", enrollment.name, "status", "Withdrawn", update_modified=False
		)
		offering = self._offering("TST E160")
		decision, _warnings = evaluate(enrollment.name, offering.name)
		self.assertFalse(decision)
		self.assertEqual(decision.code, "enrollment_inactive")

	def test_hard_prerequisite_blocks(self):
		enrollment = self._enrollment("elig9@example.com")
		prereq = make_course("TST E170", level="1")
		course = make_course("TST E171", level="1")
		course.append("course_prerequisites", {"prerequisite_course": prereq.name, "is_hard": 1})
		course.save(ignore_permissions=True)

		decision = check_prerequisites(enrollment.name, course.name)
		self.assertFalse(decision)
		self.assertEqual(decision.code, "prerequisite_missing")

	def test_soft_prerequisite_does_not_block(self):
		enrollment = self._enrollment("elig10@example.com")
		prereq = make_course("TST E180", level="1")
		course = make_course("TST E181", level="1")
		course.append("course_prerequisites", {"prerequisite_course": prereq.name, "is_hard": 0})
		course.save(ignore_permissions=True)

		self.assertTrue(check_prerequisites(enrollment.name, course.name))

	def test_duplicate_pass_is_blocked_hard(self):
		"""Stops a Level 1 student re-taking a Level 2 course after promotion."""
		enrollment = self._enrollment("elig11@example.com")
		course = make_course("TST E190", level="1")
		offering = make_offering(course.name, self.term, status="Published")

		registration = frappe.get_doc(
			{
				"doctype": "Course Registration",
				"program_enrollment": enrollment.name,
				"course_offering": offering.name,
				"registration_date": today(),
				"status": "Registered",
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value(
			"Course Registration",
			registration.name,
			{"passed": 1, "status": "Completed"},
			update_modified=False,
		)

		decision = check_duplicate(enrollment.name, course.name)
		self.assertFalse(decision)
		self.assertTrue(decision.hard)
		self.assertEqual(decision.code, "already_passed")

	def test_in_progress_course_cannot_be_registered_twice(self):
		enrollment = self._enrollment("elig12@example.com")
		course = make_course("TST E200", level="1")
		offering = make_offering(course.name, self.term, status="Published")

		frappe.get_doc(
			{
				"doctype": "Course Registration",
				"program_enrollment": enrollment.name,
				"course_offering": offering.name,
				"registration_date": today(),
				"status": "Registered",
			}
		).insert(ignore_permissions=True)

		decision = check_duplicate(enrollment.name, course.name)
		self.assertFalse(decision)
		self.assertEqual(decision.code, "already_registered")
