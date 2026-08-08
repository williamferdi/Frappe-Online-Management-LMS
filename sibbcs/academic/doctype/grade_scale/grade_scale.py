# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class GradeScale(Document):
	def validate(self):
		self.validate_bands()
		self.validate_pass_percentage()

	def on_update(self):
		self.enforce_single_default()

	def validate_bands(self):
		if not self.grade_rows:
			frappe.throw(_("Add at least one grade band."), title=_("No Grade Bands"))

		seen_grades = set()
		for row in self.grade_rows:
			if flt(row.min_pct) > flt(row.max_pct):
				frappe.throw(
					_("Row {0}: Min % ({1}) cannot exceed Max % ({2}).").format(
						row.idx, row.min_pct, row.max_pct
					),
					title=_("Invalid Grade Band"),
				)

			if not 0 <= flt(row.min_pct) <= 100 or not 0 <= flt(row.max_pct) <= 100:
				frappe.throw(
					_("Row {0}: percentages must be between 0 and 100.").format(row.idx),
					title=_("Invalid Grade Band"),
				)

			grade = (row.grade or "").strip()
			if grade in seen_grades:
				frappe.throw(
					_("Grade {0} appears more than once.").format(grade),
					title=_("Duplicate Grade"),
				)
			seen_grades.add(grade)
			row.grade = grade

		self.validate_no_overlap()

	def validate_no_overlap(self):
		"""Overlapping bands make grade lookup ambiguous, so block them."""
		bands = sorted(self.grade_rows, key=lambda r: flt(r.min_pct))
		for earlier, later in zip(bands, bands[1:]):
			if flt(later.min_pct) <= flt(earlier.max_pct):
				frappe.throw(
					_(
						"Grade bands {0} ({1}-{2}%) and {3} ({4}-{5}%) overlap. "
						"A percentage must map to exactly one grade."
					).format(
						earlier.grade,
						earlier.min_pct,
						earlier.max_pct,
						later.grade,
						later.min_pct,
						later.max_pct,
					),
					title=_("Overlapping Grade Bands"),
				)

		# A gap is legal but almost always a mistake, so warn.
		for earlier, later in zip(bands, bands[1:]):
			if flt(later.min_pct) - flt(earlier.max_pct) > 0.01:
				frappe.msgprint(
					_("Gap between {0} (up to {1}%) and {2} (from {3}%).").format(
						earlier.grade, earlier.max_pct, later.grade, later.min_pct
					),
					indicator="orange",
					alert=True,
				)

	def validate_pass_percentage(self):
		if not 0 < flt(self.pass_percentage) <= 100:
			frappe.throw(
				_("Pass Percentage must be between 0 and 100."),
				title=_("Invalid Pass Percentage"),
			)

		passing = [r for r in self.grade_rows if r.is_pass]
		if passing:
			lowest_pass = min(flt(r.min_pct) for r in passing)
			if abs(lowest_pass - flt(self.pass_percentage)) > 0.01:
				frappe.msgprint(
					_(
						"Pass Percentage is {0}% but the lowest passing grade starts at {1}%. "
						"Check that these agree."
					).format(self.pass_percentage, lowest_pass),
					indicator="orange",
					alert=True,
				)

	def enforce_single_default(self):
		if not self.is_default:
			return
		frappe.db.set_value(
			"Grade Scale",
			{"name": ("!=", self.name), "is_default": 1},
			"is_default",
			0,
			update_modified=False,
		)

	def grade_for(self, percentage):
		"""Map a percentage onto this scale.

		Returns a dict with grade, grade_points and passed, or None when the
		percentage falls outside every band.
		"""
		pct = flt(percentage)
		for row in self.grade_rows:
			if flt(row.min_pct) <= pct <= flt(row.max_pct):
				return {
					"grade": row.grade,
					"grade_points": flt(row.grade_points),
					"passed": bool(row.is_pass),
				}
		return None


def get_default_scale():
	"""The Grade Scale marked default, or the only one if there is just one."""
	name = frappe.db.get_value("Grade Scale", {"is_default": 1}, "name")
	if not name:
		scales = frappe.get_all("Grade Scale", pluck="name", limit=2)
		if len(scales) == 1:
			name = scales[0]

	return frappe.get_cached_doc("Grade Scale", name) if name else None
