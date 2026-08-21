# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""The step numbering contract, and the migration that maintains it.

The college has reordered these steps once and will again. `step_no` is a
position; the key is the identity. These tests pin the invariants that make a
reorder a one-file edit rather than a hunt through five modules.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.admissions.checklist import (
	ACTIONS,
	NO,
	NO_BY_LABEL,
	REQUIRES,
	STEPS,
	statuses_for,
	status_of,
)
from sibbcs.patches.renumber_checklist_steps import execute as renumber


def make_application(**overrides):
	values = {
		"doctype": "Admission Application",
		"full_name": "Order Candidate",
		"dob": "1989-09-09",
		"gender": "Male",
		"mobile": "9000000917",
		"email": "order.candidate@example.com",
		"program": frappe.db.get_value("Program", {}, "name"),
	}
	values.update(overrides)
	doc = frappe.get_doc(values)
	doc.insert(ignore_permissions=True)
	return doc


class TestStepOrder(FrappeTestCase):
	# -- the contract ------------------------------------------------------

	def test_positions_are_one_to_thirteen_with_no_gaps(self):
		self.assertEqual([s[0] for s in STEPS], list(range(1, len(STEPS) + 1)))

	def test_keys_and_labels_are_unique(self):
		keys = [s[6] for s in STEPS]
		labels = [s[1] for s in STEPS]
		self.assertEqual(len(set(keys)), len(keys), "two steps share a key")
		self.assertEqual(len(set(labels)), len(labels), "two steps share a label")

	def test_every_step_has_a_key_and_it_round_trips(self):
		for step_no, label, _statuses, _default, _done, _role, key in STEPS:
			self.assertTrue(key, f"step {step_no} has no key")
			self.assertEqual(NO[key], step_no)
			self.assertEqual(NO_BY_LABEL[label], step_no)

	def test_every_default_is_a_status_the_step_allows(self):
		for step_no, _label, statuses, default, done, _role, _key in STEPS:
			self.assertIn(default, statuses, f"step {step_no} defaults outside its list")
			for status in done:
				self.assertIn(status, statuses, f"step {step_no} completes on an unlisted status")

	def test_gates_and_actions_only_name_steps_that_exist(self):
		valid = {s[0] for s in STEPS}
		for step_no, requirements in REQUIRES.items():
			self.assertIn(step_no, valid)
			for required_no, required_status in requirements:
				self.assertIn(required_no, valid)
				if required_status:
					self.assertIn(required_status, statuses_for(required_no))
		for step_no in ACTIONS:
			self.assertIn(step_no, valid)

	def test_nothing_is_gated_on_a_step_that_comes_after_it(self):
		"""A gate pointing forwards could never be satisfied."""
		for step_no, requirements in REQUIRES.items():
			for required_no, _status in requirements:
				self.assertLess(
					required_no,
					step_no,
					f"step {step_no} waits on step {required_no}, which comes later",
				)

	# -- the order the college asked for ------------------------------------

	def test_the_scholarship_form_comes_after_the_interview(self):
		"""Until the interview nobody knows whether a scholarship is needed."""
		self.assertGreater(NO["scholarship"], NO["interview"])

	def test_the_scholarship_form_comes_before_the_admission_fee(self):
		self.assertLess(NO["scholarship"], NO["admission_fee"])

	def test_the_exam_still_follows_the_lms_account(self):
		self.assertGreater(NO["entrance_exam"], NO["lms_account"])

	# -- the migration -------------------------------------------------------

	def test_renumbering_moves_rows_by_label_not_by_old_number(self):
		app = make_application()

		# Put the rows back the way they were before the reorder: scholarship
		# at 5, everything between there and the interview one lower.
		old = {
			"Scholarship Form Review": 5,
			"Mentor Form Review": 6,
			"LMS Account Creation": 7,
			"Entrance Exam Review": 8,
			"Zoom Interview Review": 9,
		}
		for row in app.checklist:
			if row.step in old:
				frappe.db.set_value(
					"Admission Checklist Item",
					row.name,
					"step_no",
					old[row.step],
					update_modified=False,
				)

		renumber()

		app.reload()
		for row in app.checklist:
			self.assertEqual(
				int(row.step_no),
				NO_BY_LABEL[row.step],
				f"{row.step} did not land on its new number",
			)

	def test_a_status_recorded_before_the_reorder_survives_it(self):
		"""The point of matching on label: the officer's work is not reassigned."""
		app = make_application()

		scholarship_row = next(
			r for r in app.checklist if r.step == "Scholarship Form Review"
		)
		frappe.db.set_value(
			"Admission Checklist Item",
			scholarship_row.name,
			{"step_no": 5, "status": "Approved"},
			update_modified=False,
		)
		mentor_row = next(r for r in app.checklist if r.step == "Mentor Form Review")
		frappe.db.set_value(
			"Admission Checklist Item",
			mentor_row.name,
			{"step_no": 6, "status": "Verified"},
			update_modified=False,
		)

		renumber()

		app.reload()
		self.assertEqual(status_of(app, NO["scholarship"]), "Approved")
		self.assertEqual(status_of(app, NO["mentor_form"]), "Verified")

	def test_renumbering_twice_changes_nothing(self):
		app = make_application()
		renumber()
		app.reload()
		before = {r.step: (int(r.step_no), r.status) for r in app.checklist}

		renumber()
		app.reload()
		after = {r.step: (int(r.step_no), r.status) for r in app.checklist}

		self.assertEqual(before, after)

	def test_an_unrecognised_label_is_left_alone(self):
		"""Guessing at an unknown row would silently rewrite a record."""
		app = make_application()
		row = app.checklist[0]

		# Bypass the Select validation: this is what a row from a future or
		# renamed step would look like to the patch.
		frappe.db.sql(
			"update `tabAdmission Checklist Item` set step=%s, step_no=%s where name=%s",
			("Some Retired Step", 99, row.name),
		)

		renumber()

		self.assertEqual(
			frappe.db.get_value("Admission Checklist Item", row.name, "step_no"), 99
		)
