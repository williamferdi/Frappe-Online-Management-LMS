"""Deliver the reading manual as an LMS course, signed on completion.

    bench --site online.sibbc.org execute sibbcs.setup.phase2k_course_manual.build

Idempotent. Run `phase2j_preliminary_course.build` first -- this points a
Reading Manual at the course that builder creates.

A `Reading Manual` can now be delivered two ways. As a **Document** it is read
on the acknowledgement page, which is where it started. As an **LMS Course**
the candidate is enrolled, works through the lessons, and the acknowledgement
page refuses their signature until every lesson is complete.

That distinction is the whole point. Onboarding is gated on this step, and an
acknowledgement of a PDF is one click -- it records that somebody pressed a
button, not that anybody read anything. A course records a lesson at a time.
"""

import frappe

from sibbcs.setup.phase2j_preliminary_course import COURSE_TITLE
from sibbcs.setup.schema import add_fields, f, link, select

MANUAL_TITLE = "M.Div. Preliminary Orientation"

TEMPLATE = {
	"name": "preliminary_course",
	"subject": "Complete your orientation course — SIBBCS Online",
	"response": """
<p>Dear {{ applicant_name }},</p>

<p>
	Congratulations on your admission to the <strong>{{ program }}</strong> program
	at South India Baptist Bible College &amp; Seminary (Online). One step remains
	before your enrolment is finalised.
</p>

<p>
	<strong>{{ manual_title }}</strong> is a short orientation course covering the
	Program Handbook and the opening of the Holistic Formation Handbook. It
	carries <strong>no credit</strong>, but every lesson must be completed — it is
	how we know you have read what you are agreeing to.
</p>

<p>
	Sign in as <strong>{{ login_email }}</strong>. If you have not set a password
	yet, use the link from your account email, or the "Forgot Password" option.
</p>

<p style="margin:24px 0">
	<a href="{{ course_url }}"
	   style="background:#171717;color:#fff;padding:10px 18px;border-radius:6px;
	          text-decoration:none;display:inline-block">
		Open the orientation course
	</a>
</p>

<p>
	When every lesson is done, sign the acknowledgement:
</p>

<p style="margin:24px 0">
	<a href="{{ link }}"
	   style="background:#fff;color:#171717;border:1px solid #171717;padding:10px 18px;
	          border-radius:6px;text-decoration:none;display:inline-block">
		Sign the acknowledgement
	</a>
</p>

<p style="font-size:12px;color:#666">
	If the buttons do not work, copy these addresses into your browser:<br>
	{{ course_url }}<br>
	{{ link }}
</p>

<p style="font-size:12px;color:#666">
	The acknowledgement will not accept your signature until the course is
	complete. Your application reference is {{ application_id }}.
</p>

<p style="margin-top:24px">
	Warm regards,<br>
	<strong>Admissions Office</strong><br>
	South India Baptist Bible College &amp; Seminary (Online)<br>
	Coimbatore
</p>
""",
}


def _manual_fields():
	return add_fields(
		"Reading Manual",
		[
			select(
				"delivery",
				"Delivered As",
				["Document", "LMS Course"],
				default="Document",
				description=(
					"A Document is read on the acknowledgement page. An LMS Course "
					"enrols the candidate and holds their signature back until every "
					"lesson is complete."
				),
			),
			link(
				"lms_course",
				"LMS Course",
				"LMS Course",
				depends_on="eval:doc.delivery=='LMS Course'",
			),
		],
		insert_after="require_scroll",
	)


def _acknowledgement_fields():
	return add_fields(
		"Manual Acknowledgement",
		[f("signature", "Signature", "Attach Image", read_only=1)],
		insert_after="acknowledged_name",
	)


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


def _manual_record():
	"""The Reading Manual that points at the orientation course."""
	course = frappe.db.get_value("LMS Course", {"title": COURSE_TITLE}, "name")
	if not course:
		print(f"NO COURSE named {COURSE_TITLE!r} -- run phase2j_preliminary_course.build first.")
		return None, False

	if frappe.db.exists("Reading Manual", MANUAL_TITLE):
		frappe.db.set_value(
			"Reading Manual",
			MANUAL_TITLE,
			{"delivery": "LMS Course", "lms_course": course},
			update_modified=False,
		)
		return MANUAL_TITLE, False

	doc = frappe.get_doc(
		{
			"doctype": "Reading Manual",
			"manual_title": MANUAL_TITLE,
			"version": "Jan 2026",
			# Left inactive. Making it active is the college saying the course
			# is ready to send, and that is not a decision a builder should
			# make on their behalf.
			"is_active": 0,
			"require_scroll": 0,
			"delivery": "LMS Course",
			"lms_course": course,
			"content": (
				"<p>This orientation is delivered as a course in the LMS. Work "
				"through every lesson, then sign below.</p>"
			),
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name, True


def build():
	added = _manual_fields() + _acknowledgement_fields()
	made_template = _template()
	frappe.db.commit()
	for doctype in ("Reading Manual", "Manual Acknowledgement"):
		frappe.clear_cache(doctype=doctype)

	manual, made_manual = _manual_record()
	frappe.db.commit()

	print(f"Added: {added or 'nothing new'}")
	print(f"Email Template {TEMPLATE['name']}: {'created' if made_template else 'already present'}")
	if manual:
		state = "created (inactive)" if made_manual else "already present, relinked"
		active = frappe.db.get_value("Reading Manual", manual, "is_active")
		print(f"Reading Manual {manual!r}: {state}; is_active={active}")
		if not active:
			print("  Tick Is Active on it when the course is ready to send.")
