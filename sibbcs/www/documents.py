"""The candidate's own document page, reached by link with no login.

URL: /documents?application=APP-2026-00011&token=<upload_token>

The credential is the application's `upload_token` -- the same one
`uploads.upload_document` has always authorised against, so this page adds a
way in, not a new power. It shows only what the holder of that token already
knows: their own name, and which of their own documents are outstanding.
"""

import frappe

from sibbcs.admissions.uploads import (
	ACCEPTED_DOCUMENT_TYPES,
	OPEN_STATES,
	_resolve,
)
from sibbcs.admissions.doctype.admission_application.admission_application import (
	REQUIRED_DOCUMENTS,
)

no_cache = 1


def get_context(context):
	context.no_cache = 1
	application = frappe.form_dict.get("application")
	token = frappe.form_dict.get("token")

	context.valid = False
	context.application = application
	context.token = token

	try:
		_resolve(application, token)
	except frappe.PermissionError:
		context.error = "This link is not valid. Please ask the Admissions Office for a new one."
		return context
	except frappe.ValidationError as exc:
		# _resolve says this when the application has moved past uploads.
		context.error = str(exc)
		return context
	except Exception:
		frappe.log_error(title="Document upload page context failed")
		context.error = "Something went wrong opening this page."
		return context

	record = frappe.db.get_value(
		"Admission Application",
		application,
		["full_name", "program", "workflow_state"],
		as_dict=True,
	)

	rows = frappe.get_all(
		"Application Document",
		filters={"parent": application, "parenttype": "Admission Application"},
		fields=["document_type", "file", "verified", "remarks"],
		order_by="idx",
		ignore_permissions=True,
	)
	held = {row.document_type: row for row in rows if row.file}

	context.valid = True
	context.applicant_name = record.full_name
	context.program = record.program
	context.open_states = OPEN_STATES
	# Every type the college accepts, each carrying where it stands. A page
	# that listed only the problems would give a candidate no way to send
	# something nobody has asked for yet.
	context.documents = [
		{
			"document_type": document_type,
			"required": document_type in REQUIRED_DOCUMENTS,
			"uploaded": document_type in held,
			"verified": bool(held[document_type].verified) if document_type in held else False,
			# The reviewer's note is written to be read by the candidate: it is
			# what the resubmit email quotes, and the reason the file was not
			# accepted.
			"remarks": held[document_type].remarks if document_type in held else None,
		}
		for document_type in ACCEPTED_DOCUMENT_TYPES
	]
	context.outstanding = [
		row for row in context.documents if not row["verified"]
	]

	return context
