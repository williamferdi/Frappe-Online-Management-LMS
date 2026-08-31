# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""Generic create, read, edit and delete.

One endpoint that can write to any of two dozen DocTypes is a wide door, so
almost every test here is about what it refuses: a DocType outside the
allow-list, a field the metadata says is read-only, a permlevel the caller does
not hold, and a password field in either direction.
"""

import inspect

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.api import records
from sibbcs.api.test_student_api import make_student


class TestAllowList(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_nothing_outside_the_list_can_be_reached(self):
		"""The allow-list is checked before permissions, so even a System
		Manager cannot steer this at User, DocType or File."""
		for doctype in ("User", "DocType", "File", "Has Role", "DocPerm", "Custom DocPerm"):
			with self.subTest(doctype=doctype):
				for call in (
					lambda: records.describe(doctype),
					lambda: records.records(doctype),
					lambda: records.record(doctype, "x"),
					lambda: records.save(doctype, {}),
					lambda: records.remove(doctype, "x"),
					lambda: records.options(doctype),
				):
					with self.assertRaises(frappe.PermissionError):
						call()

	def test_user_is_deliberately_absent(self):
		"""It carries new_password, api_key and the role table. Accounts are
		handled by users_api, which is narrow on purpose."""
		self.assertNotIn("User", records.EVERY_ALLOWED)

	def test_password_fields_are_never_described(self):
		self.assertIn("Password", records.NEVER)
		for doctype in records.EVERY_ALLOWED:
			with self.subTest(doctype=doctype):
				described = records.describe(doctype)
				for field in described["fields"]:
					self.assertNotEqual(field["fieldtype"], "Password")

	def test_every_allowed_doctype_actually_exists(self):
		"""A typo here is a menu entry that 404s for everybody."""
		for doctype in records.EVERY_ALLOWED:
			with self.subTest(doctype=doctype):
				self.assertTrue(frappe.db.exists("DocType", doctype))

	def test_a_student_cannot_reach_the_editor(self):
		_, _, email = make_student()
		frappe.set_user(email)

		with self.assertRaises(frappe.PermissionError):
			records.save("Course", {"course_code": "HACK", "course_title": "Hack"})


class TestDescribe(FrappeTestCase):
	def test_it_returns_the_fields_the_form_needs(self):
		described = records.describe("Course")
		self.assertTrue(described["fields"])
		names = {f["fieldname"] for f in described["fields"]}
		self.assertIn("course_code", names)
		self.assertIn("credits", names)

	def test_child_tables_come_with_their_own_columns(self):
		described = records.describe("Course")
		self.assertTrue(described["children"], "Course has child tables")
		for _fieldname, columns in described["children"].items():
			self.assertTrue(columns)

	def test_permlevels_are_read_from_the_permission_rows(self):
		"""`get_valid_perms` answers the main permission question and returns
		only level 0. Using it here reported every permlevel-gated field as
		read-only for everybody, the Registrar it was granted to included."""
		frappe.set_user("Administrator")
		levels = records._writable_permlevels("Program Enrollment")
		self.assertIn(1, levels, "permlevel 1 was not seen")

	def test_a_role_without_write_gets_no_levels(self):
		_, _, email = make_student()
		frappe.set_user(email)
		try:
			self.assertEqual(records._writable_permlevels("Program Enrollment"), set())
		finally:
			frappe.set_user("Administrator")


class TestSave(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_it_creates_and_then_edits(self):
		code = f"GEN{frappe.generate_hash(length=5)}"
		created = records.save(
			"Course",
			{"course_code": code, "course_title": "Generic Test Course", "credits": 3, "level": "1"},
		)
		self.assertTrue(frappe.db.exists("Course", created["name"]))

		records.save("Course", {"course_title": "Renamed"}, name=created["name"])
		self.assertEqual(
			frappe.db.get_value("Course", created["name"], "course_title"), "Renamed"
		)

	def test_a_field_the_metadata_calls_read_only_is_ignored(self):
		"""Built from the metadata rather than trusted from the request, so a
		field the form never showed cannot be set by adding it to the payload."""
		student, enrollment, _ = make_student()
		before = frappe.db.get_value("Program Enrollment", enrollment.name, "credits_earned")

		records.save(
			"Program Enrollment",
			{"credits_earned": 9999, "status": "Active"},
			name=enrollment.name,
		)

		after = frappe.db.get_value("Program Enrollment", enrollment.name, "credits_earned")
		self.assertEqual(after, before, "a read-only field was written")

	def test_an_unknown_field_is_dropped_rather_than_erroring(self):
		code = f"GEN{frappe.generate_hash(length=5)}"
		created = records.save(
			"Course",
			{
				"course_code": code,
				"course_title": "Has A Stray Field",
				"credits": 3,
				"level": "1",
				"not_a_real_field": "x",
				"docstatus": 2,
			},
		)
		self.assertEqual(frappe.db.get_value("Course", created["name"], "docstatus"), 0)

	def test_validation_still_runs(self):
		"""Saved through the document, so the DocType's own rules apply."""
		with self.assertRaises(frappe.ValidationError):
			records.save("Course", {"course_title": "No code, no level"})

	def test_values_may_arrive_as_a_json_string(self):
		import json

		code = f"GEN{frappe.generate_hash(length=5)}"
		created = records.save(
			"Course",
			json.dumps(
				{"course_code": code, "course_title": "From JSON", "credits": 2, "level": "1"}
			),
		)
		self.assertTrue(frappe.db.exists("Course", created["name"]))

	def test_something_that_is_not_an_object_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			records.save("Course", ["not", "an", "object"])


class TestDelete(FrappeTestCase):
	def test_a_linked_record_refuses_to_go(self):
		"""No `force`: the message naming what holds it is the useful part."""
		offering = frappe.db.get_value("Course Offering", {}, "name")
		if not offering:
			self.skipTest("no offering on this site")

		course = frappe.db.get_value("Course Offering", offering, "course")
		# The course is linked from the offering, so deleting it must fail.
		with self.assertRaises(frappe.LinkExistsError):
			records.remove("Course", course)

	def test_delete_never_uses_force(self):
		"""Read from the syntax tree: the word appears in the docstring
		explaining why it is not passed, which a text search matches."""
		import ast

		tree = ast.parse(inspect.getsource(records.remove).lstrip())
		forced = [
			node
			for node in ast.walk(tree)
			if isinstance(node, ast.Call)
			for kw in node.keywords
			if kw.arg in ("force", "ignore_permissions")
		]
		self.assertEqual(forced, [], "remove() bypasses the link check")


class TestListing(FrappeTestCase):
	def test_it_reads_through_get_list_not_get_all(self):
		"""get_list applies this user's permissions and any user permissions;
		get_all is the one that ignores them."""
		source = inspect.getsource(records.records)
		self.assertIn("frappe.get_list", source)
		self.assertNotIn("frappe.get_all", source)

	def test_link_options_are_permission_checked_too(self):
		"""A picker that lists every student to somebody who may not read
		Student is a leak with a search box."""
		self.assertIn("frappe.get_list", inspect.getsource(records.options))

	def test_a_capped_list_says_so(self):
		page = records.records("Course", limit=1)
		self.assertIn("truncated", page)
		if page["total"] > 1:
			self.assertTrue(page["truncated"])
			self.assertEqual(len(page["rows"]), 1)

	def test_child_tables_are_not_list_columns(self):
		"""A grid rendered into a cell is unreadable, and fetching it per row
		is a query per row."""
		for doctype in records.EVERY_ALLOWED:
			with self.subTest(doctype=doctype):
				for column in records.records(doctype, limit=1)["columns"]:
					self.assertNotIn(column["fieldtype"], ("Table", "Table MultiSelect"))


class TestSections(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_a_guest_is_refused(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			records.sections()

	def test_a_section_only_lists_what_the_user_may_read(self):
		_, _, email = make_student()
		frappe.set_user(email)

		for rows in records.sections().values():
			for row in rows:
				self.assertTrue(
					frappe.has_permission(row["doctype"], "read"),
					f"{row['doctype']} listed without read permission",
				)
