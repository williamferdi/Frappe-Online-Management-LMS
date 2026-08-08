"""Small helpers for declaring DocTypes in code.

Phase 1 builds its masters by inserting DocType documents rather than by
hand-writing JSON: Frappe validates the definition on insert and, with
developer_mode on, writes the canonical JSON into the module folder itself.
Those generated JSON files are the committed source of truth; this module is
the reproducible recipe that produces them.
"""

import frappe

# ---------------------------------------------------------------------------
# permission presets
# ---------------------------------------------------------------------------

# Every flag is stated explicitly, including the zeros. Omitting a flag does NOT
# mean "denied": frappe's DocPerm fields carry their own defaults, and a partial
# row silently came back with create/write/delete set to 1. That is how Students
# ended up able to create Courses and Level Promotions.
_ALL_FLAGS = (
	"read", "write", "create", "delete", "submit", "cancel", "amend",
	"report", "export", "import", "print", "email", "share", "set_user_permissions",
)


def _perm(**granted):
	row = {flag: 0 for flag in _ALL_FLAGS}
	row.update(granted)
	return row


_FULL = _perm(
	read=1, write=1, create=1, delete=1,
	report=1, export=1, print=1, email=1, share=1,
)

_EDIT = _perm(
	read=1, write=1,
	report=1, export=1, print=1, email=1, share=1,
)

_READ = _perm(read=1, report=1, print=1, email=1)


def full(role):
	"""Create, read, write, delete."""
	return dict(role=role, **_FULL)


def edit(role):
	"""Read and write existing records, but not create or delete them."""
	return dict(role=role, **_EDIT)


def read(role):
	"""Read only."""
	return dict(role=role, **_READ)


def level(role, permlevel, write=1):
	"""Access to a restricted permlevel.

	Fields carrying `permlevel: N` are invisible unless a permission row exists
	for that role at that level. Used to lock Program Enrollment.current_level
	to the Registrar and Academic Coordinator, and Course Registration's grade
	fields to Faculty and above.
	"""
	row = _perm(read=1, write=1 if write else 0)
	row["role"] = role
	row["permlevel"] = permlevel
	return row


# ---------------------------------------------------------------------------
# field shorthands
# ---------------------------------------------------------------------------


def f(fieldname, label, fieldtype="Data", **kw):
	field = {"fieldname": fieldname, "label": label, "fieldtype": fieldtype}
	field.update(kw)
	return field


def section(fieldname, label=None, **kw):
	return f(fieldname, label, "Section Break", **kw)


def column(fieldname):
	return f(fieldname, None, "Column Break")


def link(fieldname, label, target, **kw):
	return f(fieldname, label, "Link", options=target, **kw)


def select(fieldname, label, choices, **kw):
	"""`choices` is a list; a leading "" renders as an empty first option."""
	return f(fieldname, label, "Select", options="\n".join(choices), **kw)


def check(fieldname, label, default=0, **kw):
	return f(fieldname, label, "Check", default=str(default), **kw)


def table(fieldname, label, child_doctype, **kw):
	return f(fieldname, label, "Table", options=child_doctype, **kw)


def multiselect(fieldname, label, child_doctype, **kw):
	return f(fieldname, label, "Table MultiSelect", options=child_doctype, **kw)


def fetched(fieldname, label, source, fieldtype="Data", **kw):
	"""A read-only mirror of a field on a linked document."""
	return f(
		fieldname,
		label,
		fieldtype,
		fetch_from=source,
		read_only=1,
		**kw,
	)


# ---------------------------------------------------------------------------
# doctype creation
# ---------------------------------------------------------------------------


def ensure_module(module, app="sibbcs"):
	if not frappe.db.exists("Module Def", module):
		frappe.get_doc(
			{
				"doctype": "Module Def",
				"module_name": module,
				"app_name": app,
			}
		).insert(ignore_permissions=True)
	return module


def ensure_role(role, desk_access=1):
	if not frappe.db.exists("Role", role):
		frappe.get_doc(
			{
				"doctype": "Role",
				"role_name": role,
				"desk_access": desk_access,
			}
		).insert(ignore_permissions=True)
	return role


def ensure_doctype(name, module, fields, permissions=None, **kw):
	"""Insert a DocType if absent; return it either way.

	Idempotent so the whole Phase 1 build can be re-run safely. Existing
	DocTypes are left untouched -- use `add_fields` for incremental changes so
	that a re-run never silently discards manual edits.
	"""
	if frappe.db.exists("DocType", name):
		return frappe.get_doc("DocType", name)

	definition = {
		"doctype": "DocType",
		"name": name,
		"module": module,
		"custom": 0,
		"engine": "InnoDB",
		"track_changes": 1,
		"fields": fields,
		"permissions": permissions or [],
	}
	definition.update(kw)

	doc = frappe.get_doc(definition)
	doc.insert(ignore_permissions=True)
	return doc


def add_fields(doctype, fields, insert_after=None):
	"""Append fields to an existing DocType, skipping ones already present.

	Used to close definition cycles: Course cannot declare its prerequisite
	table until Course Prerequisite exists, and Course Prerequisite links back
	to Course, so Course is created first and extended afterwards.
	"""
	doc = frappe.get_doc("DocType", doctype)
	existing = {row.fieldname for row in doc.fields}
	added = []

	for field in fields:
		if field["fieldname"] in existing:
			continue
		row = doc.append("fields", field)
		if insert_after:
			# move the new row directly after the named field
			target = next(
				(i for i, r in enumerate(doc.fields) if r.fieldname == insert_after), None
			)
			if target is not None:
				doc.fields.remove(row)
				doc.fields.insert(target + 1, row)
				for i, r in enumerate(doc.fields):
					r.idx = i + 1
		added.append(field["fieldname"])

	if added:
		doc.save(ignore_permissions=True)
	return added
