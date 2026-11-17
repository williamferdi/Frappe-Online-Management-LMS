# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""The content converter, which is the part of the move that can lose things."""

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.setup.phase6_admissions_lms import _blocks_to_markdown


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
