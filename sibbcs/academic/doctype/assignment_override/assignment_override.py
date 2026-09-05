# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""Different dates for one student, or one group."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime


class AssignmentOverride(Document):
	def validate(self):
		self.one_target_only()
		self.target_is_on_this_course()
		self.dates_run_forwards()
		self.says_something()

	def one_target_only(self):
		"""A student or a group, never both and never neither.

		Both would make "which dates apply" depend on which field the resolver
		happened to read first.
		"""
		if self.course_registration and self.course_group:
			frappe.throw(
				_("An override is for a student or for a group, not for both.")
			)
		if not self.course_registration and not self.course_group:
			frappe.throw(_("Say who this override is for."))

	def target_is_on_this_course(self):
		"""An override for somebody on another course would never resolve, and
		would sit there looking as though it had."""
		offering = frappe.db.get_value(
			"Course Assignment", self.assignment, "course_offering"
		)

		if self.course_registration:
			theirs = frappe.db.get_value(
				"Course Registration", self.course_registration, "course_offering"
			)
			if theirs != offering:
				frappe.throw(_("That student is not on this course."))

		if self.course_group:
			theirs = frappe.db.get_value(
				"Course Group", self.course_group, "course_offering"
			)
			if theirs != offering:
				frappe.throw(_("That group is not on this course."))

	def dates_run_forwards(self):
		opens = get_datetime(self.available_from) if self.available_from else None
		due = get_datetime(self.due_date) if self.due_date else None
		closes = get_datetime(self.available_until) if self.available_until else None

		if opens and due and due < opens:
			frappe.throw(_("The due date is before it becomes available."))
		if due and closes and closes < due:
			frappe.throw(_("It closes before it is due."))
		if opens and closes and closes < opens:
			frappe.throw(_("It closes before it opens."))

	def says_something(self):
		"""An override with no dates changes nothing and hides the fact that
		nothing was changed."""
		if not (self.available_from or self.due_date or self.available_until):
			frappe.throw(_("An override needs at least one date."))
