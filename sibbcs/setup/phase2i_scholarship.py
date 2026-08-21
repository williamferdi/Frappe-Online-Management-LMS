"""Step 5: the scholarship form, its review, and the per-program caps.

    bench --site online.sibbc.org execute sibbcs.setup.phase2i_scholarship.build

Idempotent.

The caps are the college's own, from their scholarship form: 8,000 rupees a
year against programmes of three, two and one year. They are seeded onto
`Program.scholarship_max` rather than written into code, so revising them is a
form edit rather than a deploy. A programme not listed keeps a cap of zero,
which `scholarship.decide` reads as "no ceiling declared" and allows -- so an
unseeded programme is visible as a blank field rather than silently capped at
nothing.
"""

import frappe

from sibbcs.admissions.checklist import ALL_STATUSES
from sibbcs.setup.schema import add_fields, f, section

# program -> total scholarship available, from the college's form
CAPS = {
	"MDIV": 24000,
	"MACS": 16000,
	"GDCS": 8000,
}

TEMPLATE = {
	"name": "scholarship_form",
	"subject": "Scholarship form — {{ program }}",
	"response": """
<p>Dear {{ applicant_name }},</p>

<p>
	South India Baptist Bible College &amp; Seminary offers a scholarship for
	candidates who face genuine financial difficulty but are committed to
	ministerial training. If that describes your situation, you are welcome to
	apply.
</p>

{% if program_cap %}
<p>
	The maximum award for <strong>{{ program }}</strong> is
	<strong>&#8377;{{ "{:,.0f}".format(program_cap) }}</strong> in total.
</p>
{% endif %}

<p>
	The form is short: a few sentences explaining your need, and your signature.
</p>

<p style="margin:24px 0">
	<a href="{{ link }}"
	   style="background:#171717;color:#fff;padding:10px 18px;border-radius:6px;
	          text-decoration:none;display:inline-block">
		Open the scholarship form
	</a>
</p>

<p style="font-size:12px;color:#666">
	If the button does not work, copy this address into your browser:<br>
	{{ link }}
</p>

<p style="font-size:12px;color:#666">
	This link is personal to you and can be used once. Applying does not affect
	your admission decision. Your application reference is {{ application_id }}.
</p>

<p style="margin-top:24px">
	Warm regards,<br>
	<strong>Admissions Office</strong><br>
	South India Baptist Bible College &amp; Seminary (Online)<br>
	Coimbatore
</p>
""",
}


def _program_fields():
	return add_fields(
		"Program",
		[
			f(
				"scholarship_max",
				"Scholarship Maximum",
				"Currency",
				description=(
					"The most a scholarship for this program can be worth in total. "
					"An approval above it is refused. Zero means no ceiling declared."
				),
			)
		],
	)


def _seed_caps():
	seeded = {}
	for program, cap in CAPS.items():
		if not frappe.db.exists("Program", program):
			continue
		# Never overwrite a figure the college has since edited in Desk.
		if frappe.db.get_value("Program", program, "scholarship_max"):
			continue
		frappe.db.set_value("Program", program, "scholarship_max", cap, update_modified=False)
		seeded[program] = cap
	return seeded


def _application_fields():
	return add_fields(
		"Admission Application",
		[
			section("sb_scholarship", "Scholarship"),
			f("scholarship_token", "Scholarship Token", "Data", read_only=1, no_copy=1),
			f("scholarship_form_url", "Scholarship Form Link", "Small Text", read_only=1),
			f("scholarship_form_sent_on", "Form Sent On", "Datetime", read_only=1),
		],
		insert_after="scholarship_request",
	)


def _request_fields():
	return add_fields(
		"Scholarship Request",
		[
			f(
				"signature",
				"Signature",
				"Attach Image",
				read_only=1,
				description="Drawn by the candidate on the form. Stored privately.",
			),
			f("submitted_on", "Submitted On", "Datetime", read_only=1),
			f("ip_address", "IP Address", "Data", read_only=1, no_copy=1),
		],
		insert_after="justification",
	)


def _widen_status_options():
	"""Admission Checklist Item.status is one Select across all 13 steps."""
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
	added = _program_fields() + _application_fields() + _request_fields()
	seeded = _seed_caps()
	widened = _widen_status_options()
	made = _template()

	frappe.db.commit()
	for doctype in ("Program", "Admission Application", "Scholarship Request", "Admission Checklist Item"):
		frappe.clear_cache(doctype=doctype)

	options = frappe.db.get_value(
		"DocField",
		{"parent": "Admission Checklist Item", "fieldname": "status"},
		"options",
	)
	caps = frappe.get_all(
		"Program", fields=["name", "scholarship_max"], order_by="name"
	)

	print(f"Added: {added or 'nothing new'}")
	print(f"Caps seeded: {seeded or 'none (already set)'}")
	print(f"Status options rewritten: {widened}")
	print(f"'Form Sent' offered: {'Form Sent' in (options or '')}")
	print(f"Email Template {TEMPLATE['name']}: {'created' if made else 'already present'}")
	for row in caps:
		mark = "" if row.scholarship_max else "   <- no ceiling declared"
		print(f"  {row.name:10} {row.scholarship_max or 0:,.0f}{mark}")
