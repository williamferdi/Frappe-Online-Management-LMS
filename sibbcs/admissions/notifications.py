"""Sending the referee and mentor request emails.

Previously these went out only when an Admissions Officer pressed a button in
Desk, so on a self-service application nobody was ever asked for a reference --
every row sat at `sent_on = NEVER`.

They are now dispatched automatically when an application is **placed**, not
when it is submitted. That distinction matters: an application is placed once
the fee clears, and emailing a candidate's pastor about an application that was
abandoned at the payment page would be worse than sending nothing.

Everything here is idempotent (a row with `sent_on` is skipped) and silent about
its own plumbing -- a missing mail account is logged and reported, never raised
at whoever happened to trigger the save.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime

from sibbcs.admissions.doctype.admission_application.admission_application import token_url

# Steps 3, 4 and 6 on the checklist mirror what has been sent.
REFEREE_STEPS = {0: 3, 1: 4}
MENTOR_STEP = 6


def outgoing_configured():
	return bool(
		frappe.db.get_value(
			"Email Account", {"default_outgoing": 1, "enable_outgoing": 1}, "name"
		)
	)


def _mark_step(application, step_no, status):
	"""Update a checklist row without saving the parent.

	checklist.set_status() saves, and this runs from on_update -- saving there
	would recurse.
	"""
	name = frappe.db.get_value(
		"Admission Checklist Item",
		{"parent": application, "parenttype": "Admission Application", "step_no": step_no},
		"name",
	)
	if not name:
		return
	current = frappe.db.get_value("Admission Checklist Item", name, "status")
	# Never walk a step backwards out of something an officer already recorded.
	if current in ("Received", "Awaiting Review", "Reviewed", "Verified", "Not Applicable"):
		return
	frappe.db.set_value(
		"Admission Checklist Item",
		name,
		{"status": status, "updated_by": frappe.session.user, "updated_on": now_datetime()},
		update_modified=False,
	)


def dispatch_requests(application, force=False):
	"""Send any outstanding referee and mentor requests for one application."""
	report = {"application": application, "referees": [], "mentor": [], "skipped": None}

	if not outgoing_configured():
		report["skipped"] = "no outgoing email account configured"
		frappe.logger("sibbcs").info(
			f"{application}: reference/mentor requests not sent -- no outgoing email account"
		)
		return report

	doc = frappe.get_doc("Admission Application", application)

	for index, row in enumerate(doc.reference_requests):
		if (row.sent_on and not force) or row.submitted_on or not row.referee_email:
			continue
		try:
			frappe.sendmail(
				recipients=[row.referee_email],
				subject=_("Reference request for {0}").format(doc.full_name),
				template="reference_request",
				args={
					"referee_name": row.referee_name,
					"applicant_name": doc.full_name,
					"program": doc.program,
					"link": token_url("reference", row.token),
				},
				header=[_("Reference Request"), "blue"],
				now=False,
			)
			frappe.db.set_value(
				"Reference Request", row.name, "sent_on", now_datetime(), update_modified=False
			)
			_mark_step(application, REFEREE_STEPS.get(index, 3), "Request Sent")
			report["referees"].append(row.referee_email)
		except Exception:
			frappe.log_error(title=f"Reference request failed for {application}")

	for row in doc.mentor_consents:
		if (row.sent_on and not force) or row.consented_on or not row.mentor_email:
			continue
		try:
			frappe.sendmail(
				recipients=[row.mentor_email],
				subject=_("Mentor consent for {0}").format(doc.full_name),
				template="mentor_consent_request",
				args={
					"mentor_name": row.mentor_name,
					"applicant_name": doc.full_name,
					"program": doc.program,
					"link": token_url("mentor-consent", row.token),
				},
				header=[_("Mentor Consent"), "blue"],
				now=False,
			)
			frappe.db.set_value(
				"Mentor Consent", row.name, "sent_on", now_datetime(), update_modified=False
			)
			_mark_step(application, MENTOR_STEP, "Request Sent")
			report["mentor"].append(row.mentor_email)
		except Exception:
			frappe.log_error(title=f"Mentor consent request failed for {application}")

	# Mail plumbing must never surface on a public form response.
	frappe.clear_messages()
	return report


def dispatch_on_placement(doc):
	"""Called from Admission Application.on_update.

	Fires once the application is placed. Cheap to call on every save: rows
	already sent are skipped, and the whole thing short-circuits when there is
	no mail account.
	"""
	if (doc.workflow_state or "Draft") == "Draft":
		return
	if not (doc.reference_requests or doc.mentor_consents):
		return

	outstanding = any(
		not r.sent_on and not r.submitted_on and r.referee_email for r in doc.reference_requests
	) or any(not m.sent_on and not m.consented_on and m.mentor_email for m in doc.mentor_consents)

	if not outstanding:
		return

	dispatch_requests(doc.name)


# ---------------------------------------------------------------------------
# catching up
# ---------------------------------------------------------------------------


def send_pending_requests(limit=200, include_drafts=False):
	"""Flush the backlog once a mail account exists.

	Deliberately a command rather than a scheduled job: configuring SMTP should
	not silently fire off a batch of emails to every referee on file. Run it
	when you mean to.

	    bench --site online.sibbc.org execute \\
	        sibbcs.admissions.notifications.send_pending_requests
	"""
	if not outgoing_configured():
		print("No outgoing email account is configured. Nothing sent.")
		return {"sent": [], "skipped": "no outgoing email account"}

	states = ["In Review", "Admitted", "Onboarded"]
	if include_drafts:
		states.append("Draft")

	applications = frappe.get_all(
		"Admission Application",
		filters={"workflow_state": ("in", states)},
		pluck="name",
		limit=limit,
	)

	sent = []
	for name in applications:
		report = dispatch_requests(name)
		if report["referees"] or report["mentor"]:
			sent.append(report)

	print(f"Dispatched requests for {len(sent)} application(s).")
	for report in sent:
		print(f"  {report['application']}: {report['referees'] + report['mentor']}")
	return {"sent": sent}


@frappe.whitelist()
def resend(application):
	"""Desk button: send or re-send this application's outstanding requests."""
	doc = frappe.get_doc("Admission Application", application)
	doc.check_permission("write")

	if not outgoing_configured():
		frappe.msgprint(
			_(
				"No outgoing email account is configured, so nothing can be sent. "
				"Set one up under Email Account, then try again."
			),
			title=_("Email Not Configured"),
			indicator="orange",
		)
		return {"skipped": "no outgoing email account"}

	report = dispatch_requests(application)
	recipients = report["referees"] + report["mentor"]

	if recipients:
		frappe.msgprint(
			_("Requests queued to: {0}").format(", ".join(recipients)), indicator="green"
		)
	else:
		frappe.msgprint(_("Nothing outstanding to send."), indicator="orange")
	return report
