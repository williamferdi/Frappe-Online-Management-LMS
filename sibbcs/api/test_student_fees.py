# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""A student's own fee records -- the page, the receipt and the statement.

Money is the one thing in the portal where "somebody else's" matters most, so
a good half of these are about what cannot be asked for.
"""

import inspect
import io
import re
from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today
from pypdf import PdfReader

from sibbcs.api import fee_pdf
from sibbcs.api import student_fees as api
from sibbcs.api.test_student_api import make_student
from sibbcs.finance.test_fees import make_invoice, make_payment

TUITION = "Monthly Tuition"
REGISTRATION = "Course Registration Fee"


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
		# As money, not a bare float: "-1332.0" is not something to print on a student's statement.
		self.assertIn("1,332.00", rows[0]["particulars"])
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
	"""These build real PDFs and read them back. Nothing is mocked except where
	the point is a failure: a PDF that is merely asserted to exist proves
	nothing about what is printed on it."""

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

	def _read(self, content):
		"""Every page's text, whitespace folded so a wrapped line still matches."""
		reader = PdfReader(io.BytesIO(content))
		return re.sub(r"\s+", " ", " ".join(page.extract_text() for page in reader.pages))

	def _made(self, call, *args):
		call(*args)
		self.assertEqual(frappe.local.response.type, "pdf")
		content = frappe.local.response.filecontent
		self.assertTrue(content.startswith(b"%PDF"), "not a PDF")
		return self._read(content)

	def test_a_receipt_is_a_pdf_named_for_the_payment(self):
		self._made(api.receipt, self.payment.name)

		self.assertEqual(frappe.local.response.filename, f"receipt-{self.payment.name}.pdf")

	def test_the_receipt_says_what_was_paid_and_for_what(self):
		text = self._made(api.receipt, self.payment.name)

		self.assertIn("Payment receipt", text)
		self.assertIn(self.payment.name, text)
		self.assertIn(fee_pdf._plain(fee_pdf._money(3000)), text)
		self.assertIn("UPI", text)
		self.assertIn("UTR-123456", text)
		self.assertIn(self.invoice.name, text)
		self.assertIn(TUITION, text)
		self.assertIn(api._me()["student_name"], text)

	def test_the_rupee_sign_is_printed(self):
		"""The standard PDF fonts have no rupee sign; a font that does is why
		this is not simply Helvetica."""
		text = self._made(api.receipt, self.payment.name)

		self.assertIn("₹", text)

	def test_without_the_rupee_font_it_writes_rs_rather_than_a_box(self):
		with mock.patch.object(fee_pdf, "_fonts_cache", ("Helvetica", "Helvetica-Bold", False)):
			text = self._made(api.receipt, self.payment.name)

		self.assertIn("Rs.", text)
		self.assertNotIn("₹", text)
		self.assertIn("3,000.00", text)

	def test_it_does_not_need_wkhtmltopdf(self):
		"""The reason this exists: Frappe's own renderer is not on the server."""
		with mock.patch("frappe.utils.pdf.get_pdf", side_effect=AssertionError("must not be used")):
			self._made(api.receipt, self.payment.name)
			self._made(api.statement)

	def test_anything_typed_by_a_person_is_shown_literally(self):
		"""A name, a reference number and a remark are typed by people. In a PDF
		they are text in a cell; markup in them must neither take effect nor
		break the page."""
		header = {
			"student_name": "Ruth <b>Bold</b> & Sons",
			"student": "S-1",
			"program_name": "<i>Divinity</i>",
		}
		payment = frappe._dict(
			name="PAY-1", received_on=today(), mode="UPI", reference_no="<img src=x onerror=alert(1)>",
			amount=100, unallocated_amount=0, applied_to=[],
		)

		text = self._read(fee_pdf.receipt_pdf(header, payment))

		self.assertIn("Ruth <b>Bold</b> & Sons", text)
		self.assertIn("<i>Divinity</i>", text)
		self.assertIn("<img src=x onerror=alert(1)>", text)

		statement = {
			"rows": [
				{"date": today(), "particulars": "<u>x</u>", "reference": "R<1>",
				 "charge": 1, "credit": 0, "balance": 1}
			],
			"charges": 1, "credits": 0, "balance": 1,
		}
		text = self._read(fee_pdf.statement_pdf(header, statement))

		self.assertIn("<u>x</u>", text)
		self.assertIn("R<1>", text)

	def test_a_control_character_in_a_name_does_not_break_the_page(self):
		header = {"student_name": "Ruth\x00 Ann\x0b", "student": "S-1", "program_name": "P"}
		payment = frappe._dict(
			name="PAY-1", received_on=today(), mode="Cash", reference_no=None,
			amount=100, unallocated_amount=0, applied_to=[],
		)

		text = self._read(fee_pdf.receipt_pdf(header, payment))

		self.assertIn("Ruth Ann", text)

	def test_the_receipt_does_not_name_the_staff_member_who_recorded_it(self):
		text = self._made(api.receipt, self.payment.name)

		self.assertNotIn("Administrator", text)

	def test_credit_beyond_the_invoices_is_stated(self):
		text = self._read(
			fee_pdf.receipt_pdf(
				{"student_name": "A", "student": "S", "program_name": "P"},
				frappe._dict(
					name="PAY-1", received_on=today(), mode="Cash", reference_no=None,
					amount=500, unallocated_amount=150, applied_to=[],
				),
			)
		)

		self.assertIn("150.00", text)
		self.assertIn("held as credit", text)

	def test_a_statement_is_a_pdf(self):
		text = self._made(api.statement)

		self.assertEqual(frappe.local.response.filename, f"statement-{self.student.name}.pdf")
		self.assertIn("Statement of account", text)
		self.assertIn(self.invoice.name, text)
		self.assertIn(self.payment.name, text)
		self.assertIn("Settled", text)

	def test_a_statement_with_nothing_on_it_says_so(self):
		text = self._read(
			fee_pdf.statement_pdf(
				{"student_name": "A", "student": "S", "program_name": "P"},
				{"rows": [], "charges": 0, "credits": 0, "balance": 0},
			)
		)

		self.assertIn("Nothing has been billed", text)

	def test_a_long_statement_runs_onto_more_pages_and_repeats_its_header(self):
		rows = [
			{"date": today(), "particulars": f"Monthly Tuition {i}", "reference": f"FEE-{i}",
			 "charge": 100, "credit": 0, "balance": 100 * (i + 1)}
			for i in range(120)
		]
		content = fee_pdf.statement_pdf(
			{"student_name": "A", "student": "S", "program_name": "P"},
			{"rows": rows, "charges": 12000, "credits": 0, "balance": 12000},
		)

		reader = PdfReader(io.BytesIO(content))

		self.assertGreater(len(reader.pages), 1)
		with_rows = [p.extract_text() for p in reader.pages if "Monthly Tuition" in p.extract_text()]
		self.assertGreater(len(with_rows), 1)
		# Every page that carries rows carries the column headings too.
		for text in with_rows:
			self.assertIn("Particulars", text)

	def test_a_statement_that_owes_nothing_and_one_in_credit_are_told_apart(self):
		header = {"student_name": "A", "student": "S", "program_name": "P"}

		credit = self._read(
			fee_pdf.statement_pdf(header, {"rows": [], "charges": 0, "credits": 50, "balance": -50})
		)
		owed = self._read(
			fee_pdf.statement_pdf(header, {"rows": [], "charges": 50, "credits": 0, "balance": 50})
		)

		self.assertIn("In credit", credit)
		self.assertIn("Outstanding", owed)

	def test_when_drawing_fails_the_student_is_told_what_to_do(self):
		with mock.patch.object(fee_pdf, "receipt_pdf", side_effect=OSError("font went missing")):
			with self.assertRaises(frappe.ValidationError) as caught:
				api.receipt(self.payment.name)

		self.assertIn("Print", str(caught.exception))
		self.assertNotIn("font went missing", str(caught.exception))
