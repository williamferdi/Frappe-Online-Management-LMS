# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""A quiz: where its questions come from, and how long a student gets."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt


class CourseQuiz(Document):
	def validate(self):
		self.draws_are_positive()
		self.total_points = self._total()

	def draws_are_positive(self):
		for source in self.sources:
			if cint(source.pick) <= 0:
				frappe.throw(_("Draw at least one question from {0}.").format(source.bank))

	def _total(self):
		"""What a full paper is worth.

		An estimate, because the questions are drawn per attempt: the mean
		point value of a bank times the number drawn. The attempt records what
		its own paper was actually out of, and that is what scoring uses.
		"""
		total = 0.0
		for source in self.sources:
			rows = frappe.get_all(
				"Bank Question", filters={"bank": source.bank}, pluck="points"
			)
			if not rows:
				continue
			average = sum(flt(value) for value in rows) / len(rows)
			total += average * min(cint(source.pick), len(rows))
		return flt(total, 2)
