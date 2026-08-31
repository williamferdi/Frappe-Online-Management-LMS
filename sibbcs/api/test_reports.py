# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""Reports, and creating accounts.

The report engine puts a field name into `GROUP BY` and `SUM()`, which is
exactly where an unchecked string stops being a field name. Most of these tests
are that check.
"""

import inspect

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.api import reports
from sibbcs.api import users_api as usr
from sibbcs.api.test_student_api import make_student


class TestReportGuards(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_a_field_the_doctype_does_not_have_is_refused(self):
		for bad in (
			"name; DROP TABLE `tabCourse`",
			"1=1",
			"notafield",
			"`tabCourse`.`name`",
			"",
		):
			with self.subTest(group_by=bad):
				with self.assertRaises(frappe.ValidationError):
					reports.run("Course", bad)

	def test_a_field_of_the_wrong_kind_is_refused(self):
		"""Grouping on free text is one row per record; totalling a Data field
		is meaningless. Both are refused rather than quietly ignored."""
		with self.assertRaises(frappe.ValidationError):
			reports.run("Course", "description")
		with self.assertRaises(frappe.ValidationError):
			reports.run("Course", "level", aggregate="course_title")

	def test_a_doctype_outside_the_allow_list_is_refused(self):
		for doctype in ("User", "DocType", "File"):
			with self.subTest(doctype=doctype):
				with self.assertRaises(frappe.PermissionError):
					reports.run(doctype, "name")
				with self.assertRaises(frappe.PermissionError):
					reports.options(doctype)

	def test_only_a_checked_name_reaches_the_query(self):
		"""The guard is a metadata lookup, not a pattern match on the string."""
		source = inspect.getsource(reports._checked_field)
		self.assertIn("get_field", source)

	def test_a_guest_gets_no_catalogue(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			reports.catalogue()

	def test_the_catalogue_lists_only_what_the_user_may_read(self):
		_, _, email = make_student()
		frappe.set_user(email)
		for doctype in reports.catalogue():
			self.assertTrue(frappe.has_permission(doctype, "read"))


class TestReportResults(FrappeTestCase):
	def test_counts_add_up_to_the_record_count(self):
		"""A report whose parts do not sum to its whole is worse than none."""
		result = reports.run("Course Offering", "term")
		self.assertEqual(
			result["count"],
			sum(row["count"] for row in result["rows"]),
		)
		self.assertEqual(result["count"], frappe.db.count("Course Offering"))

	def test_an_empty_group_is_shown_not_dropped(self):
		"""'(not set)' is a real answer, and dropping it makes the total
		disagree with the record count."""
		result = reports.run("Fee Invoice", "term")
		labels = [row["label"] for row in result["rows"]]
		self.assertNotIn(None, labels)
		self.assertNotIn("", labels)

	def test_a_total_is_returned_when_one_is_asked_for(self):
		result = reports.run("Fee Invoice", "status", aggregate="outstanding_amount")
		self.assertIsNotNone(result["total"])
		self.assertAlmostEqual(
			result["total"], sum(row["total"] for row in result["rows"]), places=2
		)

	def test_no_total_is_returned_when_none_is_asked_for(self):
		result = reports.run("Course", "level")
		self.assertIsNone(result["total"])

	def test_options_only_offers_fields_worth_using(self):
		options = reports.options("Fee Invoice")
		for field in options["group_by"]:
			self.assertIn(field["fieldtype"], reports.GROUPABLE)
		for field in options["aggregate"]:
			self.assertIn(field["fieldtype"], reports.SUMMABLE)


class TestCreateUser(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_it_never_takes_a_password(self):
		"""Frappe emails a set-password link; nobody here chooses or sees one."""
		self.assertNotIn("password", list(inspect.signature(usr.create_user).parameters))
		self.assertNotIn("new_password", inspect.getsource(usr.create_user))

	def test_only_a_system_manager_may_create(self):
		_, _, email = make_student()
		frappe.set_user(email)
		with self.assertRaises(frappe.PermissionError):
			usr.create_user("someone@example.invalid", "Someone")

	def test_it_creates_an_account_with_the_roles_asked_for(self):
		email = f"made.{frappe.generate_hash(length=8)}@example.invalid"
		result = usr.create_user(email, "Made", "Here", ["Registrar", "Accounts"])

		self.assertEqual(result["user"], email)
		self.assertEqual(result["roles"], ["Accounts", "Registrar"])
		self.assertTrue(frappe.db.exists("User", email))

	def test_an_unmanaged_role_is_refused(self):
		email = f"made.{frappe.generate_hash(length=8)}@example.invalid"
		with self.assertRaises(frappe.ValidationError):
			usr.create_user(email, "Made", roles=["System Manager"])
		self.assertFalse(frappe.db.exists("User", email))

	def test_a_duplicate_is_reported_rather_than_overwriting(self):
		email = f"made.{frappe.generate_hash(length=8)}@example.invalid"
		usr.create_user(email, "First")
		with self.assertRaises(frappe.ValidationError):
			usr.create_user(email, "Second")

	def test_an_empty_address_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			usr.create_user("   ", "Nobody")
