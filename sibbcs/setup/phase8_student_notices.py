"""The two mails a student gets from the registrar, and the fields behind them.

    bench --site online.sibbc.org execute sibbcs.setup.phase8_student_notices.build

Idempotent. Safe to re-run; an Email Template the office has reworded in Desk
is never overwritten.

Until now the registrar wrote to a *candidate* often and to a **student**
never. Somebody admitted on Tuesday heard nothing on Wednesday: no address for
the portal, no way to set a password for it, and no word when the term's
courses opened for registration. Both gaps are the same gap -- the moment
somebody stops being an applicant, this system stops talking to them.

Two fields come with the mail:

`Course Offering.lms_course_id` is the LMS's own id for the course, learned
from what `/sync/courses` answers. Our `BISTO502-2026-T6` is not an address
anybody can open over there -- `/courses/:courseId` is validated as a UUID --
so without this, every link to a course could only be the LMS front door.

`Course Offering.students_notified_on` is when the students were told. It is
the whole of the announcement's idempotency: a sweep runs daily and an
offering saved twice must not be announced twice.
"""

import frappe

from sibbcs.setup.schema import add_fields, f, section

WELCOME = {
	"name": "student_welcome",
	"subject": "Your student portal — {{ student_id }}",
	"response": """
<p>Dear {{ student_name }},</p>

<p>
	Your enrolment at <strong>South India Baptist Bible College &amp; Seminary
	(Online)</strong> is complete. You are student
	<strong>{{ student_id }}</strong>, reading for the
	<strong>{{ program_name }}</strong> at <strong>Level {{ level }}</strong>.
</p>

<p>
	Everything the college asks of you from here happens in the student portal:
	registering for courses, what you owe and what you have paid, your grades,
	and your record.
</p>

<p style="margin:24px 0">
	<a href="{{ portal_url }}"
	   style="background:#171717;color:#fff;padding:10px 18px;border-radius:6px;
	          text-decoration:none;display:inline-block">
		Open the student portal
	</a>
</p>

<p>
	Sign in as <strong>{{ login_email }}</strong>. Set your password here — the
	link is good for a few days, and nobody at the college ever sees it:
</p>

<p style="margin:24px 0">
	<a href="{{ password_url }}"
	   style="background:#fff;color:#171717;border:1px solid #171717;padding:10px 18px;
	          border-radius:6px;text-decoration:none;display:inline-block">
		Set your password
	</a>
</p>

{% if lms_url %}
<p>
	Your lessons, coursework and quizzes are in the learning site, which uses
	the password you set there when you applied:<br>
	<a href="{{ lms_url }}">{{ lms_url }}</a>
</p>
{% endif %}

<p style="font-size:12px;color:#666">
	If the buttons do not work, copy these addresses into your browser:<br>
	{{ portal_url }}<br>
	{{ password_url }}
</p>

<p style="margin-top:24px">
	Warm regards,<br>
	<strong>Office of the Registrar</strong><br>
	South India Baptist Bible College &amp; Seminary (Online)<br>
	Coimbatore
</p>
""",
}

OFFERED = {
	"name": "course_offered",
	"subject": "Open for registration: {{ course_code }} — {{ term }}",
	"response": """
<p>Dear {{ student_name }},</p>

<p>
	<strong>{{ course_title }}</strong> ({{ course_code }}) is running in
	<strong>{{ term }}</strong> and is open to you to register for.
</p>

<table style="border-collapse:collapse;margin:16px 0;font-size:14px">
	<tr>
		<td style="padding:4px 16px 4px 0;color:#666">Level</td>
		<td style="padding:4px 0"><strong>{{ course_level }}</strong>
			&mdash; you are at Level {{ student_level }}</td>
	</tr>
	<tr>
		<td style="padding:4px 16px 4px 0;color:#666">Credits</td>
		<td style="padding:4px 0">{{ credits }}</td>
	</tr>
	{% if format %}
	<tr>
		<td style="padding:4px 16px 4px 0;color:#666">Format</td>
		<td style="padding:4px 0">{{ format }}</td>
	</tr>
	{% endif %}
	{% if closes %}
	<tr>
		<td style="padding:4px 16px 4px 0;color:#666">Registration closes</td>
		<td style="padding:4px 0"><strong>{{ closes }}</strong></td>
	</tr>
	{% endif %}
</table>

<p style="margin:24px 0">
	<a href="{{ register_url }}"
	   style="background:#171717;color:#fff;padding:10px 18px;border-radius:6px;
	          text-decoration:none;display:inline-block">
		Register for this course
	</a>
</p>

<p style="font-size:12px;color:#666">
	You are being written to because this course is open at your level. A place
	is not held for you until you register. If the button does not work, copy
	this address into your browser:<br>
	{{ register_url }}
</p>

<p style="margin-top:24px">
	Warm regards,<br>
	<strong>Office of the Registrar</strong><br>
	South India Baptist Bible College &amp; Seminary (Online)<br>
	Coimbatore
</p>
""",
}


def _offering_fields():
	return add_fields(
		"Course Offering",
		[
			section("sb_learning_site", "Learning Site"),
			f(
				"lms_course_id",
				"LMS Course ID",
				"Data",
				read_only=1,
				no_copy=1,
				description=(
					"The learning site's own id for this run of the course, learned "
					"from the sync. It is what a direct link to the course is built "
					"from; the registrar's own name for the offering is not an "
					"address over there."
				),
			),
			f(
				"students_notified_on",
				"Students Notified On",
				"Datetime",
				read_only=1,
				no_copy=1,
				description=(
					"When eligible students were emailed that this course is open "
					"for registration. Clear it to have them told again."
				),
			),
		],
	)


def _templates():
	created, skipped = [], []
	for spec in (WELCOME, OFFERED):
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
	return created, skipped


def build():
	added = _offering_fields()
	created, skipped = _templates()

	frappe.db.commit()
	frappe.clear_cache(doctype="Course Offering")

	print(f"Course Offering fields added: {added or 'nothing new'}")
	print(f"Email Templates: created {created}, already present {skipped}")
