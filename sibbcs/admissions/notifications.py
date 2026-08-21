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
from sibbcs.admissions.checklist import NO

REFEREE_STEPS = {0: NO["reference_1"], 1: NO["reference_2"]}
MENTOR_STEP = NO["mentor_form"]


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


def render_template(template_name, context, fallback_subject, fallback_body):
	"""Render an Email Template record.

	NOT frappe.sendmail(template=...): that looks for a Jinja *file* at
	templates/emails/<name>.html and raises TemplateNotFound. Our templates are
	Email Template documents on purpose, so the Admissions Office can reword
	them in Desk without a deploy.

	Falls back to a plain built-in message if the record has been deleted --
	losing the pretty wording is far better than losing the request.
	"""
	if frappe.db.exists("Email Template", template_name):
		template = frappe.get_cached_doc("Email Template", template_name)
		body = template.get("response_html") or template.get("response") or fallback_body
		try:
			return (
				frappe.render_template(template.subject or fallback_subject, context),
				frappe.render_template(body, context),
			)
		except Exception:
			frappe.log_error(title=f"Email template {template_name} failed to render")

	return (
		frappe.render_template(fallback_subject, context),
		frappe.render_template(fallback_body, context),
	)


FALLBACK_REFERENCE = (
	"Reference request for {{ applicant_name }}",
	"<p>Dear {{ referee_name }},</p>"
	"<p>{{ applicant_name }} has applied to the {{ program }} programme at South "
	"India Baptist Bible College &amp; Seminary and named you as a referee.</p>"
	"<p>Please complete the short reference form here:<br>"
	'<a href="{{ link }}">{{ link }}</a></p>'
	"<p>Admissions Office</p>",
)

FALLBACK_MENTOR = (
	"Mentor consent for {{ applicant_name }}",
	"<p>Dear {{ mentor_name }},</p>"
	"<p>{{ applicant_name }} has applied to the {{ program }} programme at South "
	"India Baptist Bible College &amp; Seminary and asked you to be their mentor.</p>"
	"<p>Please confirm here:<br>"
	'<a href="{{ link }}">{{ link }}</a></p>'
	"<p>Admissions Office</p>",
)


def send_reference_row(doc, row, index=0):
	"""Email one referee their link. Returns the address, or None on failure."""
	if not row.referee_email:
		return None

	context = {
		"referee_name": row.referee_name,
		"applicant_name": doc.full_name,
		"program": doc.program,
		"link": token_url("reference", row.token),
	}
	subject, message = render_template(
		"reference_request", context, *FALLBACK_REFERENCE
	)

	frappe.sendmail(
		recipients=[row.referee_email],
		subject=subject,
		message=message,
		header=[_("Reference Request"), "blue"],
		now=False,
	)
	frappe.db.set_value(
		"Reference Request", row.name, "sent_on", now_datetime(), update_modified=False
	)
	_mark_step(doc.name, REFEREE_STEPS.get(index, 3), "Request Sent")
	return row.referee_email


def send_mentor_row(doc, row):
	"""Email one mentor their consent link."""
	if not row.mentor_email:
		return None
	context = {
		"mentor_name": row.mentor_name,
		"applicant_name": doc.full_name,
		"program": doc.program,
		"link": token_url("mentor-consent", row.token),
	}
	subject, message = render_template(
		"mentor_consent_request", context, *FALLBACK_MENTOR
	)

	frappe.sendmail(
		recipients=[row.mentor_email],
		subject=subject,
		message=message,
		header=[_("Mentor Consent"), "blue"],
		now=False,
	)
	frappe.db.set_value(
		"Mentor Consent", row.name, "sent_on", now_datetime(), update_modified=False
	)
	_mark_step(doc.name, MENTOR_STEP, "Request Sent")
	return row.mentor_email


def dispatch_requests(application, force=False):
	"""Send any outstanding referee and mentor requests for one application.

	`force` re-sends rows already stamped `sent_on` -- used by the resend
	dialog, for a referee who lost the email or whose address was corrected.
	A row that has already been *submitted* is never re-sent: its token is
	spent and the form would only tell them so.
	"""
	report = {"application": application, "referees": [], "mentor": [], "skipped": None}

	if not outgoing_configured():
		report["skipped"] = "no outgoing email account configured"
		frappe.logger("sibbcs").info(
			f"{application}: reference/mentor requests not sent -- no outgoing email account"
		)
		return report

	doc = frappe.get_doc("Admission Application", application)

	for index, row in enumerate(doc.reference_requests):
		if (row.sent_on and not force) or row.submitted_on:
			continue
		try:
			sent = send_reference_row(doc, row, index)
			if sent:
				report["referees"].append(sent)
		except Exception:
			frappe.log_error(title=f"Reference request failed for {application}")

	for row in doc.mentor_consents:
		if (row.sent_on and not force) or row.consented_on:
			continue
		try:
			sent = send_mentor_row(doc, row)
			if sent:
				report["mentor"].append(sent)
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


# ---------------------------------------------------------------------------
# setup diagnostics
# ---------------------------------------------------------------------------


@frappe.whitelist()
def mail_status(send_test_to=None):
	"""Report whether outgoing email is usable, and optionally prove it.

	Run after configuring the Email Account:

	    bench --site online.sibbc.org execute \
	        sibbcs.admissions.notifications.mail_status \
	        --kwargs "{'send_test_to': 'you@example.com'}"

	Deliberately never takes a password. The account is configured in Desk,
	where Frappe stores the credential encrypted; this only reads the result.
	"""
	frappe.only_for(("System Manager", "Administrator"))

	accounts = frappe.get_all(
		"Email Account",
		fields=["name", "email_id", "smtp_server", "smtp_port", "use_tls",
		        "enable_outgoing", "default_outgoing"],
	)

	default = frappe.db.get_value(
		"Email Account", {"default_outgoing": 1, "enable_outgoing": 1},
		["name", "email_id", "smtp_server", "smtp_port"], as_dict=True,
	)

	print("=== Email Accounts ===")
	for a in accounts:
		flag = " <- DEFAULT OUTGOING" if a.default_outgoing and a.enable_outgoing else ""
		print("  %-26s %-26s %s:%s tls=%s%s" % (
			a.name, a.email_id, a.smtp_server or "-", a.smtp_port or "-",
			a.use_tls, flag))
	if not accounts:
		print("  (none)")

	print("=== Verdict ===")
	if not default:
		print("  NOT USABLE - no account is both enabled and default outgoing.")
		return {"ok": False, "reason": "no default outgoing account"}

	print(f"  Usable: {default.email_id} via {default.smtp_server}:{default.smtp_port}")

	pending = 0
	for name in frappe.get_all(
		"Admission Application",
		filters={"workflow_state": ("in", ["In Review", "Admitted", "Onboarded"])},
		pluck="name",
	):
		pending += frappe.db.count(
			"Reference Request", {"parent": name, "sent_on": ("is", "not set")}
		)
		pending += frappe.db.count(
			"Mentor Consent", {"parent": name, "sent_on": ("is", "not set")}
		)
	print(f"  Requests waiting to be sent: {pending}")

	if send_test_to:
		try:
			frappe.sendmail(
				recipients=[send_test_to],
				subject="SIBBCS ERP - outgoing email test",
				message=(
					"<p>If you are reading this, outgoing email works.</p>"
					"<p>Referee and mentor requests will now be sent automatically "
					"when an application is placed.</p>"
				),
				now=True,
			)
			print(f"  Test email sent to {send_test_to}. Check the inbox.")
		except Exception as exc:
			print(f"  TEST SEND FAILED: {exc}")
			return {"ok": False, "reason": str(exc)}

	return {"ok": True, "account": default.email_id, "pending_requests": pending}


# ---------------------------------------------------------------------------
# resending on demand
# ---------------------------------------------------------------------------


@frappe.whitelist()
def list_requests(application):
	"""Every referee and mentor on an application, with where each one stands.

	Feeds the resend dialog, so an officer can see who has replied, who was
	emailed and when, and who was never contacted at all -- before choosing
	whom to chase.
	"""
	doc = frappe.get_doc("Admission Application", application)
	doc.check_permission("read")

	rows = []
	for index, row in enumerate(doc.reference_requests):
		rows.append(
			{
				"kind": "reference",
				"row": row.name,
				"label": row.referee_name or _("Referee {0}").format(index + 1),
				"email": row.referee_email,
				"detail": row.referee_type or "",
				"sent_on": str(row.sent_on) if row.sent_on else None,
				"done": bool(row.submitted_on),
				"done_on": str(row.submitted_on) if row.submitted_on else None,
			}
		)

	for row in doc.mentor_consents:
		rows.append(
			{
				"kind": "mentor",
				"row": row.name,
				"label": row.mentor_name or _("Mentor"),
				"email": row.mentor_email,
				"detail": row.church or "",
				"sent_on": str(row.sent_on) if row.sent_on else None,
				"done": bool(row.consented_on),
				"done_on": str(row.consented_on) if row.consented_on else None,
			}
		)

	return {
		"application": doc.name,
		"applicant": doc.full_name,
		"mail_configured": outgoing_configured(),
		"rows": rows,
	}


@frappe.whitelist()
def resend_selected(application, targets):
	"""Re-send to specific referees or mentors, even if already sent once.

	`targets` is a JSON list of {"kind": "reference"|"mentor", "row": <name>}.
	Rows that have already replied are refused rather than silently skipped --
	their token is spent, so a fresh email would only confuse the recipient.
	"""
	import json

	doc = frappe.get_doc("Admission Application", application)
	doc.check_permission("write")

	if not outgoing_configured():
		frappe.throw(
			_(
				"No outgoing email account is configured, so nothing can be sent. "
				"Set one up under Email Account first."
			),
			title=_("Email Not Configured"),
		)

	if isinstance(targets, str):
		targets = json.loads(targets)

	wanted = {(t.get("kind"), t.get("row")) for t in (targets or [])}
	if not wanted:
		frappe.throw(_("Select at least one person to resend to."))

	sent, refused = [], []

	for index, row in enumerate(doc.reference_requests):
		if ("reference", row.name) not in wanted:
			continue
		if row.submitted_on:
			refused.append(_("{0} has already replied").format(row.referee_name))
			continue
		try:
			result = send_reference_row(doc, row, index)
			sent.append(result) if result else refused.append(
				_("{0} has no email address").format(row.referee_name)
			)
		except Exception:
			frappe.log_error(title=f"Resend to referee failed for {application}")
			refused.append(_("{0} — sending failed").format(row.referee_name))

	for row in doc.mentor_consents:
		if ("mentor", row.name) not in wanted:
			continue
		if row.consented_on:
			refused.append(_("{0} has already consented").format(row.mentor_name))
			continue
		try:
			result = send_mentor_row(doc, row)
			sent.append(result) if result else refused.append(
				_("{0} has no email address").format(row.mentor_name)
			)
		except Exception:
			frappe.log_error(title=f"Resend to mentor failed for {application}")
			refused.append(_("{0} — sending failed").format(row.mentor_name))

	frappe.clear_messages()

	if sent:
		frappe.msgprint(
			_("Sent to: {0}").format(", ".join(sent)),
			title=_("Requests Sent"),
			indicator="green",
		)
	if refused:
		frappe.msgprint(
			"<br>".join(refused), title=_("Not Sent"), indicator="orange"
		)

	return {"sent": sent, "refused": refused}
