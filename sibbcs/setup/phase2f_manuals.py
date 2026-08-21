"""Step 12: the manual-reading email template, and a starter manual.

    bench --site online.sibbc.org execute sibbcs.setup.phase2f_manuals.build

Idempotent. The DocTypes (`Reading Manual`, `Manual Acknowledgement`) were
built in phase2b; only the template and an optional placeholder are new.

The placeholder manual is created **inactive** on purpose. It exists so the
step can be exercised end to end before the college has written its real
manuals, and being inactive means `manuals.applicable_manuals()` ignores it --
a candidate can never be sent lorem ipsum by accident.
"""

import frappe

TEMPLATE = {
	"name": "manual_reading",
	"subject": "Please read: {{ manual_title }}",
	"response": """
<p>Dear {{ applicant_name }},</p>

<p>
	Congratulations on completing the entrance exam. Before your admission to the
	<strong>{{ program }}</strong> program at South India Baptist Bible College
	&amp; Seminary (Online) can be finalised, please read
	<strong>{{ manual_title }}</strong>{% if manual_version %} (version
	{{ manual_version }}){% endif %} and confirm that you have done so.
</p>

<p style="margin:24px 0">
	<a href="{{ link }}"
	   style="background:#171717;color:#fff;padding:10px 18px;border-radius:6px;
	          text-decoration:none;display:inline-block">
		Open the manual
	</a>
</p>

<p style="font-size:12px;color:#666">
	If the button does not work, copy this address into your browser:<br>
	{{ link }}
</p>

<p style="font-size:12px;color:#666">
	The page asks you to type your name and tick a box to confirm your reading.
	This link is personal to you and can be used once. Your application reference
	is {{ application_id }}.
</p>

<p style="margin-top:24px">
	Warm regards,<br>
	<strong>Admissions Office</strong><br>
	South India Baptist Bible College &amp; Seminary (Online)<br>
	Coimbatore
</p>
""",
}

PLACEHOLDER = "Student Handbook (placeholder)"


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


def _placeholder():
	if frappe.db.exists("Reading Manual", PLACEHOLDER):
		return False

	frappe.get_doc(
		{
			"doctype": "Reading Manual",
			"manual_title": PLACEHOLDER,
			"version": "0",
			# Inactive: nothing is ever sent to a candidate until the college
			# replaces this with a real manual and ticks Is Active.
			"is_active": 0,
			"require_scroll": 1,
			"content": (
				"<p>Replace this with the manual the candidate must read, or attach "
				"it as a PDF. Leave <b>Is Active</b> unticked until it is ready.</p>"
			),
		}
	).insert(ignore_permissions=True)
	return True


def build():
	made_template = _template()
	made_placeholder = _placeholder()

	frappe.db.commit()

	active = frappe.get_all("Reading Manual", filters={"is_active": 1}, pluck="name")
	print(f"Email Template {TEMPLATE['name']}: {'created' if made_template else 'already present'}")
	print(f"Placeholder manual: {'created (inactive)' if made_placeholder else 'already present'}")
	print(f"Active reading manuals: {len(active)} {active}")
	if not active:
		print("No active manual -- step 12 will report that nothing applies.")
