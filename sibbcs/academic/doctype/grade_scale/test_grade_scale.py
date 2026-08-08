# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

# A plausible scale used only by these tests. The live scale is an open
# decision (#3 in the architecture doc) and is deliberately not seeded.
BANDS = [
	{"grade": "A", "min_pct": 90, "max_pct": 100, "grade_points": 4.0, "is_pass": 1},
	{"grade": "B", "min_pct": 80, "max_pct": 89.99, "grade_points": 3.0, "is_pass": 1},
	{"grade": "C", "min_pct": 70, "max_pct": 79.99, "grade_points": 2.0, "is_pass": 1},
	{"grade": "D", "min_pct": 60, "max_pct": 69.99, "grade_points": 1.0, "is_pass": 1},
	{"grade": "F", "min_pct": 0, "max_pct": 59.99, "grade_points": 0.0, "is_pass": 0},
]


def make_scale(name, bands=None, **kw):
	if frappe.db.exists("Grade Scale", name):
		frappe.delete_doc("Grade Scale", name, force=1, ignore_permissions=True)

	defaults = {
		"doctype": "Grade Scale",
		"scale_name": name,
		"pass_percentage": 60,
		"grade_rows": bands if bands is not None else BANDS,
	}
	defaults.update(kw)
	return frappe.get_doc(defaults).insert(ignore_permissions=True)


class TestGradeScale(FrappeTestCase):
	def test_scale_with_no_bands_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			make_scale("TST Empty", bands=[])

	def test_min_above_max_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			make_scale(
				"TST Inverted",
				bands=[{"grade": "A", "min_pct": 90, "max_pct": 50, "is_pass": 1}],
			)

	def test_out_of_range_percentage_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			make_scale(
				"TST OutOfRange",
				bands=[{"grade": "A", "min_pct": 90, "max_pct": 140, "is_pass": 1}],
			)

	def test_overlapping_bands_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			make_scale(
				"TST Overlap",
				bands=[
					{"grade": "A", "min_pct": 80, "max_pct": 100, "is_pass": 1},
					{"grade": "B", "min_pct": 70, "max_pct": 85, "is_pass": 1},
				],
			)

	def test_duplicate_grade_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			make_scale(
				"TST DupGrade",
				bands=[
					{"grade": "A", "min_pct": 80, "max_pct": 100, "is_pass": 1},
					{"grade": "A", "min_pct": 60, "max_pct": 79, "is_pass": 1},
				],
			)

	def test_grade_for_maps_percentage_to_band(self):
		scale = make_scale("TST Standard")
		self.assertEqual(scale.grade_for(95)["grade"], "A")
		self.assertEqual(scale.grade_for(60)["grade"], "D")
		self.assertEqual(scale.grade_for(59)["grade"], "F")

	def test_grade_for_reports_pass_state(self):
		scale = make_scale("TST Pass")
		self.assertTrue(scale.grade_for(60)["passed"])
		self.assertFalse(scale.grade_for(59.5)["passed"])

	def test_grade_for_returns_points(self):
		scale = make_scale("TST Points")
		self.assertEqual(scale.grade_for(95)["grade_points"], 4.0)

	def test_only_one_scale_stays_default(self):
		first = make_scale("TST Default One", is_default=1)
		second = make_scale("TST Default Two", is_default=1)

		self.assertEqual(frappe.db.get_value("Grade Scale", first.name, "is_default"), 0)
		self.assertEqual(frappe.db.get_value("Grade Scale", second.name, "is_default"), 1)

	def test_pass_mark_is_sixty(self):
		"""60% is confirmed in the architecture doc; guard against drift."""
		scale = make_scale("TST Sixty")
		self.assertEqual(scale.pass_percentage, 60)
		self.assertTrue(scale.grade_for(60)["passed"])
