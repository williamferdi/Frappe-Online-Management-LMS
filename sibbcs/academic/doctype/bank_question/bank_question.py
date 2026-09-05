# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""One question in a bank."""

import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt


class BankQuestion(Document):
	def validate(self):
		self.keep_a_plain_shadow()
		self.points_are_positive()
		self.somebody_has_to_be_right()

	def on_update(self):
		self.refresh_bank_count()

	def after_delete(self):
		self.refresh_bank_count()

	def keep_a_plain_shadow(self):
		"""The question without its markup.

		`title_field` and every list of questions would otherwise render raw
		HTML, and a question is written in a rich editor.
		"""
		self.question_text = re.sub(r"<[^>]+>", " ", self.question or "").replace(
			"&nbsp;", " "
		).strip()[:140]

	def points_are_positive(self):
		if flt(self.points) <= 0:
			frappe.throw(_("A question has to be worth something."))

	def somebody_has_to_be_right(self):
		"""A question with no correct option can never be answered correctly.

		Caught here rather than at marking time, where it would look like the
		student got it wrong.
		"""
		if self.question_type == "True or False" and len(self.options) != 2:
			frappe.throw(_("A true-or-false question needs exactly two options."))

		if not self.options:
			frappe.throw(_("A question needs its answers."))

		correct = [row for row in self.options if cint(row.is_correct)]
		if not correct:
			frappe.throw(_("Mark which answer is correct."))

		if self.question_type == "Choice" and len(correct) > 1:
			frappe.throw(
				_("A single-choice question has one correct answer. Use "
				  "Multiple answers for more than one.")
			)

	def refresh_bank_count(self):
		if not self.bank:
			return
		frappe.db.set_value(
			"Question Bank",
			self.bank,
			"question_count",
			frappe.db.count("Bank Question", {"bank": self.bank}),
			update_modified=False,
		)
