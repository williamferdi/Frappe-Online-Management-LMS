# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""Finance and account administration.

Both of these hand out real power -- money moving and who may see what -- so
these tests are mostly about the refusals.
"""

import inspect

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from sibbcs.api import academic_api as academic
from sibbcs.api import finance_api as fin
from sibbcs.api import users_api as usr
from sibbcs.api.test_api import make_user
from sibbcs.api.test_student_api import make_student


def make_invoice(student, amount=1000, **overrides):
	values = {
		"doctype": "Fee Invoice",
		"student": student,
		"fee_type": frappe.db.get_value("Fee Type", {}, "name"),
		"gross_amount": amount,
		"due_date": today(),
	}
	values.update(overrides)
	return frappe.get_doc(values).insert(ignore_permissions=True)


class TestFinanceAccess(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_a_student_is_refused_the_finance_console(self):
		"""Students hold read on Fee Invoice and Payment Entry -- they must, to
		see their own. These endpoints total the whole college."""
		_, _, email = make_student()
		frappe.set_user(email)

		for endpoint in (fin.invoices, fin.payments, fin.scholarships, fin.tuition):
			with self.subTest(endpoint=endpoint.__name__):
				with self.assertRaises(frappe.PermissionError):
					endpoint()

	def test_a_student_cannot_ask_what_another_student_owes(self):
		student, _, _ = make_student()
		_, _, email = make_student()
		frappe.set_user(email)

		with self.assertRaises(frappe.PermissionError):
			fin.outstanding_for(student.name)

	def test_a_student_cannot_record_a_payment(self):
		student, _, email = make_student()
		frappe.set_user(email)

		with self.assertRaises(frappe.PermissionError):
			fin.record_payment(student.name, 100, "Cash")


class TestRecordPayment(FrappeTestCase):
	def setUp(self):
		self.student, _, _ = make_student()
		self.invoice = make_invoice(self.student.name, 1000)
		frappe.db.commit()

	def test_a_payment_settles_the_oldest_invoice_first(self):
		"""With no allocation given, the document's own auto_allocate decides."""
		result = fin.record_payment(self.student.name, 1000, "UPI")

		self.assertEqual(len(result["settled"]), 1)
		self.assertEqual(result["settled"][0]["fee_invoice"], self.invoice.name)
		self.assertEqual(
			frappe.db.get_value("Fee Invoice", self.invoice.name, "status"), "Paid"
		)

	def test_a_part_payment_leaves_the_invoice_partly_paid(self):
		fin.record_payment(self.student.name, 400, "Cash")

		row = frappe.db.get_value(
			"Fee Invoice", self.invoice.name, ["status", "outstanding_amount"], as_dict=True
		)
		self.assertEqual(row.outstanding_amount, 600)
		self.assertNotEqual(row.status, "Paid")

	def test_over_allocating_an_invoice_is_refused(self):
		"""Saved through the document so validate_allocations runs -- allocating
		more than is owed is exactly the mistake worth refusing now rather than
		reconciling later."""
		with self.assertRaises(frappe.ValidationError):
			fin.record_payment(
				self.student.name,
				5000,
				"Cash",
				allocations=[
					{"fee_invoice": self.invoice.name, "allocated_amount": 5000}
				],
			)

	def test_a_payment_of_nothing_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			fin.record_payment(self.student.name, 0, "Cash")

	def test_allocations_may_arrive_as_a_json_string(self):
		import json

		result = fin.record_payment(
			self.student.name,
			300,
			"Cash",
			allocations=json.dumps(
				[{"fee_invoice": self.invoice.name, "allocated_amount": 300}]
			),
		)
		self.assertEqual(result["allocated"], 300)

	def test_money_left_over_is_reported_not_hidden(self):
		"""A payment bigger than everything owed leaves a balance, and the
		office needs to see it rather than discover it at reconciliation."""
		result = fin.record_payment(self.student.name, 1500, "Bank Transfer")
		self.assertEqual(result["allocated"], 1000)
		self.assertEqual(result["unallocated"], 500)


class TestInvoiceList(FrappeTestCase):
	def test_the_summary_separates_overdue_from_outstanding(self):
		summary = fin.invoices()["summary"]
		for key in ("billed", "collected", "outstanding", "overdue", "overdue_count"):
			self.assertIn(key, summary)
		self.assertLessEqual(summary["overdue"], summary["outstanding"])

	def test_the_statuses_come_from_the_doctype(self):
		meta = frappe.get_meta("Fee Invoice")
		options = [c for c in (meta.get_field("status").options or "").split("\n") if c]
		self.assertEqual(fin.invoices()["statuses"], options)

	def test_the_overdue_filter_returns_only_late_unsettled_invoices(self):
		for row in fin.invoices(overdue=1)["rows"]:
			self.assertTrue(row["overdue"])
			self.assertNotIn(row["status"], ("Paid", "Waived", "Cancelled"))



class TestTuitionConsole(FrappeTestCase):
	"""Who has reached the tuition ceiling, where an officer will see it."""

	def tearDown(self):
		frappe.set_user("Administrator")

	def _at_the_ceiling(self):
		student, enrollment, _ = make_student()
		ceiling = frappe.db.get_value("Program", enrollment.program, "tuition_total")
		make_invoice(
			student.name,
			amount=ceiling,
			fee_type="Monthly Tuition",
			program_enrollment=enrollment.name,
		)
		return student, enrollment

	def test_the_roster_says_who_is_at_the_ceiling(self):
		_student, enrollment = self._at_the_ceiling()

		result = fin.tuition()
		row = next(r for r in result["rows"] if r["enrollment"] == enrollment.name)

		self.assertEqual(row["state"], "ceiling_reached")
		self.assertGreaterEqual(result["summary"]["at_ceiling"], 1)
		self.assertEqual(
			result["summary"]["at_ceiling"],
			sum(1 for r in result["rows"] if r["state"] == "ceiling_reached"),
		)

	def test_accounts_may_look(self):
		email = f"acc.{frappe.generate_hash(length=8)}@example.invalid"
		make_user(email, ["Accounts"])
		frappe.set_user(email)

		self.assertIn("rows", fin.tuition())

	def test_the_student_page_carries_the_position_for_those_who_see_money(self):
		student, enrollment = self._at_the_ceiling()

		page = academic.student(student.name)

		self.assertEqual(page["tuition"]["enrollment"], enrollment.name)
		self.assertEqual(page["tuition"]["state"], "ceiling_reached")

	def test_a_teacher_is_not_shown_it(self):
		"""The position is money; it follows the permission on the invoices
		beside it, which a teacher does not hold."""
		from sibbcs.academic.doctype.academic_term.test_academic_term import make_term
		from sibbcs.academic.doctype.course.test_course import make_course
		from sibbcs.academic.doctype.course_offering.test_course_offering import (
			make_instructor,
			make_offering,
		)
		from sibbcs.academic.doctype.course_registration.test_course_registration import (
			make_registration,
		)

		student, enrollment = self._at_the_ceiling()
		tag = frappe.generate_hash(length=6)
		email = f"teach.{tag}@example.invalid"
		make_user(email, ["Faculty"])
		offering = make_offering(
			make_course(f"TUI{tag}", level="1", credits=3).name,
			make_term(f"TUI-{tag}", status="Open").name,
			status="Published",
			instructor=make_instructor(f"Tuition Teacher {tag}", user=email).name,
		).name
		make_registration(enrollment.name, offering)

		frappe.set_user(email)
		page = academic.student(student.name)

		self.assertIsNone(page["tuition"])
		self.assertEqual(page["invoices"], [])


class TestUserAdministration(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_only_a_system_manager_may_look(self):
		_, _, email = make_student()
		frappe.set_user(email)

		for endpoint in (usr.users, usr.role_summary):
			with self.subTest(endpoint=endpoint.__name__):
				with self.assertRaises(frappe.PermissionError):
					endpoint()

	def test_system_manager_cannot_be_granted_from_here(self):
		"""Handing that out from a web form is how one compromised account
		becomes every account."""
		self.assertNotIn("System Manager", usr.MANAGED_ROLES)
		self.assertIn("System Manager", usr.PROTECTED_ROLES)

		_, _, email = make_student()
		with self.assertRaises(frappe.ValidationError):
			usr.set_roles(email, ["System Manager"])

	def test_an_unmanaged_role_is_refused_rather_than_ignored(self):
		"""Silently dropping it would tell the caller it worked."""
		_, _, email = make_student()
		with self.assertRaises(frappe.ValidationError):
			usr.set_roles(email, ["Registrar", "Newsletter Manager"])

	def test_setting_roles_leaves_unmanaged_ones_exactly_as_they_were(self):
		_, _, email = make_student()
		user = frappe.get_doc("User", email)
		user.append("roles", {"role": "Newsletter Manager"})
		user.save(ignore_permissions=True)
		frappe.db.commit()

		usr.set_roles(email, ["Registrar"])

		after = {row.role for row in frappe.get_doc("User", email).roles}
		self.assertIn("Registrar", after)
		self.assertIn("Newsletter Manager", after, "an unmanaged role was dropped")
		self.assertNotIn("Student", after, "a managed role was not revoked")

	def test_the_reserved_accounts_are_untouchable(self):
		for account in ("Administrator", "Guest"):
			with self.subTest(account=account):
				with self.assertRaises(frappe.ValidationError):
					usr.set_roles(account, ["Registrar"])
				with self.assertRaises(frappe.ValidationError):
					usr.set_enabled(account, 0)

	def test_you_cannot_disable_yourself(self):
		"""Locking yourself out is a support call, not a feature."""
		with self.assertRaises(frappe.ValidationError):
			usr.set_enabled(frappe.session.user, 0)

	def test_there_is_no_endpoint_that_touches_a_password(self):
		"""Frappe owns those. A reset goes through Desk or the user themselves."""
		source = inspect.getsource(usr)
		for word in ("update_password", "new_password", "set_password", "reset_password"):
			self.assertNotIn(word, source, f"{word} appears in users_api")

	def test_disabling_never_deletes(self):
		"""A User is linked to a Student, to payments and to an audit trail."""
		source = inspect.getsource(usr)
		self.assertNotIn("delete_doc", source)

	def test_the_list_reports_which_managed_roles_an_account_holds(self):
		_, _, email = make_student()
		usr.set_roles(email, ["Faculty"])
		frappe.db.commit()

		row = next(r for r in usr.users(search=email)["rows"] if r["name"] == email)
		self.assertEqual(row["roles"], ["Faculty"])
		# All, Guest and Desk User say nothing about what somebody does here.
		self.assertNotIn("All", row["roles"])

	def test_the_role_summary_counts_only_enabled_accounts(self):
		_, _, email = make_student()
		usr.set_roles(email, ["Dean"])
		frappe.db.commit()

		before = next(r for r in usr.role_summary() if r["role"] == "Dean")["count"]
		usr.set_enabled(email, 0)
		after = next(r for r in usr.role_summary() if r["role"] == "Dean")["count"]

		self.assertEqual(after, before - 1)
