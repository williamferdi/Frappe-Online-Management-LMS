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
