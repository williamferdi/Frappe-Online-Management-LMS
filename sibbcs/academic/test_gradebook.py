# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""One test per rule about the grade scheme and the work it weighs.

The load-bearing claim of the whole phase is that a scheme is opt-in: an
offering without one grades exactly as it did before. That is pinned first,
because if it ever stops being true the migration story stops being true with
it.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

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
from sibbcs.api import academic_api, course as course_api


def make_scheme(offering, rows):
	if frappe.db.exists("Course Grade Scheme", offering):
		doc = frappe.get_doc("Course Grade Scheme", offering)
	else:
		doc = frappe.new_doc("Course Grade Scheme")
		doc.course_offering = offering
	doc.set("rows", [])
	for row in rows:
		doc.append("rows", row)
	return doc.save(ignore_permissions=True)


def make_assignment(offering, **kw):
	values = {
		"doctype": "Course Assignment",
		"course_offering": offering,
		"title": kw.pop("title", "Essay One"),
		"component": kw.pop("component", "Assignment"),
		"points_possible": kw.pop("points_possible", 20),
		"submission_type": kw.pop("submission_type", "Text Entry"),
		"late_policy": kw.pop("late_policy", "Accept"),
	}
	values.update(kw)
	return frappe.get_doc(values).insert(ignore_permissions=True)


class TestGradeScheme(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.term = make_term(
			f"TST-GB-{frappe.generate_hash(length=6)}", status="Open"
		).name

	def setUp(self):
		"""A fresh offering and a fresh student for every test.

		Sharing them coupled the tests two ways: the eligibility engine
		refuses a second registration for the same student on the same
		offering, and an assignment created by one test turned another test's
		hand-marked bucket into a computed one depending on the order they
		ran in.
		"""
		frappe.set_user("Administrator")
		suffix = frappe.generate_hash(length=6)
		self.offering = make_offering(
			make_course(f"TGB A{suffix[:4]}").name, self.term, status="Published"
		).name
		self.plain = make_offering(
			make_course(f"TGB B{suffix[:4]}").name, self.term, status="Published"
		).name

	def _register(self, offering):
		suffix = frappe.generate_hash(length=6)
		student = make_student(f"Gradebook Student {suffix}").name
		enrollment = make_enrollment(student).name
		return frappe.get_doc(
			{
				"doctype": "Course Registration",
				"program_enrollment": enrollment,
				"course_offering": offering,
				"status": "Registered",
			}
		).insert(ignore_permissions=True)

	# --- the promise that makes migration unnecessary ---------------------

	def test_an_offering_with_no_scheme_grades_exactly_as_before(self):
		"""The load-bearing claim of the phase. Hand-typed marking must be
		untouched by anything the gradebook adds."""
		registration = self._register(self.plain)

		result = academic_api.save_grades(
			registration.name,
			[
				{"component": "Assignment", "weight_pct": 60, "max_marks": 100,
				 "obtained_marks": 70},
				{"component": "Attendance", "weight_pct": 40, "max_marks": 100,
				 "obtained_marks": 90},
			],
		)

		self.assertEqual(result["final_marks"], 78.0)
		self.assertFalse(gradebook.is_scheme_driven(self.plain))

	# --- the scheme itself ------------------------------------------------

	def test_weights_must_total_one_hundred(self):
		with self.assertRaises(frappe.ValidationError):
			make_scheme(
				self.offering,
				[
					{"component": "Assignment", "weight_pct": 60},
					{"component": "Exam", "weight_pct": 30},
				],
			)

	def test_a_component_cannot_appear_twice(self):
		"""Two rows for one component do not weigh it more heavily -- the
		components table is keyed by name, so one would overwrite the other."""
		with self.assertRaises(frappe.ValidationError):
			make_scheme(
				self.offering,
				[
					{"component": "Assignment", "weight_pct": 50},
					{"component": "Assignment", "weight_pct": 50},
				],
			)

	def test_an_empty_scheme_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			make_scheme(self.offering, [])

	def test_the_scheme_is_named_after_its_offering(self):
		"""One scheme per offering, enforced by the name rather than by a
		check that could be raced."""
		scheme = make_scheme(
			self.offering,
			[
				{"component": "Assignment", "weight_pct": 50},
				{"component": "Exam", "weight_pct": 50},
			],
		)
		self.assertEqual(scheme.name, self.offering)
		self.assertEqual(scheme.total_weight, 100.0)

	# --- what a scheme does to a registration -----------------------------

	def test_saving_a_scheme_gives_every_registration_its_columns(self):
		registration = self._register(self.offering)
		self.assertEqual(len(registration.grade_components), 0)

		make_scheme(
			self.offering,
			[
				{"component": "Assignment", "weight_pct": 40},
				{"component": "Exam", "weight_pct": 60},
			],
		)

		registration.reload()
		components = {r.component: r for r in registration.grade_components}
		self.assertEqual(set(components), {"Assignment", "Exam"})
		self.assertEqual(components["Exam"].weight_pct, 60)

	def test_an_unmarked_bucket_is_flagged_unmarked(self):
		"""`obtained_marks` is decimal NOT NULL DEFAULT 0, so it cannot hold
		"nobody has marked this" -- and a student can score a genuine zero, so
		the number never meant that anyway. `marked` is what carries it."""
		registration = self._register(self.offering)
		make_scheme(
			self.offering,
			[
				{"component": "Assignment", "weight_pct": 50},
				{"component": "Exam", "weight_pct": 50},
			],
		)

		registration.reload()
		for row in registration.grade_components:
			self.assertFalse(row.marked, f"{row.component} should read as unmarked")
		self.assertFalse(registration.grade)

	def test_a_half_marked_course_does_not_become_a_fail_when_re_saved(self):
		"""The regression this phase found. The exam is marked 80, the essay is
		not marked at all, and the record is saved again -- by a scheme edit, an
		LMS sync, a status change, anything. Before `marked` existed the blank
		came back as 0.0, every component looked marked, and the student was
		awarded an F for work nobody had looked at."""
		registration = self._register(self.offering)
		make_scheme(
			self.offering,
			[
				{"component": "Assignment", "weight_pct": 50},
				{"component": "Exam", "weight_pct": 50},
			],
		)

		academic_api.save_grades(
			registration.name,
			[
				{"component": "Exam", "weight_pct": 50, "max_marks": 100,
				 "obtained_marks": 80},
				{"component": "Assignment", "weight_pct": 50, "max_marks": 100,
				 "obtained_marks": None},
			],
		)

		again = frappe.get_doc("Course Registration", registration.name)
		again.save(ignore_permissions=True)

		self.assertFalse(again.grade, "no letter until every component is marked")
		self.assertFalse(again.passed)

	def test_a_genuine_zero_is_a_mark_and_not_a_blank(self):
		"""The distinction the flag exists for: scoring nothing is a result,
		and it must complete the grade rather than hold it back."""
		registration = self._register(self.offering)
		make_scheme(
			self.offering,
			[
				{"component": "Exam", "weight_pct": 50},
				{"component": "Attendance", "weight_pct": 50},
			],
		)

		result = academic_api.save_grades(
			registration.name,
			[
				{"component": "Exam", "weight_pct": 50, "max_marks": 100,
				 "obtained_marks": 0},
				{"component": "Attendance", "weight_pct": 50, "max_marks": 100,
				 "obtained_marks": 100},
			],
		)

		self.assertEqual(result["final_marks"], 50.0)
		marks = {c["component"]: c for c in result["components"]}
		self.assertEqual(marks["Exam"]["obtained_marks"], 0)
		self.assertTrue(marks["Exam"]["marked"])

	def test_an_unmarked_component_comes_back_blank_not_zero(self):
		"""A screen drawing 0 where nobody has marked repeats the database's
		lie to the marker."""
		registration = self._register(self.offering)
		make_scheme(
			self.offering,
			[
				{"component": "Exam", "weight_pct": 50},
				{"component": "Attendance", "weight_pct": 50},
			],
		)

		result = academic_api.save_grades(
			registration.name,
			[
				{"component": "Exam", "weight_pct": 50, "max_marks": 100,
				 "obtained_marks": 70},
				{"component": "Attendance", "weight_pct": 50, "max_marks": 100,
				 "obtained_marks": None},
			],
		)

		marks = {c["component"]: c for c in result["components"]}
		self.assertIsNone(marks["Attendance"]["obtained_marks"])
		self.assertFalse(marks["Attendance"]["marked"])

	def test_reweighting_a_scheme_keeps_the_marks_already_entered(self):
		registration = self._register(self.offering)
		make_scheme(
			self.offering,
			[
				{"component": "Assignment", "weight_pct": 50},
				{"component": "Attendance", "weight_pct": 50},
			],
		)
		academic_api.save_grades(
			registration.name,
			[
				{"component": "Assignment", "weight_pct": 50, "max_marks": 100,
				 "obtained_marks": 80},
				{"component": "Attendance", "weight_pct": 50, "max_marks": 100,
				 "obtained_marks": 60},
			],
		)

		make_scheme(
			self.offering,
			[
				{"component": "Assignment", "weight_pct": 70},
				{"component": "Attendance", "weight_pct": 30},
			],
		)

		registration.reload()
		marks = {r.component: r.obtained_marks for r in registration.grade_components}
		self.assertEqual(marks["Assignment"], 80)
		self.assertEqual(marks["Attendance"], 60)

	def test_a_dropped_bucket_carrying_a_mark_is_not_silently_deleted(self):
		"""Tidying a table is not worth losing somebody's score."""
		registration = self._register(self.offering)
		make_scheme(
			self.offering,
			[
				{"component": "Assignment", "weight_pct": 50},
				{"component": "Attendance", "weight_pct": 50},
			],
		)
		academic_api.save_grades(
			registration.name,
			[
				{"component": "Assignment", "weight_pct": 50, "max_marks": 100,
				 "obtained_marks": 80},
				{"component": "Attendance", "weight_pct": 50, "max_marks": 100,
				 "obtained_marks": 55},
			],
		)

		make_scheme(self.offering, [{"component": "Assignment", "weight_pct": 100}])

		registration.reload()
		marks = {r.component: r.obtained_marks for r in registration.grade_components}
		self.assertEqual(marks.get("Attendance"), 55)

	def test_deleting_a_scheme_hands_the_offering_back_to_hand_marking(self):
		registration = self._register(self.offering)
		make_scheme(self.offering, [{"component": "Assignment", "weight_pct": 100}])
		make_assignment(self.offering)

		frappe.delete_doc("Course Grade Scheme", self.offering, ignore_permissions=True)

		self.assertFalse(gradebook.is_scheme_driven(self.offering))
		registration.reload()
		for row in registration.grade_components:
			self.assertFalse(row.auto_computed)

	# --- assignments ------------------------------------------------------

	def test_an_assignment_must_count_towards_a_bucket_the_scheme_has(self):
		"""A score rolling into a bucket that does not exist reaches nobody's
		grade."""
		make_scheme(self.offering, [{"component": "Assignment", "weight_pct": 100}])

		with self.assertRaises(frappe.ValidationError):
			make_assignment(self.offering, component="Exam", title="Orphan")

	def test_an_offering_with_no_scheme_may_still_set_work(self):
		"""Structure is optional; setting an essay is not conditional on it."""
		assignment = make_assignment(self.plain, title="No Scheme Essay")
		self.assertTrue(assignment.name)

	def test_dates_must_run_forwards(self):
		make_scheme(self.offering, [{"component": "Assignment", "weight_pct": 100}])

		with self.assertRaises(frappe.ValidationError):
			make_assignment(
				self.offering,
				title="Backwards",
				available_from="2026-10-10 09:00:00",
				due_date="2026-10-01 09:00:00",
			)

	def test_it_cannot_close_before_it_is_due(self):
		make_scheme(self.offering, [{"component": "Assignment", "weight_pct": 100}])

		with self.assertRaises(frappe.ValidationError):
			make_assignment(
				self.offering,
				title="Closes early",
				due_date="2026-10-10 09:00:00",
				available_until="2026-10-05 09:00:00",
			)

	def test_points_must_be_positive(self):
		make_scheme(self.offering, [{"component": "Assignment", "weight_pct": 100}])

		with self.assertRaises(frappe.ValidationError):
			make_assignment(self.offering, title="Worthless", points_possible=0)

	def test_a_penalty_policy_needs_a_penalty(self):
		make_scheme(self.offering, [{"component": "Assignment", "weight_pct": 100}])

		with self.assertRaises(frappe.ValidationError):
			make_assignment(
				self.offering,
				title="Toothless",
				late_policy="Accept with penalty",
				late_penalty_pct_per_day=0,
			)

	def test_work_is_unpublished_until_somebody_publishes_it(self):
		"""The whole phase is faculty-only, and this is what makes that true."""
		make_scheme(self.plain, [{"component": "Assignment", "weight_pct": 100}])
		assignment = make_assignment(self.plain, title="Draft")

		self.assertEqual(assignment.published, 0)

	# --- the two paths must not disagree ----------------------------------

	def test_a_bucket_with_an_assignment_becomes_computed(self):
		registration = self._register(self.offering)
		make_scheme(
			self.offering,
			[
				{"component": "Assignment", "weight_pct": 50},
				{"component": "Attendance", "weight_pct": 50},
			],
		)
		make_assignment(self.offering, component="Assignment")

		registration.reload()
		rows = {r.component: r for r in registration.grade_components}
		self.assertTrue(rows["Assignment"].auto_computed)
		self.assertFalse(
			rows["Attendance"].auto_computed,
			"a bucket with no assignment stays hand-markable",
		)

	def test_a_hand_mark_on_a_computed_bucket_is_refused(self):
		"""The next roll-up would write over it, so losing it now is louder
		than losing it later."""
		registration = self._register(self.offering)
		make_scheme(
			self.offering,
			[
				{"component": "Assignment", "weight_pct": 50},
				{"component": "Attendance", "weight_pct": 50},
			],
		)
		make_assignment(self.offering, component="Assignment")

		with self.assertRaises(frappe.ValidationError):
			academic_api.save_grades(
				registration.name,
				[
					{"component": "Assignment", "weight_pct": 50, "max_marks": 100,
					 "obtained_marks": 90},
					{"component": "Attendance", "weight_pct": 50, "max_marks": 100,
					 "obtained_marks": 90},
				],
			)

	def test_a_hand_mark_on_a_hand_bucket_still_works(self):
		"""A guard that also stops the legitimate case is not a guard.
		Attendance has no assignment, so it stays typeable."""
		registration = self._register(self.offering)
		make_scheme(
			self.offering,
			[
				{"component": "Assignment", "weight_pct": 50},
				{"component": "Attendance", "weight_pct": 50},
			],
		)
		make_assignment(self.offering, component="Assignment")

		registration.reload()
		academic_api.save_grades(
			registration.name,
			[
				{"component": "Assignment", "weight_pct": 50, "max_marks": 100,
				 "obtained_marks": None},
				{"component": "Attendance", "weight_pct": 50, "max_marks": 100,
				 "obtained_marks": 75},
			],
		)

		registration.reload()
		marks = {r.component: r.obtained_marks for r in registration.grade_components}
		self.assertEqual(marks["Attendance"], 75)

	def test_the_scheme_options_match_the_component_options(self):
		"""A scheme row naming a component the table cannot hold is a scheme
		that can never roll up."""
		scheme_options = frappe.get_meta("Grade Scheme Row").get_field("component").options
		component_options = frappe.get_meta("Grade Component").get_field("component").options

		self.assertEqual(scheme_options, component_options)


class TestCourseApi(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		suffix = frappe.generate_hash(length=6)
		cls.term = make_term(f"TST-CAPI-{suffix}", status="Open").name
		cls.mine_user = f"capi.mine.{suffix}@example.invalid"
		cls.theirs_user = f"capi.theirs.{suffix}@example.invalid"
		for email in (cls.mine_user, cls.theirs_user):
			if not frappe.db.exists("User", email):
				frappe.get_doc(
					{
						"doctype": "User",
						"email": email,
						"first_name": "Course API",
						"user_type": "System User",
						"send_welcome_email": 0,
						"roles": [{"role": "Faculty"}],
					}
				).insert(ignore_permissions=True)

		cls.mine = make_offering(
			make_course(f"TCA M{suffix[:3]}").name,
			cls.term,
			status="Published",
			instructor=make_instructor(f"CAPI Mine {suffix}", user=cls.mine_user).name,
		).name
		cls.theirs = make_offering(
			make_course(f"TCA T{suffix[:3]}").name,
			cls.term,
			status="Published",
			instructor=make_instructor(f"CAPI Theirs {suffix}", user=cls.theirs_user).name,
		).name

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_the_shelf_shows_only_the_teachers_own_courses(self):
		frappe.set_user(self.mine_user)

		names = [row["name"] for row in course_api.courses()["rows"]]

		self.assertIn(self.mine, names)
		self.assertNotIn(self.theirs, names)

	def test_opening_another_teachers_course_is_refused(self):
		frappe.set_user(self.mine_user)

		with self.assertRaises(frappe.PermissionError):
			course_api.course(self.theirs)

	def test_writing_a_scheme_onto_another_teachers_course_is_refused(self):
		frappe.set_user(self.mine_user)

		with self.assertRaises(frappe.PermissionError):
			course_api.save_scheme(
				self.theirs, [{"component": "Assignment", "weight_pct": 100}]
			)

	def test_a_teacher_builds_their_own_course_end_to_end(self):
		frappe.set_user(self.mine_user)

		course_api.save_scheme(
			self.mine,
			[
				{"component": "Assignment", "weight_pct": 60},
				{"component": "Exam", "weight_pct": 40},
			],
		)
		saved = course_api.save_assignment(
			self.mine,
			{
				"title": "Essay One",
				"component": "Assignment",
				"points_possible": 20,
				"submission_type": "Text Entry",
				"late_policy": "Accept",
			},
		)

		payload = course_api.course(self.mine)

		self.assertEqual(payload["scheme"]["total_weight"], 100.0)
		self.assertEqual(len(payload["assignments"]), 1)
		self.assertEqual(payload["assignments"][0]["title"], "Essay One")
		self.assertEqual(saved["assignment"]["published"], 0)

	def test_an_assignment_cannot_be_moved_to_another_course_by_payload(self):
		"""`course_offering` is not in ASSIGNMENT_FIELDS, and the endpoint
		checks the one it was given against the one on the record."""
		frappe.set_user(self.mine_user)
		course_api.save_scheme(self.mine, [{"component": "Assignment", "weight_pct": 100}])
		created = course_api.save_assignment(
			self.mine,
			{"title": "Stays put", "component": "Assignment", "points_possible": 10,
			 "submission_type": "Text Entry", "late_policy": "Accept"},
		)["assignment"]

		course_api.save_assignment(
			self.mine,
			{"title": "Renamed", "course_offering": self.theirs, "name": "hacked"},
			assignment=created["name"],
		)

		self.assertEqual(
			frappe.db.get_value("Course Assignment", created["name"], "course_offering"),
			self.mine,
		)

	def test_the_choices_come_from_the_doctypes(self):
		frappe.set_user(self.mine_user)

		options = course_api.choices()

		self.assertIn("Assignment", options["components"])
		self.assertIn("Quiz", options["components"])
		self.assertIn("Text Entry", options["submission_types"])
