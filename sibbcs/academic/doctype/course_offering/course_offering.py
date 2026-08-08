# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class CourseOffering(Document):
	def validate(self):
		self.validate_unique_per_term()
		self.validate_format_requirements()
		self.validate_capacity()
		self.validate_staff()
		self.validate_term_status()

	def validate_unique_per_term(self):
		"""One offering per course per term.

		The autoname (`{course}-{term}`) already guarantees this at the database
		level, but that surfaces as an opaque duplicate-key error -- this gives
		the coordinator a message they can act on.
		"""
		existing = frappe.db.exists(
			"Course Offering",
			{"course": self.course, "term": self.term, "name": ("!=", self.name)},
		)
		if existing:
			frappe.throw(
				_("{0} is already offered in {1} ({2}). Edit that offering instead.").format(
					self.course, self.term, existing
				),
				title=_("Duplicate Offering"),
			)

	def validate_format_requirements(self):
		# Note: do NOT add an "is zoom_time empty" check here. Document.insert()
		# calls _set_defaults(), which builds a new_doc, and frappe's
		# model/create_new.py fills EVERY Time field with nowtime()
		# unconditionally -- outside the `if df.get("default")` branch. A Time
		# field on a new document is therefore never empty, so such a check is
		# unreachable. zoom_days is a child table and is not defaulted, so that
		# is the requirement we can actually enforce.
		if self.format == "Zoom Live":
			if not self.zoom_days:
				frappe.throw(
					_("Zoom Live offerings need at least one Zoom Day."),
					title=_("Schedule Required"),
				)
		else:
			# Stale schedule data on a pre-recorded course misleads students.
			if self.zoom_days:
				frappe.msgprint(
					_("Zoom Days are ignored for {0} offerings.").format(self.format),
					indicator="orange",
					alert=True,
				)

	def validate_capacity(self):
		if cint(self.capacity) < 0:
			frappe.throw(_("Capacity cannot be negative. Use 0 for unlimited."))

		if cint(self.capacity) and cint(self.enrolled_count) > cint(self.capacity):
			frappe.throw(
				_("Capacity ({0}) is below the {1} students already registered.").format(
					self.capacity, self.enrolled_count
				),
				title=_("Capacity Too Low"),
			)

	def validate_staff(self):
		if self.instructor:
			self._require_active(self.instructor, _("Instructor"))
			self._warn_if_unqualified(self.instructor)

		if self.facilitator:
			self._require_active(self.facilitator, _("Facilitator"))
			if not frappe.db.get_value("Instructor", self.facilitator, "is_facilitator"):
				frappe.throw(
					_("{0} is not marked as a facilitator.").format(
						frappe.db.get_value("Instructor", self.facilitator, "full_name")
					),
					title=_("Not a Facilitator"),
				)

		if self.instructor and self.instructor == self.facilitator:
			frappe.msgprint(
				_("The same person is both instructor and facilitator."),
				indicator="orange",
				alert=True,
			)

	def _require_active(self, instructor, label):
		full_name, is_active = frappe.db.get_value(
			"Instructor", instructor, ["full_name", "is_active"]
		)
		if not is_active:
			frappe.throw(
				_("{0} {1} is marked inactive.").format(label, full_name),
				title=_("Inactive Instructor"),
			)

	def _warn_if_unqualified(self, instructor):
		"""Advisory only -- the coordinator can always override in practice."""
		qualified = frappe.get_all(
			"Instructor Course",
			filters={"parent": instructor, "parenttype": "Instructor"},
			pluck="course",
		)
		if qualified and self.course not in qualified:
			frappe.msgprint(
				_("{0} is not listed as qualified for {1}.").format(
					frappe.db.get_value("Instructor", instructor, "full_name"), self.course
				),
				indicator="orange",
				alert=True,
			)

	def validate_term_status(self):
		status = frappe.db.get_value("Academic Term", self.term, "status")
		if status == "Closed" and self.status in ("Draft", "Published"):
			frappe.throw(
				_("{0} is closed. New offerings cannot be published into it.").format(self.term),
				title=_("Term Closed"),
			)

	def has_seats_available(self):
		if not cint(self.capacity):
			return True
		return cint(self.enrolled_count) < cint(self.capacity)

	def refresh_enrolled_count(self):
		"""Recount active registrations.

		Course Registration arrives in Phase 3; until then the count stays at
		whatever it was, so this is a no-op on a Phase 1 site.
		"""
		if not frappe.db.exists("DocType", "Course Registration"):
			return

		count = frappe.db.count(
			"Course Registration",
			{
				"course_offering": self.name,
				"status": ("in", ["Registered", "Active", "Completed"]),
			},
		)
		self.db_set("enrolled_count", count, update_modified=False)
