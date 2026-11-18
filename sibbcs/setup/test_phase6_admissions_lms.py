# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""Who may mark the entrance exam.

The content converter was tested here too, and went with the bundled `lms` app
in Phase 7 -- there is nothing left to convert. What remains is the rule that
cost something when it was wrong.
"""

import frappe
from frappe.tests.utils import FrappeTestCase


class TestWhoMarksTheExam(FrappeTestCase):
	"""The first run of this put the demo instructors on the real entrance exam
	as teachers, because every active instructor counted. A marker is somebody
	who can sign in."""

	def setUp(self):
		frappe.set_user("Administrator")

	def test_an_instructor_with_no_login_is_not_a_marker(self):
		from sibbcs.academic.doctype.course_offering.test_course_offering import make_instructor
		from sibbcs.setup.phase6_admissions_lms import _markers

		fixture = make_instructor(f"DEMO Fixture {frappe.generate_hash(length=6)}").name
		self.assertNotIn(fixture, _markers())

	def test_an_instructor_with_an_enabled_account_is(self):
		from sibbcs.academic.doctype.course_offering.test_course_offering import make_instructor
		from sibbcs.setup.phase6_admissions_lms import _markers

		email = f"marker.{frappe.generate_hash(length=6)}@example.invalid"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Marker",
				"user_type": "System User",
				"send_welcome_email": 0,
				"roles": [{"role": "Faculty"}],
			}
		).insert(ignore_permissions=True)
		real = make_instructor(f"Real Marker {frappe.generate_hash(length=6)}", user=email).name

		self.assertIn(real, _markers())

	def test_a_disabled_account_stops_being_a_marker(self):
		from sibbcs.academic.doctype.course_offering.test_course_offering import make_instructor
		from sibbcs.setup.phase6_admissions_lms import _markers

		email = f"gone.{frappe.generate_hash(length=6)}@example.invalid"
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Gone",
				"user_type": "System User",
				"send_welcome_email": 0,
				"roles": [{"role": "Faculty"}],
			}
		).insert(ignore_permissions=True)
		leaver = make_instructor(f"Leaver {frappe.generate_hash(length=6)}", user=email).name
		user.enabled = 0
		user.save(ignore_permissions=True)
