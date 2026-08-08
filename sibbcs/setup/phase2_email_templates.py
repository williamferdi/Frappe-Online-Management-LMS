"""Email templates used by the admissions flow.

    bench --site online.sibbc.org execute sibbcs.setup.phase2_email_templates.build

Names must match the `template=` argument passed to frappe.sendmail:
`reference_request`, `mentor_consent_request`, `admission_offer`.
Idempotent -- existing templates are left alone so edits made in Desk survive.
"""

import frappe

SIGNATURE = """
<p style="margin-top:24px">
	Warm regards,<br>
	<strong>Admissions Office</strong><br>
	South India Baptist Bible College &amp; Seminary (Online)<br>
	Coimbatore
</p>
"""

TEMPLATES = [
	{
		"name": "reference_request",
		"subject": "Reference request for {{ applicant_name }}",
		"response": """
<p>Dear {{ referee_name }},</p>

<p>
	{{ applicant_name }} has applied to the <strong>{{ program }}</strong> program
	at South India Baptist Bible College &amp; Seminary (Online) and has named you
	as a referee.
</p>

<p>
	Please complete the short reference form using the link below. It takes about
	five minutes, and you will not need to create an account or sign in.
</p>

<p style="margin:24px 0">
	<a href="{{ link }}"
	   style="background:#171717;color:#fff;padding:10px 18px;border-radius:6px;
	          text-decoration:none;display:inline-block">
		Complete the reference form
	</a>
</p>

<p style="font-size:12px;color:#666">
	If the button does not work, copy this address into your browser:<br>
	{{ link }}
</p>

<p style="font-size:12px;color:#666">
	This link is personal to you and can be used once. Your answers go to the
	Admissions Office and are not shared with the applicant.
</p>
"""
		+ SIGNATURE,
	},
	{
		"name": "mentor_consent_request",
		"subject": "Mentor consent for {{ applicant_name }}",
		"response": """
<p>Dear {{ mentor_name }},</p>

<p>
	{{ applicant_name }} has applied to the <strong>{{ program }}</strong> program
	at South India Baptist Bible College &amp; Seminary (Online) and has asked you
	to serve as their mentor.
</p>

<p>
	Mentoring involves meeting the student about once a month for the duration of
	their studies, and submitting a short monthly report on their spiritual growth
	and ministry involvement. Each report arrives as its own link — you will never
	need a login.
</p>

<p style="margin:24px 0">
	<a href="{{ link }}"
	   style="background:#171717;color:#fff;padding:10px 18px;border-radius:6px;
	          text-decoration:none;display:inline-block">
		Give your consent
	</a>
</p>

<p style="font-size:12px;color:#666">
	If the button does not work, copy this address into your browser:<br>
	{{ link }}
</p>
"""
		+ SIGNATURE,
	},
	{
		"name": "admission_offer",
		"subject": "Offer of admission — {{ program }}",
		"response": """
<p>Dear {{ applicant_name }},</p>

<p>
	We are glad to offer you a place in the <strong>{{ program }}</strong> program
	at South India Baptist Bible College &amp; Seminary (Online), beginning
	{{ intake_term }}.
</p>

<p>
	To confirm your place, please pay the admission fee of
	<strong>&#8377;{{ admission_fee }}</strong>. Once we receive it we will create
	your student account and send your login details, along with your orientation
	course registration.
</p>

<p style="font-size:12px;color:#666">
	Your application reference is {{ application_id }}. Please quote it in any
	correspondence.
</p>
"""
		+ SIGNATURE,
	},
]


def build():
	created, skipped = [], []

	for spec in TEMPLATES:
		if frappe.db.exists("Email Template", spec["name"]):
			skipped.append(spec["name"])
			continue

		frappe.get_doc(
			{
				"doctype": "Email Template",
				"name": spec["name"],
				"subject": spec["subject"],
				"use_html": 1,
				"response_html": spec["response"],
				"response": spec["response"],
			}
		).insert(ignore_permissions=True)
		created.append(spec["name"])

	frappe.db.commit()
	print(f"Email Templates: {len(created)} created {created}, {len(skipped)} already present")
	return created
