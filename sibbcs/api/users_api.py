# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""Accounts and roles.

The narrowest module here, deliberately. Roles decide who may read a
candidate's file, approve a promotion or see the college's billing, so this
grants and revokes only the roles the college actually uses, only for a System
Manager, and refuses to touch anything else.

Three things it will not do, all of them on purpose:

  * **Passwords.** Frappe owns those. There is no endpoint here that sets,
    resets or reads one; the reset link is sent from Desk or by the user
    themselves.
  * **System Manager.** Granting that from a web form is how one compromised
    account becomes every account. It is a Desk action, deliberately.
  * **Deleting accounts.** A User is linked to a Student, a Payment Entry, an
    audit trail. Disabling is reversible and keeps the history; deleting is
    neither.
"""

import frappe
from frappe import _
from frappe.utils import cint

# The roles this screen manages. `setup/permissions.py` is the source of truth
# for what each one may do; this is the subset an administrator may hand out.
MANAGED_ROLES = (
	"Registrar",
	"Admissions Officer",
	"Academic Coordinator",
	"Dean",
	"Faculty",
	"Facilitator",
	"Formation Coordinator",
	"Accounts",
	"Student",
)

# Held by accounts this screen shows but must never grant or revoke.
PROTECTED_ROLES = ("System Manager", "Administrator")

# Frappe's own accounts. Neither is a person.
RESERVED_USERS = ("Administrator", "Guest")


def _require_admin():
	"""Only a System Manager changes who can do what."""
	if "System Manager" not in frappe.get_roles():
		frappe.throw(
			_("Only a System Manager may manage accounts."), frappe.PermissionError
		)


@frappe.whitelist()
def users(search=None, role=None, enabled=None, limit=200):
	"""Every account, with the roles it holds."""
	_require_admin()

	filters = {"name": ("not in", RESERVED_USERS)}
	if enabled in (0, 1, "0", "1"):
		filters["enabled"] = cint(enabled)

	or_filters = None
	if search:
		like = f"%{search}%"
		or_filters = {
			field: ("like", like) for field in ("name", "full_name", "username")
		}

	rows = frappe.get_all(
		"User",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "full_name", "enabled", "user_type", "last_active", "creation"],
		order_by="full_name asc",
		limit_page_length=cint(limit),
	)
	if not rows:
		return _page([])

	held = {}
	for entry in frappe.get_all(
		"Has Role",
		filters={"parent": ("in", [r.name for r in rows]), "parenttype": "User"},
		fields=["parent", "role"],
	):
		held.setdefault(entry.parent, []).append(entry.role)

	for row in rows:
		everything = sorted(held.get(row.name, []))
		# Frappe gives every account All, Guest and often Desk User. They say
		# nothing about what somebody does here, and listing them buries the
		# roles that matter.
		row["roles"] = [r for r in everything if r in MANAGED_ROLES]
		row["protected_roles"] = [r for r in everything if r in PROTECTED_ROLES]
		row["student"] = frappe.db.get_value("Student", {"user": row.name}, "name")

	if role:
		rows = [r for r in rows if role in r["roles"] or role in r["protected_roles"]]

	return _page(rows)


def _page(rows):
	return {
		"rows": rows,
		"managed_roles": list(MANAGED_ROLES),
		"protected_roles": list(PROTECTED_ROLES),
	}


@frappe.whitelist(methods=["POST"])
def set_roles(user, roles):
	"""Set which of the managed roles an account holds.

	Only the managed list is touched. A System Manager grant is left exactly as
	it was found, whether or not the browser sent it -- so a crafted request
	cannot use this to promote anybody, and an honest one cannot drop a role it
	never displayed.
	"""
	_require_admin()

	if user in RESERVED_USERS:
		frappe.throw(_("{0} is a system account.").format(user))
	if not frappe.db.exists("User", user):
		frappe.throw(_("Account not found."))

	if isinstance(roles, str):
		roles = frappe.parse_json(roles)
	if not isinstance(roles, list):
		frappe.throw(_("Roles must be a list."))

	wanted = {role for role in roles if role in MANAGED_ROLES}
	refused = sorted({role for role in roles if role not in MANAGED_ROLES})
	if refused:
		frappe.throw(
			_("These roles are not managed here: {0}").format(", ".join(refused)),
			title=_("Not Allowed"),
		)

	doc = frappe.get_doc("User", user)
	current = {row.role for row in doc.get("roles") or []}

	keep = {role for role in current if role not in MANAGED_ROLES}
	doc.set("roles", [{"role": role} for role in sorted(keep | wanted)])
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	after = {row.role for row in doc.get("roles") or []}
	return {
		"user": user,
		"roles": sorted(role for role in after if role in MANAGED_ROLES),
		"granted": sorted(wanted - current),
		"revoked": sorted((current & set(MANAGED_ROLES)) - wanted),
	}


@frappe.whitelist(methods=["POST"])
def set_enabled(user, enabled):
	"""Turn an account on or off.

	Disabling, never deleting. A User is linked to a Student, to payments and
	to an audit trail; disabling is reversible and keeps all of it.
	"""
	_require_admin()

	if user in RESERVED_USERS:
		frappe.throw(_("{0} is a system account.").format(user))
	if user == frappe.session.user:
		# Locking yourself out is a support call, not a feature.
		frappe.throw(_("You cannot disable your own account."))
	if not frappe.db.exists("User", user):
		frappe.throw(_("Account not found."))

	frappe.db.set_value("User", user, "enabled", cint(enabled))
	frappe.db.commit()

	return {"user": user, "enabled": cint(enabled)}


@frappe.whitelist()
def role_summary():
	"""How many accounts hold each managed role.

	Worth seeing: an empty Registrar row is why a student's message has nowhere
	to go and why nobody can approve a promotion.
	"""
	_require_admin()

	counts = {role: 0 for role in MANAGED_ROLES}
	for entry in frappe.get_all(
		"Has Role",
		filters={"role": ("in", list(MANAGED_ROLES)), "parenttype": "User"},
		fields=["role", "parent"],
	):
		if frappe.db.get_value("User", entry.parent, "enabled"):
			counts[entry.role] = counts.get(entry.role, 0) + 1

	return [{"role": role, "count": counts[role]} for role in MANAGED_ROLES]
