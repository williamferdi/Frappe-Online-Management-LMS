# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt


class Program(Document):
	def before_insert(self):
		# See Course.before_insert: set_new_name() runs before validate(), so the
		# `autoname: field:abbr` docname is derived from whatever abbr holds at
		# this point.
		self.normalise()

	def validate(self):
		self.normalise()
		self.validate_duration()
		self.validate_requirements()

	def normalise(self):
		self.abbr = (self.abbr or "").strip().upper()
		self.program_name = (self.program_name or "").strip()

	def validate_duration(self):
		if self.min_years and self.max_years and flt(self.max_years) < flt(self.min_years):
			frappe.throw(
				_("Max Years ({0}) cannot be less than Min Years ({1}).").format(
					self.max_years, self.min_years
				),
				title=_("Invalid Duration"),
			)

	def validate_requirements(self):
		"""Each rule type needs the figure it is measured against."""
		for row in self.program_requirements:
			if row.rule_type == "Level Credits":
				if not row.level:
					frappe.throw(
						_("Row {0}: a Level Credits rule needs a Level.").format(row.idx),
						title=_("Incomplete Requirement"),
					)
				if not flt(row.min_credits):
					frappe.throw(
						_("Row {0}: a Level Credits rule needs Min Credits.").format(row.idx),
						title=_("Incomplete Requirement"),
					)

			elif row.rule_type == "Elective Minimum":
				if not (flt(row.min_credits) or cint(row.min_courses)):
					frappe.throw(
						_(
							"Row {0}: an Elective Minimum rule needs Min Credits or Min Courses."
						).format(row.idx),
						title=_("Incomplete Requirement"),
					)

			elif row.rule_type == "Internship Hours":
				if not cint(row.min_hours):
					frappe.throw(
						_("Row {0}: an Internship Hours rule needs Min Hours.").format(row.idx),
						title=_("Incomplete Requirement"),
					)

			elif row.rule_type in ("Practicum", "Residential"):
				if not cint(row.min_courses):
					frappe.throw(
						_("Row {0}: a {1} rule needs Min Courses.").format(
							row.idx, row.rule_type
						),
						title=_("Incomplete Requirement"),
					)

		self.warn_on_duplicate_level_rules()

	def warn_on_duplicate_level_rules(self):
		seen = set()
		for row in self.program_requirements:
			if row.rule_type != "Level Credits":
				continue
			if row.level in seen:
				frappe.msgprint(
					_("More than one Level Credits rule for Level {0}.").format(row.level),
					indicator="orange",
					alert=True,
				)
			seen.add(row.level)

	def catalog_courses(self):
		"""Active courses that count toward this program.

		Includes courses with no program links, matching Course.counts_toward:
		an unlinked course is treated as universal rather than excluded.
		"""
		linked = frappe.get_all(
			"Course Program Link",
			filters={"program": self.name, "parenttype": "Course"},
			pluck="parent",
		)
		unlinked = frappe.db.sql(
			"""
			select c.name from `tabCourse` c
			where c.is_active = 1
			  and not exists (
				select 1 from `tabCourse Program Link` l
				where l.parent = c.name and l.parenttype = 'Course'
			  )
			""",
			pluck=True,
		)
		return sorted(set(linked) | set(unlinked))
