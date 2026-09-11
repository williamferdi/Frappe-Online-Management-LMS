# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""One thing in a module: a lesson, a page, a file, a piece of work, a link."""

import frappe
from frappe import _
from frappe.model.document import Document


class CourseModuleItem(Document):
	def validate(self):
		self.points_within_its_own_course()

	def points_within_its_own_course(self):
		"""What an item opens must be on its own course.

		The builder only ever offers the course's own lessons, pages and files,
		but `save_item` took any name it was given -- and an item pointing at
		another course's page was a way for a teacher, and for that course's
		students, to read it through the preview and the player. Checked here,
		on the record, so Desk is held to it as well (2026-09-11).
		"""
		offering = self.course_offering or frappe.db.get_value(
			"Course Module", self.module, "course_offering"
		)
		if not offering:
			return
		course = frappe.db.get_value("Course Offering", offering, "course")

		if self.assignment and frappe.db.get_value(
			"Course Assignment", self.assignment, "course_offering"
		) != offering:
			frappe.throw(_("That assignment is not on this course."))

		if self.page and frappe.db.get_value("Course Page", self.page, "course") != course:
			frappe.throw(_("That page is not on this course."))

		if self.file and frappe.db.get_value("Course File", self.file, "course") != course:
			frappe.throw(_("That file is not on this course."))

		if self.lesson:
			# A lesson lives in the course's LMS course, which every term shares.
			lms_course = frappe.db.get_value("Course", course, "lms_course")
			if not lms_course or frappe.db.get_value(
				"Course Lesson", self.lesson, "course"
			) != lms_course:
				frappe.throw(_("That lesson is not on this course."))
