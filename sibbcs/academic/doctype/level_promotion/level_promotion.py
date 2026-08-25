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
		self.validate_approver()
		self.validate_levels()
		self.validate_course_count_gate()
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

	def validate_course_count_gate(self):
		"""A level is finished when its courses are: eight of them, by default.

		Counted on `level_at_registration`, which every registration already
		stores, rather than on a lifetime total. A lifetime count would let a
		Level 3 student promote to Level 4 on eight courses passed years
		earlier at Level 1.
		"""
		required = courses_required(self.program_enrollment)
		if not required:
			return

		passed = passed_at_level(self.program_enrollment, cint(self.from_level))
		if passed >= required:
			return

		if self.override_shortfall:
			if not may_approve():
				frappe.throw(
					_("Only the Dean, Registrar or Academic Coordinator may promote "
					  "a student who is short of the course requirement."),
					frappe.PermissionError,
				)
			return

		frappe.throw(
			_(
				"Level {0} requires {1} passed courses; this student has {2}. "
				"Tick Override Shortfall to promote anyway."
			).format(self.from_level, required, passed),
			title=_("Not Enough Courses"),
		)

	def validate_approver(self):
		"""Promotion is a Dean, Registrar or Academic Coordinator decision."""
		if not may_approve():
			frappe.throw(
				_("Only the Dean, Registrar or Academic Coordinator may promote a student."),
				frappe.PermissionError,
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


# ---------------------------------------------------------------------------
# who may promote, and on what evidence
# ---------------------------------------------------------------------------

APPROVER_ROLES = ("Dean", "Registrar", "Academic Coordinator", "System Manager")

DEFAULT_COURSES_PER_LEVEL = 8


def may_approve(user=None):
	"""Dean, Registrar or Academic Coordinator. Nobody else moves a level."""
	roles = set(frappe.get_roles(user or frappe.session.user))
	return bool(roles.intersection(APPROVER_ROLES))


def courses_required(program_enrollment):
	"""How many passed courses a level takes, from the Program.

	On `Program.courses_per_level` rather than in code, because the figure is
	the college's to revise. Zero switches the gate off for that program.
	"""
	program = frappe.db.get_value("Program Enrollment", program_enrollment, "program")
	if not program:
		return DEFAULT_COURSES_PER_LEVEL

	value = frappe.db.get_value("Program", program, "courses_per_level")
	# None only when the Program record itself has gone; the column is NOT NULL
	# with a default of 8, so a real row always answers with a number.
	if value is None:
		return DEFAULT_COURSES_PER_LEVEL
	return cint(value)


def passed_at_level(program_enrollment, level):
	"""Passed courses the student took while at this level."""
	return frappe.db.count(
		"Course Registration",
		{
			"program_enrollment": program_enrollment,
			"passed": 1,
			"level_at_registration": str(cint(level)),
		},
	)


@frappe.whitelist()
def eligibility(program_enrollment):
	"""Is this student ready for the next level, and on what evidence."""
	enrollment = frappe.get_doc("Program Enrollment", program_enrollment)
	enrollment.check_permission("read")

	from_level = cint(enrollment.current_level)
	required = courses_required(program_enrollment)
	passed = passed_at_level(program_enrollment, from_level)

	blocked = None
	if from_level >= 4:
		blocked = _("Already at the final level.")
	elif required and passed < required:
		blocked = _("{0} of {1} courses passed at Level {2}.").format(
			passed, required, from_level
		)
	elif from_level == 3 and outstanding_level_three(program_enrollment):
		blocked = _("Level 3 courses are still outstanding.")

	return {
		"program_enrollment": program_enrollment,
		"student": enrollment.student,
		"from_level": from_level,
		"to_level": from_level + 1 if from_level < 4 else from_level,
		"required": required,
		"passed": passed,
		"eligible": blocked is None,
		"blocked": blocked,
		"may_approve": may_approve(),
	}


@frappe.whitelist()
@frappe.whitelist()
def promotion_board(include_blocked=0, limit=500):
	"""Every active enrollment, with its promotion verdict. The Dean's list.

	Three queries for the whole college, not three per student. The obvious
	implementation calls eligibility() in a loop, which is a get_doc and two
	counts each -- fine for a demo, three thousand queries at a thousand
	students. The counts are aggregated once and matched up in Python instead.
	"""
	if not may_approve():
		frappe.throw(
			_("Only the Dean, Registrar or Academic Coordinator may see this."),
			frappe.PermissionError,
		)

	include_blocked = int(include_blocked or 0)

	enrollments = frappe.get_all(
		"Program Enrollment",
		filters={"status": "Active"},
		fields=["name", "student", "student_name", "program", "current_level"],
		order_by="student_name asc",
		limit=limit,
	)
	if not enrollments:
		return []

	# `courses_per_level` is a NOT NULL Int with a default of 8, so it is never
	# None here and zero always means somebody typed zero. An "unset means the
	# default" branch would be unreachable -- the same trap as the Time fields
	# that are never empty.
	thresholds = {
		row.name: cint(row.courses_per_level)
		for row in frappe.get_all("Program", fields=["name", "courses_per_level"])
	}

	# One grouped count for every student at once.
	counts = {}
	for row in frappe.get_all(
		"Course Registration",
		filters={
			"passed": 1,
			"program_enrollment": ("in", [e.name for e in enrollments]),
		},
		fields=["program_enrollment", "level_at_registration", "count(name) as n"],
		group_by="program_enrollment, level_at_registration",
	):
		counts[(row.program_enrollment, str(row.level_at_registration))] = cint(row.n)

	rows = []
	for enrollment in enrollments:
		from_level = cint(enrollment.current_level)
		required = thresholds.get(enrollment.program, DEFAULT_COURSES_PER_LEVEL)
		passed = counts.get((enrollment.name, str(from_level)), 0)

		blocked = None
		if from_level >= 4:
			blocked = _("Already at the final level.")
		elif required and passed < required:
			blocked = _("{0} of {1} courses passed at Level {2}.").format(
				passed, required, from_level
			)
		elif from_level == 3 and outstanding_level_three(enrollment.name, enrollment.program):
			# Only for the handful who otherwise qualify, so the expensive
			# per-student check stays off the main path.
			blocked = _("Level 3 courses are still outstanding.")

		if blocked and not include_blocked:
			continue

		rows.append(
			{
				"program_enrollment": enrollment.name,
				"student": enrollment.student,
				"student_name": enrollment.student_name,
				"program": enrollment.program,
				"from_level": from_level,
				"to_level": from_level + 1 if from_level < 4 else from_level,
				"required": required,
				"passed": passed,
				"eligible": blocked is None,
				"blocked": blocked,
			}
		)

	return rows


@frappe.whitelist()
def eligible_for_promotion(limit=200):
	"""Every enrollment ready to move up."""
	return promotion_board(include_blocked=0, limit=limit)
