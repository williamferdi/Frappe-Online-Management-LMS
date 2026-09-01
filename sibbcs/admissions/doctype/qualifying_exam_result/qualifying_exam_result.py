# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

# The original four-subject paper. Kept because results were recorded against
# it, but the exam the college actually sets is three essays.
SECTIONS = ("english_score", "bible_score", "theology_score", "ministry_score")

# Three essays, 25 marks each, marked against the rubrics in the entrance exam
# course. See setup/phase2m_entrance_exam.py.
ESSAYS = ("essay_gospel", "essay_calling", "essay_motivation")
ESSAY_MAX = 25
ESSAY_TOTAL = ESSAY_MAX * len(ESSAYS)


class QualifyingExamResult(Document):
	def validate(self):
		self.validate_scores()
		self.compute_total()

	def on_update(self):
		self.push_to_application()
		self.push_to_checklist()

	def push_to_checklist(self):
		"""And onto the step that tracks the exam.

		Without this the college marked a paper, saw the score land on the
		application, and still had Entrance Exam Review sitting at Awaiting.
		"""
		if not self.application or not self.result:
			return

		from sibbcs.admissions.checklist import NO, record_fact

		record_fact(
			self.application,
			NO["entrance_exam"],
			"Passed" if self.result == "Pass" else "Failed",
		)

	def validate_scores(self):
		for field in SECTIONS:
			value = flt(self.get(field))
			if value < 0 or value > 100:
				frappe.throw(
					_("{0} must be between 0 and 100.").format(frappe.unscrub(field)),
					title=_("Invalid Score"),
				)

		for field in ESSAYS:
			value = flt(self.get(field))
			if value < 0 or value > ESSAY_MAX:
				frappe.throw(
					_("{0} must be between 0 and {1}.").format(
						frappe.unscrub(field), ESSAY_MAX
					),
					title=_("Invalid Score"),
				)

		if not 0 < flt(self.pass_mark) <= 100:
			frappe.throw(_("Pass Mark must be between 0 and 100."), title=_("Invalid Pass Mark"))

	def marked_essays(self):
		"""Essay marks, or an empty list if this is a four-subject result."""
		return [flt(self.get(f)) for f in ESSAYS if self.get(f) not in (None, "")]

	def compute_total(self):
		"""Total always reads as a percentage, whichever paper was sat.

		The college's exam is three essays of 25. Results recorded against the
		older four-subject paper are still averaged the way they always were --
		recomputing them under the new rule would silently rewrite a result
		somebody has already acted on.
		"""
		essays = self.marked_essays()

		if essays:
			self.total = flt(sum(essays) / ESSAY_TOTAL * 100, 2)
		else:
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
