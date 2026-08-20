"""Mentor consent form, reached by token link with no login.

URL: /mentor-consent?token=<uuid>

Frappe's template page renderer maps `-` to `_` when locating the controller
(see frappe/website/page_renderers/template_page.py set_pymodule), so the page
is mentor-consent.html and this module is mentor_consent.py.
"""

import frappe

from sibbcs.admissions.mentor_form import fields_for_render, intro_parts
from sibbcs.admissions.tokens import TokenError, get_context_for

no_cache = 1


def get_context(context):
	context.no_cache = 1
	context.form_key = "mentor-consent"
	token = frappe.form_dict.get("token")

	try:
		context.update(get_context_for("mentor-consent", token))
		context.intro = intro_parts()
		context.fields = fields_for_render()
		context.valid = True
	except TokenError as exc:
		context.valid = False
		context.error = str(exc)
	except Exception:
		frappe.log_error(title="Mentor consent form context failed")
		context.valid = False
		context.error = "Something went wrong opening this form."

	return context
