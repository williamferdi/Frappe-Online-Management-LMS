# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class InterviewRecord(Document):
	def validate(self):
		self.validate_panel()

	def on_update(self):
		self.push_to_application()

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
