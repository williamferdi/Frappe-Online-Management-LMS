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

class TestTheAppShellIsNotCached(FrappeTestCase):
	"""A cached shell keeps loading the previous build.

	The shell names a content-hashed bundle, so a browser that holds on to it
	goes on running yesterday's JavaScript: a change ships, the page does not
	move, and the deploy looks like it did nothing. It is also not a public
	document -- it carries the viewer's name, their roles and a CSRF token.
	"""

	class FakeResponse:
		def __init__(self):
			self.headers = {}

	class FakeRequest:
		def __init__(self, path):
			self.path = path

	def header_for(self, path):
		from sibbcs.setup.website import no_store_on_app_shell

		response = self.FakeResponse()
		no_store_on_app_shell(response=response, request=self.FakeRequest(path))
		return response.headers.get("Cache-Control")

	def test_every_console_and_portal_address_says_no_store(self):
		for path in (
			"/staff",
			"/staff/admissions",
			"/staff/admissions/APP-2026-00014",
			"/portal",
			"/portal/grades",
		):
			with self.subTest(path=path):
				self.assertEqual(self.header_for(path), "no-store, must-revalidate")

	def test_a_guest_page_is_left_alone(self):
		"""Those are ordinary documents and may be cached normally."""
		for path in ("/apply", "/documents", "/reference", "/"):
			with self.subTest(path=path):
				self.assertIsNone(self.header_for(path))

	def test_an_address_that_merely_starts_with_the_word_is_left_alone(self):
		"""/staffroom is not the staff console."""
		self.assertIsNone(self.header_for("/staffroom"))

	def test_it_survives_being_called_with_nothing(self):
		"""after_request hooks run on every request, including ones with no
		response to speak of; this must never be what breaks a page."""
		from sibbcs.setup.website import no_store_on_app_shell

		self.assertIsNone(no_store_on_app_shell())
		self.assertIsNone(no_store_on_app_shell(response=self.FakeResponse()))

	def test_the_hook_is_registered(self):
		self.assertIn(
			"sibbcs.setup.website.no_store_on_app_shell",
			frappe.get_hooks("after_request"),
		)


class TestTheDocumentsPageCanUpload(FrappeTestCase):
	"""The upload handler must find its status element from the row.

	`templates/includes/dropzone.html` wraps the file input in its own
	`div.dropzone`, and `.doc-status` is a *sibling* of that wrapper, not a
	child. So `input.parentElement.querySelector('.doc-status')` returned null,
	the next line threw, and because the throw happened inside a promise the
	page showed nothing: a candidate chose a document and absolutely nothing
	happened, no upload and no error.

	Found on 2026-11-19 by walking a real application through the form. The
	dropzone include was added after this handler was written, which is exactly
	how a working page breaks without anybody touching it.
	"""

	PAGE = os.path.join(WWW, "documents.html")

	def markup(self):
		return open(self.PAGE, encoding="utf-8").read()

	def test_the_status_is_looked_up_from_the_row(self):
		self.assertIn("closest('.doc-row')", self.markup())

	def test_the_inputs_parent_is_never_searched(self):
		"""The specific line that broke it."""
		self.assertNotIn("input.parentElement", self.markup())

	def test_the_status_is_a_sibling_of_the_dropzone_not_a_child(self):
		"""Which is *why* the parent is the wrong place to look.

		If somebody ever moves the status inside the dropzone this test fails,
		and the handler above can go back to being simpler.
		"""
		markup = self.markup()
		dropzone_at = markup.index('<div class="dropzone"')
		status_at = markup.index('<span class="doc-status"')
		closing = markup.index("</div>", markup.index('class="doc-input"'))
		self.assertLess(dropzone_at, status_at, "the dropzone should come first")
		self.assertLess(closing, status_at, "the status must sit outside the dropzone")

	def test_the_page_uses_the_dropzone_include(self):
		self.assertIn("templates/includes/dropzone.html", self.markup())


class TestAnUploadSurvivesAMobileConnection(FrappeTestCase):
	"""Both upload pages post a file as base64 inside a JSON body, which is a
	third larger than the file. nginx closes a stalled request body after sixty
	seconds, and on 19 Nov 2026 APP-2026-00014 lost every document it attached
	-- twice -- to 408s that took three and a half minutes each to arrive, with
	nothing moving on screen in between.

	So: shrink a photograph before sending it, say which file is going up
	before it is attempted, and leave the candidate a way back.
	"""

	INCLUDE = "templates/includes/image_shrink.html"

	def page(self, name):
		return open(os.path.join(WWW, name), encoding="utf-8").read()

	def helper(self):
		return open(
			os.path.join(os.path.dirname(WWW), "templates", "includes", "image_shrink.html"),
			encoding="utf-8",
		).read()

	def test_the_helper_exists(self):
		self.assertIn("sibbcsPrepareUpload", self.helper())

	def test_both_upload_pages_include_it(self):
		for name in ("apply.html", "documents.html"):
			with self.subTest(page=name):
				self.assertIn(self.INCLUDE, self.page(name))

	def test_both_upload_pages_go_through_it(self):
		for name in ("apply.html", "documents.html"):
			with self.subTest(page=name):
				self.assertIn("sibbcsPrepareUpload", self.page(name))

	def test_neither_page_reads_a_file_for_itself_any_more(self):
		"""A second, unshrunk path would reintroduce the bug on whichever page
		kept it, and nothing would say so until an applicant lost a document.
		"""
		for name in ("apply.html", "documents.html"):
			with self.subTest(page=name):
				self.assertNotIn("readAsDataURL", self.page(name))

	def test_a_pdf_is_never_re_encoded(self):
		"""It is already compressed, and a canvas cannot render one."""
		self.assertIn(r"/^image\/(jpeg|png)$/i", self.helper())

	def test_the_original_is_sent_when_shrinking_does_not_help(self):
		helper = self.helper()
		self.assertIn("blob.size >= file.size", helper)
		self.assertIn("return asIs(file)", helper)

	def test_a_re_encoded_file_is_renamed_with_its_new_type(self):
		"""`uploads._validate_file` checks the extension, the declared content
		type and the magic bytes against one another, so a PNG re-encoded as
		JPEG that kept its name is refused outright.
		"""
		helper = self.helper()
		self.assertIn("jpegName", helper)
		self.assertIn("'image/jpeg'", helper)

	def test_the_cameras_rotation_is_applied_before_it_is_discarded(self):
		"""Frappe strips EXIF on save without rotating first, so a mark sheet
		photographed in portrait would otherwise arrive on its side.
		"""
		self.assertIn("imageOrientation: 'from-image'", self.helper())

	def test_the_apply_form_names_the_file_it_is_sending(self):
		markup = self.page("apply.html")
		self.assertIn("'Uploading ' + (i + 1) + ' of ' + chosen.length", markup)

	def test_the_apply_form_leaves_a_way_to_finish_the_job(self):
		markup = self.page("apply.html")
		self.assertIn('id="doc-link"', markup)
		self.assertIn("'/documents?application='", markup)

	def test_the_apply_form_does_not_promise_a_state_that_does_not_exist(self):
		"""`checklist.derive_state` returns In Review. "Submitted" belongs to
		the Frappe workflow in phase2_workflow.py, which is not active on the
		site -- so an applicant told to expect it never sees it, and neither
		does the officer reading the same record.
		"""
		markup = self.page("apply.html")
		self.assertIn("<b>In Review</b>", markup)
		self.assertNotIn("<b>Submitted</b>", markup)


class TestNothingIsSentBeforeItIsSeen(FrappeTestCase):
	"""The college asked for a look at the whole application, documents
	included, before anything is saved -- and for the same on the resubmission
	page, where choosing a file used to send it that instant with no way to
	see what had been chosen or to change your mind.
	"""

	def page(self, name):
		return open(os.path.join(WWW, name), encoding="utf-8").read()

	# --- /apply -----------------------------------------------------------

	def test_the_button_no_longer_submits_the_form(self):
		markup = self.page("apply.html")
		self.assertIn("Review my application", markup)
		self.assertNotIn(">\n        Submit application", markup)

	def test_there_is_a_review_panel_with_a_way_back(self):
		markup = self.page("apply.html")
		self.assertIn('id="apply-review"', markup)
		self.assertIn('id="confirm-btn"', markup)
		self.assertIn('id="back-btn"', markup)

	def test_the_review_says_nothing_has_been_saved_yet(self):
		"""Otherwise it reads as a receipt, and somebody closes the tab."""
		self.assertIn("Nothing has been saved yet", self.page("apply.html"))

	def test_only_the_confirm_button_posts(self):
		"""The form's own submit must not reach the server any more, or the
		review is a screen the application has already gone past.
		"""
		markup = self.page("apply.html")
		submit_handler = markup.split("form.addEventListener('submit'")[1].split(
			"document.getElementById('back-btn')"
		)[0]
		self.assertNotIn("fetch(", submit_handler)
		self.assertIn("buildReview()", submit_handler)

	def test_the_review_is_built_from_the_form_rather_than_a_second_list(self):
		"""A hand-kept list of fields is one more thing to update when a field
		is added, and the failure is silent: the field is collected and saved
		and simply never shown to the person confirming it.
		"""
		markup = self.page("apply.html")
		self.assertIn("form.querySelectorAll('fieldset')", markup)
		self.assertIn("label[for=", markup)

	def test_the_honeypot_is_not_shown_back_to_the_applicant(self):
		markup = self.page("apply.html")
		self.assertIn("control.id === 'website'", markup)

	def test_a_field_left_empty_is_shown_as_empty_rather_than_dropped(self):
		""""Did I fill that in?" is the question the page exists to answer."""
		self.assertIn("Not given", self.page("apply.html"))

	def test_the_documents_are_shown_not_listed(self):
		markup = self.page("apply.html")
		self.assertIn("review-docs", markup)
		self.assertIn("createObjectURL", markup)

	def test_the_previews_are_released(self):
		"""An object URL holds the whole file until it is revoked, and a
		candidate who goes back and changes three photographs would hold
		three of them for as long as the tab is open.
		"""
		markup = self.page("apply.html")
		self.assertIn("previewUrls.forEach(URL.revokeObjectURL)", markup)

	# --- /documents -------------------------------------------------------

	def test_the_resubmission_page_shows_what_was_chosen(self):
		markup = self.page("documents.html")
		self.assertIn("chosen-preview", markup)
		self.assertIn("chosen-name", markup)
		self.assertIn("chosen-size", markup)

	def test_it_can_be_taken_back_before_it_is_sent(self):
		markup = self.page("documents.html")
		self.assertIn("chosen-remove", markup)
		self.assertIn("function forget(", markup)

	def test_sending_is_a_separate_decision(self):
		"""Choosing a file used to upload it on the spot, so the wrong file was
		already on the record before the candidate had seen it.
		"""
		markup = self.page("documents.html")
		self.assertIn("chosen-send", markup)
		self.assertIn("Send this document", markup)
		handler = markup.split("input.addEventListener('change'")[1].split("\n")[0]
		self.assertIn("showChosen", handler)
		self.assertNotIn("send(", handler)

	def test_the_page_no_longer_claims_there_is_nothing_to_submit(self):
		markup = self.page("documents.html")
		self.assertNotIn("there is nothing to submit at the end", markup)
		self.assertIn("Send this document</b>", markup)

	def test_its_object_urls_are_released_too(self):
		self.assertIn("revokeObjectURL", self.page("documents.html"))


class TestTheDropZoneIncludeComesAfterTheMarkup(FrappeTestCase):
	"""`dropzone.html` upgrades every `.dropzone` it can find at the moment it
	runs, and it runs where it is included. On /documents it sat at the top of
	the block, before any of them existed -- so every drop zone there rendered
	with no prompt in it and never named a chosen file back to the candidate.
	/apply had it at the foot all along, which is why the same include worked
	on one page and not the other.
	"""

	INCLUDES = (
		'{% include "templates/includes/dropzone.html" %}',
		'{% include "templates/includes/image_shrink.html" %}',
	)

	def page(self, name):
		return open(os.path.join(WWW, name), encoding="utf-8").read()

	def test_every_page_includes_it_below_its_own_drop_zones(self):
		for name in ("apply.html", "documents.html"):
			markup = self.page(name)
			first_zone = markup.find('class="dropzone"')
			self.assertGreater(first_zone, -1, f"{name} has no drop zone")
			for include in self.INCLUDES:
				with self.subTest(page=name, include=include):
					self.assertGreater(
						markup.find(include),
						first_zone,
						f"{include} runs before {name}'s drop zones exist",
					)
