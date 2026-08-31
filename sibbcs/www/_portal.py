# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""Boots the React app.

`website_route_rules` in hooks.py points every /portal/... and /console/...
address at this page, so a deep link or a refresh lands here and the router
takes it from there.

The HTML is generated -- `yarn build` writes `_portal.html` from the Vite
output and appends the Jinja loop that turns this context into globals. Do not
hand-edit it; the next build overwrites it.
"""

import frappe

from sibbcs.api.session import session_payload

no_cache = 1


def get_context(context):
	context.no_cache = 1
	context.boot = get_boot()

	# Minting a CSRF token writes to the session. Without a commit the token in
	# the page and the one on the server disagree on the very first request,
	# and every write from a freshly loaded page is rejected.
	frappe.db.commit()

	return context


def get_boot():
	payload = session_payload()
	payload["csrf_token"] = frappe.sessions.get_csrf_token()
	return payload
