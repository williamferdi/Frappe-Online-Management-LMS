"""Step 7 fields: the applicant's LMS account and the entrance exam link.

    bench --site online.sibbc.org execute sibbcs.setup.phase2e_lms_account.build

Idempotent.

Everything here is read-only on the form. The account, the link and both
timestamps are facts produced by `admissions/lms_account.py`; letting an
officer type a date into `exam_link_sent_on` would make the checklist claim
something nobody can verify.
"""

import frappe

from sibbcs.setup.schema import add_fields, column, f, link, section

TEMPLATE = {
	"name": "lms_account_invite",
	"subject": "Your SIBBCS account and entrance exam",
	"response": """
<p>Dear {{ applicant_name }},</p>

<p>
	Thank you for applying to the <strong>{{ program }}</strong> program at South
	India Baptist Bible College &amp; Seminary (Online). We have created your
	account so you can sit the entrance exam.
</p>

<p>
	Your username is <strong>{{ login_email }}</strong>. For your own security we
	do not send passwords by email — please choose your own using the button
	below.
</p>

<p style="margin:24px 0">
	<a href="{{ password_link }}"
	   style="background:#171717;color:#fff;padding:10px 18px;border-radius:6px;
	          text-decoration:none;display:inline-block">
		Set your password
	</a>
</p>

{% if exam_link %}
<p>
	Once your password is set, you can sit the entrance exam here:
</p>

<p style="margin:24px 0">
	<a href="{{ exam_link }}"
	   style="background:#fff;color:#171717;border:1px solid #171717;padding:10px 18px;
	          border-radius:6px;text-decoration:none;display:inline-block">
		Go to the entrance exam
	</a>
</p>

<p style="font-size:12px;color:#666">
	If the buttons do not work, copy these addresses into your browser:<br>
	{{ password_link }}<br>
	{{ exam_link }}
</p>
{% else %}
<p style="font-size:12px;color:#666">
	If the button does not work, copy this address into your browser:<br>
	{{ password_link }}
</p>
{% endif %}

<p style="font-size:12px;color:#666">
	Your application reference is {{ application_id }}. Please quote it in any
	correspondence. If you did not apply to SIBBCS, please ignore this message.
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
	add_fields(
		"Admission Application",
		[
			section("sb_lms", "LMS Access"),
			link(
				"applicant_user",
				"Applicant Login",
				"User",
				read_only=1,
				description=(
					"The account created at step 7. The same login is kept when "
					"the applicant becomes a student."
				),
			),
			f("lms_account_created_on", "Account Created On", "Datetime", read_only=1),
			column("cb_lms"),
			f("entrance_exam_link", "Entrance Exam Link", "Small Text", read_only=1),
			f("exam_link_sent_on", "Exam Link Sent On", "Datetime", read_only=1),
		],
		insert_after="enrolled_on",
	)


def _email_template():
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
	_application_fields()
	made = _email_template()

	frappe.db.commit()
	frappe.clear_cache(doctype="Admission Application")

	meta = frappe.get_meta("Admission Application")
	present = [
		df.fieldname
		for df in meta.fields
		if df.fieldname
		in ("applicant_user", "lms_account_created_on", "entrance_exam_link", "exam_link_sent_on")
	]
	print(f"Admission Application carries {len(present)} of 4 LMS access fields: {present}")
	print(f"Email Template {TEMPLATE['name']}: {'created' if made else 'already present'}")
	print("Point step 7 at the exam with one of:")
	print("  bench --site <site> set-config entrance_exam_lms_course '<lms course>'")
	print("  bench --site <site> set-config entrance_exam_url '<full url>'")
