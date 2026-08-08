"""Referee form, reached by token link with no login.

URL: /reference?token=<uuid>
"""

import frappe

from sibbcs.admissions.tokens import TokenError, get_context_for

no_cache = 1


def get_context(context):
	context.no_cache = 1
	context.form_key = "reference"
	token = frappe.form_dict.get("token")

	try:
		context.update(get_context_for("reference", token))
		context.valid = True
	except TokenError as exc:
		context.valid = False
		context.error = str(exc)
	except Exception:
		frappe.log_error(title="Reference form context failed")
		context.valid = False
		context.error = "Something went wrong opening this form."

	return context
