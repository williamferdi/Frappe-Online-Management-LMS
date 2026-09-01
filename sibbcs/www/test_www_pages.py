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
	"documents",
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


class TestPublicShell(FrappeTestCase):
	"""The shell the six guest pages sit in.

	It replaces Frappe's `templates/web.html`, which means it also replaces
	everything that template quietly provided. The CSRF token is the one that
	matters, and it is the one this project has already got wrong once.
	"""

	SHELL = os.path.join(
		os.path.dirname(WWW), "templates", "sibbcs_public.html"
	)

	GUEST_PAGES = [
		"apply",
		"reference",
		"mentor-consent",
		"manual-reading",
		"scholarship",
		"fee-paid",
		"documents",
	]

	def shell(self):
		return open(self.SHELL, encoding="utf-8").read()

	def test_the_shell_exists(self):
		self.assertTrue(os.path.exists(self.SHELL))

	def test_every_guest_page_uses_it(self):
		for page in self.GUEST_PAGES:
			with self.subTest(page=page):
				markup = open(os.path.join(WWW, page + ".html"), encoding="utf-8").read()
				self.assertIn(
					'{% extends "templates/sibbcs_public.html" %}',
					markup,
					f"{page}.html is not on the guest shell",
				)

	def test_the_shell_carries_the_csrf_marker(self):
		"""`base_template_page.add_csrf_token` injects the token by replacing
		this comment. The marker lives in Frappe's base.html, which this shell
		deliberately does not extend -- so without repeating it the token is
		never injected, every form still works for guests (whose session has no
		token to check), and a signed-in user gets "Invalid Request"."""
		self.assertIn("<!-- csrf_token -->", self.shell())

	def test_the_shell_defines_frappe_before_the_marker(self):
		"""The injected line assigns to `frappe`, which exists on a Desk page
		and does not exist here."""
		markup = self.shell()
		shim = markup.index("window.frappe = window.frappe || {}")
		marker = markup.index("<!-- csrf_token -->")
		self.assertLess(shim, marker, "the shim must come before the injection point")

	def test_the_shell_loads_the_guest_stylesheet(self):
		self.assertIn("/assets/sibbcs/css/public.css", self.shell())
		self.assertTrue(
			os.path.exists(
				os.path.join(os.path.dirname(WWW), "public", "css", "public.css")
			)
		)

	def test_a_token_link_is_kept_out_of_search_engines(self):
		"""These addresses are personal to one referee or applicant."""
		self.assertIn("noindex", self.shell())

	def test_the_pages_still_find_the_csrf_helper(self):
		"""Each form reads the token through the one shared include."""
		for page in self.GUEST_PAGES:
			with self.subTest(page=page):
				markup = open(os.path.join(WWW, page + ".html"), encoding="utf-8").read()
				if "sibbcsCsrfToken" in markup:
					self.assertIn("templates/includes/csrf.html", markup)


class TestTheDocumentPage(FrappeTestCase):
	"""The page a candidate is sent when documents are wanted again.

	Its credential is the upload_token already on the application -- the same
	one `uploads.upload_document` has always checked -- so the page adds a way
	in, not a new power.
	"""

	def an_application(self):
		from sibbcs.admissions.doctype.admission_application.test_admission_application import (
			make_application,
		)

		tag = frappe.generate_hash(length=6)
		return make_application(
			full_name=f"Upload {tag}",
			email=f"upload.{tag}@example.invalid",
			documents=[
				{
					"document_type": "SSC/10th Mark Sheet",
					"file": "/files/ssc.pdf",
					"remarks": "The scan is cut off",
				}
			],
		)

	def context_for(self, **form):
		from sibbcs.www import documents as page

		frappe.form_dict.update(form)
		try:
			return page.get_context(frappe._dict())
		finally:
			for key in form:
				frappe.form_dict.pop(key, None)

	def test_a_link_with_no_token_opens_nothing(self):
		doc = self.an_application()
		self.assertFalse(self.context_for(application=doc.name).valid)

	def test_a_wrong_token_opens_nothing(self):
		doc = self.an_application()
		context = self.context_for(application=doc.name, token="x" * 40)

		self.assertFalse(context.valid)
		self.assertIn("not valid", context.error)

	def test_the_right_token_shows_that_candidate_their_own_documents(self):
		doc = self.an_application()
		context = self.context_for(application=doc.name, token=doc.upload_token)

		self.assertTrue(context.valid)
		self.assertEqual(context.applicant_name, doc.full_name)

		by_type = {row["document_type"]: row for row in context.documents}
		self.assertTrue(by_type["SSC/10th Mark Sheet"]["uploaded"])
		self.assertFalse(by_type["Photo"]["uploaded"])
		self.assertTrue(by_type["Photo"]["required"])

	def test_it_tells_them_why_a_document_was_not_accepted(self):
		"""The remark is the reason, and it is no use to anybody unread."""
		doc = self.an_application()
		context = self.context_for(application=doc.name, token=doc.upload_token)

		row = next(
			r for r in context.documents if r["document_type"] == "SSC/10th Mark Sheet"
		)
		self.assertEqual(row["remarks"], "The scan is cut off")

	def test_an_application_past_uploads_is_refused(self):
		doc = self.an_application()
		frappe.db.set_value(
			"Admission Application", doc.name, "workflow_state", "Admitted"
		)

		self.assertFalse(
			self.context_for(application=doc.name, token=doc.upload_token).valid
		)


class TestTheApplyForm(FrappeTestCase):
	"""The public form's markup, where a silent change would cost applications."""

	def page(self):
		return open(os.path.join(WWW, "apply.html"), encoding="utf-8").read()

	def test_each_section_is_a_numbered_heading(self):
		"""Seven sections, seven bands. A form this long is unreadable when the
		headings look like the labels."""
		markup = self.page()
		self.assertEqual(markup.count('class="sib-legend"'), 7)
		self.assertEqual(markup.count('class="sib-legend-bar"'), 7)
		for number in range(1, 8):
			self.assertIn(f'<span class="step">{number}</span>', markup)

	def test_the_two_references_are_named_not_numbered(self):
		markup = self.page()
		self.assertIn("Spiritual &amp; Ministerial Reference", markup)
		self.assertIn("Academic &amp; Professional Reference", markup)
		self.assertNotIn("Referee 1", markup)
		self.assertNotIn("Referee 2", markup)

	def test_the_named_references_still_carry_the_types_the_system_stores(self):
		"""The heading is for the applicant; `referee_type` is what the
		checklist, the reference form and the console all key on."""
		markup = self.page()
		self.assertIn('id="referee1_type" value="Pastor-Mentor"', markup)
		self.assertIn('id="referee2_type" value="Professor-Employer"', markup)

	def test_every_document_input_is_a_drop_zone(self):
		markup = self.page()
		self.assertEqual(markup.count('class="dropzone"'), 7)
		self.assertIn("templates/includes/dropzone.html", markup)

	def test_a_drop_zone_keeps_the_real_file_input(self):
		"""The drop handler sets `input.files` and fires `change`, so the upload
		code is untouched -- and a browser that cannot drag still has a picker."""
		markup = self.page()
		self.assertEqual(markup.count('type="file"'), 7)
		self.assertEqual(markup.count("doc-input"), 8)  # seven inputs, one selector

	def test_a_phone_number_is_a_country_code_and_digits(self):
		markup = self.page()
		for prefix in ("mobile", "whatsapp", "mentor_mobile"):
			with self.subTest(field=prefix):
				self.assertIn(f'id="{prefix}_code"', markup)
				self.assertIn(f'id="{prefix}_number"', markup)
		self.assertIn('list="country-codes"', markup)
		self.assertIn('<datalist id="country-codes">', markup)

	def test_the_old_single_phone_boxes_are_gone(self):
		"""They would still post, and post something the new code never built."""
		markup = self.page()
		self.assertNotIn('id="mobile"', markup)
		self.assertNotIn('id="whatsapp"', markup)
		self.assertNotIn('id="mentor_mobile"', markup)

	def test_the_submitted_payload_still_uses_the_field_names(self):
		"""Two boxes on the page, one field on the DocType."""
		markup = self.page()
		self.assertIn("payload.mobile = phone('mobile')", markup)
		self.assertIn("payload.whatsapp = phone('whatsapp')", markup)
		self.assertIn("payload.mentor_mobile = phone('mentor_mobile')", markup)


class TestTheGuestStylesheetIsVersioned(FrappeTestCase):
	"""A stylesheet nobody can see the change to might as well not have changed.

	`/assets/...` is served with a long cache life and a name that never
	changes, so a returning applicant kept the CSS they downloaded last time.
	Found the honest way: a restyled form came back looking exactly as before.
	"""

	def test_the_shell_asks_for_a_version(self):
		shell = open(
			os.path.join(os.path.dirname(WWW), "templates", "sibbcs_public.html"),
			encoding="utf-8",
		).read()
		self.assertIn("public.css?v={{ asset_version }}", shell)

	def test_the_hook_supplies_one_that_changes_with_the_build(self):
		from sibbcs.setup.website import add_asset_version

		context = frappe._dict()
		add_asset_version(context)
		self.assertTrue(context.asset_version)

	def test_the_hook_is_registered(self):
		self.assertIn(
			"sibbcs.setup.website.add_asset_version",
			frappe.get_hooks("update_website_context"),
		)
