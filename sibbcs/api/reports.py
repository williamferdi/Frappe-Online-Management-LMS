# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""Reports: group any of the console's records and count or total them.

One report that answers many questions rather than twenty that each answer
one. "How many applications per state", "outstanding by fee type", "students
per level", "registrations per term" are the same query with different columns,
and the college will want a twenty-first next month.

The group-by field and the field being totalled are both checked against the
DocType's own metadata before they reach a query -- they end up in `GROUP BY`
and `SUM()`, which is exactly where an unchecked string becomes an injection.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from sibbcs.api.records import EVERY_ALLOWED, _require

# Worth grouping by. A report grouped on a free-text field is one row per
# record with extra steps.
GROUPABLE = {"Select", "Link", "Check", "Data", "Int"}

# Worth totalling.
SUMMABLE = {"Currency", "Float", "Int", "Percent"}


@frappe.whitelist()
def options(doctype):
	"""Which fields this DocType can be grouped by, and which summed."""
	_require(doctype)

	meta = frappe.get_meta(doctype)
	return {
		"doctype": doctype,
		"label": _(doctype),
		"group_by": [
			{"fieldname": df.fieldname, "label": df.label or df.fieldname, "fieldtype": df.fieldtype}
			for df in meta.fields
			if df.fieldtype in GROUPABLE and not cint(df.hidden)
		],
		"aggregate": [
			{"fieldname": df.fieldname, "label": df.label or df.fieldname, "fieldtype": df.fieldtype}
			for df in meta.fields
			if df.fieldtype in SUMMABLE and not cint(df.hidden)
		],
	}


def _checked_field(doctype, fieldname, allowed_types, what):
	"""A fieldname that survives this is one the DocType actually has.

	It is interpolated into SQL after this, so nothing else may.
	"""
	if not fieldname:
		return None

	df = frappe.get_meta(doctype).get_field(fieldname)
	if not df or df.fieldtype not in allowed_types:
		frappe.throw(
			_("{0} cannot be used to {1} {2}.").format(fieldname, what, doctype)
		)
	return df.fieldname


@frappe.whitelist()
def run(doctype, group_by, aggregate=None, filters=None, limit=100):
	"""Count -- and optionally total -- records grouped by one field."""
	_require(doctype)

	group_field = _checked_field(doctype, group_by, GROUPABLE, "group")
	if not group_field:
		frappe.throw(_("Choose a field to group by."))

	sum_field = _checked_field(doctype, aggregate, SUMMABLE, "total")

	if isinstance(filters, str):
		filters = frappe.parse_json(filters)

	fields = [f"`{group_field}` as label", "count(name) as count"]
	if sum_field:
		fields.append(f"sum(`{sum_field}`) as total")

	rows = frappe.get_list(
		doctype,
		filters=filters or {},
		fields=fields,
		group_by=f"`{group_field}`",
		order_by="count desc",
		limit_page_length=min(cint(limit) or 100, 500),
	)

	for row in rows:
		# A NULL group is a real answer -- "no term set" is worth seeing, and
		# dropping it makes the totals disagree with the record count.
		if row.get("label") in (None, ""):
			row["label"] = "(not set)"
		if sum_field:
			row["total"] = flt(row.get("total"), 2)

	return {
		"doctype": doctype,
		"group_by": group_field,
		"aggregate": sum_field,
		"rows": rows,
		"count": sum(cint(row["count"]) for row in rows),
		"total": flt(sum(flt(row.get("total")) for row in rows), 2) if sum_field else None,
	}


@frappe.whitelist()
def catalogue():
	"""What can be reported on, grouped the way the navigation is."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Please sign in."), frappe.PermissionError)

	return sorted(
		doctype for doctype in EVERY_ALLOWED if frappe.has_permission(doctype, "read")
	)
