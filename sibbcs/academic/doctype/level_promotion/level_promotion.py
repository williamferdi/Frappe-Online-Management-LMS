# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, today

from sibbcs.academic.doctype.course_registration.course_registration import (
	credits_earned,
	refresh_enrollment_progress,
)


class LevelPromotion(Document):
	"""The audit trail for a level change.

	`current_level` on Program Enrollment is never edited silently -- it moves
	through this document, which records who approved it and on what evidence.
	"""

	def validate(self):
		self.validate_levels()
		self.validate_level_four_gate()
		self.capture_evidence()

	def on_submit(self):
		self.apply()

	def after_insert(self):
		# The DocType is not submittable, so applying on insert keeps the
		# promotion and the enrollment in step.
		self.apply()

	def validate_levels(self):
		from_level = cint(self.from_level)
		to_level = cint(self.to_level)

		if from_level == to_level:
			frappe.throw(_("From and To level are the same."), title=_("Nothing to Promote"))

		current = frappe.db.get_value(
			"Program Enrollment", self.program_enrollment, "current_level"
		)
		if cint(current) != from_level:
			frappe.throw(
				_("This enrollment is at Level {0}, not Level {1}.").format(current, from_level),
				title=_("Level Mismatch"),
			)

		if to_level > from_level + 1:
			frappe.throw(
				_("Levels are promoted one at a time ({0} to {1} skips a level).").format(
					from_level, to_level
				),
				title=_("Invalid Promotion"),
			)

	def validate_level_four_gate(self):
		"""§3: every Level 3 course must be completed and passed before Level 4."""
		if cint(self.to_level) != 4:
			return

		program = frappe.db.get_value("Program Enrollment", self.program_enrollment, "program")
		outstanding = outstanding_level_three(self.program_enrollment, program)

		if outstanding:
			frappe.throw(
				_(
					"Level 4 requires every Level 3 course to be completed and passed. "
					"Outstanding: {0}"
				).format(", ".join(outstanding[:10])),
				title=_("Level 4 Gate"),
			)

	def capture_evidence(self):
		self.credits_at_promotion = credits_earned(self.program_enrollment)
		self.courses_passed = frappe.db.count(
			"Course Registration", {"program_enrollment": self.program_enrollment, "passed": 1}
		)
		if not self.approved_by:
			self.approved_by = frappe.session.user
			self.approved_on = today()

	def apply(self):
		"""Move the enrollment's level. current_level is permlevel-gated, so
		this writes directly rather than through a normal save."""
		frappe.db.set_value(
			"Program Enrollment",
			self.program_enrollment,
			"current_level",
			str(cint(self.to_level)),
			update_modified=False,
		)
		refresh_enrollment_progress(self.program_enrollment)


def outstanding_level_three(program_enrollment, program=None):
	"""Level 3 courses for this program that are not yet passed."""
	program = program or frappe.db.get_value(
		"Program Enrollment", program_enrollment, "program"
	)

	level_three = frappe.get_all(
		"Course", filters={"level": "3", "is_active": 1}, pluck="name"
	)
	if program:
		linked = set(
			frappe.get_all(
				"Course Program Link",
				filters={"program": program, "parenttype": "Course"},
				pluck="parent",
			)
		)
		if linked:
			# A course with no program links counts as universal (Course.counts_toward),
			# so only exclude ones explicitly tied to a *different* program.
			tied = set(
				frappe.get_all(
					"Course Program Link", filters={"parenttype": "Course"}, pluck="parent"
				)
			)
			level_three = [c for c in level_three if c in linked or c not in tied]

	passed = set(
		frappe.get_all(
			"Course Registration",
			filters={"program_enrollment": program_enrollment, "passed": 1},
			pluck="course",
		)
	)
	return sorted(c for c in level_three if c not in passed)


@frappe.whitelist()
def promote(program_enrollment, to_level, remarks=None):
	"""Desk/API entry point for a promotion."""
	enrollment = frappe.get_doc("Program Enrollment", program_enrollment)
	enrollment.check_permission("write")

	promotion = frappe.get_doc(
		{
			"doctype": "Level Promotion",
			"program_enrollment": program_enrollment,
			"from_level": enrollment.current_level,
			"to_level": str(cint(to_level)),
			"remarks": remarks,
		}
	)
	promotion.insert(ignore_permissions=True)
	return promotion.name
