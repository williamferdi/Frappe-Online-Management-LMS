# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""One test per rule about handing work in, marking it, and posting it.

The rule the whole phase turns on is that a posted score reaches
`final_marks`, the Grade Scale and the transcript through the same row a
marker used to type into -- and that an unposted one reaches nothing and
nobody.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, now_datetime

from sibbcs.academic import gradebook
from sibbcs.academic.doctype.academic_term.test_academic_term import make_term
from sibbcs.academic.doctype.course.test_course import make_course
from sibbcs.academic.doctype.course_offering.test_course_offering import (
	make_instructor,
	make_offering,
)
from sibbcs.academic.doctype.program_enrollment.test_program_enrollment import (
	make_enrollment,
	make_student,
)
from sibbcs.academic.test_gradebook import make_assignment, make_scheme
from sibbcs.api import coursework, marking


def make_user(email, roles, name="Marking Test"):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": name,
				"user_type": "System User",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
	user = frappe.get_doc("User", email)
	user.set("roles", [])
	for role in roles:
		user.append("roles", {"role": role})
	user.save(ignore_permissions=True)
	return email


class TestMarking(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.term = make_term(
			f"TST-MK-{frappe.generate_hash(length=6)}", status="Open"
		).name

	def setUp(self):
		frappe.set_user("Administrator")
		suffix = frappe.generate_hash(length=6)
		self.offering = make_offering(
			make_course(f"TMK {suffix[:4]}").name, self.term, status="Published"
		).name
		make_scheme(
			self.offering,
			[
				{"component": "Assignment", "weight_pct": 50},
				{"component": "Attendance", "weight_pct": 50},
			],
		)
		self.assignment = make_assignment(
			self.offering, title=f"Essay {suffix[:4]}", points_possible=20
		).name
		self.registration = self._register()

	def tearDown(self):
		frappe.set_user("Administrator")

	def _register(self):
		suffix = frappe.generate_hash(length=6)
		student = make_student(f"Marking Student {suffix}").name
		enrollment = make_enrollment(student).name
		registration = frappe.get_doc(
			{
				"doctype": "Course Registration",
				"program_enrollment": enrollment,
				"course_offering": self.offering,
				"status": "Registered",
			}
		).insert(ignore_permissions=True)
		return registration.name

	def _mark(self, score, post=None, **kw):
		return marking.grade(
			self.assignment, self.registration, score=score, post=post, **kw
		)

	# --- the queue --------------------------------------------------------

	def test_the_queue_lists_students_who_handed_in_nothing(self):
		""""Who has not submitted" is the question a marker actually asks."""
		data = marking.queue(self.assignment)

		self.assertEqual(len(data["rows"]), 1)
		self.assertIsNone(data["rows"][0]["submission"])
		self.assertEqual(data["missing"], 1)

	def test_the_queue_counts_what_is_waiting(self):
		self._mark(15)
		data = marking.queue(self.assignment)

		self.assertEqual(data["ungraded"], 0)
		self.assertEqual(data["unposted"], 1)

	# --- marking ----------------------------------------------------------

	def test_a_score_above_the_marks_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._mark(25)

	def test_a_negative_score_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._mark(-1)

	def test_marking_records_who_did_it(self):
		result = self._mark(15)
		self.assertEqual(result["submission"]["graded_by"], "Administrator")
		self.assertTrue(result["submission"]["graded_on"])

	def test_excused_work_carries_no_score(self):
		result = marking.grade(self.assignment, self.registration, excused=1)
		self.assertIn(result["submission"]["score"], (None, 0, 0.0))
		self.assertEqual(result["submission"]["status"], "Excused")

	# --- posting ----------------------------------------------------------

	def test_an_unposted_score_does_not_reach_the_grade(self):
		"""The point of a posting policy. A mark exists the moment it is
		typed; whether it counts is what `posted` says."""
		self._mark(20)

		registration = frappe.get_doc("Course Registration", self.registration)
		marks = {r.component: r for r in registration.grade_components}

		self.assertFalse(marks["Assignment"].marked)
		self.assertFalse(registration.grade)

	def test_a_posted_score_reaches_the_component(self):
		self._mark(15, post=1)

		registration = frappe.get_doc("Course Registration", self.registration)
		marks = {r.component: r for r in registration.grade_components}

		# 15 of 20 is 75%, and the component is out of 100.
		self.assertTrue(marks["Assignment"].marked)
		self.assertEqual(marks["Assignment"].obtained_marks, 75.0)
		self.assertEqual(marks["Assignment"].source_assignments, 1)

	def test_a_posted_score_reaches_the_transcript(self):
		"""The end of the phase: a mark reaches final_marks, the Grade Scale
		and the letter, through the row a marker used to type into."""
		self._mark(20, post=1)

		# Attendance has no assignment, so it stays hand-marked.
		from sibbcs.api import academic_api

		academic_api.save_grades(
			self.registration,
			[
				{"component": "Attendance", "weight_pct": 50, "max_marks": 100,
				 "obtained_marks": 90},
			],
		)

		registration = frappe.get_doc("Course Registration", self.registration)
		self.assertEqual(registration.final_marks, 95.0)
		self.assertTrue(registration.grade)

	def test_withdrawing_a_posted_score_takes_it_back_out(self):
		self._mark(20, post=1)
		marking.set_posted(self.assignment, 0, course_registration=self.registration)

		registration = frappe.get_doc("Course Registration", self.registration)
		marks = {r.component: r for r in registration.grade_components}
		self.assertFalse(marks["Assignment"].marked)

	def test_posting_an_unmarked_submission_does_nothing(self):
		"""Showing a student a blank and calling it a result."""
		coursework_registration = self.registration
		frappe.get_doc(
			{
				"doctype": "Assignment Submission",
				"assignment": self.assignment,
				"course_registration": coursework_registration,
				"status": "Submitted",
				"submitted_on": now_datetime(),
			}
		).insert(ignore_permissions=True)

		result = marking.set_posted(self.assignment, 1)
		self.assertEqual(result["changed"], 0)

	def test_the_gradebook_shows_no_total_until_the_course_is_fully_marked(self):
		"""`final_marks` is a Float and so NOT NULL DEFAULT 0: a half-marked
		course reads back 0.0, and printing that as a total beside a grade of
		"not final" is the same lie `marked` exists to stop telling."""
		self._mark(20, post=1)

		grid = marking.gradebook_grid(self.offering)
		row = next(
			entry
			for entry in grid["rows"]
			if entry["course_registration"] == self.registration
		)

		# Attendance is still unmarked, so nothing has been totalled.
		self.assertFalse(row["marks_complete"])
		self.assertIsNone(row["final_marks"])

		from sibbcs.api import academic_api

		academic_api.save_grades(
			self.registration,
			[{"component": "Attendance", "weight_pct": 50, "max_marks": 100,
			  "obtained_marks": 80}],
		)

		grid = marking.gradebook_grid(self.offering)
		row = next(
			entry
			for entry in grid["rows"]
			if entry["course_registration"] == self.registration
		)
		self.assertTrue(row["marks_complete"])
		self.assertEqual(row["final_marks"], 90.0)

	# --- late work --------------------------------------------------------

	def test_a_late_penalty_applies_once_however_often_it_is_saved(self):
		"""The penalty is computed from `score`, never written into it, so
		re-saving cannot compound the deduction."""
		frappe.db.set_value(
			"Course Assignment",
			self.assignment,
			{
				"due_date": add_days(now_datetime(), -3),
				"late_policy": "Accept with penalty",
				"late_penalty_pct_per_day": 10,
			},
		)

		submission = frappe.get_doc(
			{
				"doctype": "Assignment Submission",
				"assignment": self.assignment,
				"course_registration": self.registration,
				"status": "Submitted",
				"submitted_on": now_datetime(),
			}
		).insert(ignore_permissions=True)

		submission.score = 20
		submission.posted = 1
		submission.save(ignore_permissions=True)

		first = gradebook.effective_score(submission.as_dict())
		submission.save(ignore_permissions=True)
		submission.reload()
		second = gradebook.effective_score(submission.as_dict())

		self.assertEqual(first, second)
		self.assertEqual(submission.score, 20, "the mark given is not rewritten")
		self.assertLess(second, 20, "but what it is worth is reduced")

	def test_a_penalty_cannot_take_a_mark_below_zero(self):
		frappe.db.set_value(
			"Course Assignment",
			self.assignment,
			{
				"due_date": add_days(now_datetime(), -40),
				"late_policy": "Accept with penalty",
				"late_penalty_pct_per_day": 10,
			},
		)
		submission = frappe.get_doc(
			{
				"doctype": "Assignment Submission",
				"assignment": self.assignment,
				"course_registration": self.registration,
				"status": "Submitted",
				"submitted_on": now_datetime(),
				"score": 20,
			}
		).insert(ignore_permissions=True)

		self.assertEqual(gradebook.effective_score(submission.as_dict()), 0.0)

	# --- the rules that keep courses apart --------------------------------

	def test_a_submission_cannot_join_two_different_courses(self):
		other = make_offering(
			make_course(f"TMK X{frappe.generate_hash(length=4)}").name,
			self.term,
			status="Published",
		).name
		student = make_student(f"Other {frappe.generate_hash(length=6)}").name
		other_registration = frappe.get_doc(
			{
				"doctype": "Course Registration",
				"program_enrollment": make_enrollment(student).name,
				"course_offering": other,
				"status": "Registered",
			}
		).insert(ignore_permissions=True)

		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Assignment Submission",
					"assignment": self.assignment,
					"course_registration": other_registration.name,
					"status": "Submitted",
				}
			).insert(ignore_permissions=True)

	def test_a_teacher_cannot_mark_another_teachers_assignment(self):
		suffix = frappe.generate_hash(length=6)
		email = make_user(f"stranger.mk.{suffix}@example.invalid", ["Faculty"])
		make_instructor(f"MK Stranger {suffix}", user=email)

		frappe.set_user(email)
		with self.assertRaises(frappe.PermissionError):
			marking.queue(self.assignment)


class TestCoursework(FrappeTestCase):
	"""The student's half."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.term = make_term(
			f"TST-CW-{frappe.generate_hash(length=6)}", status="Open"
		).name

	def setUp(self):
		frappe.set_user("Administrator")
		suffix = frappe.generate_hash(length=6)
		self.offering = make_offering(
			make_course(f"TCW {suffix[:4]}").name, self.term, status="Published"
		).name
		make_scheme(self.offering, [{"component": "Assignment", "weight_pct": 100}])
		self.assignment = make_assignment(
			self.offering, title=f"Paper {suffix[:4]}", points_possible=10, published=1
		).name

		self.email = make_user(f"cw.{suffix}@example.invalid", ["Student"], "Coursework")
		self.student = make_student(f"Coursework Student {suffix}", user=self.email).name
		self.registration = frappe.get_doc(
			{
				"doctype": "Course Registration",
				"program_enrollment": make_enrollment(self.student).name,
				"course_offering": self.offering,
				"status": "Registered",
			}
		).insert(ignore_permissions=True).name

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_a_student_sees_the_published_work_on_their_course(self):
		frappe.set_user(self.email)
		data = coursework.coursework(self.registration)

		self.assertEqual(len(data["rows"]), 1)
		self.assertEqual(data["rows"][0]["assignment"]["title"][:5], "Paper")

	def test_unpublished_work_is_invisible(self):
		frappe.db.set_value("Course Assignment", self.assignment, "published", 0)

		frappe.set_user(self.email)
		self.assertEqual(coursework.coursework(self.registration)["rows"], [])

	def test_a_student_cannot_open_somebody_elses_registration(self):
		other = make_student(f"Someone Else {frappe.generate_hash(length=6)}").name
		other_registration = frappe.get_doc(
			{
				"doctype": "Course Registration",
				"program_enrollment": make_enrollment(other).name,
				"course_offering": self.offering,
				"status": "Registered",
			}
		).insert(ignore_permissions=True).name

		frappe.set_user(self.email)
		with self.assertRaises(frappe.PermissionError):
			coursework.coursework(other_registration)

	def test_handing_work_in(self):
		frappe.set_user(self.email)
		result = coursework.submit(self.registration, self.assignment, body="My essay")

		self.assertEqual(result["attempt"], 1)
		self.assertEqual(result["submission"]["status"], "Submitted")

	def test_an_unposted_mark_is_absent_from_the_students_payload(self):
		"""Not hidden by the front end -- absent from the payload."""
		frappe.set_user(self.email)
		coursework.submit(self.registration, self.assignment, body="My essay")

		frappe.set_user("Administrator")
		marking.grade(self.assignment, self.registration, score=9)

		frappe.set_user(self.email)
		row = coursework.coursework(self.registration)["rows"][0]

		self.assertNotIn("score", row["submission"])
		self.assertNotIn("feedback", row["submission"])

	def test_a_posted_mark_reaches_the_student(self):
		frappe.set_user(self.email)
		coursework.submit(self.registration, self.assignment, body="My essay")

		frappe.set_user("Administrator")
		marking.grade(
			self.assignment, self.registration, score=9, feedback="Good work", post=1
		)

		frappe.set_user(self.email)
		row = coursework.coursework(self.registration)["rows"][0]

		self.assertEqual(row["submission"]["score"], 9)
		self.assertEqual(row["submission"]["feedback"], "Good work")

	def test_work_cannot_be_resubmitted_once_it_has_been_returned(self):
		frappe.set_user(self.email)
		coursework.submit(self.registration, self.assignment, body="First")

		frappe.set_user("Administrator")
		marking.grade(self.assignment, self.registration, score=9, post=1)

		frappe.set_user(self.email)
		with self.assertRaises(frappe.ValidationError):
			coursework.submit(self.registration, self.assignment, body="Second")

	def test_a_closed_assignment_refuses_work_and_says_why(self):
		frappe.db.set_value(
			"Course Assignment",
			self.assignment,
			"available_until",
			add_days(now_datetime(), -1),
		)

		frappe.set_user(self.email)
		row = coursework.coursework(self.registration)["rows"][0]
		self.assertFalse(row["open"]["open"])
		self.assertIn("closed", row["open"]["reason"].lower())

		with self.assertRaises(frappe.ValidationError):
			coursework.submit(self.registration, self.assignment, body="Too late")

	def test_no_endpoint_here_takes_a_student(self):
		"""The house rule that keeps the portal honest."""
		import inspect

		for name, function in inspect.getmembers(coursework, inspect.isfunction):
			# Only what this module defines. An imported helper is covered by
			# the rules of the module it comes from.
			if function.__module__ != coursework.__name__:
				continue
			if not name.startswith("_"):
				parameters = inspect.signature(function).parameters
				self.assertNotIn("student", parameters, name)
				self.assertNotIn("user", parameters, name)
