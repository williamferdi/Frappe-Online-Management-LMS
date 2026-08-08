# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""Workspaces must actually render.

A Frappe v15 Workspace draws from its `content` block list, not from the
`shortcuts` / `links` child tables directly. A workspace with populated child
tables but empty `content` shows a completely blank page -- which is what
shipped in Phases 1-2 and was only caught by looking at the screen. These
tests assert the thing the page depends on.
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.setup.workspaces import WORKSPACES, build_all

EXPECTED = [spec["name"] for spec in WORKSPACES]


class TestWorkspaces(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		build_all()

	def test_every_workspace_exists(self):
		for name in EXPECTED:
			self.assertTrue(frappe.db.exists("Workspace", name), name)

	def test_content_is_never_empty(self):
		"""The exact failure that made Academic and Admissions render blank."""
		for name in EXPECTED:
			content = frappe.db.get_value("Workspace", name, "content")
			blocks = json.loads(content or "[]")
			self.assertTrue(blocks, f"{name} has no layout blocks -- it will render blank")

	def test_shortcut_blocks_resolve_to_rows(self):
		for name in EXPECTED:
			ws = frappe.get_doc("Workspace", name)
			labels = {s.label for s in ws.shortcuts}
			for block in json.loads(ws.content or "[]"):
				if block["type"] != "shortcut":
					continue
				self.assertIn(
					block["data"]["shortcut_name"],
					labels,
					f"{name}: shortcut block has no matching row",
				)

	def test_card_blocks_resolve_to_card_breaks(self):
		for name in EXPECTED:
			ws = frappe.get_doc("Workspace", name)
			cards = {l.label for l in ws.links if l.type == "Card Break"}
			for block in json.loads(ws.content or "[]"):
				if block["type"] != "card":
					continue
				self.assertIn(
					block["data"]["card_name"],
					cards,
					f"{name}: card block has no matching Card Break",
				)

	def test_every_target_exists(self):
		for name in EXPECTED:
			ws = frappe.get_doc("Workspace", name)
			for shortcut in ws.shortcuts:
				self.assertTrue(
					frappe.db.exists("DocType", shortcut.link_to),
					f"{name}: shortcut to missing DocType {shortcut.link_to}",
				)
			for link in ws.links:
				if link.type != "Link":
					continue
				target = "Report" if link.link_type == "Report" else "DocType"
				self.assertTrue(
					frappe.db.exists(target, link.link_to),
					f"{name}: link to missing {target} {link.link_to}",
				)

	def test_blocks_carry_ids(self):
		"""Frappe's editor keys blocks by id; duplicates collapse on render."""
		for name in EXPECTED:
			blocks = json.loads(frappe.db.get_value("Workspace", name, "content") or "[]")
			ids = [b.get("id") for b in blocks]
			self.assertTrue(all(ids), f"{name}: a block is missing its id")
			self.assertEqual(len(ids), len(set(ids)), f"{name}: duplicate block ids")

	def test_rebuild_is_idempotent(self):
		build_all()
		for name in EXPECTED:
			blocks = json.loads(frappe.db.get_value("Workspace", name, "content") or "[]")
			self.assertTrue(blocks, name)
