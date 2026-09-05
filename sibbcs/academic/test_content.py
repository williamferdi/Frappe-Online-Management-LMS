# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""One test per rule about writing course content in this app.

The claim worth testing is that a lesson written here is an ordinary LMS
lesson -- same DocTypes, same reference rows -- so the LMS keeps working as
the content store and nothing has quietly forked.
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.academic import lesson_content, lms_sync
from sibbcs.academic.doctype.academic_term.test_academic_term import make_term
from sibbcs.academic.doctype.course.test_course import make_course
from sibbcs.academic.doctype.course_offering.test_course_offering import make_offering
from sibbcs.api import content, syllabus


class TestContentAuthoring(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.term = make_term(
			f"TST-CN-{frappe.generate_hash(length=6)}", status="Open"
		).name

	def setUp(self):
		frappe.set_user("Administrator")
		suffix = frappe.generate_hash(length=6)
		self.course = make_course(f"TCN {suffix[:4]}").name
		self.offering = make_offering(self.course, self.term, status="Published").name

	def _with_space(self):
		lms_sync.ensure_lms_course(self.course)
		return frappe.db.get_value("Course", self.course, "lms_course")

	def _chapter(self, title="Week One"):
		return content.save_chapter(self.offering, title)["chapter"]

	# --- a lesson written here is an LMS lesson ---------------------------

	def test_a_chapter_is_referenced_from_the_course(self):
		"""The reference row is what carries order and what the LMS editor
		reads. A chapter without one is visible here and not there."""
		lms_course = self._with_space()
		chapter = self._chapter()

		refs = frappe.get_all(
			"Chapter Reference",
			filters={"parent": lms_course, "parenttype": "LMS Course"},
			pluck="chapter",
		)
		self.assertIn(chapter, refs)

	def test_a_lesson_is_referenced_from_its_chapter(self):
		self._with_space()
		chapter = self._chapter()
		lesson = content.save_lesson(
			self.offering, chapter, "First lesson",
			[{"type": "paragraph", "data": {"text": "Hello"}}],
		)["lesson"]

		refs = frappe.get_all(
			"Lesson Reference",
			filters={"parent": chapter, "parenttype": "Course Chapter"},
			pluck="lesson",
		)
		self.assertIn(lesson, refs)

	def test_the_content_is_editorjs_the_reader_can_draw(self):
		"""Written here, read by the same renderer a student gets."""
		self._with_space()
		chapter = self._chapter()
		lesson = content.save_lesson(
			self.offering,
			chapter,
			"Blocks",
			[
				{"type": "header", "data": {"text": "A heading", "level": 2}},
				{"type": "paragraph", "data": {"text": "Some words"}},
			],
		)["lesson"]

		stored = frappe.db.get_value("Course Lesson", lesson, "content")
		parsed = json.loads(stored)
		self.assertEqual([b["type"] for b in parsed["blocks"]], ["header", "paragraph"])

		payload = lesson_content.lesson_payload(lesson)
		self.assertEqual([b["type"] for b in payload["blocks"]], ["header", "paragraph"])

	def test_a_block_the_reader_cannot_draw_is_not_saved(self):
		"""The editor must not be able to write something the reader would meet
		as an unrecognised block."""
		self._with_space()
		chapter = self._chapter()
		lesson = content.save_lesson(
			self.offering,
			chapter,
			"Mixed",
			[
				{"type": "paragraph", "data": {"text": "Kept"}},
				{"type": "somethingElse", "data": {"x": 1}},
			],
		)["lesson"]

		parsed = json.loads(frappe.db.get_value("Course Lesson", lesson, "content"))
		self.assertEqual([b["type"] for b in parsed["blocks"]], ["paragraph"])

	def test_a_lesson_written_here_reaches_the_module_builder(self):
		"""The whole point: write it, then add it to a module without leaving."""
		self._with_space()
		chapter = self._chapter()
		content.save_lesson(
			self.offering, chapter, "Findable",
			[{"type": "paragraph", "data": {"text": "x"}}],
		)

		offered = syllabus.outline(self.offering)["choices"]["lessons"]
		self.assertEqual([row["title"] for row in offered], ["Findable"])

	def test_editing_a_lesson_replaces_its_blocks(self):
		self._with_space()
		chapter = self._chapter()
		lesson = content.save_lesson(
			self.offering, chapter, "Draft",
			[{"type": "paragraph", "data": {"text": "First"}}],
		)["lesson"]

		content.save_lesson(
			self.offering, chapter, "Revised",
			[{"type": "header", "data": {"text": "Now a heading", "level": 2}}],
			name=lesson,
		)

		draft = content.lesson(lesson)
		self.assertEqual(draft["title"], "Revised")
		self.assertEqual([b["type"] for b in draft["blocks"]], ["header"])

	# --- the outline falls back ------------------------------------------

	def test_a_chapter_with_no_reference_row_is_still_found(self):
		"""A chapter made by a script may have no reference row. It was
		invisible to the builder, while sitting in the database."""
		lms_course = self._with_space()
		chapter = frappe.get_doc(
			{"doctype": "Course Chapter", "course": lms_course, "title": "Orphan"}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Course Lesson",
				"course": lms_course,
				"chapter": chapter.name,
				"title": "Unreferenced",
				"content": json.dumps({"blocks": []}),
			}
		).insert(ignore_permissions=True)

		offered = syllabus.outline(self.offering)["choices"]["lessons"]
		self.assertIn("Unreferenced", [row["title"] for row in offered])

	# --- deleting -----------------------------------------------------------

	def test_deleting_a_lesson_takes_its_module_items_with_it(self):
		"""An item pointing at a deleted lesson is one a student cannot open
		and a teacher cannot explain."""
		self._with_space()
		chapter = self._chapter()
		lesson = content.save_lesson(
			self.offering, chapter, "Doomed",
			[{"type": "paragraph", "data": {"text": "x"}}],
		)["lesson"]

		module = syllabus.save_module(self.offering, {"title": "Week One"})["module"]
		syllabus.save_item(module, {"item_type": "Lesson", "lesson": lesson})

		result = content.delete_lesson(self.offering, lesson)

		self.assertEqual(result["module_items_removed"], 1)
		self.assertEqual(
			frappe.db.count("Course Module Item", {"lesson": lesson}), 0
		)

	# --- pages and files, which previously had no way to exist ------------

	def test_a_page_can_be_written_and_reaches_the_builder(self):
		content.save_page(self.offering, "Syllabus", body="<p>Welcome</p>", published=1)

		offered = syllabus.outline(self.offering)["choices"]["pages"]
		self.assertEqual([row["title"] for row in offered], ["Syllabus"])

	def test_a_file_can_be_recorded_and_reaches_the_builder(self):
		content.save_file(self.offering, "Reading list", file="/files/reading.pdf")

		offered = syllabus.outline(self.offering)["choices"]["files"]
		self.assertEqual([row["title"] for row in offered], ["Reading list"])

	# --- scoping ------------------------------------------------------------

	def test_content_cannot_be_written_onto_another_teachers_course(self):
		from sibbcs.academic.doctype.course_offering.test_course_offering import (
			make_instructor,
		)

		suffix = frappe.generate_hash(length=6)
		email = f"content.{suffix}@example.invalid"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Content",
				"user_type": "System User",
				"send_welcome_email": 0,
				"roles": [{"role": "Faculty"}],
			}
		).insert(ignore_permissions=True)
		make_instructor(f"Content {suffix}", user=email)

		frappe.set_user(email)
		with self.assertRaises(frappe.PermissionError):
			content.save_page(self.offering, "Not mine")

	def test_a_course_with_no_space_says_so_rather_than_failing_oddly(self):
		with self.assertRaises(frappe.ValidationError):
			content.save_chapter(self.offering, "Too early")
