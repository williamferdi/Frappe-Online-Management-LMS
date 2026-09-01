# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

# What the panel decided -> what the checklist step says. `Defer` is neither
# a pass nor a failure, and the step has its own word for it.
OUTCOMES = {
	"Recommend": "Cleared",
	"Reject": "Rejected",
	"Defer": "Deferred",
}


class InterviewRecord(Document):
	def validate(self):
		self.validate_panel()

	def on_update(self):
		self.push_to_application()
		self.push_to_checklist()


	def push_to_checklist(self):
		"""An interview that happened should not leave its step at Awaiting.

		Scheduled while there is no outcome yet, then whatever the panel
		decided. `record_fact` will not walk the step out of a status an
		officer has already recorded, so this can only ever add what is known.
		"""
		if not self.application:
			return

		from sibbcs.admissions.checklist import NO, record_fact

		status = OUTCOMES.get(self.outcome) if self.outcome else None
		if not status and self.scheduled_on:
			status = "Scheduled"
		if not status:
			return

		record_fact(self.application, NO["interview"], status)

	def validate_panel(self):
		seen = set()
		for row in self.panel:
			if row.user in seen:
				frappe.throw(
					_("{0} is on the panel twice.").format(row.user),
					title=_("Duplicate Panel Member"),
				)
			seen.add(row.user)

		if self.outcome and not self.panel:
			frappe.msgprint(
				_("Outcome recorded with no panel members listed."),
				indicator="orange",
				alert=True,
			)

	def push_to_application(self):
		if not (self.application and self.outcome):
			return
		frappe.db.set_value(
			"Admission Application",
			self.application,
			"interview_outcome",
			self.outcome,
			update_modified=False,
		)


def latest_for(application):
	name = frappe.db.get_value(
		"Interview Record",
		{"application": application},
		"name",
		order_by="scheduled_on desc, creation desc",
	)
	return frappe.get_doc("Interview Record", name) if name else None


def is_recommended(application):
	record = latest_for(application)
	return bool(record and record.outcome == "Recommend")
