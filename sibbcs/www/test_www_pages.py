# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""Every portal page must find its controller.

frappe/website/page_renderers/template_page.py `set_pymodule()` locates a page's
controller by taking the template basename and replacing `-` with `_`. So
`my-courses.html` is served by `my_courses.py`, never `my-courses.py`.

Get that wrong and the page still renders -- Frappe just serves the template
with an empty context. Jinja's DebugUndefined then prints `{{ student_name }}`
literally while `{{ credits_earned or 0 }}` still resolves to 0, which is a
genuinely confusing way to fail. `my-courses.py` shipped exactly like that.
"""

import os

import frappe
from frappe.tests.utils import FrappeTestCase

WWW = os.path.dirname(os.path.abspath(__file__))

# Pages whose context is built in Python. A template with no controller is
# legitimate (static content), so only these are required to resolve.
PAGES_WITH_CONTROLLERS = [
	"reference",
	"scholarship",
	"mentor-consent",
	"manual-reading",
	"my-courses",
	"apply",
	"fee-paid",
]


def controller_for(page):
	"""The filename Frappe will actually look for."""
	return os.path.join(WWW, page.replace("-", "_") + ".py")


class TestWwwPages(FrappeTestCase):
	def test_templates_exist(self):
		for page in PAGES_WITH_CONTROLLERS:
			self.assertTrue(
				os.path.exists(os.path.join(WWW, page + ".html")),
				f"{page}.html is missing",
			)

	def test_controllers_use_underscores(self):
		"""The bug: a hyphenated controller filename is silently never loaded."""
		for page in PAGES_WITH_CONTROLLERS:
			expected = controller_for(page)
			self.assertTrue(
				os.path.exists(expected),
				f"{page}.html has no controller at {os.path.basename(expected)} "
				f"-- Frappe replaces '-' with '_' when resolving it",
			)

	def test_no_hyphenated_controller_files_remain(self):
		for filename in os.listdir(WWW):
			if filename.endswith(".py"):
				self.assertNotIn(
					"-", filename, f"{filename} can never be imported by Frappe"
				)

	def test_controllers_expose_get_context(self):
		for page in PAGES_WITH_CONTROLLERS:
			module_name = "sibbcs.www." + page.replace("-", "_")
			module = frappe.get_module(module_name)
			self.assertTrue(
				hasattr(module, "get_context"),
				f"{module_name} has no get_context()",
			)

	def test_my_courses_context_has_its_keys(self):
		"""Guards the exact symptom: template variables missing from context."""
		from sibbcs.www.my_courses import get_context

		context = frappe._dict()
		get_context(context)

		# With no Student linked to Administrator, the page must take the
		# no_enrollment branch -- and say so explicitly rather than leaving
		# every variable undefined.
		self.assertIn("no_enrollment", context)
		self.assertTrue(context.no_enrollment)


class TestCsrfHeader(FrappeTestCase):
	"""Every form must read the CSRF token the way Frappe actually sets it.

	Frappe injects `frappe.csrf_token` into a rendered web page; it never sets
	`window.csrf_token`, which only exists inside the Desk bundle. A Guest
	session carries no CSRF token at all and validate_csrf_token() returns
	early when there is none -- so a form reading the wrong name works
	perfectly for the outsiders it was built for and fails with "Invalid
	Request" the first time a signed-in user submits it. That is exactly how
	the manual acknowledgement broke: the candidate has to sign in to take the
	orientation course, so they are never a Guest.
	"""

	def _posting_pages(self):
		pages = []
		for name in os.listdir(WWW):
			if not name.endswith(".html"):
				continue
			with open(os.path.join(WWW, name), encoding="utf-8") as handle:
				body = handle.read()
			if "X-Frappe-CSRF-Token" in body:
				pages.append((name, body))
		return pages

	def test_there_are_pages_that_post(self):
		self.assertTrue(self._posting_pages(), "no page posts; this suite would pass vacuously")

	def test_no_page_reads_window_csrf_token(self):
		for name, body in self._posting_pages():
			self.assertNotIn(
				"window.csrf_token ||",
				body,
				f"{name} reads window.csrf_token, which is undefined on a web page",
			)

	def test_every_posting_page_uses_the_shared_helper(self):
		for name, body in self._posting_pages():
			self.assertIn(
				"sibbcsCsrfToken()",
				body,
				f"{name} sends a CSRF header without going through sibbcsCsrfToken()",
			)
			self.assertIn(
				'include "templates/includes/csrf.html"',
				body,
				f"{name} calls sibbcsCsrfToken() but never includes its definition",
			)

	def test_the_helper_prefers_the_name_frappe_sets(self):
		path = os.path.join(os.path.dirname(WWW), "templates", "includes", "csrf.html")
		self.assertTrue(os.path.exists(path), "the shared csrf include is missing")
		with open(path, encoding="utf-8") as handle:
			body = handle.read()
		self.assertIn("frappe.csrf_token", body)
