"""Step 9: the Calendly interview booking link.

    bench --site online.sibbc.org execute sibbcs.setup.phase2h_interview.build

Idempotent.

Three things:

* two read-only fields on the application -- the candidate's own booking link
  and when it was emailed;
* the `Invite Sent` status, which step 9 gained so that a sent link is not
  reported as `Awaiting`. `Admission Checklist Item.status` is one Select
  across every step, so widening one step means rewriting that field's
  options -- `add_fields` cannot do it, since the field already exists;
* the email template.

Point it at the event once, without the query string a browser adds:

    bench --site <site> set-config calendly_interview_url \\
        "https://calendly.com/admissions-online-sibbc/30min"
"""

import frappe

from sibbcs.admissions.checklist import ALL_STATUSES
from sibbcs.setup.schema import add_fields, f, section

TEMPLATE = {
	"name": "interview_invite",
	"subject": "Book your admission interview — {{ program }}",
	"response": """
<p>Dear {{ applicant_name }},</p>

<p>
	Thank you for your application to the <strong>{{ program }}</strong> program at
	South India Baptist Bible College &amp; Seminary (Online). The next step is a
	short interview over Zoom with our admissions panel.
</p>

<p>
	Please choose a time that suits you. Your name and email are already filled
	in, and you can reschedule later from the same confirmation email.
</p>

<p style="margin:24px 0">
	<a href="{{ link }}"
	   style="background:#171717;color:#fff;padding:10px 18px;border-radius:6px;
	          text-decoration:none;display:inline-block">
		Choose your interview time
	</a>
</p>

<p style="font-size:12px;color:#666">
	If the button does not work, copy this address into your browser:<br>
	{{ link }}
</p>

<p style="font-size:12px;color:#666">
	The Zoom joining details come with your booking confirmation. Your
	application reference is {{ application_id }}.
</p>

<p style="margin-top:24px">
	Warm regards,<br>
	<strong>Admissions Office</strong><br>
	South India Baptist Bible College &amp; Seminary (Online)<br>
	Coimbatore
</p>
""",
}


def _application_fields():
	return add_fields(
		"Admission Application",
		[
			section("sb_interview", "Interview Booking"),
			f(
				"interview_booking_url",
				"Booking Link",
				"Small Text",
				read_only=1,
				description=(
					"This candidate's own Calendly link, with their details "
					"prefilled and the application number attached. Copy it if you "
					"need to send it by WhatsApp."
				),
			),
			f("interview_link_sent_on", "Booking Link Sent On", "Datetime", read_only=1),
		],
		insert_after="exam_link_sent_on",
	)


def _widen_status_options():
	"""Rewrite Admission Checklist Item.status with every current status."""
	doctype = frappe.get_doc("DocType", "Admission Checklist Item")
	field = next((df for df in doctype.fields if df.fieldname == "status"), None)
	if not field:
		return False

	wanted = "\n".join(ALL_STATUSES)
	if field.options == wanted:
		return False

	field.options = wanted
	doctype.save(ignore_permissions=True)
	return True


def _template():
	if frappe.db.exists("Email Template", TEMPLATE["name"]):
		return False

	frappe.get_doc(
		{
			"doctype": "Email Template",
			"name": TEMPLATE["name"],
			"subject": TEMPLATE["subject"],
			"use_html": 1,
			"response_html": TEMPLATE["response"],
			"response": TEMPLATE["response"],
		}
	).insert(ignore_permissions=True)
	return True


def build():
	added = _application_fields()
	widened = _widen_status_options()
	made = _template()

	frappe.db.commit()
	frappe.clear_cache(doctype="Admission Application")
	frappe.clear_cache(doctype="Admission Checklist Item")

	options = frappe.db.get_value(
		"DocField",
		{"parent": "Admission Checklist Item", "fieldname": "status"},
		"options",
	)
	print(f"Added: {added or 'nothing new'}")
	print(f"Status options rewritten: {widened}")
	print(f"'Invite Sent' offered: {'Invite Sent' in (options or '')}")
	print(f"Email Template {TEMPLATE['name']}: {'created' if made else 'already present'}")

	from sibbcs.admissions.interview import event_url

	print(f"Calendly event: {event_url() or 'NOT SET -- step 9 will report that'}")
