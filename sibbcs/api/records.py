# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""Generic create, read, edit and delete, driven by Frappe's own metadata.

Forty DocTypes do not need forty hand-written forms. `describe()` hands the
browser the field definitions Frappe already holds -- types, options, mandatory
flags, `depends_on` -- and one React form renders any of them.

That is a wide door, so it is a narrow one by construction:

  * **An allow-list, never a parameter.** `ALLOWED` names every DocType this
    layer will touch. Anything else is refused before a permission is even
    checked, so no crafted request reaches `DocType`, `User`, `File` or the
    password fields on any of them.
  * **`User` is deliberately absent.** It carries `new_password`, `api_key` and
    the role table; generic CRUD over it is how a form ends up setting a
    password. `users_api` handles accounts, and handles them narrowly.
  * **Nothing here passes `ignore_permissions`.** Reads go through
    `frappe.get_list`, which applies permissions and user permissions; writes go
    through the document, which applies permlevels.
"""

import frappe
from frappe import _

from frappe.utils import cint

# What the console may edit, grouped the way the navigation is. The key is the
# section; a DocType absent from every list cannot be reached at all.
ALLOWED = {
	"academic": [
		"Program",
		"Course",
		"Course Offering",
		"Academic Term",
		"Instructor",
		"Grade Scale",
		"Weekday",
		"Program Enrollment",
		"Course Registration",
		"Level Promotion",
	],
	"admissions": [
		"Admission Application",
		"Lead",
		"Qualifying Exam Result",
		"Interview Record",
		"Scholarship Request",
		"Reading Manual",
	],
	"finance": [
		"Fee Type",
		"Fee Invoice",
		"Payment Entry",
	],
	"portal": [
		"Announcement",
		"Portal Message",
	],
}

EVERY_ALLOWED = {name for group in ALLOWED.values() for name in group}

# Layout, not data. The form draws its own sections.
LAYOUT_TYPES = {"Section Break", "Column Break", "Tab Break", "Fold"}

# Never sent to a browser and never accepted from one. A Password field has no
# business in a generic form, and Frappe's own reads of it are deliberate.
NEVER = {"Password", "Button", "Image", "Signature", "Barcode"}

CHILD_TYPES = {"Table", "Table MultiSelect"}


def _require(doctype, ptype="read"):
	"""The allow-list first, then Frappe's own permission check."""
	if doctype not in EVERY_ALLOWED:
		frappe.throw(
			_("{0} cannot be edited from the console.").format(doctype),
			frappe.PermissionError,
		)
	if not frappe.has_permission(doctype, ptype):
		frappe.throw(
			_("You do not have permission to {0} {1}.").format(ptype, doctype),
			frappe.PermissionError,
		)


def _writable_permlevels(doctype):
	"""Which permlevels this user may write on this DocType.

	Read from the permission rows directly. `get_valid_perms` answers the
	main permission question and returns **only level 0**, so using it here
	reported every permlevel-gated field as read-only for everybody --
	including the Registrar the level was granted to.

	Custom DocPerm replaces DocPerm entirely when any row exists for the
	DocType, which is how Frappe itself resolves them.
	"""
	roles = set(frappe.get_roles())

	source = "Custom DocPerm"
	if not frappe.db.count("Custom DocPerm", {"parent": doctype}):
		source = "DocPerm"

	levels = set()
	for perm in frappe.get_all(
		source,
		filters={"parent": doctype, "write": 1},
		fields=["role", "permlevel"],
	):
		if perm.role in roles:
			levels.add(cint(perm.permlevel))

	# Administrator is exempt from permission checks everywhere else in
	# Frappe; it should not be uniquely restricted here.
	if frappe.session.user == "Administrator":
		levels |= {
			cint(df.permlevel) for df in frappe.get_meta(doctype).fields
		}

	return levels


def _field(df, writable_levels):
	return {
		"fieldname": df.fieldname,
		"label": df.label,
		"fieldtype": df.fieldtype,
		"options": df.options,
		"reqd": cint(df.reqd),
		"read_only": cint(df.read_only) or cint(df.permlevel) not in writable_levels,
		"hidden": cint(df.hidden),
		"depends_on": df.depends_on,
		"mandatory_depends_on": df.mandatory_depends_on,
		"default": df.default,
		"description": df.description,
		"permlevel": cint(df.permlevel),
		"precision": df.precision,
		"in_list_view": cint(df.in_list_view),
	}


@frappe.whitelist()
def sections():
	"""What the console may edit, and whether this user may see each one."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Please sign in."), frappe.PermissionError)

	out = {}
	for section, doctypes in ALLOWED.items():
		rows = []
		for doctype in doctypes:
			if not frappe.has_permission(doctype, "read"):
				continue
			meta = frappe.get_meta(doctype)
			rows.append(
				{
					"doctype": doctype,
					"label": _(doctype),
					"is_submittable": cint(meta.is_submittable),
					"can_create": bool(frappe.has_permission(doctype, "create")),
					"can_write": bool(frappe.has_permission(doctype, "write")),
					"can_delete": bool(frappe.has_permission(doctype, "delete")),
					"count": frappe.db.count(doctype),
				}
			)
		if rows:
			out[section] = rows
	return out


@frappe.whitelist()
def describe(doctype):
	"""Every field the form needs to draw itself, in document order."""
	_require(doctype)

	meta = frappe.get_meta(doctype)
	writable = _writable_permlevels(doctype)

	fields = [
		_field(df, writable)
		for df in meta.fields
		if df.fieldtype not in NEVER and not cint(df.hidden)
	]

	# Child tables carry their own field list; the form renders them as a grid.
	children = {}
	for df in meta.fields:
		if df.fieldtype in CHILD_TYPES and df.options:
			child = frappe.get_meta(df.options)
			children[df.fieldname] = [
				_field(cf, {0})
				for cf in child.fields
				if cf.fieldtype not in NEVER and cf.fieldtype not in LAYOUT_TYPES
				and not cint(cf.hidden)
			]

	return {
		"doctype": doctype,
		"label": _(doctype),
		"fields": fields,
		"children": children,
		"title_field": meta.title_field or "name",
		"is_submittable": cint(meta.is_submittable),
		"autoname": meta.autoname,
		"list_fields": [df.fieldname for df in meta.fields if cint(df.in_list_view)],
		"can_create": bool(frappe.has_permission(doctype, "create")),
		"can_write": bool(frappe.has_permission(doctype, "write")),
		"can_delete": bool(frappe.has_permission(doctype, "delete")),
	}


@frappe.whitelist()
def records(doctype, search=None, filters=None, order_by=None, limit=100, start=0):
	"""A page of records.

	`frappe.get_list`, not `get_all`: the first applies this user's permissions
	and any user permissions on top; the second is the one that ignores them.
	"""
	_require(doctype)

	meta = frappe.get_meta(doctype)
	fields = ["name"] + [
		df.fieldname
		for df in meta.fields
		if cint(df.in_list_view)
		and df.fieldtype not in LAYOUT_TYPES
		and df.fieldtype not in NEVER
		and df.fieldtype not in CHILD_TYPES
	]
	if meta.title_field and meta.title_field not in fields:
		fields.append(meta.title_field)
	fields.append("modified")

	if isinstance(filters, str):
		filters = frappe.parse_json(filters)

	or_filters = None
	if search:
		like = f"%{search}%"
		searchable = ["name"] + [
			df.fieldname
			for df in meta.fields
			if df.fieldtype in ("Data", "Small Text") and cint(df.in_list_view)
		]
		or_filters = {field: ("like", like) for field in dict.fromkeys(searchable)}

	limit = min(cint(limit) or 100, 500)
	rows = frappe.get_list(
		doctype,
		filters=filters or {},
		or_filters=or_filters,
		fields=list(dict.fromkeys(fields)),
		order_by=order_by or "modified desc",
		limit_page_length=limit + 1,
		limit_start=cint(start),
	)

	truncated = len(rows) > limit
	return {
		"doctype": doctype,
		"rows": rows[:limit],
		"truncated": truncated,
		"columns": [
			_field(df, {0})
			for df in meta.fields
			if df.fieldname in fields and df.fieldtype not in LAYOUT_TYPES
		],
		"total": frappe.db.count(doctype, filters or {}),
	}


@frappe.whitelist()
def record(doctype, name):
	"""One document, with its child tables."""
	_require(doctype)

	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")

	meta = frappe.get_meta(doctype)
	blocked = {df.fieldname for df in meta.fields if df.fieldtype in NEVER}

	values = {
		key: value
		for key, value in doc.as_dict(convert_dates_to_str=True).items()
		if key not in blocked
	}

	return {"doctype": doctype, "name": doc.name, "values": values}


def _assignable(doctype):
	"""Fields a caller may set: not read-only, not layout, not a password.

	Built from the metadata rather than trusted from the request, so a field
	the form never showed cannot be set by adding it to the payload.
	"""
	meta = frappe.get_meta(doctype)
	writable = _writable_permlevels(doctype)

	return {
		df.fieldname: df
		for df in meta.fields
		if df.fieldtype not in NEVER
		and df.fieldtype not in LAYOUT_TYPES
		and not cint(df.read_only)
		and cint(df.permlevel) in writable
	}


@frappe.whitelist(methods=["POST"])
def save(doctype, values, name=None):
	"""Create or update one document.

	Only fields the metadata says are writable are applied, so a payload naming
	`docstatus`, `owner` or a permlevel-gated field changes nothing. The save
	itself is an ordinary one -- validate, permissions and permlevels all run.
	"""
	_require(doctype, "write" if name else "create")

	if isinstance(values, str):
		values = frappe.parse_json(values)
	if not isinstance(values, dict):
		frappe.throw(_("Values must be an object."))

	allowed = _assignable(doctype)

	if name:
		doc = frappe.get_doc(doctype, name)
		doc.check_permission("write")
	else:
		doc = frappe.new_doc(doctype)

	for fieldname, value in values.items():
		df = allowed.get(fieldname)
		if not df:
			continue
		if df.fieldtype in CHILD_TYPES:
			doc.set(fieldname, [])
			for row in value or []:
				if isinstance(row, dict):
					doc.append(fieldname, row)
		else:
			doc.set(fieldname, value)

	doc.save()
	frappe.db.commit()

	return {"doctype": doctype, "name": doc.name}


@frappe.whitelist(methods=["POST"])
def remove(doctype, name):
	"""Delete one document, link checks and all.

	No `force`: a document something else points at should refuse to go, and
	the message naming what holds it is the useful part.
	"""
	_require(doctype, "delete")

	frappe.delete_doc(doctype, name)
	frappe.db.commit()
	return {"doctype": doctype, "name": name, "deleted": True}


@frappe.whitelist()
def options(doctype, txt=None, limit=20):
	"""Choices for a Link field.

	Permission-checked like everything else: a link picker that lists every
	student to somebody who may not read Student is a leak with a search box.
	"""
	_require(doctype)

	meta = frappe.get_meta(doctype)
	fields = ["name"]
	if meta.title_field and meta.title_field != "name":
		fields.append(meta.title_field)

	or_filters = None
	if txt:
		like = f"%{txt}%"
		or_filters = {field: ("like", like) for field in fields}

	rows = frappe.get_list(
		doctype,
		or_filters=or_filters,
		fields=fields,
		limit_page_length=min(cint(limit) or 20, 50),
		order_by="modified desc",
	)

	return [
		{"value": row["name"], "label": row.get(meta.title_field) or row["name"]}
		for row in rows
	]
