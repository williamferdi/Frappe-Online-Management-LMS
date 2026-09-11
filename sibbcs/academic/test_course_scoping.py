# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""One test per gap the audit of 2026-09-11 found: a teacher reaching into a
course they do not teach.

Two teachers, one course each, and every test asks whether "mine" can reach
"theirs". The teacher's own course is tested alongside wherever it is not
already covered elsewhere, because a guard that also stops the legitimate case
is not a guard.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, now_datetime

from sibbcs.academic import lms_sync
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
from sibbcs.academic.test_permissions import make_user
from sibbcs.academic.test_quizzes import make_bank, make_question
from sibbcs.api import academic_api, collaboration, content, marking, quiz, syllabus


class TestCourseScoping(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		suffix = frappe.generate_hash(length=6)
		cls.suffix = suffix
		cls.term = make_term(f"TST-CSC-{suffix}", status="Open").name

		cls.mine_user = make_user(f"csc.mine.{suffix}@example.invalid", ["Faculty"])
		cls.theirs_user = make_user(f"csc.theirs.{suffix}@example.invalid", ["Faculty"])
		cls.office_user = make_user(
			f"csc.office.{suffix}@example.invalid", ["Academic Coordinator"]
		)

		mine_instructor = make_instructor(f"CSC Mine {suffix}", user=cls.mine_user).name
		theirs_instructor = make_instructor(
			f"CSC Theirs {suffix}", user=cls.theirs_user
		).name

		cls.mine_course = make_course(f"TSC CM{suffix[:3]}").name
		cls.theirs_course = make_course(f"TSC CT{suffix[:3]}").name
		cls.mine_offering = make_offering(
			cls.mine_course, cls.term, instructor=mine_instructor, status="Published"
		).name
		cls.theirs_offering = make_offering(
			cls.theirs_course, cls.term, instructor=theirs_instructor, status="Published"
		).name

		# One student on each course, and one on both.
		cls.mine_student, _ = cls._student_on([cls.mine_offering])
		cls.theirs_student, theirs_registrations = cls._student_on([cls.theirs_offering])
		cls.both_student, _ = cls._student_on([cls.mine_offering, cls.theirs_offering])
		cls.theirs_registration = theirs_registrations[cls.theirs_offering]

		for offering in (cls.mine_offering, cls.theirs_offering):
			make_scheme(offering, [{"component": "Assignment", "weight_pct": 100}])
		cls.mine_assignment = make_assignment(
			cls.mine_offering, title=f"Mine {suffix[:4]}", published=1
		).name
		cls.theirs_assignment = make_assignment(
			cls.theirs_offering, title=f"Theirs {suffix[:4]}", published=1
		).name

		# The Course's own material.
		cls.mine_page = cls._page(cls.mine_course, "Mine")
		cls.theirs_page = cls._page(cls.theirs_course, "Theirs")
		cls.theirs_file = frappe.get_doc(
			{
				"doctype": "Course File",
				"course": cls.theirs_course,
				"title": "Their reading",
				"file": "/files/their-reading.pdf",
			}
		).insert(ignore_permissions=True).name

		lms_sync.ensure_lms_course(cls.theirs_course)
		chapter = content.save_chapter(cls.theirs_offering, "Their week")["chapter"]
		cls.theirs_lesson = content.save_lesson(
			cls.theirs_offering,
			chapter,
			"Their lecture",
			[{"type": "paragraph", "data": {"text": "Not yours"}}],
		)["lesson"]

		cls.mine_bank = make_bank(f"CSC Mine {suffix}", cls.mine_course).name
		cls.theirs_bank = make_bank(f"CSC Theirs {suffix}", cls.theirs_course).name
		cls.shared_bank = make_bank(f"CSC Shared {suffix}").name
		cls.mine_question = make_question(cls.mine_bank).name
		cls.theirs_question = make_question(cls.theirs_bank).name
		cls.theirs_quiz = frappe.get_doc(
			{
				"doctype": "Course Quiz",
				"course": cls.theirs_course,
				"title": f"Their quiz {suffix}",
				"sources": [{"bank": cls.theirs_bank, "pick": 1}],
			}
		).insert(ignore_permissions=True).name

		criteria = [{"title": "Argument", "points_possible": 10}]
		cls.mine_rubric = marking.save_rubric("Mine", criteria, course=cls.mine_course)["name"]
		theirs = marking.save_rubric("Theirs", criteria, course=cls.theirs_course)
		cls.theirs_rubric = theirs["name"]
		cls.theirs_criterion = theirs["criteria"][0]["name"]
		cls.shared_rubric = marking.save_rubric(f"Shared {suffix}", criteria)["name"]

		# Collaboration, on each side.
		cls.mine_set = cls._insert(
			"Course Group Set", course_offering=cls.mine_offering, title="Mine"
		)
		cls.theirs_set = cls._insert(
			"Course Group Set", course_offering=cls.theirs_offering, title="Theirs"
		)
		cls.theirs_group = cls._insert("Course Group", group_set=cls.theirs_set, title="Theirs")
		cls.theirs_override = cls._insert(
			"Assignment Override",
			assignment=cls.theirs_assignment,
			course_registration=cls.theirs_registration,
			due_date=add_days(now_datetime(), 3),
		)
		cls.theirs_discussion = cls._insert(
			"Course Discussion", course_offering=cls.theirs_offering, title="Theirs"
		)

		cls.mine_module = syllabus.save_module(cls.mine_offering, {"title": "Mine"})["module"]
		cls.theirs_module = syllabus.save_module(cls.theirs_offering, {"title": "Theirs"})[
			"module"
		]

	@staticmethod
	def _insert(doctype, **values):
		return frappe.get_doc({"doctype": doctype, **values}).insert(
			ignore_permissions=True
		).name

	@classmethod
	def _page(cls, course, title):
		return cls._insert("Course Page", course=course, title=title, body=f"<p>{title}</p>")

	@staticmethod
	def _student_on(offerings):
		student = make_student(f"CSC Student {frappe.generate_hash(length=6)}").name
		enrollment = make_enrollment(student).name
		registrations = {
			offering: frappe.get_doc(
				{
					"doctype": "Course Registration",
					"program_enrollment": enrollment,
					"course_offering": offering,
					"status": "Registered",
				}
			).insert(ignore_permissions=True).name
			for offering in offerings
		}
		return student, registrations

	def setUp(self):
		frappe.set_user("Administrator")
		# The scoping answers are memoised per request, and a whole test run is
		# one request. Start each test from what the database says.
		frappe.local.sibbcs_scope_cache = {}

	def tearDown(self):
		frappe.set_user("Administrator")

	# --- the old page endpoints -------------------------------------------

	def test_the_old_page_endpoints_are_gone(self):
		"""`syllabus.page` opened any page by name and `save_page` could
		overwrite one; nothing called them, so they went."""
		for name in ("page", "pages", "save_page"):
			self.assertFalse(hasattr(syllabus, name), name)

	# --- quizzes ----------------------------------------------------------

	def test_another_courses_question_bank_is_not_readable(self):
		"""It carries the answers."""
		frappe.set_user(self.mine_user)
		with self.assertRaises(frappe.PermissionError):
			quiz.bank(self.theirs_bank)

	def test_a_teacher_reads_their_own_bank_and_a_shared_one(self):
		frappe.set_user(self.mine_user)
		self.assertEqual(quiz.bank(self.mine_bank)["name"], self.mine_bank)
		self.assertEqual(quiz.bank(self.shared_bank)["name"], self.shared_bank)

	def test_the_bank_list_is_the_teachers_own_and_the_shared_ones(self):
		frappe.set_user(self.mine_user)
		names = [row["name"] for row in quiz.banks()["rows"]]

		self.assertIn(self.mine_bank, names)
		self.assertIn(self.shared_bank, names)
		self.assertNotIn(self.theirs_bank, names)

	def test_another_courses_question_cannot_be_changed(self):
		frappe.set_user(self.mine_user)
		with self.assertRaises(frappe.PermissionError):
			quiz.save_question(
				self.theirs_bank, {"question": "<p>Changed</p>"}, question=self.theirs_question
			)

	def test_a_question_cannot_be_pulled_into_the_teachers_own_bank(self):
		frappe.set_user(self.mine_user)
		with self.assertRaises(frappe.PermissionError):
			quiz.save_question(
				self.mine_bank, {"question": "<p>Mine now</p>"}, question=self.theirs_question
			)

		self.assertEqual(
			frappe.db.get_value("Bank Question", self.theirs_question, "bank"), self.theirs_bank
		)

	def test_another_courses_question_cannot_be_deleted(self):
		frappe.set_user(self.mine_user)
		with self.assertRaises(frappe.PermissionError):
			quiz.delete_question(self.theirs_question)

		self.assertTrue(frappe.db.exists("Bank Question", self.theirs_question))

	def test_another_courses_quiz_cannot_be_changed_or_carried_off(self):
		frappe.set_user(self.mine_user)
		with self.assertRaises(frappe.PermissionError):
			quiz.save_quiz(
				self.theirs_course, {"reveal_answers": "After the attempt"}, name=self.theirs_quiz
			)
		with self.assertRaises(frappe.PermissionError):
			quiz.save_quiz(
				self.mine_course, {"reveal_answers": "After the attempt"}, name=self.theirs_quiz
			)

		row = frappe.db.get_value(
			"Course Quiz", self.theirs_quiz, ["course", "reveal_answers"], as_dict=True
		)
		self.assertEqual(row.course, self.theirs_course)
		self.assertNotEqual(row.reveal_answers, "After the attempt")

	def test_a_quiz_cannot_draw_on_another_courses_bank(self):
		frappe.set_user(self.mine_user)
		with self.assertRaises(frappe.PermissionError):
			quiz.save_quiz(
				self.mine_course,
				{"title": "Borrowed", "sources": [{"bank": self.theirs_bank, "pick": 1}]},
			)

	def test_a_shared_bank_is_changed_only_by_the_office(self):
		frappe.set_user(self.mine_user)
		with self.assertRaises(frappe.PermissionError):
			quiz.save_bank("Renamed", name=self.shared_bank)

		frappe.set_user(self.office_user)
		quiz.save_bank(f"CSC Shared {self.suffix} (edited)", name=self.shared_bank)

	def test_a_teacher_still_builds_a_quiz_for_their_own_course(self):
		frappe.set_user(self.mine_user)
		bank = quiz.save_bank(
			f"CSC Mine new {frappe.generate_hash(length=5)}", course=self.mine_course
		)["bank"]
		quiz.save_question(
			bank,
			{
				"question": "<p>2 + 2?</p>",
				"question_type": "Choice",
				"points": 1,
				"options": [
					{"option_text": "4", "is_correct": 1},
					{"option_text": "5", "is_correct": 0},
				],
			},
		)

		made = quiz.save_quiz(
			self.mine_course, {"title": "Mine", "sources": [{"bank": bank, "pick": 1}]}
		)
		self.assertTrue(made["quiz"])

	# --- rubrics ----------------------------------------------------------

	def test_another_courses_rubric_cannot_be_rewritten_or_carried_off(self):
		frappe.set_user(self.mine_user)
		criteria = [{"title": "Anything", "points_possible": 1}]
		with self.assertRaises(frappe.PermissionError):
			marking.save_rubric(
				"Rewritten", criteria, name=self.theirs_rubric, course=self.theirs_course
			)
		with self.assertRaises(frappe.PermissionError):
			marking.save_rubric("Moved", criteria, name=self.theirs_rubric, course=self.mine_course)

		self.assertEqual(
			frappe.db.get_value("Course Rubric", self.theirs_rubric, "course"), self.theirs_course
		)

	def test_a_rubric_cannot_take_another_rubrics_criterion(self):
		frappe.set_user(self.mine_user)
		marking.save_rubric(
			"Mine",
			[{"name": self.theirs_criterion, "title": "Stolen", "points_possible": 5}],
			name=self.mine_rubric,
			course=self.mine_course,
		)

		frappe.set_user("Administrator")
		row = frappe.db.get_value(
			"Rubric Criterion", self.theirs_criterion, ["rubric", "title"], as_dict=True
		)
		self.assertEqual(row.rubric, self.theirs_rubric)
		self.assertNotEqual(row.title, "Stolen")

	def test_a_shared_rubric_is_changed_only_by_the_office(self):
		frappe.set_user(self.mine_user)
		with self.assertRaises(frappe.PermissionError):
			marking.save_rubric(
				"Shared, edited", [{"title": "X", "points_possible": 1}], name=self.shared_rubric
			)

	def test_the_rubric_list_is_the_teachers_own_and_the_shared_ones(self):
		frappe.set_user(self.mine_user)
		names = [row["name"] for row in marking.rubrics()["rows"]]

		self.assertIn(self.mine_rubric, names)
		self.assertIn(self.shared_rubric, names)
		self.assertNotIn(self.theirs_rubric, names)

	def test_another_courses_rubric_is_not_readable(self):
		frappe.set_user(self.mine_user)
		with self.assertRaises(frappe.PermissionError):
			marking.rubric(self.theirs_rubric)

	# --- collaboration ----------------------------------------------------

	def test_a_group_set_cannot_be_taken_from_another_course(self):
		frappe.set_user(self.mine_user)
		with self.assertRaises(frappe.PermissionError):
			collaboration.save_group_set(self.mine_offering, "Mine now", name=self.theirs_set)

		self.assertEqual(
			frappe.db.get_value("Course Group Set", self.theirs_set, "course_offering"),
			self.theirs_offering,
		)

	def test_a_teacher_still_edits_their_own_group_set(self):
		frappe.set_user(self.mine_user)
		collaboration.save_group_set(self.mine_offering, "Renamed", name=self.mine_set)

		self.assertEqual(
			frappe.db.get_value("Course Group Set", self.mine_set, "title"), "Renamed"
		)

	def test_a_group_cannot_be_moved_into_the_teachers_own_set(self):
		frappe.set_user(self.mine_user)
		with self.assertRaises(frappe.PermissionError):
			collaboration.save_group(self.mine_set, "Mine now", name=self.theirs_group)

		self.assertEqual(
			frappe.db.get_value("Course Group", self.theirs_group, "group_set"), self.theirs_set
		)

	def test_an_override_cannot_be_moved_onto_the_teachers_own_assignment(self):
		frappe.set_user(self.mine_user)
		with self.assertRaises(frappe.PermissionError):
			collaboration.save_override(
				self.mine_assignment, {"reason": "Mine now"}, name=self.theirs_override
			)

		self.assertEqual(
			frappe.db.get_value("Assignment Override", self.theirs_override, "assignment"),
			self.theirs_assignment,
		)

	def test_an_override_cannot_be_for_another_courses_group(self):
		"""Refused by the override itself, which already checked its target."""
		frappe.set_user(self.mine_user)
		with self.assertRaises(frappe.ValidationError):
			collaboration.save_override(
				self.mine_assignment,
				{"course_group": self.theirs_group, "due_date": add_days(now_datetime(), 3)},
			)

	def test_a_discussion_cannot_be_taken_from_another_course(self):
		frappe.set_user(self.mine_user)
		with self.assertRaises(frappe.PermissionError):
			collaboration.save_discussion(
				self.mine_offering, {"title": "Mine now"}, name=self.theirs_discussion
			)

		self.assertEqual(
			frappe.db.get_value("Course Discussion", self.theirs_discussion, "course_offering"),
			self.theirs_offering,
		)

	def test_a_discussion_cannot_grade_another_courses_assignment(self):
		frappe.set_user(self.mine_user)
		with self.assertRaises(frappe.PermissionError):
			collaboration.save_discussion(
				self.mine_offering, {"title": "Borrowed marks", "assignment": self.theirs_assignment}
			)

	# --- module items -----------------------------------------------------

	def test_an_item_cannot_open_another_courses_material(self):
		"""Otherwise it reads another course's page or lesson through the
		preview -- and puts it in front of this course's students."""
		frappe.set_user(self.mine_user)
		for pointer in (
			{"item_type": "Page", "page": self.theirs_page},
			{"item_type": "File", "file": self.theirs_file},
			{"item_type": "Lesson", "lesson": self.theirs_lesson},
			{"item_type": "Assignment", "assignment": self.theirs_assignment},
		):
			with self.subTest(pointer=pointer["item_type"]):
				with self.assertRaises(frappe.ValidationError):
					syllabus.save_item(self.mine_module, {"title": "Borrowed", **pointer})

	def test_an_item_still_opens_its_own_courses_page(self):
		frappe.set_user(self.mine_user)
		item = syllabus.save_item(
			self.mine_module, {"item_type": "Page", "page": self.mine_page}
		)["item"]

		self.assertEqual(frappe.db.get_value("Course Module Item", item, "page"), self.mine_page)

	def test_a_module_cannot_wait_for_another_courses_module(self):
		frappe.set_user(self.mine_user)
		syllabus.save_module(
			self.mine_offering, {"prerequisites": [self.theirs_module]}, module=self.mine_module
		)

		self.assertEqual(frappe.get_doc("Course Module", self.mine_module).prerequisites, [])

	# --- students ---------------------------------------------------------

	def test_a_teachers_roll_is_their_own_students(self):
		frappe.set_user(self.mine_user)
		names = [row["name"] for row in academic_api.students(limit=500)["rows"]]

		self.assertIn(self.mine_student, names)
		self.assertIn(self.both_student, names)
		self.assertNotIn(self.theirs_student, names)

	def test_a_teacher_cannot_open_a_student_they_do_not_teach(self):
		frappe.set_user(self.mine_user)
		with self.assertRaises(frappe.PermissionError):
			academic_api.student(self.theirs_student)

	def test_a_students_record_shows_a_teacher_only_their_own_courses(self):
		frappe.set_user(self.mine_user)
		offerings = [
			row["course_offering"]
			for row in academic_api.student(self.both_student)["registrations"]
		]

		self.assertEqual(offerings, [self.mine_offering])

	def test_the_office_still_sees_every_course_on_a_students_record(self):
		frappe.set_user(self.office_user)
		offerings = {
			row["course_offering"]
			for row in academic_api.student(self.both_student)["registrations"]
		}

		self.assertEqual(offerings, {self.mine_offering, self.theirs_offering})

	def test_the_demographics_describe_a_teachers_own_students(self):
		frappe.set_user(self.mine_user)
		self.assertEqual(academic_api.demographics()["total"], 2)

	def test_desk_shows_a_teacher_only_their_own_students(self):
		frappe.set_user(self.mine_user)
		names = frappe.get_list("Student", pluck="name", limit_page_length=0)

		self.assertIn(self.mine_student, names)
		self.assertNotIn(self.theirs_student, names)
		self.assertFalse(frappe.has_permission("Student", "read", doc=self.theirs_student))
		self.assertEqual(
			frappe.get_list(
				"Program Enrollment", filters={"student": self.theirs_student}, pluck="name"
			),
			[],
		)

	# --- Desk: the permission rules themselves ----------------------------

	def test_desk_holds_a_teacher_to_their_own_courses_pages_and_files(self):
		frappe.set_user(self.mine_user)

		self.assertTrue(frappe.has_permission("Course Page", "write", doc=self.mine_page))
		self.assertFalse(frappe.has_permission("Course Page", "write", doc=self.theirs_page))
		self.assertFalse(frappe.has_permission("Course Page", "read", doc=self.theirs_page))
		self.assertFalse(frappe.has_permission("Course File", "write", doc=self.theirs_file))

		pages = frappe.get_list("Course Page", pluck="name", limit_page_length=0)
		self.assertIn(self.mine_page, pages)
		self.assertNotIn(self.theirs_page, pages)

	def test_desk_lets_a_teacher_read_but_not_change_a_shared_bank(self):
		frappe.set_user(self.mine_user)

		self.assertTrue(frappe.has_permission("Question Bank", "read", doc=self.shared_bank))
		self.assertFalse(frappe.has_permission("Question Bank", "write", doc=self.shared_bank))
		self.assertFalse(frappe.has_permission("Question Bank", "read", doc=self.theirs_bank))

		banks = frappe.get_list("Question Bank", pluck="name", limit_page_length=0)
		self.assertIn(self.mine_bank, banks)
		self.assertIn(self.shared_bank, banks)
		self.assertNotIn(self.theirs_bank, banks)

	def test_desk_guards_the_questions_and_criteria_inside(self):
		frappe.set_user(self.mine_user)

		self.assertTrue(frappe.has_permission("Bank Question", "write", doc=self.mine_question))
		self.assertFalse(frappe.has_permission("Bank Question", "read", doc=self.theirs_question))
		self.assertFalse(
			frappe.has_permission("Rubric Criterion", "write", doc=self.theirs_criterion)
		)
		self.assertNotIn(
			self.theirs_question,
			frappe.get_list("Bank Question", pluck="name", limit_page_length=0),
		)

	def test_desk_holds_a_teacher_to_their_own_courses_quizzes(self):
		frappe.set_user(self.mine_user)
		self.assertFalse(frappe.has_permission("Course Quiz", "write", doc=self.theirs_quiz))

	def test_the_office_is_not_narrowed(self):
		frappe.set_user(self.office_user)

		self.assertTrue(frappe.has_permission("Question Bank", "write", doc=self.theirs_bank))
		self.assertTrue(frappe.has_permission("Course Page", "write", doc=self.theirs_page))
		self.assertIn(self.theirs_student, frappe.get_list("Student", pluck="name", limit_page_length=0))
