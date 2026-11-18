# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import cint

from sibbcs.academic.doctype.academic_term.academic_term import derive_term_dates


def make_term(name, **kw):
	if frappe.db.exists("Academic Term", name):
		return frappe.get_doc("Academic Term", name)

	defaults = {
		"doctype": "Academic Term",
		"term_name": name,
		"start_date": "2026-01-01",
		"end_date": "2026-02-28",
		"duration_months": 2,
		"status": "Planned",
	}
	defaults.update(kw)
	return frappe.get_doc(defaults).insert(ignore_permissions=True)


class TestAcademicTerm(FrappeTestCase):
	def test_end_date_must_follow_start_date(self):
		with self.assertRaises(frappe.ValidationError):
			make_term("TST-TERM-A", start_date="2026-03-01", end_date="2026-02-01")

	def test_end_date_equal_to_start_date_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			make_term("TST-TERM-B", start_date="2026-03-01", end_date="2026-03-01")

	def test_duration_must_be_at_least_one_month(self):
		with self.assertRaises(frappe.ValidationError):
			make_term("TST-TERM-C", duration_months=0)

	def test_a_duration_typed_into_a_form_arrives_as_a_string(self):
		"""Which is how this rule threw a 500 instead of refusing politely.

		`validate` runs before the database layer casts anything, so a number
		typed into the console form is still a `str` here. Comparing it with an
		int raised TypeError, and the browser got a bare 500 with no message --
		reported from production on 2026-11-18 while creating 2026-T6. The
		int cases above all passed throughout, which is exactly why nobody saw
		it: the form never sends an int.
		"""
		term = make_term(
			f"TST-TERM-STR-{frappe.generate_hash(length=4)}",
			duration_months="2",
			start_date="2026-01-01",
			end_date="2026-02-28",
		)
		self.assertEqual(cint(term.duration_months), 2)

	def test_a_duration_of_zero_as_a_string_is_still_refused(self):
		""" "0" is a non-empty string, so a bare falsiness check lets it past."""
		with self.assertRaises(frappe.ValidationError):
			make_term(f"TST-TERM-Z-{frappe.generate_hash(length=4)}", duration_months="0")

	def test_a_duration_left_blank_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			make_term(f"TST-TERM-E-{frappe.generate_hash(length=4)}", duration_months="")

	def test_registration_cannot_close_before_it_opens(self):
		with self.assertRaises(frappe.ValidationError):
			make_term(
				"TST-TERM-D",
				registration_opens="2026-01-20",
				registration_closes="2026-01-10",
			)

	def test_registration_cannot_open_after_term_ends(self):
		with self.assertRaises(frappe.ValidationError):
			make_term(
				"TST-TERM-E",
				start_date="2026-01-01",
				end_date="2026-02-28",
				registration_opens="2026-03-15",
				registration_closes="2026-03-20",
			)

	def test_valid_term_saves(self):
		term = make_term(
			"TST-TERM-F",
			start_date="2026-01-01",
			end_date="2026-02-28",
			registration_opens="2025-12-01",
			registration_closes="2026-01-01",
		)
		self.assertEqual(term.name, "TST-TERM-F")

	def test_closed_term_is_never_open_for_registration(self):
		term = make_term("TST-TERM-G", status="Closed")
		self.assertFalse(term.is_registration_open())

	def test_derive_term_dates_spans_the_duration(self):
		dates = derive_term_dates("2026-08-08", duration_months=2)
		self.assertEqual(str(dates["start_date"]), "2026-08-08")
		# start + 2 months, minus a day
		self.assertEqual(str(dates["end_date"]), "2026-10-07")
		self.assertEqual(str(dates["registration_closes"]), "2026-08-08")

	def test_seeded_2026_terms_exist(self):
		"""The five published 2026 intakes should be present after seeding."""
		for term in ("2026-T1", "2026-T2", "2026-T3", "2026-T4", "2026-T5"):
			self.assertTrue(frappe.db.exists("Academic Term", term), f"{term} missing")

	def test_seeded_deadlines_match_the_published_dates(self):
		expected = {
			"2026-T1": "2026-01-24",
			"2026-T2": "2026-03-21",
			"2026-T3": "2026-06-13",
			"2026-T4": "2026-08-08",
			"2026-T5": "2026-10-03",
		}
		for term, deadline in expected.items():
			self.assertEqual(
				str(frappe.db.get_value("Academic Term", term, "application_deadline")),
				deadline,
			)
