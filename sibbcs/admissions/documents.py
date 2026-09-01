# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""Reviewing what a candidate uploaded, and asking for it again.

Step 2 of the checklist -- Applicant Documents Review -- is the only step whose
verdict is per-file rather than per-application, so it gets its own small module
rather than another checklist action.

**Nothing here decides that step's status.** `set_docs_verified()` already
derives `docs_verified` from the required documents and
`mirror_gates_to_checklist()` moves the step from it, so ticking the last
required box moves the step to Verified on the same save, without this module
saying anything about it. One rule, in one place; two would eventually disagree.
"""

from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from sibbcs.admissions import checklist
from sibbcs.admissions.doctype.admission_application.admission_application import (
	REQUIRED_DOCUMENTS,
)
from sibbcs.admissions.notifications import outgoing_configured
from sibbcs.admissions.uploads import OPEN_STATES, new_upload_token
from sibbcs.finance.gateway import public_url

REMARKS_MAX = 500


def _application(name, permission="write"):
	doc = frappe.get_doc("Admission Application", name)
	# The document's own permission, not a role list: the permission matrix
	# already says who may work an application, and a second list here would be
	# one more place to forget.
	doc.check_permission(permission)
	return doc


def _row(doc, row_name):
	found = next(
		(r for r in doc.application_documents if r.name == row_name), None
	)
	if not found:
		frappe.throw(_("That document is not on this application."))
	return found


def _documents(doc):
	return [
		{
			"name": row.name,
			"document_type": row.document_type,
			"file": row.file,
			"verified": cint(row.verified),
			"verified_by": row.verified_by,
			"remarks": row.remarks,
			"idx": row.idx,
		}
		for row in doc.application_documents
	]


def _state(doc):
	"""Everything the reviewing screen needs after a change.

	Returned whole rather than as a patch because ticking one box can move the
	checklist step, which can unblock a later step -- the screen would have to
	guess at all of that.
	"""
	return {
		"documents": _documents(doc),
		"checklist": checklist.board(doc.name),
		"docs_verified": cint(doc.docs_verified),
		"required": list(REQUIRED_DOCUMENTS),
		"outstanding": outstanding_for(doc),
	}


@frappe.whitelist(methods=["POST"])
def review(application, row, verified=None, remarks=None):
	"""Tick, untick or annotate one uploaded document.

	Saved through the parent document, never around it: the save is what runs
	`set_docs_verified()` and moves the checklist step. `frappe.db.set_value`
	here would tick the box and leave the step where it was.
	"""
	doc = _application(application)
	target = _row(doc, row)

	if verified is not None:
		ticked = cint(verified)
		if ticked and not target.file:
			frappe.throw(
				_("{0} has not been uploaded yet, so there is nothing to verify.").format(
					target.document_type
				)
			)
		target.verified = ticked
		# Who says so, and when they stopped saying so.
		target.verified_by = frappe.session.user if ticked else None

	if remarks is not None:
		target.remarks = (remarks or "").strip()[:REMARKS_MAX] or None

	doc.save()
	return _state(doc)


def outstanding_for(doc):
	"""What the candidate still has to do about their documents.

	Two different problems, deliberately distinguished: a required document
	that never arrived, and one that arrived and was not accepted. "Send it
	again" is useless advice for a file nobody has ever seen.
	"""
	supplied = {row.document_type: row for row in doc.application_documents if row.file}

	items = [
		{"document_type": document_type, "missing": True, "remarks": None}
		for document_type in REQUIRED_DOCUMENTS
		if document_type not in supplied
	]
	items += [
		{"document_type": row.document_type, "missing": False, "remarks": row.remarks}
		for row in doc.application_documents
		if row.file and not cint(row.verified)
	]
	return items


@frappe.whitelist()
def outstanding(application):
	return outstanding_for(_application(application, "read"))


RESUBMIT_SUBJECT = "Documents needed for your application — {{ application }}"

RESUBMIT_BODY = (
	"<p>Dear {{ applicant_name }},</p>"
	"<p>Thank you for applying to the {{ program }} programme at South India "
	"Baptist Bible College &amp; Seminary. Before we can take your application "
	"further we need the following documents:</p>"
	"<ul>{% for item in items %}<li><b>{{ item.document_type }}</b>"
	"{% if item.missing %} — we have not received this yet"
	"{% else %} — please send this again{% endif %}"
	"{% if item.remarks %}<br><i>{{ item.remarks }}</i>{% endif %}"
	"</li>{% endfor %}</ul>"
	"{% if message %}<p>{{ message }}</p>{% endif %}"
	"<p>You can upload them here — no login needed, and the link is yours "
	"alone:<br><a href=\"{{ link }}\">{{ link }}</a></p>"
	"<p>PDF, JPG or PNG, up to 5 MB each. Your application reference is "
	"<b>{{ application }}</b>.</p>"
	"<p>Admissions Office</p>"
)


@frappe.whitelist(methods=["POST"])
def request_resubmit(application, message=None):
	"""Ask the candidate, in one click, for the documents still outstanding.

	The link carries the application's own `upload_token`, which is what
	`uploads.upload_document` already authorises against -- so a re-upload
	lands on the right application, replaces the row rather than duplicating
	it, and clears the verification that no longer applies.
	"""
	doc = _application(application)

	items = outstanding_for(doc)
	if not items:
		frappe.throw(
			_("Every document has been verified. There is nothing to ask for."),
			title=_("Nothing Outstanding"),
		)

	if not doc.email:
		frappe.throw(_("This application has no email address to write to."))

	# Sending a link that will be refused when they click it is worse than
	# saying so now.
	if (doc.workflow_state or "") not in OPEN_STATES:
		frappe.throw(
			_(
				"This application is at {0} and no longer accepts uploads. "
				"Move it back before asking for documents."
			).format(doc.workflow_state),
			title=_("Uploads Closed"),
		)

	if not outgoing_configured():
		frappe.throw(
			_(
				"No outgoing email account is configured, so nothing can be sent. "
				"Set one up in Desk under Email Account."
			),
			title=_("Email Not Configured"),
		)

	if not doc.upload_token:
		# Applications created in Desk rather than through /apply never had one.
		doc.upload_token = new_upload_token()

	# Built here rather than through `token_url`, which assumes one token and
	# no other parameters: the upload endpoint needs the application named too.
	link = public_url(
		f"/documents?application={quote(doc.name)}&token={doc.upload_token}"
	)

	context = {
		"applicant_name": doc.full_name,
		"program": doc.program,
		"application": doc.name,
		"items": items,
		"message": (message or "").strip() or None,
		"link": link,
	}

	subject = frappe.render_template(RESUBMIT_SUBJECT, context)
	body = frappe.render_template(RESUBMIT_BODY, context)

	frappe.sendmail(
		recipients=[doc.email],
		subject=subject,
		message=body,
		header=[_("Documents Needed"), "orange"],
		now=False,
	)

	doc.docs_resubmit_requested_on = now_datetime()
	doc.save()

	# After the save, so `mirror_gates_to_checklist` cannot overwrite it on the
	# way past. The mirror leaves this status alone once set -- only an actual
	# upload moves it on.
	checklist.set_status(
		doc.name,
		checklist.NO["documents"],
		"Resubmit Requested",
	)

	return {
		"sent_to": doc.email,
		"items": items,
		"requested_on": str(doc.docs_resubmit_requested_on),
	}
