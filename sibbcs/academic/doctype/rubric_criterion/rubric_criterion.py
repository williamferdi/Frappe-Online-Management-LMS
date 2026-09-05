# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""One thing a rubric asks the marker to judge."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from sibbcs.academic.doctype.course_rubric.course_rubric import refresh_total


class RubricCriterion(Document):
	def validate(self):
		self.points_are_positive()
		self.no_rating_exceeds_the_criterion()

	def on_update(self):
		refresh_total(self.rubric)

	def after_delete(self):
		refresh_total(self.rubric)

	def points_are_positive(self):
		if flt(self.points_possible) <= 0:
			frappe.throw(_("A criterion has to be worth something."))

	def no_rating_exceeds_the_criterion(self):
		"""A rating worth more than the criterion is a marker being offered a
		score the total cannot hold."""
		for rating in self.ratings:
			if flt(rating.points) > flt(self.points_possible):
				frappe.throw(
					_("The rating {0} is worth {1}, more than the {2} this criterion carries.").format(
						rating.title, rating.points, self.points_possible
					)
				)
			if flt(rating.points) < 0:
				frappe.throw(_("A rating cannot be worth less than nothing."))
