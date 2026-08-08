# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, today

from sibbcs.academic import lms_sync
from sibbcs.academic.eligibility import evaluate, may_override


class CourseRegistration(Document):
	def validate(self):
		self.set_defaults()
		self.validate_override_authority()
		self.run_eligibility()
		self.compute_grade()

	def before_insert(self):
		if not self.level_at_registration:
			self.level_at_registration = frappe.db.get_value(
				"Program Enrollment", self.program_enrollment, "current_level"
			)

	def on_update(self):
		self.refresh_offering_count()
		self.maybe_sync_lms()

	def on_trash(self):
		self.refresh_offering_count(removing=True)

	# -- basics ------------------------------------------------------------

	def set_defaults(self):
		if not self.registration_date:
			self.registration_date = today()

	def validate_override_authority(self):
		"""A student must not be able to grant themselves an override."""
		if not self.override_reason:
			self.override_by = None
			return

		if not may_override():
			frappe.throw(
				_("Only an Academic Coordinator may authorise a cross-level override."),
				title=_("Override Not Permitted"),
			)

		self.override_by = self.override_by or frappe.session.user

	# -- the rule engine ---------------------------------------------------

	def run_eligibility(self):
		"""§3. Skipped for terminal states so history can always be corrected."""
		if self.status in ("Withdrawn", "Failed", "Completed"):
			return

		decision, warnings = evaluate(
			self.program_enrollment,
			self.course_offering,
			has_override=bool(self.override_reason),
			exclude=self.name if not self.is_new() else None,
		)

		for warning in warnings:
			frappe.msgprint(warning, indicator="orange", alert=True)

		if decision:
			return

		if decision.needs_override and not self.override_reason:
			frappe.throw(
				_("{0}<br><br>An Academic Coordinator can allow this by filling in "
				  "<b>Override Reason</b>.").format(decision.reason),
				title=_("Registration Blocked"),
			)

		frappe.throw(decision.reason, title=_("Registration Blocked"))

	# -- grading -----------------------------------------------------------

	def compute_grade(self):
		"""Weighted total from the grade components, mapped onto the Grade Scale.

		Only computes once every component carries marks; a partially graded
		registration keeps its previous grade rather than showing a misleading
		low score.
		"""
		if not self.grade_components:
			return

		total_weight = sum(flt(c.weight_pct) for c in self.grade_components)
		if total_weight and abs(total_weight - 100) > 0.01:
			frappe.msgprint(
				_("Grade component weights add up to {0}%, not 100%.").format(total_weight),
				indicator="orange",
				alert=True,
			)

		for component in self.grade_components:
			max_marks = flt(component.max_marks) or 100
			component.weighted_score = flt(
				flt(component.obtained_marks) / max_marks * flt(component.weight_pct), 2
			)

		if any(c.obtained_marks in (None, "") for c in self.grade_components):
			return

		self.final_marks = flt(sum(flt(c.weighted_score) for c in self.grade_components), 2)
		self.apply_grade_scale()

	def apply_grade_scale(self):
		from sibbcs.academic.doctype.grade_scale.grade_scale import get_default_scale

		scale = get_default_scale()
		if not scale:
			# Grade Scale bands are an open decision; fall back to the pass mark
			# rather than inventing letter grades.
			self.passed = int(flt(self.final_marks) >= 60)
			return

		band = scale.grade_for(self.final_marks)
		if not band:
			return

		self.grade = band["grade"]
		self.grade_points = band["grade_points"]
		self.passed = int(band["passed"])

	# -- side effects ------------------------------------------------------

	def refresh_offering_count(self, removing=False):
		count = frappe.db.count(
			"Course Registration",
			{
				"course_offering": self.course_offering,
				"status": ("in", ("Registered", "Active", "Completed")),
				"name": ("!=", self.name) if removing else ("!=", ""),
			},
		)
		frappe.db.set_value(
			"Course Offering", self.course_offering, "enrolled_count", count, update_modified=False
		)

	def maybe_sync_lms(self):
		"""§6. Never let an LMS problem undo an accepted registration."""
		if self.lms_enrollment_created:
			return
		if self.status not in ("Registered", "Active"):
			return
		lms_sync.sync_registration(self)


# ---------------------------------------------------------------------------
# transcript helpers
# ---------------------------------------------------------------------------


def completed_registrations(program_enrollment):
	"""A student's transcript is their set of completed registrations."""
	return frappe.get_all(
		"Course Registration",
		filters={"program_enrollment": program_enrollment, "status": "Completed"},
		fields=[
			"name", "course", "course_title", "term", "credits",
			"final_marks", "grade", "grade_points", "passed",
		],
		order_by="term asc, course asc",
	)


def credits_earned(program_enrollment):
	rows = frappe.get_all(
		"Course Registration",
		filters={"program_enrollment": program_enrollment, "passed": 1},
		fields=["credits"],
	)
	return flt(sum(flt(r.credits) for r in rows), 2)


def compute_cgpa(program_enrollment):
	"""Credit-weighted mean of grade points over passed registrations."""
	rows = frappe.get_all(
		"Course Registration",
		filters={"program_enrollment": program_enrollment, "passed": 1},
		fields=["credits", "grade_points"],
	)
	total_credits = sum(flt(r.credits) for r in rows)
	if not total_credits:
		return 0.0
	weighted = sum(flt(r.credits) * flt(r.grade_points) for r in rows)
	return flt(weighted / total_credits, 2)


def refresh_enrollment_progress(program_enrollment):
	"""Recompute the cached CGPA and credits on Program Enrollment."""
	frappe.db.set_value(
		"Program Enrollment",
		program_enrollment,
		{
			"credits_earned": credits_earned(program_enrollment),
			"cgpa": compute_cgpa(program_enrollment),
		},
		update_modified=False,
	)
