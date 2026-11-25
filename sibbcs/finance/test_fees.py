# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""The fee engine -- architecture doc §5, all four streams."""

from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, getdate, today

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

	def _bill_to(self, enrollment, amount, label):
		"""Put `amount` of gross tuition on the books against an earlier term."""
		frappe.get_doc(
			{
				"doctype": "Fee Invoice",
				"student": enrollment.student,
				"program_enrollment": enrollment.name,
				"fee_type": "Monthly Tuition",
				"gross_amount": amount,
				"due_date": today(),
				"term": make_term(label, status="Closed").name,
			}
		).insert(ignore_permissions=True)

	def test_less_than_a_month_left_is_not_billed(self):
		"""The tail invoice. Rs78,000 is not a multiple of a Rs4,332 term, so
		after 18 terms Rs24 was left and arrived as an invoice of its own."""
		_s, enrollment, _term = self._setup("tui13@example.com", "TST T210", "TST-TUI-13")
		self._bill_to(enrollment, 77976, "TST-TUI-13-PRIOR")
		program = frappe._dict(monthly_tuition=2166, tuition_total=78000, cap_on_gross=1)

		outcome = fees.compute_tuition(enrollment, program, 2)

		self.assertEqual(outcome["gross"], 0)
		self.assertEqual(outcome["reason"], "ceiling reached")

	def test_the_last_full_term_is_still_billed_in_full(self):
		"""One term short of the tail: Rs4,356 left, so a whole Rs4,332 term goes."""
		_s, enrollment, _term = self._setup("tui14@example.com", "TST T220", "TST-TUI-14")
		self._bill_to(enrollment, 73644, "TST-TUI-14-PRIOR")
		program = frappe._dict(monthly_tuition=2166, tuition_total=78000, cap_on_gross=1)

		outcome = fees.compute_tuition(enrollment, program, 2)

		self.assertEqual(outcome["gross"], 4332)

	def test_exactly_one_month_left_is_still_billed(self):
		"""The boundary: a remainder equal to the monthly rate is a month."""
		_s, enrollment, _term = self._setup("tui15@example.com", "TST T230", "TST-TUI-15")
		self._bill_to(enrollment, 52500, "TST-TUI-15-PRIOR")
		program = frappe._dict(monthly_tuition=1500, tuition_total=54000, cap_on_gross=1)

		outcome = fees.compute_tuition(enrollment, program, 2)

		self.assertEqual(outcome["gross"], 1500)

	def test_a_sliver_under_a_month_is_not_billed(self):
		_s, enrollment, _term = self._setup("tui16@example.com", "TST T240", "TST-TUI-16")
		self._bill_to(enrollment, 52501, "TST-TUI-16-PRIOR")
		program = frappe._dict(monthly_tuition=1500, tuition_total=54000, cap_on_gross=1)

		outcome = fees.compute_tuition(enrollment, program, 2)

		self.assertEqual(outcome["gross"], 0)

	def test_the_tail_does_not_spend_the_scholarship(self):
		"""No invoice, so nothing is discounted and nothing is used up."""
		_s, enrollment, term = self._setup(
			"tui17@example.com", "TST T250", "TST-TUI-17", monthly_discount=666, cap=24000
		)
		self._register(enrollment, term, "TST T250")
		self._bill_to(enrollment, 52990, "TST-TUI-17-PRIOR")

		outcome = fees.bill_enrollment_for_term(enrollment.name, term.name)

		self.assertIsNone(outcome["invoice"])
		enrollment.reload()
		self.assertEqual(enrollment.scholarship_used_to_date, 0)

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



class TestLateRegistrantBilling(FrappeTestCase):
	"""A student who registers after a term has started is still billed for it.

	The nightly job used to match `start_date == today`. 2026-T6 began on
	16 Nov; a student registered on 20 Nov, the job reported "Complete" every
	night, and no invoice was ever raised. Registration runs for weeks into a
	term, so this was the ordinary case, not an edge.
	"""

	# The set-up is the tuition stream's own; borrowing it rather than
	# subclassing keeps its tests from running twice.
	_setup = TestTuitionStream._setup
	_register = TestTuitionStream._register

	def _started_term(self, name, started_days_ago=10, status="Open"):
		return make_term(
			name,
			status=status,
			start_date=add_days(today(), -started_days_ago),
			end_date=add_days(today(), 60),
		)

	def _run_nightly_for(self, term):
		"""The real entry point, aimed at one term.

		The test database holds terms left by other tests, and billing every one
		of them would make this slow without testing anything more.
		"""
		with mock.patch.object(fees, "terms_to_bill", return_value=[term.name]):
			fees.run_term_tuition_scheduled()

	def _invoices(self, enrollment):
		return frappe.get_all(
			"Fee Invoice",
			filters={"program_enrollment": enrollment.name, "fee_type": "Monthly Tuition"},
			fields=["name", "term", "due_date", "gross_amount"],
		)

	def test_a_registration_after_the_start_date_is_billed(self):
		term = self._started_term("TST-LATE-1")
		_s, enrollment, _t = self._setup("late1@example.com", "TST L100", "TST-LATE-1")
		self._register(enrollment, term, "TST L100")

		self._run_nightly_for(term)

		rows = self._invoices(enrollment)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0].term, term.name)
		self.assertEqual(rows[0].gross_amount, 3000)

	def test_a_late_invoice_is_not_overdue_the_moment_it_appears(self):
		term = self._started_term("TST-LATE-2", started_days_ago=10)
		_s, enrollment, _t = self._setup("late2@example.com", "TST L110", "TST-LATE-2")
		self._register(enrollment, term, "TST L110")

		self._run_nightly_for(term)

		due = getdate(self._invoices(enrollment)[0].due_date)
		# start + 14 would be four days ago
		self.assertEqual(due, getdate(add_days(today(), 14)))

	def test_an_invoice_for_a_term_yet_to_start_still_falls_due_after_it_starts(self):
		"""The other side of the max(): billing early must not pull the date in."""
		term = make_term(
			"TST-LATE-3",
			status="Open",
			start_date=add_days(today(), 5),
			end_date=add_days(today(), 65),
		)
		_s, enrollment, _t = self._setup("late3@example.com", "TST L120", "TST-LATE-3")
		self._register(enrollment, term, "TST L120")

		fees.bill_enrollment_for_term(enrollment.name, term.name)

		due = getdate(self._invoices(enrollment)[0].due_date)
		self.assertEqual(due, getdate(add_days(today(), 19)))

	def test_running_the_job_every_night_bills_a_term_once(self):
		term = self._started_term("TST-LATE-4")
		_s, enrollment, _t = self._setup("late4@example.com", "TST L130", "TST-LATE-4")
		self._register(enrollment, term, "TST L130")

		for _night in range(3):
			self._run_nightly_for(term)

		self.assertEqual(len(self._invoices(enrollment)), 1)

	def test_a_student_with_no_registration_is_still_paused_on_a_started_term(self):
		term = self._started_term("TST-LATE-5")
		_s, enrollment, _t = self._setup("late5@example.com", "TST L140", "TST-LATE-5")

		self._run_nightly_for(term)

		self.assertEqual(self._invoices(enrollment), [])

	def test_which_terms_the_job_offers(self):
		started_open = self._started_term("TST-LATE-6A", status="Open")
		started_active = self._started_term("TST-LATE-6B", status="Active")
		starts_today = self._started_term("TST-LATE-6C", started_days_ago=0)
		closed = self._started_term("TST-LATE-6D", status="Closed")
		planned = self._started_term("TST-LATE-6E", status="Planned")
		not_started = make_term(
			"TST-LATE-6F",
			status="Open",
			start_date=add_days(today(), 3),
			end_date=add_days(today(), 63),
		)

		offered = set(fees.terms_to_bill())

		self.assertTrue({started_open.name, started_active.name, starts_today.name} <= offered)
		self.assertFalse({closed.name, planned.name, not_started.name} & offered)

	def test_the_start_day_itself_still_bills(self):
		"""What the old job did must survive the change."""
		term = self._started_term("TST-LATE-7", started_days_ago=0)
		_s, enrollment, _t = self._setup("late7@example.com", "TST L150", "TST-LATE-7")
		self._register(enrollment, term, "TST L150")

		self._run_nightly_for(term)

		rows = self._invoices(enrollment)
		self.assertEqual(len(rows), 1)
		self.assertEqual(getdate(rows[0].due_date), getdate(add_days(today(), 14)))



class TestCeilingState(FrappeTestCase):
	"""The one rule for when billing stops -- pure, so the boundary is exact."""

	def test_uncapped_is_never_reached(self):
		self.assertEqual(fees.ceiling_state(0, 999999, 1500), (None, False))

	def test_a_month_or_more_left_is_not_reached(self):
		self.assertEqual(fees.ceiling_state(54000, 52500, 1500), (1500, False))
		self.assertEqual(fees.ceiling_state(54000, 0, 1500), (54000, False))

	def test_less_than_a_month_left_is_reached(self):
		self.assertEqual(fees.ceiling_state(54000, 52501, 1500), (1499, True))
		self.assertEqual(fees.ceiling_state(78000, 77976, 2166), (24, True))

	def test_billed_to_the_ceiling_or_past_it_is_reached(self):
		self.assertEqual(fees.ceiling_state(54000, 54000, 1500), (0, True))
		self.assertTrue(fees.ceiling_state(54000, 56000, 1500)[1])


class TestTuitionPosition(FrappeTestCase):
	"""What the screens show about a student's tuition -- and that it is what
	the nightly job would do. The job used to know a student had reached the
	ceiling and told nobody."""

	_setup = TestTuitionStream._setup
	_register = TestTuitionStream._register
	_bill_to = TestTuitionStream._bill_to

	def _program(self, enrollment):
		return frappe.get_doc("Program", enrollment.program)

	def test_nothing_billed_yet(self):
		_s, enrollment, _t = self._setup("pos1@example.com", "TST P100", "TST-POS-1")

		position = fees.tuition_position(enrollment)

		ceiling = flt(self._program(enrollment).tuition_total)
		self.assertTrue(ceiling, "the test programme is expected to carry a ceiling")
		self.assertEqual(position["state"], "billing")
		self.assertEqual(position["billed"], 0)
		self.assertEqual(position["remaining"], ceiling)
		self.assertEqual(position["terms_billed"], 0)
		self.assertIsNone(position["scholarship"])

	def test_it_counts_what_has_been_billed(self):
		_s, enrollment, term = self._setup(
			"pos2@example.com", "TST P110", "TST-POS-2", monthly_discount=800, cap=24000
		)
		self._register(enrollment, term, "TST P110")
		fees.bill_enrollment_for_term(enrollment.name, term.name)

		position = fees.tuition_position(enrollment.name)

		self.assertEqual(position["billed"], 3000)
		self.assertEqual(position["terms_billed"], 1)
		self.assertEqual(
			position["scholarship"],
			{"monthly": 800, "cap": 24000, "used": 1600, "remaining": 22400},
		)

	def test_it_says_when_the_ceiling_is_reached(self):
		_s, enrollment, _t = self._setup("pos3@example.com", "TST P120", "TST-POS-3")
		ceiling = flt(self._program(enrollment).tuition_total)
		self._bill_to(enrollment, ceiling - 24, "TST-POS-3-PRIOR")

		position = fees.tuition_position(enrollment)

		self.assertEqual(position["state"], "ceiling_reached")
		# The unbilled sliver is shown, not hidden: it is less than a month.
		self.assertEqual(position["remaining"], 24)

	def test_the_screen_and_the_job_agree(self):
		"""The reason for sharing one rule: they cannot say different things."""
		_s, enrollment, term = self._setup("pos4@example.com", "TST P130", "TST-POS-4")
		self._register(enrollment, term, "TST P130")
		ceiling = flt(self._program(enrollment).tuition_total)
		self._bill_to(enrollment, ceiling - 100, "TST-POS-4-PRIOR")

		position = fees.tuition_position(enrollment)
		outcome = fees.bill_enrollment_for_term(enrollment.name, term.name, dry_run=True)

		self.assertEqual(position["state"], "ceiling_reached")
		self.assertIn("ceiling", outcome["skipped"])

	def test_a_cancelled_invoice_is_not_counted(self):
		_s, enrollment, _t = self._setup("pos5@example.com", "TST P140", "TST-POS-5")
		self._bill_to(enrollment, 3000, "TST-POS-5-PRIOR")
		name = frappe.db.get_value(
			"Fee Invoice", {"program_enrollment": enrollment.name, "fee_type": "Monthly Tuition"}
		)
		frappe.db.set_value("Fee Invoice", name, "status", "Cancelled")

		position = fees.tuition_position(enrollment)

		self.assertEqual(position["billed"], 0)
		self.assertEqual(position["terms_billed"], 0)

	def test_uncapped_has_no_remainder(self):
		program = frappe._dict(monthly_tuition=1500, tuition_total=0, cap_on_gross=1)
		enrollment = frappe._dict(name="X")

		position = fees._position(enrollment, program, {"gross": 9000, "net": 9000, "terms": 3})

		self.assertEqual(position["state"], "uncapped")
		self.assertIsNone(position["remaining"])
		self.assertEqual(position["billed"], 9000)

	def test_net_is_measured_when_the_programme_says_so(self):
		program = frappe._dict(monthly_tuition=1500, tuition_total=54000, cap_on_gross=0)
		enrollment = frappe._dict(name="X")

		position = fees._position(enrollment, program, {"gross": 3000, "net": 1400, "terms": 1})

		self.assertEqual(position["billed"], 1400)

	def test_the_roster_puts_those_at_the_ceiling_first(self):
		_s, open_one, _t = self._setup("pos6@example.com", "TST P150", "TST-POS-6")
		_s, at_ceiling, _t = self._setup("pos7@example.com", "TST P160", "TST-POS-7")
		ceiling = flt(self._program(at_ceiling).tuition_total)
		self._bill_to(at_ceiling, ceiling, "TST-POS-7-PRIOR")

		names = [row["enrollment"] for row in fees.tuition_positions()]

		self.assertIn(open_one.name, names)
		self.assertLess(names.index(at_ceiling.name), names.index(open_one.name))

	def test_the_roster_names_the_student(self):
		_s, enrollment, _t = self._setup("pos8@example.com", "TST P170", "TST-POS-8")

		row = next(r for r in fees.tuition_positions() if r["enrollment"] == enrollment.name)

		self.assertEqual(row["student"], enrollment.student)
		self.assertEqual(row["program"], enrollment.program)
		self.assertEqual(row["level"], enrollment.current_level)



class TestCancellingTuition(FrappeTestCase):
	"""Cancelling a tuition invoice undoes its billing.

	It used to flip a status and nothing else. The ceiling stopped counting the
	invoice, but the scholarship it spent was never returned and the billing job
	never raised the term again -- so the student lost that scholarship for
	good and the same tuition arrived at the far end of the programme instead.
	"""

	_setup = TestTuitionStream._setup
	_register = TestTuitionStream._register
	_registration = TestRegistrationFee._registration

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.term = make_term("TST-FEE-TERM", status="Open").name

	def _billed(self, email, code, term_name, **kw):
		_s, enrollment, term = self._setup(email, code, term_name, **kw)
		self._register(enrollment, term, code)
		outcome = fees.bill_enrollment_for_term(enrollment.name, term.name)
		return enrollment, term, frappe.get_doc("Fee Invoice", outcome["invoice"])

	def _cancel(self, invoice):
		invoice.reload()
		invoice.status = "Cancelled"
		invoice.save(ignore_permissions=True)
		return invoice

	def _used(self, enrollment):
		return flt(
			frappe.db.get_value("Program Enrollment", enrollment.name, "scholarship_used_to_date")
		)

	def test_cancelling_returns_the_scholarship_it_spent(self):
		enrollment, _term, invoice = self._billed(
			"can1@example.com", "TST C100", "TST-CAN-1", monthly_discount=800, cap=24000
		)
		self.assertEqual(self._used(enrollment), 1600)

		self._cancel(invoice)

		self.assertEqual(self._used(enrollment), 0)

	def test_it_is_returned_once_not_every_time_the_invoice_is_saved(self):
		"""Two invoices spent 3,200. Cancelling one returns 1,600; saving the
		cancelled one again for a remark must not return it a second time."""
		enrollment, _term, first = self._billed(
			"can2@example.com", "TST C110", "TST-CAN-2", monthly_discount=800, cap=24000
		)
		second_term = make_term("TST-CAN-2B", status="Open")
		self._register(enrollment, second_term, "TST C111")
		fees.bill_enrollment_for_term(enrollment.name, second_term.name)
		self.assertEqual(self._used(enrollment), 3200)

		self._cancel(first)
		self.assertEqual(self._used(enrollment), 1600)

		first.reload()
		first.remarks = "Billed in error"
		first.save(ignore_permissions=True)
		self.assertEqual(self._used(enrollment), 1600)

	def test_it_never_goes_below_zero(self):
		enrollment, _term, invoice = self._billed(
			"can3@example.com", "TST C120", "TST-CAN-3", monthly_discount=800, cap=24000
		)
		frappe.db.set_value(
			"Program Enrollment", enrollment.name, "scholarship_used_to_date", 500, update_modified=False
		)

		self._cancel(invoice)

		self.assertEqual(self._used(enrollment), 0)

	def test_an_invoice_with_no_discount_returns_nothing(self):
		enrollment, _term, invoice = self._billed("can4@example.com", "TST C130", "TST-CAN-4")

		self._cancel(invoice)

		self.assertEqual(self._used(enrollment), 0)

	def test_the_cancelled_term_is_billable_again(self):
		"""The job used to see the cancelled invoice and call the term billed."""
		enrollment, term, invoice = self._billed(
			"can5@example.com", "TST C140", "TST-CAN-5", monthly_discount=800, cap=24000
		)
		self._cancel(invoice)

		again = fees.bill_enrollment_for_term(enrollment.name, term.name)

		self.assertIsNotNone(again["invoice"])
		self.assertNotEqual(again["invoice"], invoice.name)
		replacement = frappe.get_doc("Fee Invoice", again["invoice"])
		self.assertEqual(replacement.discount_amount, 1600)
		self.assertEqual(self._used(enrollment), 1600)

	def test_the_ceiling_does_not_move_to_the_tail(self):
		"""Cancel and re-bill must leave the student at the same total as if
		nothing had happened -- the point of undoing it properly."""
		enrollment, term, invoice = self._billed(
			"can6@example.com", "TST C150", "TST-CAN-6", monthly_discount=800, cap=24000
		)
		before = fees.tuition_billed_to_date(enrollment.name)

		self._cancel(invoice)
		fees.bill_enrollment_for_term(enrollment.name, term.name)

		self.assertEqual(fees.tuition_billed_to_date(enrollment.name), before)

	def test_a_live_invoice_still_blocks_a_second_bill_for_its_term(self):
		enrollment, term, _invoice = self._billed("can7@example.com", "TST C160", "TST-CAN-7")

		again = fees.bill_enrollment_for_term(enrollment.name, term.name)

		self.assertIsNone(again["invoice"])
		self.assertIn("already billed", again["skipped"])

	def test_an_invoice_with_money_on_it_cannot_be_cancelled(self):
		"""Re-raising the term would charge the student twice."""
		enrollment, _term, invoice = self._billed("can8@example.com", "TST C170", "TST-CAN-8")
		make_payment(
			enrollment.student, 500, [{"fee_invoice": invoice.name, "allocated_amount": 500}]
		)
		invoice.reload()

		invoice.status = "Cancelled"
		with self.assertRaises(frappe.ValidationError):
			invoice.save(ignore_permissions=True)

	def test_a_cancelled_invoice_cannot_be_reopened(self):
		"""The job raises the term itself; a revived one would bill it twice."""
		_enrollment, _term, invoice = self._billed("can9@example.com", "TST C180", "TST-CAN-9")
		self._cancel(invoice)

		invoice.reload()
		invoice.status = "Unpaid"
		with self.assertRaises(frappe.ValidationError):
			invoice.save(ignore_permissions=True)

	def test_cancelling_another_kind_of_fee_leaves_the_scholarship_alone(self):
		"""The registration fee is not discountable and spent none of it."""
		_student, enrollment, registration = self._registration("can10@example.com", "TST C190")
		frappe.db.set_value(
			"Program Enrollment",
			enrollment.name,
			{"scholarship_total_cap": 24000, "scholarship_used_to_date": 900},
			update_modified=False,
		)
		registration.reload()
		invoice = frappe.get_doc("Fee Invoice", registration.registration_fee_invoice)

		invoice.status = "Cancelled"
		invoice.save(ignore_permissions=True)

		self.assertEqual(self._used(enrollment), 900)

	def test_a_remark_on_a_live_invoice_returns_nothing(self):
		enrollment, _term, invoice = self._billed(
			"can11@example.com", "TST C200", "TST-CAN-11", monthly_discount=800, cap=24000
		)

		invoice.remarks = "Chased by phone"
		invoice.save(ignore_permissions=True)

		self.assertEqual(self._used(enrollment), 1600)


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

	def _rows(self, student):
		from sibbcs.finance.report.student_fee_ledger.student_fee_ledger import execute

		_columns, rows = execute({"student": student.name})
		return rows[:-1], rows[-1]

	def test_a_waived_invoice_is_not_left_in_the_balance(self):
		"""It kept its full net on the record, so the balance carried money the
		college chose not to collect."""
		student = make_student(email="ledger2@example.com")
		make_invoice(student.name, gross_amount=350, due_date="2026-01-01", status="Waived")

		rows, closing = self._rows(student)

		self.assertEqual([r["entry_type"] for r in rows], ["Invoice", "Waived"])
		self.assertEqual(rows[1]["credit"], 350)
		self.assertEqual(closing["balance"], 0)
		self.assertEqual(closing["status"], "Settled")

	def test_only_the_unpaid_rest_of_a_part_paid_invoice_is_waived(self):
		student = make_student(email="ledger3@example.com")
		invoice = make_invoice(student.name, gross_amount=3000, due_date="2026-01-01")
		make_payment(
			student.name, 1000, [{"fee_invoice": invoice.name, "allocated_amount": 1000}],
			received_on="2026-01-05",
		)
		frappe.db.set_value("Fee Invoice", invoice.name, "status", "Waived")

		rows, closing = self._rows(student)

		waived = next(r for r in rows if r["entry_type"] == "Waived")
		self.assertEqual(waived["credit"], 2000)
		self.assertEqual(closing["balance"], 0)

	def test_a_waiver_does_not_hide_what_is_still_owed(self):
		student = make_student(email="ledger4@example.com")
		make_invoice(student.name, gross_amount=350, due_date="2026-01-01", status="Waived")
		make_invoice(student.name, gross_amount=700, due_date="2026-02-01")

		_rows, closing = self._rows(student)

		self.assertEqual(closing["balance"], 700)
		self.assertEqual(closing["status"], "Outstanding")

	def test_the_waiver_sits_directly_under_its_invoice(self):
		student = make_student(email="ledger5@example.com")
		make_invoice(student.name, gross_amount=350, due_date="2026-01-01", status="Waived")
		make_invoice(student.name, gross_amount=700, due_date="2026-01-01")

		rows, _closing = self._rows(student)

		kinds = [(r["entry_type"], r["reference"]) for r in rows]
		first = rows[0]["reference"]
		self.assertEqual(kinds[0], ("Invoice", first))
		self.assertEqual(kinds[1], ("Waived", first))

	def test_the_staff_ledger_and_the_student_statement_agree(self):
		"""One question, asked from both sides: what does this student owe? A
		student told one figure and the office another is the worst outcome."""
		from sibbcs.api import student_fees

		student = make_student(email="ledger6@example.com")
		part = make_invoice(student.name, gross_amount=3000, due_date="2026-01-01")
		make_payment(
			student.name, 1000, [{"fee_invoice": part.name, "allocated_amount": 1000}],
			received_on="2026-01-05",
		)
		make_invoice(student.name, gross_amount=350, due_date="2026-02-01", status="Waived")
		make_invoice(student.name, gross_amount=350, due_date="2026-02-02", status="Waived")
		make_payment(
			student.name, 600, [{"fee_invoice": part.name, "allocated_amount": 600}],
			received_on="2026-01-09",
		)
		make_invoice(student.name, gross_amount=500, due_date="2026-03-01")

		_rows, closing = self._rows(student)
		invoices = student_fees._invoices(student.name)
		payments = student_fees._payments(student.name, invoices)
		statement = student_fees._statement(invoices, payments)

		self.assertEqual(statement["balance"], closing["balance"])
		self.assertEqual(statement["charges"], closing["charge"])
		self.assertEqual(statement["credits"], closing["credit"])

	def test_ledger_requires_a_student(self):
		from sibbcs.finance.report.student_fee_ledger.student_fee_ledger import execute

		with self.assertRaises(frappe.ValidationError):
			execute({})


class TestGatewayBoundary(FrappeTestCase):
	"""Nothing outside finance/<provider>.py should name a vendor."""

	def test_default_provider_is_resolvable(self):
		from sibbcs.finance import gateway

		self.assertIn(gateway.active_provider(), gateway.PROVIDERS)

	def test_provider_module_has_the_required_interface(self):
		from sibbcs.finance import gateway

		provider = gateway.get_provider()
		for attribute in ("is_configured", "create_payment_link", "PROVIDER_NAME"):
			self.assertTrue(hasattr(provider, attribute), attribute)

	def test_unknown_provider_is_refused(self):
		from sibbcs.finance import gateway

		with self.assertRaises(frappe.ValidationError):
			gateway.get_provider("not-a-gateway")

	def test_public_url_never_carries_the_dev_port(self):
		"""frappe.utils.get_url() appends :8000 outside production mode, which
		would hand the gateway an address the outside world cannot reach."""
		from sibbcs.finance import gateway

		self.assertNotIn(":8000", gateway.public_url("/x"))
		self.assertNotIn(":8000", gateway.webhook_url())

	def test_webhook_url_points_at_the_active_provider(self):
		from sibbcs.finance import gateway

		self.assertIn(gateway.active_provider(), gateway.webhook_url())
		self.assertTrue(gateway.webhook_url().endswith(".webhook"))

	def test_schema_carries_no_vendor_name(self):
		"""The gateway can change; the columns should not have to."""
		for doctype, field in (
			("Fee Invoice", "payment_link"),
			("Fee Invoice", "payment_reference"),
			("Payment Entry", "gateway_payment_id"),
		):
			self.assertTrue(frappe.get_meta(doctype).get_field(field), f"{doctype}.{field}")

		for doctype in ("Fee Invoice", "Payment Entry"):
			for df in frappe.get_meta(doctype).fields:
				self.assertNotIn("razorpay", df.fieldname, f"{doctype}.{df.fieldname}")


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


class TestApplicationFeeSettledByHand(FrappeTestCase):
	"""`settle_application_fee` -- the only way to take an application fee
	without a gateway, and the gateway is not configured.
	"""

	def _application(self):
		from sibbcs.admissions.doctype.admission_application.test_admission_application import (
			make_application,
		)

		app = make_application(
			full_name="Fee Payer",
			email=f"{frappe.generate_hash(length=10)}@example.invalid",
		)
		invoice = fees.raise_application_fee(app.name)
		self.assertIsNotNone(invoice, "no Application Fee type seeded")
		return app, invoice

	def test_paying_it_places_the_application(self):
		app, invoice = self._application()
		self.assertEqual(app.workflow_state, "Draft")

		state = fees.settle_application_fee(app.name, mode="UPI", reference_no="UTR-1")

		self.assertEqual(state, "In Review")
		app.reload()
		self.assertTrue(app.application_fee_paid)
		self.assertEqual(app.workflow_state, "In Review")

		invoice.reload()
		self.assertEqual(invoice.status, "Paid")
		self.assertEqual(flt(invoice.outstanding_amount), 0)
		self.assertEqual(flt(invoice.paid_amount), 350)
		self.assertEqual(invoice.payment_reference, "UTR-1")

	def test_the_payment_survives_the_next_save(self):
		"""The bug this field exists for.

		`paid_amount` is derived from the allocations, and an application fee
		has none -- so writing it straight through left a settlement that the
		next save of the invoice quietly reversed.
		"""
		app, invoice = self._application()
		fees.settle_application_fee(app.name, mode="Cash")

		invoice.reload()
		invoice.remarks = (invoice.remarks or "") + " · receipt filed"
		invoice.save(ignore_permissions=True)

		invoice.reload()
		self.assertEqual(invoice.status, "Paid")
		self.assertEqual(flt(invoice.paid_amount), 350)
		self.assertEqual(flt(invoice.outstanding_amount), 0)

	def test_the_gateway_is_not_credited_for_money_taken_by_hand(self):
		app, invoice = self._application()
		fees.settle_application_fee(app.name, mode="Bank Transfer")
		invoice.reload()
		self.assertFalse(invoice.get("payment_provider"))

	def test_who_took_it_and_how_is_on_the_record(self):
		app, invoice = self._application()
		fees.settle_application_fee(
			app.name, mode="Cheque", reference_no="CHQ-77", remarks="counter"
		)
		invoice.reload()
		self.assertIn("Cheque", invoice.remarks)
		self.assertIn("CHQ-77", invoice.remarks)
		self.assertIn("counter", invoice.remarks)
		self.assertIn(frappe.session.user, invoice.remarks)
		self.assertIn("Application fee for", invoice.remarks)  # the original is kept

	def test_part_of_the_fee_leaves_it_in_draft(self):
		app, invoice = self._application()
		state = fees.settle_application_fee(app.name, amount=100, mode="Cash")

		self.assertEqual(state, "Draft")
		invoice.reload()
		self.assertEqual(invoice.status, "Partly Paid")
		self.assertEqual(flt(invoice.outstanding_amount), 250)
		app.reload()
		self.assertFalse(app.application_fee_paid)

	def test_the_rest_of_a_part_payment_completes_it(self):
		app, invoice = self._application()
		fees.settle_application_fee(app.name, amount=100, mode="Cash")
		state = fees.settle_application_fee(app.name, amount=250, mode="UPI")

		self.assertEqual(state, "In Review")
		invoice.reload()
		self.assertEqual(invoice.status, "Paid")
		self.assertEqual(flt(invoice.paid_amount), 350)

	def test_more_than_is_owed_is_refused(self):
		app, _invoice = self._application()
		with self.assertRaises(frappe.ValidationError):
			fees.settle_application_fee(app.name, amount=500, mode="Cash")

	def test_nothing_is_refused(self):
		app, _invoice = self._application()
		with self.assertRaises(frappe.ValidationError):
			fees.settle_application_fee(app.name, amount=0, mode="Cash")

	def test_the_gateways_own_mode_is_refused(self):
		"""`Online` is what the webhook writes for a row a gateway signed for."""
		app, _invoice = self._application()
		with self.assertRaises(frappe.ValidationError):
			fees.settle_application_fee(app.name, mode="Online")

	def test_running_it_twice_does_not_take_the_fee_twice(self):
		app, invoice = self._application()
		fees.settle_application_fee(app.name, mode="UPI")
		state = fees.settle_application_fee(app.name, mode="UPI")

		self.assertEqual(state, "In Review")
		invoice.reload()
		self.assertEqual(flt(invoice.paid_amount), 350)
		self.assertEqual(flt(invoice.direct_paid_amount), 350)

	def test_an_application_with_no_invoice_says_so(self):
		from sibbcs.admissions.doctype.admission_application.test_admission_application import (
			make_application,
		)

		app = make_application(email=f"{frappe.generate_hash(length=10)}@example.invalid")
		frappe.db.delete("Fee Invoice", {"admission_application": app.name})
		with self.assertRaises(frappe.ValidationError):
			fees.settle_application_fee(app.name, mode="Cash")
