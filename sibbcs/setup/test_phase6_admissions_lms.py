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
