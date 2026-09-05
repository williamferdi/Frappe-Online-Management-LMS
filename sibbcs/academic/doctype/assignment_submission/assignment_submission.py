# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""One student's answer to one piece of work."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, get_datetime, now_datetime

from sibbcs.academic import gradebook, overrides


class AssignmentSubmission(Document):
	def validate(self):
		self.belongs_to_the_same_course()
		self.one_row_per_attempt()
		self.count_the_days_late()
		self.score_is_within_the_marks()
		self.excused_work_carries_no_score()
		self.note_who_marked_it()

	def on_update(self):
		"""A posted score is a change to the transcript, so roll it up now.

		Unposting rolls up too: withdrawing a mark has to take it back out of
		the total, or the student keeps a grade the marker has retracted.
		"""
		if self.has_value_changed("posted") or (
			self.posted
			and (
				self.has_value_changed("score")
				or self.has_value_changed("scored")
				or self.has_value_changed("excused")
			)
		):
			gradebook.roll_up(self.course_registration)

	def on_trash(self):
		registration = self.course_registration
		if self.posted:
			frappe.enqueue(
				"sibbcs.academic.gradebook.roll_up",
				registration=registration,
				enqueue_after_commit=True,
				queue="short",
			)

	# --- the rules --------------------------------------------------------

	def belongs_to_the_same_course(self):
		"""The assignment and the registration must be the same course run.

		Without this a score for one course could be filed against another
		course's registration, and it would roll into that course's grade.
		"""
		assignment_offering = frappe.db.get_value(
			"Course Assignment", self.assignment, "course_offering"
		)
		registration_offering = frappe.db.get_value(
			"Course Registration", self.course_registration, "course_offering"
		)

		if assignment_offering != registration_offering:
			frappe.throw(
				_("That assignment belongs to {0} and the registration to {1}.").format(
					assignment_offering, registration_offering
				),
				frappe.ValidationError,
			)

	def one_row_per_attempt(self):
		existing = frappe.db.exists(
			"Assignment Submission",
			{
				"assignment": self.assignment,
				"course_registration": self.course_registration,
				"attempt": cint(self.attempt) or 1,
				"name": ("!=", self.name or ""),
			},
		)
		if existing:
			frappe.throw(
				_("Attempt {0} for this assignment already exists ({1}).").format(
					self.attempt, existing
				)
			)

	def count_the_days_late(self):
		"""Days late, rounded up, from the due date.

		Stored rather than derived at read time so that moving a due date does
		not silently re-penalise work already handed in and marked.
		"""
		if not self.submitted_on:
			self.late_days = 0
			return

		# The due date this student was actually given. Without this an
		# extension would still be marked late, and the penalty would be
		# applied to work that was handed in on time.
		due = overrides.due_for(self.assignment, self.course_registration)
		if not due:
			self.late_days = 0
			return

		overdue = get_datetime(self.submitted_on) - get_datetime(due)
		seconds = overdue.total_seconds()
		self.late_days = 0 if seconds <= 0 else int(seconds // 86400) + 1

	def score_is_within_the_marks(self):
		if self.score in (None, ""):
			return

		possible = flt(
			frappe.db.get_value("Course Assignment", self.assignment, "points_possible")
		)
		if flt(self.score) < 0:
			frappe.throw(_("A score cannot be negative."))
		if possible and flt(self.score) > possible:
			frappe.throw(
				_("{0} is more than the {1} points this is out of.").format(
					self.score, possible
				)
			)

	def excused_work_carries_no_score(self):
		"""Excused means left out of the total, not scored zero.

		Holding both would make the roll-up's answer depend on which field it
		read first.
		"""
		if self.excused and self.score not in (None, ""):
			frappe.throw(
				_("Excused work is left out of the total, so it cannot also carry a score.")
			)

	def note_who_marked_it(self):
		"""Record that this has been marked, and by whom.

		`scored` rather than "the score is not blank": the column is decimal
		NOT NULL DEFAULT 0, so an untouched submission reads back as 0.0 and
		would otherwise be indistinguishable from one marked zero.
		"""
		if self.excused:
			self.scored = 0
			return

		if self.has_value_changed("score") and self.score not in (None, ""):
			self.scored = 1
			self.graded_by = frappe.session.user
			self.graded_on = now_datetime()
			if self.status in ("Draft", "Submitted", "Missing"):
				self.status = "Graded"
