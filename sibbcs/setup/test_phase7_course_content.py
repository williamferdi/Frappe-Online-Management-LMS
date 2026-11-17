# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""Carrying the academic courses out of the bundled LMS.

The risk here is not the conversion -- Phase 6 already tests that -- but what
the migration lands on. Two of these courses have a counterpart somebody is
authoring by hand, and an import that merged into it, or that a student could
open, is the damage worth testing against.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.setup import phase7_course_content as p7
from sibbcs.setup.phase7_course_content import LEGACY_COURSES


class TestWhatIsInScope(FrappeTestCase):
	def test_the_duplicate_orientation_course_is_not_carried(self):
		"""`orientation-to-online-study` is a 49-lesson twin of the course
		Phase 6 already moved. Importing it would put those pages in twice."""
		self.assertNotIn("orientation-to-online-study", LEGACY_COURSES)
		self.assertNotIn("m-div-preliminary-orientation", LEGACY_COURSES)

	def test_the_admissions_courses_are_not_carried_again(self):
		from sibbcs.setup.phase6_admissions_lms import EXAM_SOURCE, ORIENTATION_SOURCE

		self.assertNotIn(EXAM_SOURCE, LEGACY_COURSES)
		self.assertNotIn(ORIENTATION_SOURCE, LEGACY_COURSES)

	def test_an_empty_course_is_not_carried(self):
		"""`introduction-to-the-old-testament` has chapters and no lessons."""
		self.assertNotIn("introduction-to-the-old-testament", LEGACY_COURSES)


class TestTheArchiveCannotBeMistakenForACourse(FrappeTestCase):
	def test_every_external_id_is_marked_as_legacy(self):
		"""The registrar must never match an enrolment onto an archive. It
		upserts on externalId, so the prefix is what keeps these out of reach
		of a Course Offering push."""
		for external_id, _code, _name in LEGACY_COURSES.values():
			self.assertTrue(
				external_id.startswith("LEGACY-"),
				f"{external_id} would be addressable by the registrar",
			)

	def test_no_archive_id_collides_with_an_offering_name(self):
		offerings = set(frappe.get_all("Course Offering", pluck="name"))
		for external_id, _code, _name in LEGACY_COURSES.values():
			self.assertNotIn(external_id, offerings)

	def test_the_ids_and_codes_are_distinct(self):
		ids = [v[0] for v in LEGACY_COURSES.values()]
		codes = [v[1] for v in LEGACY_COURSES.values()]
		self.assertEqual(len(ids), len(set(ids)))
		self.assertEqual(len(codes), len(set(codes)))

	def test_every_name_says_where_it_came_from(self):
		"""Two of these sit beside a live course of the same subject. A title
		that does not distinguish them is how the wrong one gets taught."""
		for _id, _code, name in LEGACY_COURSES.values():
			self.assertIn("old LMS", name)

	def test_the_courses_are_created_unpublished(self):
		"""An archive a student can open is a second place to read the
		syllabus."""
		import inspect

		source = inspect.getsource(p7.ensure_courses)
		self.assertIn('"status": "unpublished"', source)
		self.assertNotIn('"status": "published"', source)


class TestTheExportIsHonestAboutWhatItDid(FrappeTestCase):
	def test_a_course_that_is_not_here_is_reported_not_skipped(self):
		"""The bundled app is being removed, so a slug may already be gone.
		Reporting it is the difference between a short export and a silent
		one."""
		import inspect

		self.assertIn("missing", inspect.getsource(p7.export_content))

	def test_the_report_names_empty_pages(self):
		"""A lesson whose content did not convert looks like a successful
		import until somebody opens it."""
		import inspect

		self.assertIn("empty_pages", inspect.getsource(p7.export_content))

	def test_export_runs_twice_and_agrees_with_itself(self):
		import os
		import tempfile

		if not any(frappe.db.exists("LMS Course", s) for s in LEGACY_COURSES):
			self.skipTest("none of the legacy courses are on this site")

		with tempfile.TemporaryDirectory() as box:
			path = os.path.join(box, "academic.json")
			first = p7.export_content(path)
			second = p7.export_content(path)
		self.assertEqual(first["courses"], second["courses"])
		self.assertEqual(first["linked_files"], second["linked_files"])


class TestInstructorContentIsLabelledForWhatItIs(FrappeTestCase):
	"""On the entrance exam `instructor_content` is the mark scheme. On a taught
	course it is the lecturer's notes -- and on church-history it is where the
	material actually is, under lessons with nothing student-facing at all.
	Carrying that across as a "marking rubric" would mislabel it."""

	def test_phase_seven_calls_them_instructor_notes(self):
		self.assertEqual(p7.NOTES_LABEL, "instructor notes")

	def test_the_exam_keeps_calling_them_a_marking_rubric(self):
		from sibbcs.setup.phase6_admissions_lms import NOTES_LABEL

		self.assertEqual(NOTES_LABEL, "marking rubric")

	def test_the_label_reaches_the_page_title(self):
		from unittest.mock import patch

		from sibbcs.setup import phase6_admissions_lms as p6

		with patch.object(p6, "_chapters_in_order", return_value=["ch"]):
			with patch.object(p6, "_lessons_in_order", return_value=["ls"]):
				with patch.object(
					p6,
					"lesson_markdown",
					return_value={"title": "Class 4", "markdown": "", "rubric": "notes"},
				):
					with patch.object(frappe.db, "get_value", return_value="Unit 1"):
						modules = p6._course_export("c", [], [], notes_label=p7.NOTES_LABEL)

		titles = [page["title"] for page in modules[0]["pages"]]
		self.assertIn("Class 4 — instructor notes", titles)
		self.assertNotIn("Class 4 — marking rubric", titles)

	def test_the_notes_page_is_never_published(self):
		"""Staff-only, whatever it is called."""
		from unittest.mock import patch

		from sibbcs.setup import phase6_admissions_lms as p6

		with patch.object(p6, "_chapters_in_order", return_value=["ch"]):
			with patch.object(p6, "_lessons_in_order", return_value=["ls"]):
				with patch.object(
					p6,
					"lesson_markdown",
					return_value={"title": "Class 4", "markdown": "x", "rubric": "notes"},
				):
					with patch.object(frappe.db, "get_value", return_value="Unit 1"):
						modules = p6._course_export("c", [], [], notes_label=p7.NOTES_LABEL)

		notes = [p for p in modules[0]["pages"] if p["title"].endswith("instructor notes")]
		self.assertEqual(len(notes), 1)
		self.assertFalse(notes[0]["published"])
