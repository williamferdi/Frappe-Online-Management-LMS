# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""Pay-then-enrol, and the eight-course promotion gate."""

from unittest.mock import patch

from frappe.utils import cint

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.academic.doctype.course_registration.course_registration import (
	registration_fee_settled,
	require_fee_before_lms,
)
from sibbcs.academic.doctype.level_promotion import level_promotion as promo


class TestFeeGatesLmsAccess(FrappeTestCase):
	"""The course opens when the fee is settled, not when Register is pressed."""

	def test_the_gate_is_on_by_default(self):
		with patch.dict(frappe.conf, {}, clear=False):
			frappe.conf.pop("require_fee_for_lms_access", None)
			self.assertTrue(require_fee_before_lms())

	def test_the_gate_can_be_switched_off(self):
		"""There is no gateway yet; this switch is what keeps a term running."""
		with patch.dict(frappe.conf, {"require_fee_for_lms_access": 0}):
			self.assertFalse(require_fee_before_lms())

	def test_no_invoice_means_not_settled(self):
		"""A missing invoice means the fee run has not caught up, not that
		anybody paid."""
		registration = frappe._dict({"registration_fee_invoice": None})
		with patch.dict(frappe.conf, {"require_fee_for_lms_access": 1}):
			self.assertFalse(registration_fee_settled(registration))

	def test_an_unpaid_invoice_keeps_the_course_shut(self):
		registration = frappe._dict({"registration_fee_invoice": "FEE-TEST-0001"})
		with patch.dict(frappe.conf, {"require_fee_for_lms_access": 1}), patch(
			"frappe.db.get_value", return_value="Unpaid"
		):
			self.assertFalse(registration_fee_settled(registration))

	def test_paid_waived_and_cancelled_all_open_the_course(self):
		registration = frappe._dict({"registration_fee_invoice": "FEE-TEST-0001"})
		for status in ("Paid", "Waived", "Cancelled"):
			with patch.dict(frappe.conf, {"require_fee_for_lms_access": 1}), patch(
				"frappe.db.get_value", return_value=status
			):
				self.assertTrue(
					registration_fee_settled(registration), f"{status} should open the course"
				)

	def test_with_the_gate_off_an_unpaid_registration_still_opens(self):
		registration = frappe._dict({"registration_fee_invoice": None})
		with patch.dict(frappe.conf, {"require_fee_for_lms_access": 0}):
			self.assertTrue(registration_fee_settled(registration))


class TestPromotionGate(FrappeTestCase):
	"""Eight passed courses at the current level, approved by the right people."""

	def test_the_threshold_comes_from_the_program(self):
		program = frappe.db.get_value("Program", {}, "name")
		if not program:
			self.skipTest("no Program in the catalog")

		frappe.db.set_value("Program", program, "courses_per_level", 8, update_modified=False)
		enrollment = frappe.db.get_value("Program Enrollment", {"program": program}, "name")
		if not enrollment:
			self.skipTest("no Program Enrollment to read")

		self.assertEqual(promo.courses_required(enrollment), 8)

		frappe.db.set_value("Program", program, "courses_per_level", 6, update_modified=False)
		self.assertEqual(promo.courses_required(enrollment), 6)

		frappe.db.set_value("Program", program, "courses_per_level", 8, update_modified=False)

	def test_zero_switches_the_gate_off_for_that_program(self):
		program = frappe.db.get_value("Program", {}, "name")
		enrollment = frappe.db.get_value("Program Enrollment", {"program": program}, "name")
		if not enrollment:
			self.skipTest("no Program Enrollment to read")

		frappe.db.set_value("Program", program, "courses_per_level", 0, update_modified=False)
		self.assertEqual(promo.courses_required(enrollment), 0)
		frappe.db.set_value("Program", program, "courses_per_level", 8, update_modified=False)

	def test_the_default_is_eight(self):
		self.assertEqual(promo.DEFAULT_COURSES_PER_LEVEL, 8)

	def test_passes_are_counted_at_the_level_they_were_taken(self):
		"""Not a lifetime total: eight passed at Level 1 must not unlock Level 4."""
		enrollment = frappe.db.get_value("Program Enrollment", {}, "name")
		if not enrollment:
			self.skipTest("no Program Enrollment to read")

		with patch("frappe.db.count", return_value=8) as counter:
			promo.passed_at_level(enrollment, 3)

		filters = counter.call_args[0][1]
		self.assertEqual(filters["level_at_registration"], "3")
		self.assertEqual(filters["passed"], 1)

	# -- who may approve ---------------------------------------------------

	def test_the_named_approvers_are_the_ones_the_college_asked_for(self):
		self.assertIn("Dean", promo.APPROVER_ROLES)
		self.assertIn("Registrar", promo.APPROVER_ROLES)
		self.assertIn("Academic Coordinator", promo.APPROVER_ROLES)

	def test_a_student_may_not_approve_a_promotion(self):
		with patch("frappe.get_roles", return_value=["Student", "LMS Student"]):
			self.assertFalse(promo.may_approve())

	def test_faculty_may_not_approve_a_promotion(self):
		with patch("frappe.get_roles", return_value=["Faculty"]):
			self.assertFalse(promo.may_approve())

	def test_each_named_role_may_approve(self):
		for role in ("Dean", "Registrar", "Academic Coordinator"):
			with patch("frappe.get_roles", return_value=[role]):
				self.assertTrue(promo.may_approve(), f"{role} should be able to promote")

	def test_the_dean_role_exists(self):
		self.assertTrue(
			frappe.db.exists("Role", "Dean"),
			"the college named the Dean as an approver; the role must exist",
		)

	# -- the verdict the Desk list reads -----------------------------------

	def test_eligibility_reports_the_evidence_not_just_a_verdict(self):
		enrollment = frappe.db.get_value("Program Enrollment", {}, "name")
		if not enrollment:
			self.skipTest("no Program Enrollment to read")

		verdict = promo.eligibility(enrollment)
		for key in ("from_level", "to_level", "required", "passed", "eligible", "may_approve"):
			self.assertIn(key, verdict)

	def test_a_student_short_of_the_count_is_told_how_short(self):
		enrollment = frappe.db.get_value("Program Enrollment", {}, "name")
		if not enrollment:
			self.skipTest("no Program Enrollment to read")

		with patch.object(promo, "passed_at_level", return_value=2), patch.object(
			promo, "courses_required", return_value=8
		):
			verdict = promo.eligibility(enrollment)

		self.assertFalse(verdict["eligible"])
		self.assertIn("2", verdict["blocked"])
		self.assertIn("8", verdict["blocked"])

	def test_the_working_list_is_not_readable_by_a_student(self):
		with patch("frappe.get_roles", return_value=["Student"]):
			with self.assertRaises(frappe.PermissionError):
				promo.eligible_for_promotion()


class TestPromotionBoard(FrappeTestCase):
	"""The Dean's page reads one function; it has to be right and cheap."""

	def test_a_student_cannot_open_the_board(self):
		with patch("frappe.get_roles", return_value=["Student"]):
			with self.assertRaises(frappe.PermissionError):
				promo.promotion_board()

	def test_each_named_approver_can_open_it(self):
		for role in ("Dean", "Registrar", "Academic Coordinator"):
			with patch("frappe.get_roles", return_value=[role]):
				promo.promotion_board(limit=5)

	def test_every_row_carries_what_the_page_draws(self):
		rows = promo.promotion_board(include_blocked=1, limit=20)
		if not rows:
			self.skipTest("no active enrollments to report on")

		for row in rows:
			for key in (
				"program_enrollment", "student", "student_name", "program",
				"from_level", "to_level", "required", "passed", "eligible", "blocked",
			):
				self.assertIn(key, row)

	def test_blocked_rows_are_hidden_unless_asked_for(self):
		visible = promo.promotion_board(include_blocked=0, limit=50)
		self.assertTrue(
			all(row["eligible"] for row in visible),
			"a student who is not ready appeared on the default list",
		)

	def test_showing_blocked_can_only_add_rows(self):
		ready = promo.promotion_board(include_blocked=0, limit=50)
		everyone = promo.promotion_board(include_blocked=1, limit=50)
		self.assertGreaterEqual(len(everyone), len(ready))

	def test_the_board_agrees_with_the_single_record_verdict(self):
		"""The aggregate query is an optimisation; it must not change answers."""
		rows = promo.promotion_board(include_blocked=1, limit=10)
		if not rows:
			self.skipTest("no active enrollments to compare")

		for row in rows:
			verdict = promo.eligibility(row["program_enrollment"])
			self.assertEqual(
				row["eligible"],
				verdict["eligible"],
				f"{row['program_enrollment']}: board and eligibility() disagree",
			)
			self.assertEqual(row["passed"], verdict["passed"])
			self.assertEqual(row["required"], verdict["required"])

	def test_a_new_program_gets_the_default_threshold(self):
		"""The field is NOT NULL with a default of 8, so there is no unset state --
		only a number somebody chose. Zero therefore always means zero."""
		meta = frappe.get_meta("Program")
		field = next(df for df in meta.fields if df.fieldname == "courses_per_level")
		self.assertEqual(cint(field.default), promo.DEFAULT_COURSES_PER_LEVEL)

	def test_an_explicit_zero_reaches_the_board_as_no_requirement(self):
		program = frappe.db.get_value("Program", {}, "name")
		if not program:
			self.skipTest("no Program in the catalog")

		frappe.db.set_value("Program", program, "courses_per_level", 0, update_modified=False)
		try:
			rows = [
				r
				for r in promo.promotion_board(include_blocked=1, limit=50)
				if r["program"] == program
			]
			if not rows:
				self.skipTest("no enrollment on that program")
			self.assertEqual(rows[0]["required"], 0)
		finally:
			frappe.db.set_value(
				"Program", program, "courses_per_level", 8, update_modified=False
			)

	def test_the_board_does_not_query_per_student(self):
		"""Three queries for the college, not three per student."""
		rows = promo.promotion_board(include_blocked=1, limit=50)
		if len(rows) < 2:
			self.skipTest("need at least two enrollments to tell the difference")

		with patch.object(promo, "eligibility", side_effect=AssertionError("per-row call")):
			promo.promotion_board(include_blocked=1, limit=50)


class TestPromotionPage(FrappeTestCase):
	def test_the_page_is_registered_for_the_approvers(self):
		self.assertTrue(frappe.db.exists("Page", "level-promotions"), "the page is missing")

		roles = {row.role for row in frappe.get_doc("Page", "level-promotions").roles}
		for role in ("Dean", "Registrar", "Academic Coordinator"):
			self.assertIn(role, roles, f"{role} cannot open the promotions page")

	def test_the_page_is_not_open_to_students(self):
		roles = {row.role for row in frappe.get_doc("Page", "level-promotions").roles}
		self.assertNotIn("Student", roles)
		self.assertTrue(roles, "a page with no roles is open to everyone")
