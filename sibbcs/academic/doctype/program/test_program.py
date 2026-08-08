# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


def make_program(abbr, **kw):
	if frappe.db.exists("Program", abbr):
		frappe.delete_doc("Program", abbr, force=1, ignore_permissions=True)

	defaults = {
		"doctype": "Program",
		"abbr": abbr,
		"program_name": kw.pop("program_name", f"Test Program {abbr}"),
		"is_active": 1,
	}
	defaults.update(kw)
	return frappe.get_doc(defaults).insert(ignore_permissions=True)


class TestProgram(FrappeTestCase):
	def test_abbreviation_is_upper_cased(self):
		program = make_program("tstp")
		self.assertEqual(program.name, "TSTP")

	def test_max_years_cannot_be_below_min_years(self):
		with self.assertRaises(frappe.ValidationError):
			make_program("TSTP2", min_years=4, max_years=2)

	def test_level_credits_rule_needs_a_level(self):
		with self.assertRaises(frappe.ValidationError):
			make_program(
				"TSTP3",
				program_requirements=[{"rule_type": "Level Credits", "min_credits": 24}],
			)

	def test_level_credits_rule_needs_min_credits(self):
		with self.assertRaises(frappe.ValidationError):
			make_program(
				"TSTP4",
				program_requirements=[{"rule_type": "Level Credits", "level": "1"}],
			)

	def test_internship_hours_rule_needs_min_hours(self):
		with self.assertRaises(frappe.ValidationError):
			make_program(
				"TSTP5",
				program_requirements=[{"rule_type": "Internship Hours"}],
			)

	def test_elective_minimum_accepts_courses_instead_of_credits(self):
		program = make_program(
			"TSTP6",
			program_requirements=[{"rule_type": "Elective Minimum", "min_courses": 3}],
		)
		self.assertEqual(len(program.program_requirements), 1)

	def test_practicum_rule_needs_min_courses(self):
		with self.assertRaises(frappe.ValidationError):
			make_program("TSTP7", program_requirements=[{"rule_type": "Practicum"}])

	def test_complete_requirement_set_saves(self):
		program = make_program(
			"TSTP8",
			min_years=3,
			max_years=8,
			program_requirements=[
				{"rule_type": "Level Credits", "level": "1", "min_credits": 24},
				{"rule_type": "Elective Minimum", "min_credits": 6},
				{"rule_type": "Internship Hours", "min_hours": 360},
				{"rule_type": "Residential", "min_courses": 1},
			],
		)
		self.assertEqual(len(program.program_requirements), 4)


class TestSeededPrograms(FrappeTestCase):
	def test_the_four_programs_exist(self):
		for abbr in ("MDIV", "MACS", "GDCS", "BTH-TAM"):
			self.assertTrue(frappe.db.exists("Program", abbr), f"{abbr} missing")

	def test_ata_fee_applies_to_mdiv_only(self):
		"""Architecture doc §5: ATA Registration is M.Div only."""
		self.assertEqual(frappe.db.get_value("Program", "MDIV", "requires_ata_fee"), 1)
		for abbr in ("MACS", "GDCS", "BTH-TAM"):
			self.assertEqual(
				frappe.db.get_value("Program", abbr, "requires_ata_fee"), 0, f"{abbr}"
			)

	def test_mdiv_has_thirty_two_courses(self):
		self.assertEqual(frappe.db.get_value("Program", "MDIV", "total_courses"), 32)
