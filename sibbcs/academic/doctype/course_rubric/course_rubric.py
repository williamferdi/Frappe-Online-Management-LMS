# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""A rubric, and what it totals to."""

import frappe
from frappe.model.document import Document
from frappe.utils import flt


class CourseRubric(Document):
	def onload(self):
		self.set_onload("criteria_count", self._criteria_count())

	def validate(self):
		self.total_points = self._total()

	def _criteria_count(self):
		return frappe.db.count("Rubric Criterion", {"rubric": self.name})

	def _total(self):
		"""Summed from the criteria, which live in their own DocType.

		A criterion has to be a Link target for a rubric assessment, so it
		cannot be a child row -- which means the total cannot be summed from a
		table on this document and has to be read back.
		"""
		if self.is_new():
			return flt(self.total_points)

		total = frappe.db.sql(
			"""SELECT SUM(points_possible) FROM `tabRubric Criterion` WHERE rubric = %s""",
			self.name,
		)
		return flt(total[0][0] if total and total[0] else 0, 2)


def refresh_total(rubric):
	"""Kept in step by the criterion, which is the thing that changes."""
	if not rubric or not frappe.db.exists("Course Rubric", rubric):
		return
	doc = frappe.get_doc("Course Rubric", rubric)
	doc.save(ignore_permissions=True)
