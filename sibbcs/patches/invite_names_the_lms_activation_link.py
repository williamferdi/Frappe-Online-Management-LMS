"""Move the applicant invitation onto the LMS activation link.

`lms_account_invite` is an Email Template, so the Admissions Office can reword
it in Desk -- and the builder is idempotent and never overwrites an existing
one. That is right for wording and wrong for a variable name: the template
referenced `{{ password_link }}`, which `send_invite` stopped passing on 19 Nov
2026, and `render_template` leaves an unknown variable as literal text rather
than failing. Every invitation would have gone out with the characters
`{{ password_link }}` printed where the button should be, and no working link
anywhere in the message.

So this one must move, on every site, and only where it still names
`password_link` -- a template somebody has already reworded is left as they
wrote it.

**Both fields.** `render_template` reads `response_html` first and falls back to
`response`, and the builder fills both. Rewriting only `response` changes
nothing about what is actually sent, which is how the first version of this
patch passed its own check and sent the old email anyway.

Why the variable changed: the entrance exam is sat in Campus LMS Lite. The
invitation used to carry a Frappe `/update-password` link, so a candidate set a
password on a portal where they hold no roles and nothing to read, while the
LMS activation link they actually needed went into the officer's report and was
never sent.
"""

import frappe

TEMPLATE = "lms_account_invite"
OLD_VARIABLE = "password_link"


def execute():
	if not frappe.db.exists("Email Template", TEMPLATE):
		# Not every site has run the builder. The next build seeds the new one.
		return

	doc = frappe.get_doc("Email Template", TEMPLATE)
	stale = OLD_VARIABLE in (doc.response or "") or OLD_VARIABLE in (doc.response_html or "")
	if not stale:
		return

	from sibbcs.setup.phase2e_lms_account import TEMPLATE as SEED

	doc.response = SEED["response"]
	doc.response_html = SEED["response"]
	doc.flags.ignore_permissions = True
	doc.save(ignore_permissions=True)

	frappe.logger("sibbcs").info(
		f"{TEMPLATE} rewritten: it still named {OLD_VARIABLE}, which is no longer passed"
	)
