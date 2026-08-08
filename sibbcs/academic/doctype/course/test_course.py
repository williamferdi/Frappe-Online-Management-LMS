# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


def make_course(code, **kw):
	if frappe.db.exists("Course", code):
		return frappe.get_doc("Course", code)

	defaults = {
		"doctype": "Course",
		"course_code": code,
		"course_title": kw.pop("course_title", f"Test {code}"),
		"credits": kw.pop("credits", 3),
		"level": kw.pop("level", "1"),
		"course_type": kw.pop("course_type", "Core"),
		"department": kw.pop("department", "BIST"),
	}
	defaults.update(kw)
	return frappe.get_doc(defaults).insert(ignore_permissions=True)


class TestCourse(FrappeTestCase):
	def test_course_code_is_upper_cased(self):
		doc = make_course("tst c100")
		self.assertEqual(doc.name, "TST C100")

	def test_credits_must_be_positive(self):
		with self.assertRaises(frappe.ValidationError):
			make_course("TST C101", credits=0)

	def test_course_cannot_be_its_own_prerequisite(self):
		doc = make_course("TST C110")
		doc.append("course_prerequisites", {"prerequisite_course": doc.name})
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_duplicate_prerequisite_rejected(self):
		base = make_course("TST C120")
		other = make_course("TST C121")
		base.append("course_prerequisites", {"prerequisite_course": other.name})
		base.append("course_prerequisites", {"prerequisite_course": other.name})
		with self.assertRaises(frappe.ValidationError):
			base.save(ignore_permissions=True)

	def test_prerequisite_cycle_rejected(self):
		"""A requires B, then B requires A -- the second save must fail."""
		a = make_course("TST C130")
		b = make_course("TST C131")

		a.append("course_prerequisites", {"prerequisite_course": b.name})
		a.save(ignore_permissions=True)

		b.append("course_prerequisites", {"prerequisite_course": a.name})
		with self.assertRaises(frappe.ValidationError):
			b.save(ignore_permissions=True)

	def test_hard_prerequisites_lists_only_hard_ones(self):
		soft = make_course("TST C140")
		hard = make_course("TST C141")
		course = make_course("TST C142")
		course.append("course_prerequisites", {"prerequisite_course": soft.name, "is_hard": 0})
		course.append("course_prerequisites", {"prerequisite_course": hard.name, "is_hard": 1})
		course.save(ignore_permissions=True)

		self.assertEqual(course.hard_prerequisites(), [hard.name])

	def test_unlinked_course_counts_toward_every_program(self):
		"""A course with no program links is universal, not excluded."""
		course = make_course("TST C150")
		self.assertTrue(course.counts_toward("MDIV"))

	def test_linked_course_counts_only_toward_its_programs(self):
		course = make_course("TST C151", programs=[{"program": "MDIV"}])
		self.assertTrue(course.counts_toward("MDIV"))
		self.assertFalse(course.counts_toward("MACS"))
