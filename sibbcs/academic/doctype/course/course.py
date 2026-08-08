# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class Course(Document):
	def before_insert(self):
		# Must run here, not in validate(): insert() calls set_new_name() -- which
		# derives the docname from course_code via `autoname: field:course_code` --
		# before before_save/validate. Normalising in validate() would leave a
		# lower-cased docname behind.
		self.normalise()

	def validate(self):
		self.normalise()
		self.validate_credits()
		self.validate_prerequisites()

	def normalise(self):
		self.course_code = (self.course_code or "").strip().upper()
		self.course_title = (self.course_title or "").strip()

	def validate_credits(self):
		if flt(self.credits) <= 0:
			frappe.throw(_("Credits must be greater than zero."), title=_("Invalid Credits"))

	def validate_prerequisites(self):
		seen = set()
		for row in self.course_prerequisites:
			if row.prerequisite_course == self.name:
				frappe.throw(
					_("A course cannot be its own prerequisite."),
					title=_("Invalid Prerequisite"),
				)

			if row.prerequisite_course in seen:
				frappe.throw(
					_("{0} is listed as a prerequisite more than once.").format(
						row.prerequisite_course
					),
					title=_("Duplicate Prerequisite"),
				)
			seen.add(row.prerequisite_course)

		self.validate_no_prerequisite_cycle()

	def validate_no_prerequisite_cycle(self):
		"""Walk the prerequisite graph and refuse to close a loop.

		Without this, a cycle (A requires B, B requires A) makes the Phase 3
		registration check unsatisfiable -- neither course could ever be taken.
		"""
		direct = [r.prerequisite_course for r in self.course_prerequisites if r.prerequisite_course]
		if not direct:
			return

		visited = set()
		queue = list(direct)
		while queue:
			current = queue.pop()
			if current in visited:
				continue
			visited.add(current)

			if current == self.name:
				frappe.throw(
					_(
						"Prerequisite cycle detected: {0} already depends on this course, "
						"directly or indirectly."
					).format(", ".join(direct)),
					title=_("Circular Prerequisite"),
				)

			queue.extend(
				frappe.get_all(
					"Course Prerequisite",
					filters={"parent": current, "parenttype": "Course"},
					pluck="prerequisite_course",
				)
			)

	def hard_prerequisites(self):
		"""Courses that must be passed before this one may be registered."""
		return [r.prerequisite_course for r in self.course_prerequisites if r.is_hard]

	def counts_toward(self, program):
		"""Whether this course can satisfy requirements for `program`.

		A course with no programs listed is treated as universal, so that a
		partially-seeded catalog does not silently exclude courses from audits.
		"""
		linked = [r.program for r in self.programs]
		return program in linked if linked else True
