# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""Saying so when a list is cut short.

Every list endpoint here caps its rows. Returning the cap silently means a
Registrar searching a common name gets two hundred results, no sign there are
four hundred, and no reason to doubt what is on screen. One extra row is
fetched so the caller can be told.
"""

import frappe
from frappe.utils import cint


def fetch_capped(doctype, limit, **kwargs):
	"""`frappe.get_all` with an honest answer about the cap.

	Returns `(rows, truncated)`. One row beyond the limit is asked for and
	thrown away -- cheaper than a second COUNT query, and enough to know.
	"""
	limit = cint(limit) or 200
	kwargs["limit_page_length"] = limit + 1

	rows = frappe.get_all(doctype, **kwargs)
	truncated = len(rows) > limit
	return rows[:limit], truncated
