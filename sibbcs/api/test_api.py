# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""The endpoints the React front end boots and draws itself from."""

import json
import os

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.api import session as session_api
from sibbcs.api import student as student_api

APP = frappe.get_app_path("sibbcs")
PORTAL_HTML = os.path.join(APP, "www", "_portal.html")
BUNDLE_DIR = os.path.join(APP, "public", "portal")


def make_user(email, roles):
	if frappe.db.exists("User", email):
		frappe.delete_doc("User", email, force=True, ignore_permissions=True)
	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": email.split("@")[0],
			"send_welcome_email": 0,
			"roles": [{"role": role} for role in roles],
		}
	)
	user.insert(ignore_permissions=True)
	return user


class TestSessionPayload(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_a_guest_is_neither_staff_nor_student(self):
		frappe.set_user("Guest")
		payload = session_api.session_payload()
		self.assertEqual(payload["user"], "Guest")
		self.assertFalse(payload["is_staff"])
		self.assertFalse(payload["is_student"])
		self.assertEqual(payload["student"], "")

	def test_every_key_the_front_end_reads_is_present(self):
		"""The page writes these straight onto window; a missing key is an
		undefined global at first paint, not a caught error."""
		payload = session_api.session_payload()
		for key in (
			"user",
			"full_name",
			"user_image",
			"roles",
			"is_staff",
			"is_student",
			"student",
			"enrollment",
			"site_name",
			"app_version",
		):
			self.assertIn(key, payload)

	def test_the_payload_survives_json(self):
		"""Jinja renders each value with `| tojson`. A date or a frappe._dict
		that json cannot serialise breaks the whole page, not one field."""
		json.dumps(session_api.session_payload())

	def test_a_registrar_is_staff(self):
		make_user("api.registrar@example.com", ["Registrar"])
		frappe.set_user("api.registrar@example.com")
		payload = session_api.session_payload()
		self.assertTrue(payload["is_staff"])
		self.assertFalse(payload["is_student"])

	def test_a_student_is_not_staff(self):
		make_user("api.student@example.com", ["Student"])
		frappe.set_user("api.student@example.com")
		payload = session_api.session_payload()
		self.assertFalse(payload["is_staff"])
		self.assertTrue(payload["is_student"])

	def test_lms_student_alone_is_not_staff(self):
		"""Applicants get LMS Student for the entrance exam. That must not
		open the staff console's navigation."""
		make_user("api.applicant@example.com", ["LMS Student"])
		frappe.set_user("api.applicant@example.com")
		self.assertFalse(session_api.session_payload()["is_staff"])

	def test_dean_is_recognised(self):
		"""Dean approves promotions but is absent from setup/permissions.py, so
		it is easy to leave out of the console's role list."""
		self.assertIn("Dean", session_api.STAFF_ROLES)


class TestMyCourses(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_a_guest_is_refused(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			student_api.my_courses()

	def test_a_signed_in_user_with_no_enrollment_gets_an_empty_answer(self):
		"""An admitted applicant whose enrolment is not created yet is an
		ordinary state. The portal explains it; it is not an error."""
		make_user("api.noenrol@example.com", ["Student"])
		frappe.set_user("api.noenrol@example.com")

		result = student_api.my_courses()
		self.assertIsNone(result["enrollment"])
		self.assertEqual(result["registrations"], [])

	def test_it_takes_no_argument_naming_a_student(self):
		"""There must be no parameter through which one student could ask for
		another's record."""
		import inspect

		signature = inspect.signature(student_api.my_courses)
		self.assertEqual(list(signature.parameters), [])

	def test_it_is_whitelisted_but_not_for_guests(self):
		"""allow_guest=True would let the endpoint run before any session
		exists. Frappe records those in frappe.guest_methods."""
		self.assertIn(student_api.my_courses, frappe.whitelisted)
		self.assertNotIn(student_api.my_courses, frappe.guest_methods)


class TestPortalPage(FrappeTestCase):
	def test_the_controller_matches_the_template_name(self):
		"""Frappe finds a page's controller by swapping '-' for '_' in the
		template basename. `_portal.html` needs `_portal.py`."""
		self.assertTrue(os.path.exists(os.path.join(APP, "www", "_portal.py")))
		self.assertTrue(os.path.exists(PORTAL_HTML))

	def test_the_page_carries_the_boot_loop(self):
		"""Without it the app has no session, no CSRF token and no roles, and
		every write is rejected. The loop is appended by the Vite build, so a
		stale or hand-edited _portal.html loses it silently."""
		html = open(PORTAL_HTML, encoding="utf-8").read()
		self.assertIn("{% for key in boot %}", html)
		self.assertIn("boot[key] | tojson", html)

	def test_the_page_loads_the_built_bundle(self):
		html = open(PORTAL_HTML, encoding="utf-8").read()
		self.assertIn("/assets/sibbcs/portal/assets/", html)

	def test_the_bundle_the_page_names_is_on_disk(self):
		"""Editing the source changes nothing until `yarn build` runs, and a
		half-finished build leaves the page pointing at a file that is gone."""
		import re

		html = open(PORTAL_HTML, encoding="utf-8").read()
		referenced = re.findall(r"/assets/sibbcs/portal/(assets/[\w.-]+\.(?:js|css))", html)
		self.assertTrue(referenced, "the page names no bundle at all")
		for asset in referenced:
			self.assertTrue(
				os.path.exists(os.path.join(BUNDLE_DIR, asset)),
				f"{asset} is referenced by _portal.html but is not built",
			)

	def test_the_boot_context_includes_a_csrf_token(self):
		from sibbcs.www import _portal

		boot = _portal.get_boot()
		self.assertTrue(boot["csrf_token"])
		self.assertIn("roles", boot)

	def test_the_routes_reach_this_page(self):
		"""Both trees are one page; React Router decides the rest. Without the
		<path:app_path> rules a refresh on a deep link 404s."""
		rules = frappe.get_hooks("website_route_rules")
		routes = {rule["from_route"]: rule["to_route"] for rule in rules}

		for route in (
			"/portal",
			"/portal/<path:app_path>",
			"/staff",
			"/staff/<path:app_path>",
		):
			self.assertEqual(routes.get(route), "_portal", f"{route} is not routed")

	def test_the_staff_tree_avoids_werkzeug_s_console_path(self):
		"""`bench start` wraps the app in Werkzeug's debug middleware, which
		reserves /console for its own interactive console and answers 400 there
		before Frappe sees the request -- while /console/anything worked, which
		made it look like a routing bug of ours."""
		routes = {rule["from_route"] for rule in frappe.get_hooks("website_route_rules")}
		self.assertNotIn("/console", routes)
