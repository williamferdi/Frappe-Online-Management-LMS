# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""The content converter, which is the part of the move that can lose things."""

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.finance import gateway
from sibbcs.setup.phase6_admissions_lms import _absolutise, _blocks_to_markdown


class TestLessonToMarkdown(FrappeTestCase):
	def test_prose_becomes_paragraphs(self):
		md = _blocks_to_markdown(
			[
				{"type": "header", "data": {"text": "Welcome", "level": 2}},
				{"type": "paragraph", "data": {"text": "Dear student,"}},
				{"type": "paragraph", "data": {"text": "Grace to you."}},
			]
		)
		self.assertEqual(md, "## Welcome\n\nDear student,\n\nGrace to you.")

	def test_emphasis_the_college_wrote_is_kept(self):
		"""Inline markup passes through Markdown and is sanitised on render, so
		stripping it would only lose emphasis somebody meant."""
		md = _blocks_to_markdown([{"type": "paragraph", "data": {"text": "Read <b>every</b> lesson."}}])
		self.assertIn("<b>every</b>", md)

	def test_lists_keep_their_kind(self):
		bullets = _blocks_to_markdown([{"type": "list", "data": {"style": "unordered", "items": ["One", "Two"]}}])
		numbered = _blocks_to_markdown([{"type": "list", "data": {"style": "ordered", "items": ["One", "Two"]}}])
		self.assertEqual(bullets, "- One\n- Two")
		self.assertEqual(numbered, "1. One\n1. Two")

	def test_newer_editorjs_list_items_are_objects(self):
		"""Later versions store `{content: ...}` rather than a bare string, and
		a converter that assumed strings would write "None" into the handbook."""
		md = _blocks_to_markdown([{"type": "list", "data": {"items": [{"content": "One"}, {"content": "Two"}]}}])
		self.assertEqual(md, "- One\n- Two")

	def test_quotes_and_rules_survive(self):
		md = _blocks_to_markdown(
			[{"type": "quote", "data": {"text": "Study to show thyself approved."}}, {"type": "delimiter", "data": {}}]
		)
		self.assertEqual(md, "> Study to show thyself approved.\n\n---")

	def test_a_block_type_we_do_not_know_is_dropped_not_rendered_wrong(self):
		md = _blocks_to_markdown(
			[{"type": "paragraph", "data": {"text": "Kept."}}, {"type": "warning", "data": {"title": "x"}}]
		)
		self.assertEqual(md, "Kept.")

	def test_an_empty_lesson_converts_to_nothing_rather_than_noise(self):
		"""`export_content` reports empty pages, and it can only do that if an
		empty lesson really comes back empty."""
		self.assertEqual(_blocks_to_markdown([]), "")
		self.assertEqual(_blocks_to_markdown([{"type": "paragraph", "data": {"text": "  "}}]), "")


class TestWhoMarksTheExam(FrappeTestCase):
	"""The first run of this put the demo instructors on the real entrance exam
	as teachers, because every active instructor counted. A marker is somebody
	who can sign in."""

	def setUp(self):
		frappe.set_user("Administrator")

	def test_an_instructor_with_no_login_is_not_a_marker(self):
		from sibbcs.academic.doctype.course_offering.test_course_offering import make_instructor
		from sibbcs.setup.phase6_admissions_lms import _markers

		fixture = make_instructor(f"DEMO Fixture {frappe.generate_hash(length=6)}").name
		self.assertNotIn(fixture, _markers())

	def test_an_instructor_with_an_enabled_account_is(self):
		from sibbcs.academic.doctype.course_offering.test_course_offering import make_instructor
		from sibbcs.setup.phase6_admissions_lms import _markers

		email = f"marker.{frappe.generate_hash(length=6)}@example.invalid"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Marker",
				"user_type": "System User",
				"send_welcome_email": 0,
				"roles": [{"role": "Faculty"}],
			}
		).insert(ignore_permissions=True)
		real = make_instructor(f"Real Marker {frappe.generate_hash(length=6)}", user=email).name

		self.assertIn(real, _markers())

	def test_a_disabled_account_stops_being_a_marker(self):
		from sibbcs.academic.doctype.course_offering.test_course_offering import make_instructor
		from sibbcs.setup.phase6_admissions_lms import _markers

		email = f"gone.{frappe.generate_hash(length=6)}@example.invalid"
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Gone",
				"user_type": "System User",
				"send_welcome_email": 0,
				"roles": [{"role": "Faculty"}],
			}
		).insert(ignore_permissions=True)
		leaver = make_instructor(f"Leaver {frappe.generate_hash(length=6)}", user=email).name
		user.enabled = 0
		user.save(ignore_permissions=True)

		self.assertNotIn(leaver, _markers())


class TestHandbookLinks(FrappeTestCase):
	"""Every orientation page links to its handbook PDF, and the link was
	site-relative -- which is 49 broken links the moment the page is served
	from lms.sibbc.org instead of from here."""

	def test_a_relative_file_link_is_made_absolute(self):
		found, private = [], []
		out = _absolutise(
			"*[Open the full handbook](/files/program_manual.pdf).*", found, private
		)
		self.assertIn(gateway.public_url("/files/program_manual.pdf"), out)
		self.assertNotIn("](/files/", out)
		self.assertEqual(found, ["/files/program_manual.pdf"])
		self.assertEqual(private, [])

	def test_the_absolute_link_carries_no_dev_port(self):
		"""gateway.public_url, not frappe.utils.get_url -- see its docstring."""
		out = _absolutise("[h](/files/program_manual.pdf)", [], [])
		self.assertNotIn(":8000", out)

	def test_a_link_already_absolute_is_left_alone(self):
		found = []
		text = "[h](https://example.org/files/program_manual.pdf)"
		self.assertEqual(_absolutise(text, found, []), text)
		self.assertEqual(found, [])

	def test_a_private_file_link_is_reported_not_just_rewritten(self):
		"""Fetching one needs a session on this site, which a candidate working
		in the LMS has not got, so an absolute link sends them to the wrong
		login page. The export has to say so."""
		found, private = [], []
		_absolutise("[x](/private/files/secret.pdf)", found, private)
		self.assertEqual(private, ["/private/files/secret.pdf"])
		self.assertEqual(found, [])

	def test_every_occurrence_is_rewritten_not_only_the_first(self):
		found = []
		out = _absolutise(
			"[a](/files/program_manual.pdf) and [b](/files/formation_handbook.pdf)",
			found,
			[],
		)
		self.assertNotIn("](/files/", out)
		self.assertEqual(len(found), 2)

	def test_nothing_to_rewrite_is_not_an_error(self):
		self.assertEqual(_absolutise("", [], []), "")
		self.assertEqual(_absolutise(None, [], []), "")


class TestTheBuilderStaysRunnable(FrappeTestCase):
	"""It is a builder, so re-running it must work. It stopped working once
	already, silently: `entrance_exam.quiz_names` was removed when the exam
	moved to the LMS and this module went on importing it, so `export_content`
	raised ImportError on the next run."""

	def test_the_quiz_is_found_without_a_helper_from_another_module(self):
		from sibbcs.setup import phase6_admissions_lms as p6

		quiz = p6._exam_quiz()
		# Either the bundled quiz is still here with its essays, or it is gone
		# and we say so -- never an exception.
		if quiz is not None:
			self.assertTrue(quiz["questions"])
			self.assertTrue(all("prompt" in q and "points" in q for q in quiz["questions"]))

	def test_export_content_runs_twice(self):
		import os
		import tempfile

		from sibbcs.setup import phase6_admissions_lms as p6

		with tempfile.TemporaryDirectory() as box:
			path = os.path.join(box, "export.json")
			first = p6.export_content(path)
			second = p6.export_content(path)
		self.assertEqual(first["orientation_pages"], second["orientation_pages"])
		self.assertEqual(first["linked_files"], second["linked_files"])
