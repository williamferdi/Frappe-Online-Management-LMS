"""Scholarship form, reached by token link with no login.

URL: /scholarship?token=<uuid>

Resolution is `admissions.scholarship.resolve`, not the generic token
controller: a Scholarship Request is a standalone document, not a child row of
the application, so the token lives on the application itself.
"""

import frappe

from sibbcs.admissions.scholarship import intro, resolve
from sibbcs.admissions.tokens import TokenError

no_cache = 1


def get_context(context):
	context.no_cache = 1
	token = frappe.form_dict.get("token")

	try:
		app = resolve(token)
		context.token = token
		context.applicant_name = app.full_name
		context.applicant_email = app.email
		context.program = app.program
		context.program_title = (
			frappe.db.get_value("Program", app.program, "program_name") or app.program
		)
		context.intro = intro(app.program)
		context.valid = True
	except TokenError as exc:
		context.valid = False
		context.error = str(exc)
	except Exception:
		frappe.log_error(title="Scholarship form context failed")
		context.valid = False
		context.error = "Something went wrong opening this form."

	return context
