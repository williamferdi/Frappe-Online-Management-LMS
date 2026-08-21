"""Step 12: sending the reading manuals, and recording that they were read.

A candidate who has passed the entrance exam is sent the manuals they must
read. They open a link, read the manual, type their name and confirm. Step 12
reaches **Acknowledged** only when every manual that applies to them has been
confirmed -- not the first one.

No login, by design. The candidate does have an account by this point (step 7
made one), but requiring a sign-in to acknowledge a document is friction that
buys nothing: the token already identifies exactly one manual for exactly one
applicant, and is spent on use.

What is recorded is deliberately thin but legally useful: who typed their
name, when, and from which address. `Manual Acknowledgement.acknowledged_name`
is what the candidate typed, not what the office believes their name to be --
if those differ, that difference is evidence, and overwriting it would destroy
the only thing the record is for.

Which manuals apply is a property of the manual, not of this code: a Reading
Manual with no programs listed is universal, one with programs listed applies
to those programs only.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime

from sibbcs.admissions.doctype.admission_application.admission_application import token_url

STEP = 12
FORM_KEY = "manual-reading"


# ---------------------------------------------------------------------------
# which manuals apply
# ---------------------------------------------------------------------------


def applicable_manuals(program=None):
	"""Active manuals for a program. No programs listed means universal."""
	names = frappe.get_all(
		"Reading Manual",
		filters={"is_active": 1},
		pluck="name",
		ignore_permissions=True,
	)

	applicable = []
	for name in names:
		scoped = frappe.get_all(
			"Reading Manual Program",
			filters={"parent": name, "parenttype": "Reading Manual"},
			pluck="program",
			ignore_permissions=True,
		)
		if not scoped or (program and program in scoped):
			applicable.append(name)

	return sorted(applicable)


def attach_manuals(doc):
	"""Give the application a row per applicable manual. Idempotent.

	Sets tokens here rather than in issue_tokens() because the rows do not
	exist until the manuals are sent.
	"""
	from sibbcs.admissions.tokens import generate_token

	held = {r.manual for r in doc.get("manual_acknowledgements") or []}
	added = []

	for manual in applicable_manuals(doc.program):
		if manual in held:
			continue
		doc.append("manual_acknowledgements", {"manual": manual, "token": generate_token()})
		added.append(manual)

	return added


# ---------------------------------------------------------------------------
# sending
# ---------------------------------------------------------------------------


FALLBACK_MANUAL = (
	"Please read: {{ manual_title }}",
	"<p>Dear {{ applicant_name }},</p>"
	"<p>Before your admission to South India Baptist Bible College &amp; Seminary "
	"can be completed, please read <b>{{ manual_title }}</b> and confirm that you "
	"have done so.</p>"
	"<p>Open it here:<br>"
	'<a href="{{ link }}">{{ link }}</a></p>'
	"<p>Admissions Office</p>",
)


def send_manual_row(doc, row):
	"""Email one manual link. Returns the address, or None."""
	from sibbcs.admissions.notifications import render_template

	if not doc.email:
		return None

	title, version = frappe.db.get_value(
		"Reading Manual", row.manual, ["manual_title", "version"]
	)

	context = {
		"applicant_name": doc.full_name,
		"manual_title": title,
		"manual_version": version,
		"program": doc.program,
		"link": token_url(FORM_KEY, row.token),
		"application_id": doc.name,
	}
	subject, message = render_template("manual_reading", context, *FALLBACK_MANUAL)

	frappe.sendmail(
		recipients=[doc.email],
		subject=subject,
		message=message,
		header=[_("Reading Manual"), "blue"],
		now=False,
	)
	frappe.db.set_value(
		"Manual Acknowledgement", row.name, "sent_on", now_datetime(), update_modified=False
	)
	return doc.email


def send_manuals(application, force=False):
	"""Attach any missing manual rows and email the outstanding ones.

	`force` re-sends rows already stamped `sent_on`. A manual already
	acknowledged is never re-sent: its token is spent.
	"""
	from sibbcs.admissions.checklist import blocked_reason
	from sibbcs.admissions.notifications import outgoing_configured

	doc = frappe.get_doc("Admission Application", application)

	reason = blocked_reason(doc, STEP)
	if reason:
		frappe.throw(reason, title=_("Step Blocked"))

	report = {
		"application": doc.name,
		"attached": [],
		"sent": [],
		"warnings": [],
	}

	report["attached"] = attach_manuals(doc)
	if report["attached"]:
		doc.flags.ignore_permissions = True
		doc.save(ignore_permissions=True)
		doc.reload()

	if not doc.get("manual_acknowledgements"):
		report["warnings"].append(
			"No active reading manual applies to this program, so nothing was sent."
		)
		return report

	if not outgoing_configured():
		report["warnings"].append(
			"No outgoing email account is configured, so nothing was sent."
		)
		return report

	for row in doc.manual_acknowledgements:
		if row.acknowledged_on:
			continue
		if row.sent_on and not force:
			continue
		try:
			if send_manual_row(doc, row):
				report["sent"].append(row.manual)
		except Exception:
			frappe.log_error(title=f"Manual link failed for {doc.name}")
			report["warnings"].append(f"{row.manual} could not be emailed.")

	if report["sent"]:
		_set_step(doc.name)

	return report


# ---------------------------------------------------------------------------
# acknowledging
# ---------------------------------------------------------------------------


def acknowledge(token, reader_name, confirmed):
	"""Record that one manual was read. Called from the guest endpoint."""
	from sibbcs.admissions.tokens import mark_submitted, resolve

	if str(confirmed) not in ("1", "true", "on", "yes", "True"):
		frappe.throw(
			_("Please tick the box to confirm you have read the manual."),
			title=_("Not Confirmed"),
		)

	reader_name = (reader_name or "").strip()
	if len(reader_name) < 3:
		frappe.throw(_("Please type your full name."), title=_("Name Needed"))

	resolved = resolve(FORM_KEY, token)

	result = mark_submitted(
		FORM_KEY,
		token,
		{
			# What they typed, not what we think their name is.
			"acknowledged_name": reader_name[:140],
			"ip_address": frappe.local.request_ip or "",
		},
	)

	_set_step(resolved["parent"])
	return result


def _set_step(application):
	"""Sent while any manual is outstanding; Acknowledged once all are in."""
	rows = frappe.get_all(
		"Manual Acknowledgement",
		filters={"parent": application, "parenttype": "Admission Application"},
		fields=["name", "acknowledged_on"],
		ignore_permissions=True,
	)
	if not rows:
		return None

	status = "Acknowledged" if all(r.acknowledged_on for r in rows) else "Sent"

	name = frappe.db.get_value(
		"Admission Checklist Item",
		{"parent": application, "parenttype": "Admission Application", "step_no": STEP},
		"name",
	)
	if not name:
		return status

	current = frappe.db.get_value("Admission Checklist Item", name, "status")
	if current == "Acknowledged":
		return current  # never walk the step backwards

	frappe.db.set_value(
		"Admission Checklist Item",
		name,
		{"status": status, "updated_by": frappe.session.user, "updated_on": now_datetime()},
		update_modified=False,
	)
	return status


# ---------------------------------------------------------------------------
# Desk
# ---------------------------------------------------------------------------


@frappe.whitelist()
def send(application, force=0):
	doc = frappe.get_doc("Admission Application", application)
	doc.check_permission("write")

	report = send_manuals(application, force=int(force or 0) == 1)

	lines = []
	if report["sent"]:
		lines.append(_("Sent: {0}").format(", ".join(report["sent"])))
	elif not report["warnings"]:
		lines.append(_("Every manual has already been sent."))
	for warning in report["warnings"]:
		lines.append(f"<span style='color:var(--orange-600)'>{warning}</span>")

	frappe.msgprint(
		"<br>".join(lines),
		title=_("Reading Manuals"),
		indicator="orange" if report["warnings"] else "green",
	)
	return report


@frappe.whitelist()
def status(application):
	"""What the Desk button needs: one line per manual."""
	doc = frappe.get_doc("Admission Application", application)
	doc.check_permission("read")

	rows = []
	for row in doc.get("manual_acknowledgements") or []:
		rows.append(
			{
				"manual": row.manual,
				"sent_on": str(row.sent_on) if row.sent_on else None,
				"acknowledged_on": str(row.acknowledged_on) if row.acknowledged_on else None,
				"acknowledged_name": row.acknowledged_name,
			}
		)

	return {
		"application": doc.name,
		"rows": rows,
		"outstanding": [r["manual"] for r in rows if not r["acknowledged_on"]],
		"applicable": applicable_manuals(doc.program),
	}
