# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

SECTIONS = ("english_score", "bible_score", "theology_score", "ministry_score")


class QualifyingExamResult(Document):
	def validate(self):
		self.validate_scores()
		self.compute_total()

	def on_update(self):
		self.push_to_application()

	def validate_scores(self):
		for field in SECTIONS:
			value = flt(self.get(field))
			if value < 0 or value > 100:
				frappe.throw(
					_("{0} must be between 0 and 100.").format(frappe.unscrub(field)),
					title=_("Invalid Score"),
				)

		if not 0 < flt(self.pass_mark) <= 100:
			frappe.throw(_("Pass Mark must be between 0 and 100."), title=_("Invalid Pass Mark"))

	def compute_total(self):
		"""Total is the mean of the four sections, so it reads as a percentage."""
		self.total = flt(sum(flt(self.get(f)) for f in SECTIONS) / len(SECTIONS), 2)
		self.result = "Pass" if self.total >= flt(self.pass_mark) else "Fail"

	def push_to_application(self):
		"""Mirror the score onto the application so the workflow can gate on it."""
		if not self.application:
			return
		frappe.db.set_value(
			"Admission Application",
			self.application,
			"qualifying_exam_score",
			self.total,
			update_modified=False,
		)


def latest_for(application):
	"""Most recent result for an application, or None."""
	name = frappe.db.get_value(
		"Qualifying Exam Result",
		{"application": application},
		"name",
		order_by="conducted_on desc, creation desc",
	)
	return frappe.get_doc("Qualifying Exam Result", name) if name else None


def has_passed(application):
	result = latest_for(application)
	return bool(result and result.result == "Pass")
