# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""The checklist board payload.

The board is drawn entirely from `checklist.board()`, so everything the form
script relies on has to be in that dict. A missing key does not raise in
JavaScript -- it renders as `undefined` in a cell, which is a quiet way to be
wrong. These tests pin the shape.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.admissions.checklist import ACTIONS, NO, STEPS, board, set_status, update_step

REQUIRED_KEYS = {
	"step_no",
	"step",
	"status",
	"statuses",
	"owner_role",
	"done",
	"done_statuses",
	"blocked",
	"remarks",
	"updated_by",
	"updated_on",
	"action",
}


def baseline_done():
	"""How many steps a brand-new application already counts as complete.

	Not zero: Scholarship Form Review defaults to Not Applicable, which is one
	of its done statuses -- most candidates never ask for one, so the default
	is the finished state rather than a task nobody will do.
	"""
	return sum(1 for step in STEPS if step[3] in step[4])


def make_application(**overrides):
	values = {
		"doctype": "Admission Application",
		"full_name": "Board Candidate",
		"dob": "1992-05-05",
		"gender": "Female",
		"mobile": "9000000914",
		"email": "board.candidate@example.com",
		"program": frappe.db.get_value("Program", {}, "name"),
	}
	values.update(overrides)
	doc = frappe.get_doc(values)
	doc.insert(ignore_permissions=True)
	return doc


class TestChecklistBoard(FrappeTestCase):
	def test_the_board_has_a_row_per_step_in_order(self):
		data = board(make_application().name)

		self.assertEqual(len(data["rows"]), len(STEPS))
		self.assertEqual(
			[r["step_no"] for r in data["rows"]], [s[0] for s in STEPS]
		)

	def test_every_row_carries_what_the_form_script_reads(self):
		data = board(make_application().name)
		for row in data["rows"]:
			missing = REQUIRED_KEYS - set(row)
			self.assertFalse(missing, f"step {row['step_no']} is missing {missing}")

	def test_the_board_carries_progress_and_state(self):
		data = board(make_application().name)

		self.assertEqual(data["progress"]["total"], len(STEPS))
		self.assertEqual(data["progress"]["done"], baseline_done())
		self.assertEqual(data["state"], "Draft")
		self.assertTrue(data["can_write"])

	def test_progress_counts_completed_steps(self):
		app = make_application()
		set_status(app, NO["application_review"], "Approved")
		app.reload()

		data = board(app.name)
		self.assertEqual(data["progress"]["done"], baseline_done() + 1)
		row = next(r for r in data["rows"] if r["step_no"] == NO["application_review"])
		self.assertTrue(row["done"])

	def test_a_blocked_step_says_why(self):
		"""The reason is the tooltip and the line under the select."""
		data = board(make_application().name)

		row = next(r for r in data["rows"] if r["step_no"] == NO["entrance_exam"])
		self.assertTrue(row["blocked"])
		# Name the step, not its number: the number moves when the college
		# reorders, and asserting on it makes a reorder look like a bug.
		self.assertIn("LMS Account Creation", row["blocked"])

	def test_done_statuses_are_what_the_board_greys_out(self):
		"""The board disables exactly the options that would complete a step."""
		data = board(make_application().name)

		row = next(r for r in data["rows"] if r["step_no"] == NO["entrance_exam"])
		self.assertEqual(row["done_statuses"], ["Passed"])
		for status in row["done_statuses"]:
			self.assertIn(status, row["statuses"])

	def test_only_steps_with_something_to_do_carry_an_action(self):
		data = board(make_application().name)

		with_action = {r["step_no"] for r in data["rows"] if r["action"]}
		self.assertEqual(with_action, set(ACTIONS))

		for row in data["rows"]:
			if row["action"]:
				self.assertEqual(row["action"], ACTIONS[row["step_no"]])

	def test_remarks_and_the_audit_stamp_reach_the_board(self):
		app = make_application()
		update_step(app.name, NO["application_review"], "Under Review", remarks="Waiting on the referee.")

		row = next(r for r in board(app.name)["rows"] if r["step_no"] == NO["application_review"])
		self.assertEqual(row["remarks"], "Waiting on the referee.")
		self.assertEqual(row["updated_by"], frappe.session.user)
		self.assertTrue(row["updated_on"])

	def test_moving_a_step_through_the_board_returns_the_new_state(self):
		app = make_application()
		result = update_step(app.name, NO["application_review"], "Approved")

		self.assertEqual(result["step_no"], 1)
		self.assertEqual(result["status"], "Approved")
		self.assertEqual(result["state"], "Draft")

	def test_the_board_refuses_a_move_that_would_jump_a_gate(self):
		"""The select greys these out, but the server is what enforces it."""
		app = make_application()
		with self.assertRaises(frappe.ValidationError):
			update_step(app.name, NO["entrance_exam"], "Passed")

	def test_an_intermediate_status_is_allowed_on_a_blocked_step(self):
		"""Scheduling an exam early is fine; passing it early is not."""
		app = make_application()
		result = update_step(app.name, NO["entrance_exam"], "Scheduled")
		self.assertEqual(result["status"], "Scheduled")

	def test_a_status_that_does_not_belong_to_the_step_is_refused(self):
		app = make_application()
		with self.assertRaises(frappe.ValidationError):
			update_step(app.name, NO["application_review"], "Onboarded")
