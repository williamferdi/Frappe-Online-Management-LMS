# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""The fee engine -- architecture doc §5, all four streams."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, today

from sibbcs.academic.doctype.academic_term.test_academic_term import make_term
from sibbcs.academic.doctype.course.test_course import make_course
from sibbcs.academic.doctype.course_offering.test_course_offering import make_offering
from sibbcs.academic.doctype.program_enrollment.test_program_enrollment import (
	make_enrollment,
	make_student,
)
from sibbcs.finance import fees
from sibbcs.finance.doctype.fee_invoice.fee_invoice import (
	outstanding_for_student,
	total_outstanding,
)


def make_invoice(student, fee_name="Application Fee", **kw):
	defaults = {
		"doctype": "Fee Invoice",
		"student": student,
		"fee_type": fee_name,
		"gross_amount": 350,
		"due_date": today(),
	}
	defaults.update(kw)
	return frappe.get_doc(defaults).insert(ignore_permissions=True)


def make_payment(student, amount, allocations=None, **kw):
	defaults = {
		"doctype": "Payment Entry",
		"student": student,
		"amount": amount,
		"mode": "UPI",
		"received_on": today(),
	}
	defaults.update(kw)
	doc = frappe.get_doc(defaults)
	for row in allocations or []:
		doc.append("allocations", row)
	return doc.insert(ignore_permissions=True)


class TestFeeTypeSeed(FrappeTestCase):
	def test_the_six_fee_types_exist(self):
		for name in (
			"Application Fee", "Admission Fee", "Course Registration Fee",
			"Monthly Tuition", "ATA Registration", "Graduation & Transcript",
		):
			self.assertTrue(frappe.db.exists("Fee Type", name), name)

	def test_amounts_match_the_spec(self):
		expected = {
			"Application Fee": 350, "Admission Fee": 2000,
			"Course Registration Fee": 350, "Monthly Tuition": 1500,
			"ATA Registration": 2000, "Graduation & Transcript": 2000,
		}
		for name, amount in expected.items():
			self.assertEqual(
				flt(frappe.db.get_value("Fee Type", name, "default_amount")), amount, name
			)

	def test_only_tuition_is_discountable(self):
		"""§5 Stream 2: the per-registration fee is not discountable."""
		self.assertTrue(frappe.db.get_value("Fee Type", "Monthly Tuition", "discountable"))
		for name in ("Application Fee", "Course Registration Fee", "ATA Registration"):
			self.assertFalse(
				frappe.db.get_value("Fee Type", name, "discountable"), name
			)

	def test_ata_is_scoped_to_mdiv(self):
		programs = frappe.get_all(
			"Fee Type Program", filters={"parent": "ATA Registration"}, pluck="program"
		)
		self.assertEqual(programs, ["MDIV"])


class TestInvoiceArithmetic(FrappeTestCase):
	def test_net_is_gross_minus_discount(self):
		student = make_student(email="fee1@example.com")
		invoice = make_invoice(
			student.name, "Monthly Tuition", gross_amount=3000, discount_amount=1600
		)
		self.assertEqual(invoice.net_amount, 1400)
		self.assertEqual(invoice.outstanding_amount, 1400)

	def test_discount_cannot_exceed_gross(self):
		student = make_student(email="fee2@example.com")
		with self.assertRaises(frappe.ValidationError):
			make_invoice(
				student.name, "Monthly Tuition", gross_amount=1000, discount_amount=2000
			)

	def test_non_discountable_fee_rejects_a_discount(self):
		student = make_student(email="fee3@example.com")
		with self.assertRaises(frappe.ValidationError):
			make_invoice(
				student.name, "Course Registration Fee", gross_amount=350, discount_amount=50
			)

	def test_negative_gross_rejected(self):
		student = make_student(email="fee4@example.com")
		with self.assertRaises(frappe.ValidationError):
			make_invoice(student.name, gross_amount=-1)

	def test_new_invoice_is_unpaid(self):
		student = make_student(email="fee5@example.com")
		self.assertEqual(make_invoice(student.name).status, "Unpaid")


class TestPaymentAllocation(FrappeTestCase):
	def test_full_payment_marks_invoice_paid(self):
		student = make_student(email="pay1@example.com")
		invoice = make_invoice(student.name, gross_amount=350)
		make_payment(
			student.name, 350, [{"fee_invoice": invoice.name, "allocated_amount": 350}]
		)
		invoice.reload()
		self.assertEqual(invoice.status, "Paid")
		self.assertEqual(invoice.outstanding_amount, 0)

	def test_partial_payment_marks_partly_paid(self):
		student = make_student(email="pay2@example.com")
		invoice = make_invoice(student.name, gross_amount=1000)
		make_payment(
			student.name, 400, [{"fee_invoice": invoice.name, "allocated_amount": 400}]
		)
		invoice.reload()
		self.assertEqual(invoice.status, "Partly Paid")
		self.assertEqual(invoice.outstanding_amount, 600)

	def test_over_allocation_within_one_entry_rejected(self):
		student = make_student(email="pay3@example.com")
		invoice = make_invoice(student.name, gross_amount=350)
		with self.assertRaises(frappe.ValidationError):
			make_payment(
				student.name, 500, [{"fee_invoice": invoice.name, "allocated_amount": 500}]
			)

	def test_over_allocation_across_two_entries_rejected(self):
		"""The classic reconciliation bug: each entry looks fine alone."""
		student = make_student(email="pay4@example.com")
		invoice = make_invoice(student.name, gross_amount=1000)
		make_payment(
			student.name, 600, [{"fee_invoice": invoice.name, "allocated_amount": 600}]
		)
		with self.assertRaises(frappe.ValidationError):
			make_payment(
				student.name, 600, [{"fee_invoice": invoice.name, "allocated_amount": 600}]
			)

	def test_allocation_beyond_payment_amount_rejected(self):
		student = make_student(email="pay5@example.com")
		a = make_invoice(student.name, gross_amount=500)
		b = make_invoice(student.name, "Admission Fee", gross_amount=500)
		with self.assertRaises(frappe.ValidationError):
			make_payment(
				student.name,
				600,
				[
					{"fee_invoice": a.name, "allocated_amount": 500},
					{"fee_invoice": b.name, "allocated_amount": 500},
				],
			)

	def test_cannot_pay_another_students_invoice(self):
		one = make_student(email="pay6@example.com")
		two = make_student(full_name="Other", email="pay7@example.com")
		invoice = make_invoice(two.name, gross_amount=350)
		with self.assertRaises(frappe.ValidationError):
			make_payment(
				one.name, 350, [{"fee_invoice": invoice.name, "allocated_amount": 350}]
			)

	def test_duplicate_allocation_rows_rejected(self):
		student = make_student(email="pay8@example.com")
		invoice = make_invoice(student.name, gross_amount=1000)
		with self.assertRaises(frappe.ValidationError):
			make_payment(
				student.name,
				1000,
				[
					{"fee_invoice": invoice.name, "allocated_amount": 500},
					{"fee_invoice": invoice.name, "allocated_amount": 500},
				],
			)

	def test_unallocated_is_tracked(self):
		student = make_student(email="pay9@example.com")
		invoice = make_invoice(student.name, gross_amount=350)
		entry = make_payment(
			student.name, 1000, [{"fee_invoice": invoice.name, "allocated_amount": 350}]
		)
		self.assertEqual(entry.unallocated_amount, 650)

	def test_auto_allocate_settles_oldest_first(self):
		student = make_student(email="pay10@example.com")
		old = make_invoice(student.name, gross_amount=350, due_date="2026-01-01")
		new = make_invoice(student.name, "Admission Fee", gross_amount=2000, due_date="2026-06-01")

		entry = make_payment(student.name, 1000)
		entry.auto_allocate()
		entry.save(ignore_permissions=True)

		allocated = {r.fee_invoice: flt(r.allocated_amount) for r in entry.allocations}
		self.assertEqual(allocated.get(old.name), 350)
		self.assertEqual(allocated.get(new.name), 650)

	def test_total_outstanding(self):
		student = make_student(email="pay11@example.com")
		make_invoice(student.name, gross_amount=350)
		make_invoice(student.name, "Admission Fee", gross_amount=2000)
		self.assertEqual(total_outstanding(student.name), 2350)


class TestRegistrationFee(FrappeTestCase):
	"""§5 Stream 2."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.term = make_term("TST-FEE-TERM", status="Open").name

	def _registration(self, email, code):
		student = make_student(full_name=f"Fee {email}", email=email)
		enrollment = make_enrollment(student.name)
		course = make_course(code, level="1")
		offering = make_offering(course.name, self.term, status="Published")
		registration = frappe.get_doc(
			{
				"doctype": "Course Registration",
				"program_enrollment": enrollment.name,
				"course_offering": offering.name,
				"registration_date": today(),
				"status": "Registered",
			}
		).insert(ignore_permissions=True)
		return student, enrollment, registration

	def test_registration_raises_a_350_fee(self):
		student, _e, registration = self._registration("regfee1@example.com", "TST F100")
		registration.reload()
		self.assertTrue(registration.registration_fee_invoice)
		invoice = frappe.get_doc("Fee Invoice", registration.registration_fee_invoice)
		self.assertEqual(invoice.net_amount, 350)
		self.assertEqual(invoice.fee_type, "Course Registration Fee")

	def test_registration_fee_is_not_raised_twice(self):
		_s, _e, registration = self._registration("regfee2@example.com", "TST F110")
		fees.raise_registration_fee(registration.name)
		count = frappe.db.count(
			"Fee Invoice", {"course_registration": registration.name}
		)
		self.assertEqual(count, 1)

	def test_registration_fee_ignores_scholarship(self):
		"""Even with a scholarship, the per-registration fee is billed in full."""
		student, enrollment, registration = self._registration("regfee3@example.com", "TST F120")
		frappe.db.set_value(
			"Program Enrollment",
			enrollment.name,
			{"scholarship_monthly_discount": 800, "scholarship_total_cap": 24000},
			update_modified=False,
		)
		registration.reload()
		invoice = frappe.get_doc("Fee Invoice", registration.registration_fee_invoice)
		self.assertEqual(invoice.discount_amount, 0)
		self.assertEqual(invoice.net_amount, 350)


class TestTuitionStream(FrappeTestCase):
	"""§5 Stream 3 -- the paused subscription, plus the Rs54,000 ceiling."""

	def _setup(self, email, code, term_name, monthly_discount=0, cap=0):
		student = make_student(full_name=f"Tui {email}", email=email)
		enrollment = make_enrollment(student.name)
		if monthly_discount or cap:
			frappe.db.set_value(
				"Program Enrollment",
				enrollment.name,
				{
					"scholarship_monthly_discount": monthly_discount,
					"scholarship_total_cap": cap,
				},
				update_modified=False,
			)
			enrollment.reload()
		term = make_term(term_name, status="Open")
		return student, enrollment, term

	def _register(self, enrollment, term, code):
		course = make_course(code, level="1")
		offering = make_offering(course.name, term.name, status="Published")
		return frappe.get_doc(
			{
				"doctype": "Course Registration",
				"program_enrollment": enrollment.name,
				"course_offering": offering.name,
				"registration_date": today(),
				"status": "Registered",
			}
		).insert(ignore_permissions=True)

	def test_tuition_is_paused_without_registrations(self):
		"""The whole point of the paused subscription."""
		_s, enrollment, term = self._setup("tui1@example.com", "TST T100", "TST-TUI-1")
		outcome = fees.bill_enrollment_for_term(enrollment.name, term.name)
		self.assertIsNone(outcome["invoice"])
		self.assertIn("paused", outcome["skipped"])

	def test_tuition_bills_when_registered(self):
		_s, enrollment, term = self._setup("tui2@example.com", "TST T110", "TST-TUI-2")
		self._register(enrollment, term, "TST T110")

		outcome = fees.bill_enrollment_for_term(enrollment.name, term.name)
		invoice = frappe.get_doc("Fee Invoice", outcome["invoice"])
		# 2 months x Rs1500
		self.assertEqual(invoice.gross_amount, 3000)
		self.assertEqual(invoice.months_billed, 2)

	def test_tuition_is_not_billed_twice_for_a_term(self):
		_s, enrollment, term = self._setup("tui3@example.com", "TST T120", "TST-TUI-3")
		self._register(enrollment, term, "TST T120")

		fees.bill_enrollment_for_term(enrollment.name, term.name)
		second = fees.bill_enrollment_for_term(enrollment.name, term.name)
		self.assertIsNone(second["invoice"])
		self.assertIn("already billed", second["skipped"])

	def test_scholarship_discount_is_applied(self):
		_s, enrollment, term = self._setup(
			"tui4@example.com", "TST T130", "TST-TUI-4", monthly_discount=800, cap=24000
		)
		self._register(enrollment, term, "TST T130")

		outcome = fees.bill_enrollment_for_term(enrollment.name, term.name)
		invoice = frappe.get_doc("Fee Invoice", outcome["invoice"])
		self.assertEqual(invoice.gross_amount, 3000)
		self.assertEqual(invoice.discount_amount, 1600)  # 2 x 800
		self.assertEqual(invoice.net_amount, 1400)

	def test_scholarship_spend_is_recorded(self):
		_s, enrollment, term = self._setup(
			"tui5@example.com", "TST T140", "TST-TUI-5", monthly_discount=800, cap=24000
		)
		self._register(enrollment, term, "TST T140")
		fees.bill_enrollment_for_term(enrollment.name, term.name)

		enrollment.reload()
		self.assertEqual(enrollment.scholarship_used_to_date, 1600)

	def test_discount_stops_at_the_scholarship_cap(self):
		"""Architecture doc §5: the cap is what makes a flexible award safe."""
		_s, enrollment, term = self._setup(
			"tui6@example.com", "TST T150", "TST-TUI-6", monthly_discount=800, cap=1000
		)
		self._register(enrollment, term, "TST T150")

		outcome = fees.bill_enrollment_for_term(enrollment.name, term.name)
		invoice = frappe.get_doc("Fee Invoice", outcome["invoice"])
		# wanted 1600, but only 1000 of cap remains
		self.assertEqual(invoice.discount_amount, 1000)
		self.assertEqual(invoice.net_amount, 2000)

	def test_tuition_stops_at_the_programme_ceiling(self):
		"""Decision #1: cap at Rs54,000, pay-as-you-go."""
		_s, enrollment, term = self._setup("tui7@example.com", "TST T160", "TST-TUI-7")
		self._register(enrollment, term, "TST T160")

		# pretend Rs54,000 has already been billed
		frappe.get_doc(
			{
				"doctype": "Fee Invoice",
				"student": enrollment.student,
				"program_enrollment": enrollment.name,
				"fee_type": "Monthly Tuition",
				"gross_amount": 54000,
				"due_date": today(),
				"term": make_term("TST-TUI-7-PRIOR", status="Closed").name,
			}
		).insert(ignore_permissions=True)

		outcome = fees.bill_enrollment_for_term(enrollment.name, term.name)
		self.assertIsNone(outcome["invoice"])
		self.assertIn("ceiling", outcome["skipped"])

	def test_final_invoice_is_trimmed_to_the_ceiling(self):
		"""Never overshoot the advertised total."""
		_s, enrollment, term = self._setup("tui8@example.com", "TST T170", "TST-TUI-8")
		self._register(enrollment, term, "TST T170")

		frappe.get_doc(
			{
				"doctype": "Fee Invoice",
				"student": enrollment.student,
				"program_enrollment": enrollment.name,
				"fee_type": "Monthly Tuition",
				"gross_amount": 52000,
				"due_date": today(),
				"term": make_term("TST-TUI-8-PRIOR", status="Closed").name,
			}
		).insert(ignore_permissions=True)

		outcome = fees.bill_enrollment_for_term(enrollment.name, term.name)
		invoice = frappe.get_doc("Fee Invoice", outcome["invoice"])
		# Rs3000 would overshoot; only Rs2000 of headroom remains
		self.assertEqual(invoice.gross_amount, 2000)

	def test_ceiling_is_measured_on_gross_not_net(self):
		"""If measured on net, a scholarship would merely stretch the payment
		period instead of reducing the bill -- cancelling out Stream 4."""
		_s, enrollment, term = self._setup(
			"tui9@example.com", "TST T180", "TST-TUI-9", monthly_discount=800, cap=24000
		)
		self._register(enrollment, term, "TST T180")
		fees.bill_enrollment_for_term(enrollment.name, term.name)

		on_gross = fees.tuition_billed_to_date(enrollment.name, on_gross=True)
		on_net = fees.tuition_billed_to_date(enrollment.name, on_gross=False)
		self.assertEqual(on_gross, 3000)
		self.assertEqual(on_net, 1400)

	def test_inactive_enrollment_is_not_billed(self):
		_s, enrollment, term = self._setup("tui10@example.com", "TST T190", "TST-TUI-10")
		self._register(enrollment, term, "TST T190")
		frappe.db.set_value(
			"Program Enrollment", enrollment.name, "status", "Withdrawn", update_modified=False
		)

		outcome = fees.bill_enrollment_for_term(enrollment.name, term.name)
		self.assertIsNone(outcome["invoice"])

	def test_run_term_tuition_reports_both_lists(self):
		_s, enrollment, term = self._setup("tui11@example.com", "TST T200", "TST-TUI-11")
		self._register(enrollment, term, "TST T200")

		result = fees.run_term_tuition(term.name)
		billed = {b["enrollment"] for b in result["billed"]}
		self.assertIn(enrollment.name, billed)


class TestOneTimeFees(FrappeTestCase):
	"""§5 Stream 1."""

	def test_ata_only_for_mdiv(self):
		student = make_student(email="ata1@example.com")
		enrollment = make_enrollment(student.name, program="MACS")
		self.assertIsNone(fees.raise_ata_fee(student.name, enrollment.name, "MACS"))

	def test_ata_raised_for_mdiv(self):
		student = make_student(email="ata2@example.com")
		enrollment = make_enrollment(student.name, program="MDIV")
		invoice = fees.raise_ata_fee(student.name, enrollment.name, "MDIV")
		self.assertIsNotNone(invoice)
		self.assertEqual(invoice.net_amount, 2000)

	def test_ata_not_raised_twice(self):
		student = make_student(email="ata3@example.com")
		enrollment = make_enrollment(student.name, program="MDIV")
		fees.raise_ata_fee(student.name, enrollment.name, "MDIV")
		self.assertIsNone(fees.raise_ata_fee(student.name, enrollment.name, "MDIV"))


class TestLedger(FrappeTestCase):
	def test_running_balance(self):
		from sibbcs.finance.report.student_fee_ledger.student_fee_ledger import execute

		student = make_student(email="ledger1@example.com")
		invoice = make_invoice(student.name, gross_amount=350, due_date="2026-01-01")
		make_payment(
			student.name,
			200,
			[{"fee_invoice": invoice.name, "allocated_amount": 200}],
			received_on="2026-01-05",
		)

		_columns, rows = execute({"student": student.name})
		closing = rows[-1]
		self.assertEqual(closing["charge"], 350)
		self.assertEqual(closing["credit"], 200)
		self.assertEqual(closing["balance"], 150)

	def test_ledger_requires_a_student(self):
		from sibbcs.finance.report.student_fee_ledger.student_fee_ledger import execute

		with self.assertRaises(frappe.ValidationError):
			execute({})


class TestRazorpaySignature(FrappeTestCase):
	"""The webhook is the one place an outsider can mark invoices paid."""

	def test_valid_signature_accepted(self):
		import hashlib
		import hmac

		from sibbcs.finance.razorpay import verify_signature

		secret = "whsec_test"
		body = b'{"event":"payment.captured"}'
		signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
		self.assertTrue(verify_signature(body, signature, secret))

	def test_wrong_signature_rejected(self):
		from sibbcs.finance.razorpay import verify_signature

		self.assertFalse(
			verify_signature(b'{"event":"x"}', "deadbeef", "whsec_test")
		)

	def test_missing_signature_rejected(self):
		from sibbcs.finance.razorpay import verify_signature

		self.assertFalse(verify_signature(b"{}", None, "whsec_test"))

	def test_missing_secret_rejected(self):
		from sibbcs.finance.razorpay import verify_signature

		self.assertFalse(verify_signature(b"{}", "abc", None))

	def test_tampered_body_rejected(self):
		import hashlib
		import hmac

		from sibbcs.finance.razorpay import verify_signature

		secret = "whsec_test"
		signature = hmac.new(secret.encode(), b'{"amount":100}', hashlib.sha256).hexdigest()
		self.assertFalse(verify_signature(b'{"amount":999999}', signature, secret))
