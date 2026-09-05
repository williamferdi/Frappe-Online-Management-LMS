# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""One piece of work set on one run of a course."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, get_datetime

from sibbcs.academic import gradebook


class CourseAssignment(Document):
	def validate(self):
		self.points_are_positive()
		self.dates_run_forwards()
		self.component_is_in_the_scheme()
		self.penalty_belongs_to_its_policy()

	def on_update(self):
		"""A new assignment can make a hand-marked bucket a computed one.

		`auto_components` reads the assignments, so the first assignment
		counting towards a component changes that component's nature for every
		registration on the offering.
		"""
		if gradebook.is_scheme_driven(self.course_offering):
			gradebook.sync_offering(self.course_offering)

	def after_delete(self):
		"""Removing the last assignment in a bucket hands it back to hand marking.

		after_delete rather than on_trash: `auto_components` reads the
		assignments table, and until the row is actually gone it would still
		count this one.
		"""
		if gradebook.is_scheme_driven(self.course_offering):
			gradebook.sync_offering(self.course_offering)

	def points_are_positive(self):
		if flt(self.points_possible) <= 0:
			frappe.throw(_("Points possible must be more than zero."))

	def dates_run_forwards(self):
		"""Available, then due, then closed.

		Each pair is checked on its own so that setting only two of the three
		is still checked, and the message names the pair that is wrong rather
		than the whole set.
		"""
		opens = get_datetime(self.available_from) if self.available_from else None
		due = get_datetime(self.due_date) if self.due_date else None
		closes = get_datetime(self.available_until) if self.available_until else None

		if opens and due and due < opens:
			frappe.throw(_("The due date is before the work becomes available."))
		if opens and closes and closes < opens:
			frappe.throw(_("It closes before it opens."))
		if due and closes and closes < due:
			frappe.throw(
				_("It closes before it is due, so nothing could ever be handed in on time.")
			)

	def component_is_in_the_scheme(self):
		"""A score that rolls into a bucket the scheme does not have is a score
		that reaches nobody's grade.

		Only checked when a scheme exists: an offering marked by hand may set
		work without declaring any structure at all.
		"""
		scheme = gradebook.scheme_for(self.course_offering)
		if not scheme:
			return

		components = [row.component for row in scheme.rows]
		if self.component not in components:
			frappe.throw(
				_(
					"{0} is not in this course's grade scheme, so a score for it "
					"would count towards nothing. The scheme has: {1}."
				).format(self.component, ", ".join(components)),
				title=_("Not in the Grade Scheme"),
			)

	def penalty_belongs_to_its_policy(self):
		if self.late_policy != "Accept with penalty":
			self.late_penalty_pct_per_day = 0
		elif flt(self.late_penalty_pct_per_day) <= 0:
			frappe.throw(
				_("A late penalty policy needs a penalty. Set one, or choose another policy.")
			)
