# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""How one offering's marks add up to a hundred."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from sibbcs.academic import gradebook

TOLERANCE = 0.01


class CourseGradeScheme(Document):
	def validate(self):
		self.no_empty_scheme()
		self.no_repeated_component()
		self.weights_total_one_hundred()

	def on_update(self):
		# The weights just moved, so every registration on this offering is
		# now describing a different course from the one it is graded against.
		gradebook.sync_offering(self.course_offering)

	def on_trash(self):
		"""Deleting a scheme hands the offering back to hand marking.

		The components stay exactly as they are, marks and all -- what changes
		is only that nothing will recompute them.
		"""
		for name in frappe.get_all(
			"Course Registration",
			filters={"course_offering": self.course_offering},
			pluck="name",
		):
			frappe.db.set_value(
				"Grade Component",
				{"parent": name, "parenttype": "Course Registration"},
				"auto_computed",
				0,
				update_modified=False,
			)

	def no_empty_scheme(self):
		if not self.rows:
			frappe.throw(_("A grade scheme needs at least one component."))

	def no_repeated_component(self):
		"""Two rows for one component cannot both roll up into it.

		`grade_components` is keyed by component name, so a duplicate is not a
		heavier weighting -- it is one row silently overwriting the other.
		"""
		seen = set()
		for row in self.rows:
			if row.component in seen:
				frappe.throw(
					_("{0} appears twice. Give it one row with the whole weight.").format(
						row.component
					)
				)
			seen.add(row.component)

	def weights_total_one_hundred(self):
		"""Refused, not warned about.

		`compute_grade` only warns, because it inherited hand-typed rows that
		were already wrong and refusing them would have locked people out of
		their own data. A scheme is new, so it can be held to the rule that
		makes the arithmetic mean anything.
		"""
		self.total_weight = flt(sum(flt(row.weight_pct) for row in self.rows), 2)

		if abs(self.total_weight - 100) > TOLERANCE:
			frappe.throw(
				_("The component weights add up to {0}%, not 100%.").format(
					self.total_weight
				),
				title=_("Weights Do Not Balance"),
			)
