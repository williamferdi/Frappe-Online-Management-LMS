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

		draft = content.lesson(lesson, self.offering)
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

	# --- changing a file -------------------------------------------------------

	def _upload(self):
		"""A private upload, as Frappe's upload endpoint stores one. The content
		differs every time, or Frappe would hand back the same address. Text,
		not PDF: Frappe parses every PDF upload for scripts, and random bytes
		are not a PDF."""
		return (
			frappe.get_doc(
				{
					"doctype": "File",
					"file_name": f"reading-{frappe.generate_hash(length=6)}.txt",
					"content": frappe.generate_hash().encode(),
					"is_private": 1,
				}
			)
			.insert(ignore_permissions=True)
			.file_url
		)

	def test_replacing_a_file_keeps_the_record_its_module_items_point_at(self):
		name = content.save_file(self.offering, "Reading", file=self._upload())["file"]
		new = self._upload()

		content.save_file(self.offering, "Reading", file=new, name=name)

		self.assertEqual(frappe.db.get_value("Course File", name, "file"), new)
		self.assertEqual(frappe.db.count("Course File", {"course": self.course}), 1)

	def test_the_replacement_is_attached_so_students_can_open_it(self):
		"""A private file is served to whoever can read what it is attached to."""
		name = content.save_file(self.offering, "Reading", file=self._upload())["file"]
		new = self._upload()

		content.save_file(self.offering, "Reading", file=new, name=name)

		self.assertTrue(
			frappe.db.exists(
				"File",
				{"file_url": new, "attached_to_doctype": "Course File", "attached_to_name": name},
			)
		)

	def test_renaming_a_file_leaves_its_attachment_and_description_alone(self):
		upload = self._upload()
		name = content.save_file(
			self.offering, "Reading", file=upload, description="Chapters 1-3"
		)["file"]

		content.save_file(self.offering, "Reading list", name=name)

		row = frappe.db.get_value(
			"Course File", name, ["title", "file", "description"], as_dict=True
		)
		self.assertEqual(
			(row.title, row.file, row.description), ("Reading list", upload, "Chapters 1-3")
		)

	def test_somebody_elses_private_upload_cannot_be_attached(self):
		"""Attaching it would serve it to everyone who can read the course's files."""
		theirs = self._upload()
		frappe.set_user(self._user(["Academic Coordinator"]))

		with self.assertRaises(frappe.PermissionError):
			content.save_file(self.offering, "Not mine", file=theirs)

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

	# --- reading a page back, which was open to any member of staff ---------

	def _user(self, roles):
		email = f"page.{frappe.generate_hash(length=6)}@example.invalid"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Page",
				"user_type": "System User",
				"send_welcome_email": 0,
				"roles": [{"role": role} for role in roles],
			}
		).insert(ignore_permissions=True)
		return email

	def test_a_page_opens_through_an_offering_on_its_course(self):
		page = content.save_page(self.offering, "Syllabus", body="<p>Welcome</p>")["page"]

		row = content.page(page, self.offering)

		self.assertEqual(row.body, "<p>Welcome</p>")

	def test_a_page_will_not_open_through_an_offering_on_another_course(self):
		"""Otherwise naming an offering you do teach would open a page from one
		you do not."""
		other = make_offering(
			make_course(f"TCN {frappe.generate_hash(length=4)}").name,
			self.term,
			status="Published",
		).name
		page = content.save_page(other, "Somebody else's syllabus")["page"]

		with self.assertRaises(frappe.PermissionError):
			content.page(page, self.offering)

	def test_a_teacher_cannot_open_a_page_on_a_course_they_do_not_teach(self):
		"""The hole this closes: by name alone, any member of staff could read
		any page in the college."""
		from sibbcs.academic.doctype.course_offering.test_course_offering import (
			make_instructor,
		)

		page = content.save_page(self.offering, "Syllabus", body="<p>Welcome</p>")["page"]
		email = self._user(["Faculty"])
		make_instructor(f"Page {email[5:11]}", user=email)

		frappe.set_user(email)
		with self.assertRaises(frappe.PermissionError):
			content.page(page, self.offering)

	def test_someone_who_is_not_staff_cannot_open_a_page_at_all(self):
		"""`assert_may_teach` alone would let them through -- `offering_scope`
		is None for a student too -- so the staff check has to come first."""
		page = content.save_page(self.offering, "Syllabus")["page"]
		email = self._user([])

		frappe.set_user(email)
		with self.assertRaises(frappe.PermissionError):
			content.page(page, self.offering)

	# --- reading a lesson back, the same hole as pages ----------------------

	def _lesson(self, offering=None, title="Creation"):
		"""A lesson written through `offering`, with its course's space made."""
		offering = offering or self.offering
		lms_sync.ensure_lms_course(frappe.db.get_value("Course Offering", offering, "course"))
		chapter = content.save_chapter(offering, "Week One")["chapter"]
		return content.save_lesson(
			offering, chapter, title,
			[{"type": "paragraph", "data": {"text": "In the beginning"}}],
		)["lesson"]

	def test_a_lesson_opens_through_an_offering_on_its_course(self):
		lesson = self._lesson()

		draft = content.lesson(lesson, self.offering)

		self.assertEqual([b["type"] for b in draft["blocks"]], ["paragraph"])

	def test_a_lesson_will_not_open_through_an_offering_on_another_course(self):
		"""Otherwise naming an offering you do teach would open a lesson from
		one you do not."""
		self._with_space()
		other = make_offering(
			make_course(f"TCN {frappe.generate_hash(length=4)}").name,
			self.term,
			status="Published",
		).name
		lesson = self._lesson(other, "Somebody else's lecture")

		with self.assertRaises(frappe.PermissionError):
			content.lesson(lesson, self.offering)

	def test_a_teacher_cannot_open_a_lesson_on_a_course_they_do_not_teach(self):
		from sibbcs.academic.doctype.course_offering.test_course_offering import (
			make_instructor,
		)

		lesson = self._lesson()
		email = self._user(["Faculty"])
		make_instructor(f"Lesson {email[5:11]}", user=email)

		frappe.set_user(email)
		with self.assertRaises(frappe.PermissionError):
			content.lesson(lesson, self.offering)

	def test_someone_who_is_not_staff_cannot_open_a_lesson_at_all(self):
		lesson = self._lesson()
		email = self._user([])

		frappe.set_user(email)
		with self.assertRaises(frappe.PermissionError):
			content.lesson(lesson, self.offering)
