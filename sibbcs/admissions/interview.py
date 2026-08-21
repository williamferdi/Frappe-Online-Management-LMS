"""Step 9: sending the candidate their interview booking link.

The college books Zoom interviews through Calendly on the free plan, so this
is deliberately one-way: we send the link, the candidate picks a slot, and an
officer records the booking. Calendly's webhooks -- which would move step 9 by
themselves -- need a paid plan, and the college has chosen not to buy one. The
module is shaped so that adding them later is an addition, not a rewrite: the
link and the email stay exactly as they are.

Two things the link does that a bare Calendly URL does not:

* **Prefills the candidate.** Name and email go in as query parameters, so a
  candidate who has already typed them into the application does not type them
  again, and the booking cannot be made under a different address by accident.
* **Carries the application number** in `utm_content`. Calendly shows it
  against the booking, which is what lets an officer match a slot to an
  application without guessing from the name -- two candidates called Kumar is
  not a hypothetical.

Set the event link once:

    bench --site online.sibbc.org set-config calendly_interview_url \\
        "https://calendly.com/admissions-online-sibbc/30min"
"""

from urllib.parse import urlencode, urlsplit, urlunsplit

import frappe
from frappe import _
from frappe.utils import now_datetime

STEP = 9


def event_url():
	"""The configured Calendly event, stripped of any view state.

	A link copied out of a browser carries `?month=2026-08&date=2026-08-28`,
	which pins the widget to one month and one day. Sent to a candidate a
	month later it opens on a date that has already passed, so the query
	string is discarded rather than trusted.
	"""
	raw = (frappe.conf.get("calendly_interview_url") or "").strip()
	if not raw:
		return None

	parts = urlsplit(raw)
	if parts.scheme not in ("http", "https") or not parts.netloc:
		frappe.log_error(
			title="Calendly link is not a URL",
			message=f"calendly_interview_url is set to {raw!r}",
		)
		return None

	return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def configured():
	return bool(event_url())


def booking_url(doc):
	"""The candidate's own booking link, or None if none is configured."""
	base = event_url()
	if not base:
		return None

	params = {}
	if doc.full_name:
		params["name"] = doc.full_name
	if doc.email:
		params["email"] = doc.email
	params["utm_source"] = "sibbcs-erp"
	params["utm_content"] = doc.name

	return f"{base}?{urlencode(params)}"


FALLBACK_INVITE = (
	"Book your admission interview -- {{ program }}",
	"<p>Dear {{ applicant_name }},</p>"
	"<p>The next step in your application to South India Baptist Bible College "
	"&amp; Seminary is a short interview over Zoom. Please pick a time that "
	"suits you:</p>"
	'<p><a href="{{ link }}">{{ link }}</a></p>'
	"<p>You will receive the Zoom joining details from the booking "
	"confirmation.</p>"
	"<p>Admissions Office</p>",
)


def send_invite(application):
	"""Email the candidate their booking link. Idempotent enough to repeat."""
	from sibbcs.admissions.checklist import blocked_reason
	from sibbcs.admissions.notifications import render_template, outgoing_configured

	doc = frappe.get_doc("Admission Application", application)

	reason = blocked_reason(doc, STEP)
	if reason:
		frappe.throw(reason, title=_("Step Blocked"))

	report = {"application": doc.name, "link": None, "emailed": None, "warnings": []}

	link = booking_url(doc)
	report["link"] = link

	if not link:
		report["warnings"].append(
			"No Calendly event is configured, so nothing was sent. "
			"Set calendly_interview_url."
		)
		return report

	# Stored so an officer can copy the same personalised link into WhatsApp,
	# which is how a good few of these conversations actually happen.
	doc.db_set("interview_booking_url", link, update_modified=False)

	if not doc.email:
		report["warnings"].append("This application has no email address.")
		return report

	if not outgoing_configured():
		report["warnings"].append(
			"No outgoing email account is configured, so nothing was sent."
		)
		return report

	context = {
		"applicant_name": doc.full_name,
		"program": doc.program,
		"link": link,
		"application_id": doc.name,
	}
	subject, message = render_template("interview_invite", context, *FALLBACK_INVITE)

	try:
		frappe.sendmail(
			recipients=[doc.email],
			subject=subject,
			message=message,
			header=[_("Interview"), "blue"],
			now=False,
		)
	except Exception:
		frappe.log_error(title=f"Interview invite failed for {doc.name}")
		report["warnings"].append("The invitation email could not be sent.")
		return report

	report["emailed"] = doc.email
	doc.db_set("interview_link_sent_on", now_datetime(), update_modified=False)
	_mark_step(doc.name)
	return report


def _mark_step(application):
	"""Invite Sent -- not Scheduled.

	Sending a link is not a booking. On the free plan nobody here learns that
	a slot was taken until an officer looks, so the step says what we actually
	know and waits for them to move it on.
	"""
	name = frappe.db.get_value(
		"Admission Checklist Item",
		{"parent": application, "parenttype": "Admission Application", "step_no": STEP},
		"name",
	)
	if not name:
		return

	current = frappe.db.get_value("Admission Checklist Item", name, "status")
	if current != "Awaiting":
		return  # an officer has already moved this on; do not undo them

	frappe.db.set_value(
		"Admission Checklist Item",
		name,
		{
			"status": "Invite Sent",
			"updated_by": frappe.session.user,
			"updated_on": now_datetime(),
		},
		update_modified=False,
	)


@frappe.whitelist()
def send(application):
	doc = frappe.get_doc("Admission Application", application)
	doc.check_permission("write")

	report = send_invite(application)

	lines = []
	if report["emailed"]:
		lines.append(_("Booking link sent to <b>{0}</b>.").format(report["emailed"]))
	if report["link"]:
		lines.append(
			_("Their link: <a href='{0}' target='_blank'>{0}</a>").format(report["link"])
		)
	for warning in report["warnings"]:
		lines.append(f"<span style='color:var(--orange-600)'>{warning}</span>")

	frappe.msgprint(
		"<br>".join(lines),
		title=_("Interview Booking"),
		indicator="orange" if report["warnings"] else "green",
	)
	return report
