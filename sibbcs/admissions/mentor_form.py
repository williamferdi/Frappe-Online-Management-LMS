"""The Mentor Consent Form -- SIBBCS Online Programs.

The questions and the introduction are the college's own, from their existing
mentor form.

TWO THINGS TAKEN FROM CONFIG, NOT HARDCODED:
the mentor role description and the Mentor Handbook are linked from the
introduction, but the source form showed only the link text. Set them with:

    bench --site online.sibbc.org set-config mentor_role_description_url '<url>'
    bench --site online.sibbc.org set-config mentor_handbook_url '<url>'

Until set, the sentence renders without a hyperlink rather than pointing a
mentor at a dead address.
"""

import json

import frappe
from frappe import _

GENDERS = ["Male", "Female"]

# fieldname, label, kind, required
# kind: text | textarea | number | select | image
FIELDS = [
	("mentor_name", "Mentor Full Name", "text", True),
	("mentor_mobile", "Mentor Phone", "text", True),
	("mentor_email", "Mentor Email", "text", True),
	("mentor_gender", "Mentor Gender", "select", True),
	("mentor_age", "Mentor Age", "number", True),
	("mentor_image", "Mentor Image", "image", False),
	("current_position", "Mentor's Current Position in Ministry", "textarea", True),
	("denomination", "Mentor Denomination", "text", True),
	("address_line_1", "Address Line 1", "text", True),
	("address_line_2", "Address Line 2", "text", False),
	("city", "City / District", "text", True),
	("state", "State / Province", "text", True),
	("postal_code", "Postal Code", "text", True),
	("country", "Country", "text", True),
	("prior_theological_education", "Any Prior Theological Education?", "textarea", True),
	("mentoring_experience", "Any Mentoring Experience?", "textarea", True),
	("years_of_ministry", "Years of Ministry Experience", "number", True),
]

BY_FIELD = {f[0]: f for f in FIELDS}

# Everything the mentor may write. mentor_image is handled separately, through
# the upload endpoint, because it is a file rather than a value.
WRITABLE = [f[0] for f in FIELDS if f[2] != "image"] + ["handbook_acknowledged"]

MAX_LEN = {
	"mentor_name": 140,
	"mentor_mobile": 20,
	"mentor_email": 140,
	"denomination": 140,
	"address_line_1": 140,
	"address_line_2": 140,
	"city": 100,
	"state": 100,
	"postal_code": 20,
	"country": 100,
	"current_position": 500,
	"prior_theological_education": 500,
	"mentoring_experience": 500,
}


def intro_parts():
	"""The introduction, split so the template can hyperlink the two documents."""
	return {
		"lead": (
			"Dear Mentor, thank you for your willingness to complete this form. "
			"Mentoring is a sacred and meaningful responsibility, and we are "
			"grateful for your partnership in shaping a student's spiritual and "
			"ministerial growth. Before filling out the form, please take a "
			"moment to review the mentor role description."
		),
		"role_url": frappe.conf.get("mentor_role_description_url") or "",
		"handbook_url": frappe.conf.get("mentor_handbook_url") or "",
		"tail": (
			"Please read the handbook thoroughly. This handbook is intended to "
			"serve as the primary guide for mentoring the student in accordance "
			"with the guidelines and expectations of SIBBCS."
		),
	}


def fields_for_render():
	return [
		{
			"fieldname": name,
			"label": label,
			"kind": kind,
			"required": required,
			"options": GENDERS if name == "mentor_gender" else [],
		}
		for name, label, kind, required in FIELDS
	]


def validate_answers(answers):
	"""Required fields present, values sane, lengths capped."""
	cleaned = {}

	for name, label, kind, required in FIELDS:
		if kind == "image":
			continue

		value = answers.get(name)
		value = "" if value is None else str(value).strip()

		if required and not value:
			frappe.throw(_("Please fill in: {0}").format(label), title=_("Incomplete"))

		if not value:
			continue

		if kind == "number":
			if not value.isdigit():
				frappe.throw(
					_("{0} should be a number.").format(label), title=_("Invalid Value")
				)
			number = int(value)
			if name == "mentor_age" and not 16 <= number <= 120:
				frappe.throw(_("Please check the mentor's age."), title=_("Invalid Value"))
			if name == "years_of_ministry" and not 0 <= number <= 90:
				frappe.throw(
					_("Please check the years of ministry experience."),
					title=_("Invalid Value"),
				)
			cleaned[name] = number
			continue

		if kind == "select" and value not in GENDERS:
			frappe.throw(_("Please choose a valid {0}.").format(label))

		cleaned[name] = value[: MAX_LEN.get(name, 500)]

	if cleaned.get("mentor_email"):
		frappe.utils.validate_email_address(cleaned["mentor_email"], throw=True)

	cleaned["handbook_acknowledged"] = (
		1 if str(answers.get("handbook_acknowledged")) in ("1", "true", "on", "yes") else 0
	)

	return cleaned


def submit(token, answers):
	"""Record a completed mentor consent against its token."""
	from sibbcs.admissions.tokens import mark_submitted

	if isinstance(answers, str):
		answers = json.loads(answers)

	cleaned = validate_answers(answers)

	# Only fields the mentor is allowed to write; mark_submitted also filters
	# against the row's meta, so this is belt and braces.
	values = {k: v for k, v in cleaned.items() if k in WRITABLE}

	return mark_submitted("mentor-consent", token, values)


def format_answers(row):
	"""Readable HTML of a completed mentor form, for the Desk viewer."""
	parts = []
	for name, label, kind, _required in FIELDS:
		if kind == "image":
			continue
		value = row.get(name)
		if value in (None, "", 0) and name != "years_of_ministry":
			continue
		parts.append(
			"<tr>"
			f"<td style='padding:6px 14px 6px 0;vertical-align:top;color:var(--text-muted)'>{label}</td>"
			f"<td style='padding:6px 0;vertical-align:top'><b>{frappe.utils.escape_html(str(value))}</b></td>"
			"</tr>"
		)

	parts.append(
		"<tr><td style='padding:6px 14px 6px 0;color:var(--text-muted)'>Handbook read</td>"
		f"<td style='padding:6px 0'><b>{'Yes' if row.get('handbook_acknowledged') else 'No'}</b></td></tr>"
	)

	table = "<table style='width:100%'>" + "".join(parts) + "</table>"

	if row.get("mentor_image"):
		table = (
			f"<div style='margin-bottom:14px'><img src='{row.get('mentor_image')}' "
			"style='max-width:140px;border-radius:6px'></div>" + table
		)

	return table


@frappe.whitelist()
def view(application, row):
	"""Desk: show one completed mentor form in readable form."""
	doc = frappe.get_doc("Admission Application", application)
	doc.check_permission("read")

	target = next((r for r in doc.mentor_consents if r.name == row), None)
	if not target:
		frappe.throw(_("Mentor form not found."))

	return {
		"mentor": target.mentor_name,
		"email": target.mentor_email,
		"consented_on": str(target.consented_on) if target.consented_on else None,
		"html": format_answers(target),
	}
