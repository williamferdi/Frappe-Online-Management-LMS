"""Tell the mentor the handbook is attached.

`notifications.send_mentor_row` attaches the Mentor Handbook from 19 Nov 2026,
and an attachment nobody is told about is an attachment nobody opens. The
wording lives in an Email Template so the Admissions Office can reword it, and
the builder never overwrites an existing one -- so a template seeded before the
handbook existed has to be brought forward once.

**Both fields.** `render_template` reads `response_html` first and falls back to
`response`. The first attempt at this edited only `response`, which is not the
field that is sent, so the live email went out unchanged while everything
reported success.

Left alone where the mentor is already told, so a rewording survives.
"""

import frappe

TEMPLATE = "mentor_consent_request"
MARKER = "Mentor Handbook"


def execute():
	if not frappe.db.exists("Email Template", TEMPLATE):
		return

	doc = frappe.get_doc("Email Template", TEMPLATE)
	if MARKER in (doc.response_html or "") and MARKER in (doc.response or ""):
		return

	from sibbcs.setup.phase2_email_templates import TEMPLATES

	seed = next((t for t in TEMPLATES if t["name"] == TEMPLATE), None)
	if not seed:
		return

	doc.response = seed["response"]
	doc.response_html = seed["response"]
	doc.flags.ignore_permissions = True
	doc.save(ignore_permissions=True)

	frappe.logger("sibbcs").info(f"{TEMPLATE} rewritten to name the attached handbook")
