"""Reading manual acknowledgement, reached by token link with no login.

URL: /manual-reading?token=<uuid>

Frappe's template page renderer maps `-` to `_` when locating the controller
(see frappe/website/page_renderers/template_page.py set_pymodule), so the page
is manual-reading.html and this module is manual_reading.py.
"""

import frappe

from sibbcs.admissions.tokens import TokenError, get_context_for

no_cache = 1


def get_context(context):
	context.no_cache = 1
	context.form_key = "manual-reading"
	token = frappe.form_dict.get("token")

	try:
		context.update(get_context_for("manual-reading", token))

		manual = frappe.db.get_value(
			"Reading Manual",
			context.row.get("manual"),
			["manual_title", "version", "content", "attachment", "require_scroll"],
			as_dict=True,
		)
		if not manual:
			raise TokenError("This manual is no longer available.")

		context.manual = manual

		# A course-backed manual holds the signature back until every lesson is
		# done. The page needs to say how far they have got, not just refuse.
		from sibbcs.admissions.manuals import course_progress, manual_course

		course = manual_course(context.row.get("manual"))
		context.course = course
		context.progress = course_progress(context.application, course) if course else None
		context.course_url = f"/lms/courses/{course}" if course else None
		# The file is private, so it is fetched through the token endpoint
		# rather than a /files/ link the candidate cannot open.
		context.attachment_url = (
			f"/api/method/sibbcs.admissions.tokens.download_manual?token={token}"
			if manual.attachment
			else None
		)
		context.valid = True
	except TokenError as exc:
		context.valid = False
		context.error = str(exc)
	except Exception:
		frappe.log_error(title="Manual reading page context failed")
		context.valid = False
		context.error = "Something went wrong opening this page."

	return context
