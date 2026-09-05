# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""A group of students within one course."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class CourseGroup(Document):
	def validate(self):
		self.members_are_on_this_course()
		self.nobody_is_in_it_twice()
		self.nobody_is_in_two_groups_of_one_set()
		self.within_the_limit()

	def members_are_on_this_course(self):
		offering = frappe.db.get_value(
			"Course Group Set", self.group_set, "course_offering"
		)
		for row in self.members:
			theirs = frappe.db.get_value(
				"Course Registration", row.course_registration, "course_offering"
			)
			if theirs != offering:
				frappe.throw(
					_("{0} is not on this course.").format(row.student_name or row.course_registration)
				)

	def nobody_is_in_it_twice(self):
		seen = set()
		for row in self.members:
			if row.course_registration in seen:
				frappe.throw(
					_("{0} is listed twice.").format(row.student_name or row.course_registration)
				)
			seen.add(row.course_registration)

	def nobody_is_in_two_groups_of_one_set(self):
		"""A group set is a partition, not a set of overlapping clubs.

		Otherwise a differentiated date resolved through groups would depend on
		which group happened to be read first.
		"""
		siblings = frappe.get_all(
			"Course Group",
			filters={"group_set": self.group_set, "name": ("!=", self.name or "")},
			pluck="name",
		)
		if not siblings:
			return

		taken = {
			row.course_registration: row.parent
			for row in frappe.get_all(
				"Course Group Member",
				filters={"parent": ("in", siblings), "parenttype": "Course Group"},
				fields=["course_registration", "parent"],
			)
		}

		for row in self.members:
			if row.course_registration in taken:
				frappe.throw(
					_("{0} is already in {1}.").format(
						row.student_name or row.course_registration,
						frappe.db.get_value("Course Group", taken[row.course_registration], "title"),
					)
				)

	def within_the_limit(self):
		limit = cint(
			frappe.db.get_value("Course Group Set", self.group_set, "group_limit")
		)
		if limit and len(self.members) > limit:
			frappe.throw(
				_("This group set allows {0} members per group.").format(limit)
			)
