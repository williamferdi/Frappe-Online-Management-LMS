# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""A student's own fee records -- the page, the receipt and the statement.

Money is the one thing in the portal where "somebody else's" matters most, so
a good half of these are about what cannot be asked for.
"""

import inspect
from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from sibbcs.api import student_fees as api
from sibbcs.api.test_student_api import make_student
from sibbcs.finance.test_fees import make_invoice, make_payment

TUITION = "Monthly Tuition"
REGISTRATION = "Course Registration Fee"
FAKE_PDF = b"%PDF-1.4 stub"


def pay(student, invoice, amount):
	return make_payment(
		student.name, amount, [{"fee_invoice": invoice.name, "allocated_amount": amount}]
	)


class TestTheFeesPage(FrappeTestCase):
	def setUp(self):
		self.student, self.enrollment, self.email = make_student()
		frappe.set_user(self.email)

	def tearDown(self):
		frappe.set_user("Administrator")

	def _as_admin(self, fn):
		frappe.set_user("Administrator")
		try:
			return fn()
		finally:
			frappe.set_user(self.email)

	def test_a_student_with_nothing_billed_sees_an_empty_account(self):
		page = api.fees()

		self.assertEqual(page["invoices"], [])
		self.assertEqual(page["payments"], [])
		self.assertEqual(page["statement"]["rows"], [])
		self.assertEqual(page["statement"]["balance"], 0)
		self.assertEqual(page["summary"]["outstanding"], 0)

	def test_it_shows_their_invoices_and_nobody_elses(self):
		other, _e, _m = make_student()
		mine = self._as_admin(lambda: make_invoice(self.student.name, TUITION, gross_amount=3000))
		theirs = self._as_admin(lambda: make_invoice(other.name, TUITION, gross_amount=9999))

		names = [row["name"] for row in api.fees()["invoices"]]

		self.assertIn(mine.name, names)
		self.assertNotIn(theirs.name, names)

	def test_a_cancelled_invoice_is_not_shown(self):
		"""A cancelled tuition invoice is the college correcting its own books,
		and the term is billed again -- showing it invites "billed twice"."""
		live = self._as_admin(lambda: make_invoice(self.student.name, REGISTRATION, gross_amount=350))
		dead = self._as_admin(lambda: make_invoice(self.student.name, REGISTRATION, gross_amount=350))
		frappe.db.set_value("Fee Invoice", dead.name, "status", "Cancelled")

		names = [row["name"] for row in api.fees()["invoices"]]

		self.assertIn(live.name, names)
		self.assertNotIn(dead.name, names)

	def test_a_paid_invoice_stays_visible_with_the_payment_that_settled_it(self):
		"""The reason this page exists: paying used to make an invoice vanish."""
		invoice = self._as_admin(lambda: make_invoice(self.student.name, TUITION, gross_amount=3000))
		payment = self._as_admin(lambda: pay(self.student, invoice, 3000))

		page = api.fees()

		row = next(r for r in page["invoices"] if r["name"] == invoice.name)
		self.assertEqual(row["status"], "Paid")
		self.assertEqual(row["outstanding_amount"], 0)
		self.assertEqual([p["name"] for p in page["payments"]], [payment.name])
		self.assertEqual(
			page["payments"][0]["applied_to"],
			[{"invoice": invoice.name, "fee_type": TUITION, "term": None, "amount": 3000}],
		)

	def test_the_summary_adds_up(self):
		a = self._as_admin(lambda: make_invoice(self.student.name, TUITION, gross_amount=3000))
		self._as_admin(lambda: make_invoice(self.student.name, REGISTRATION, gross_amount=350))
		self._as_admin(lambda: pay(self.student, a, 1000))

		summary = api.fees()["summary"]

		self.assertEqual(summary["billed"], 3350)
		self.assertEqual(summary["paid"], 1000)
		self.assertEqual(summary["outstanding"], 2350)

	def test_an_overdue_invoice_is_counted_and_a_current_one_is_not(self):
		late = self._as_admin(
			lambda: make_invoice(
				self.student.name, REGISTRATION, gross_amount=350, due_date=add_days(today(), -3)
			)
		)
		self._as_admin(
			lambda: make_invoice(
				self.student.name, REGISTRATION, gross_amount=350, due_date=add_days(today(), 9)
			)
		)

		page = api.fees()

		self.assertEqual(page["summary"]["overdue_count"], 1)
		self.assertEqual(page["summary"]["overdue"], 350)
		flags = {r["name"]: r["overdue"] for r in page["invoices"]}
		self.assertTrue(flags[late.name])
		self.assertEqual(sum(flags.values()), 1)

	def test_a_waived_invoice_is_not_owed(self):
		"""Its net stays on the record; telling the student they owe it would be
		telling them they owe what the college forgave."""
		invoice = self._as_admin(
			lambda: make_invoice(self.student.name, TUITION, gross_amount=3000, status="Waived")
		)

		page = api.fees()

		row = next(r for r in page["invoices"] if r["name"] == invoice.name)
		self.assertEqual(row["status"], "Waived")
		self.assertEqual(row["outstanding_amount"], 0)
		self.assertEqual(page["summary"]["outstanding"], 0)
		self.assertEqual(page["summary"]["billed"], 0)

	def test_a_scholarship_shows_in_the_statement(self):
		self._as_admin(
			lambda: make_invoice(
				self.student.name, TUITION, gross_amount=4332, discount_amount=1332
			)
		)

		rows = api.fees()["statement"]["rows"]

		self.assertIn("scholarship", rows[0]["particulars"])
		self.assertEqual(rows[0]["charge"], 3000)

	def test_a_payment_towards_an_invoice_cancelled_afterwards_is_still_listed(self):
		invoice = self._as_admin(
			lambda: make_invoice(self.student.name, REGISTRATION, gross_amount=350)
		)
		payment = self._as_admin(lambda: pay(self.student, invoice, 350))
		frappe.db.set_value("Fee Invoice", invoice.name, "status", "Cancelled")

		listed = api.fees()["payments"]

		self.assertEqual([p["name"] for p in listed], [payment.name])
		self.assertEqual(listed[0]["applied_to"][0]["fee_type"], REGISTRATION)

	def test_money_paid_beyond_the_invoices_is_reported_as_credit(self):
		invoice = self._as_admin(lambda: make_invoice(self.student.name, REGISTRATION, gross_amount=350))
		self._as_admin(
			lambda: make_payment(
				self.student.name, 500, [{"fee_invoice": invoice.name, "allocated_amount": 350}]
			)
		)

		payment = api.fees()["payments"][0]

		self.assertEqual(payment["amount"], 500)
		self.assertEqual(payment["unallocated_amount"], 150)


class TestTheStatement(FrappeTestCase):
	def setUp(self):
		self.student, _e, self.email = make_student()

	def tearDown(self):
		frappe.set_user("Administrator")

	def _statement(self):
		frappe.set_user(self.email)
		return api.fees()["statement"]

	def test_it_runs_a_balance_in_date_order(self):
		invoice = make_invoice(
			self.student.name, TUITION, gross_amount=3000, due_date=add_days(today(), -10)
		)
		make_payment(
			self.student.name, 1000, [{"fee_invoice": invoice.name, "allocated_amount": 1000}],
			received_on=add_days(today(), -5),
		)

		statement = self._statement()

		self.assertEqual([r["kind"] for r in statement["rows"]], ["Invoice", "Payment"])
		self.assertEqual([r["balance"] for r in statement["rows"]], [3000, 2000])
		self.assertEqual(statement["balance"], 2000)
		self.assertEqual(statement["charges"], 3000)
		self.assertEqual(statement["credits"], 1000)

	def test_a_waived_invoice_leaves_a_zero_balance(self):
		"""The staff ledger counts a waived invoice as owed. A student reading
		that would be told they still owe what was forgiven."""
		make_invoice(self.student.name, TUITION, gross_amount=3000, status="Waived")

		statement = self._statement()

		self.assertEqual([r["kind"] for r in statement["rows"]], ["Invoice", "Waived"])
		self.assertEqual(statement["balance"], 0)

	def test_a_part_paid_then_waived_invoice_waives_only_the_rest(self):
		invoice = make_invoice(self.student.name, TUITION, gross_amount=3000)
		make_payment(
			self.student.name, 1000, [{"fee_invoice": invoice.name, "allocated_amount": 1000}]
		)
		frappe.db.set_value("Fee Invoice", invoice.name, "status", "Waived")

		statement = self._statement()

		waived = next(r for r in statement["rows"] if r["kind"] == "Waived")
		self.assertEqual(waived["credit"], 2000)
		self.assertEqual(statement["balance"], 0)

	def test_an_overpayment_leaves_the_account_in_credit(self):
		invoice = make_invoice(self.student.name, REGISTRATION, gross_amount=350)
		make_payment(
			self.student.name, 500, [{"fee_invoice": invoice.name, "allocated_amount": 350}]
		)

		self.assertEqual(self._statement()["balance"], -150)


class TestWhoMayAsk(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_a_guest_is_refused_everywhere(self):
		frappe.set_user("Guest")
		for call in (api.fees, api.statement, lambda: api.receipt("PAY-0001")):
			with self.subTest(call=getattr(call, "__name__", "receipt")):
				with self.assertRaises(frappe.PermissionError):
					call()

	def test_none_of_them_names_a_student(self):
		"""A student or enrollment parameter would be a way to read another
		person's account by guessing a name."""
		for endpoint in (api.fees, api.statement):
			self.assertEqual(list(inspect.signature(endpoint).parameters), [])
		self.assertEqual(list(inspect.signature(api.receipt).parameters), ["payment"])

	def test_they_are_whitelisted_but_never_for_guests(self):
		for endpoint in (api.fees, api.receipt, api.statement):
			with self.subTest(endpoint=endpoint.__name__):
				self.assertIn(endpoint, frappe.whitelisted)
				self.assertNotIn(endpoint, frappe.guest_methods)

	def test_an_applicant_with_no_enrollment_is_not_an_error(self):
		email = f"applicant.{frappe.generate_hash(length=8)}@example.invalid"
		frappe.get_doc({
			"doctype": "User", "email": email, "first_name": "Applicant",
			"send_welcome_email": 0, "roles": [{"role": "Student"}],
		}).insert(ignore_permissions=True)

		frappe.set_user(email)

		page = api.fees()
		self.assertIsNone(page["enrollment"])
		self.assertEqual(page["invoices"], [])
		self.assertEqual(page["payments"], [])
		self.assertEqual(page["statement"]["rows"], [])
		self.assertEqual(page["summary"]["outstanding"], 0)
		with self.assertRaises(frappe.DoesNotExistError):
			api.statement()

	def test_somebody_elses_receipt_is_indistinguishable_from_none(self):
		"""The refusal must not become a way to find out which numbers exist."""
		mine, _e, my_email = make_student()
		theirs, _e2, _m = make_student()
		invoice = make_invoice(theirs.name, REGISTRATION, gross_amount=350)
		payment = pay(theirs, invoice, 350)

		frappe.set_user(my_email)
		answers = []
		for name in (payment.name, "PAY-DOES-NOT-EXIST"):
			with self.assertRaises(frappe.DoesNotExistError) as caught:
				api.receipt(name)
			answers.append(str(caught.exception))

		self.assertEqual(answers[0], answers[1])


class TestThePdfs(FrappeTestCase):
	def setUp(self):
		self.student, self.enrollment, self.email = make_student()
		self.invoice = make_invoice(self.student.name, TUITION, gross_amount=3000)
		self.payment = make_payment(
			self.student.name, 3000,
			[{"fee_invoice": self.invoice.name, "allocated_amount": 3000}],
			mode="UPI", reference_no="UTR-123456",
		)
		frappe.set_user(self.email)

	def tearDown(self):
		frappe.set_user("Administrator")

	def _render(self, call, *args):
		with mock.patch("frappe.utils.pdf.get_pdf", return_value=FAKE_PDF) as get_pdf:
			call(*args)
		return get_pdf.call_args[0][0]

	def test_a_receipt_is_a_pdf_named_for_the_payment(self):
		self._render(api.receipt, self.payment.name)

		self.assertEqual(frappe.local.response.type, "pdf")
		self.assertEqual(frappe.local.response.filecontent, FAKE_PDF)
		self.assertEqual(frappe.local.response.filename, f"receipt-{self.payment.name}.pdf")

	def test_the_receipt_says_what_was_paid_and_for_what(self):
		document = self._render(api.receipt, self.payment.name)

		self.assertIn(self.payment.name, document)
		self.assertIn("3,000.00", document)
		self.assertIn("UPI", document)
		self.assertIn("UTR-123456", document)
		self.assertIn(self.invoice.name, document)
		self.assertIn(TUITION, document)

	def test_anything_typed_by_a_person_is_escaped(self):
		"""A name, a reference number and a remark are typed by people and land
		inside an HTML page that is then rendered."""
		header = {
			"student_name": "Ruth <b>Bold</b> & Sons",
			"student": "S-1",
			"program_name": "<i>Divinity</i>",
		}
		payment = frappe._dict(
			name="PAY-1", received_on=today(), mode="UPI", reference_no="<img src=x onerror=alert(1)>",
			amount=100, unallocated_amount=0, applied_to=[],
		)

		document = api.receipt_html(header, payment)

		self.assertIn("Ruth &lt;b&gt;Bold&lt;/b&gt; &amp; Sons", document)
		self.assertIn("&lt;img src=x onerror=alert(1)&gt;", document)
		self.assertNotIn("<b>Bold</b>", document)
		self.assertNotIn("<img", document)
		self.assertNotIn("<i>Divinity</i>", document)

		statement = api.statement_html(
			header,
			{
				"rows": [
					{"date": today(), "particulars": "<u>x</u>", "reference": "R<1>",
					 "charge": 1, "credit": 0, "balance": 1}
				],
				"charges": 1, "credits": 0, "balance": 1,
			},
		)
		self.assertNotIn("<u>x</u>", statement)
		self.assertIn("&lt;u&gt;x&lt;/u&gt;", statement)

	def test_the_receipt_does_not_name_the_staff_member_who_recorded_it(self):
		document = self._render(api.receipt, self.payment.name)

		self.assertNotIn("Administrator", document)

	def test_credit_beyond_the_invoices_is_stated(self):
		html = api.receipt_html(
			{"student_name": "A", "student": "S", "program_name": "P"},
			frappe._dict(
				name="PAY-1", received_on=today(), mode="Cash", reference_no=None,
				amount=500, unallocated_amount=150, applied_to=[],
			),
		)

		self.assertIn("150.00", html)
		self.assertIn("held as credit", html)

	def test_a_statement_is_a_pdf(self):
		document = self._render(api.statement)

		self.assertEqual(frappe.local.response.type, "pdf")
		self.assertEqual(frappe.local.response.filename, f"statement-{self.student.name}.pdf")
		self.assertIn("Statement of account", document)
		self.assertIn(self.invoice.name, document)
		self.assertIn(self.payment.name, document)

	def test_when_the_renderer_fails_the_student_is_told_what_to_do(self):
		with mock.patch("frappe.utils.pdf.get_pdf", side_effect=OSError("no wkhtmltopdf")):
			with self.assertRaises(frappe.ValidationError) as caught:
				api.receipt(self.payment.name)

		self.assertIn("Print", str(caught.exception))
		self.assertNotIn("wkhtmltopdf", str(caught.exception))
