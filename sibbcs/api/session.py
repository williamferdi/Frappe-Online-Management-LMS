# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""What the front end needs to know before it renders anything.

`boot()` is called two ways and must answer identically both times:

  - by `www/_portal.py`, whose result Jinja writes into the page as globals, so
    the app has a session on first paint without a round trip;
  - over HTTP, after signing in, when the page was not re-rendered.

Nothing here is a permission decision. It reports the roles a user already has
so navigation can be drawn; every endpoint still checks its own permissions.
"""

import frappe

# Roles that get the staff console. Mirrors `setup/permissions.py`, plus Dean,
# which `level_promotion.APPROVER_ROLES` recognises but the matrix does not name.
STAFF_ROLES = (
	"System Manager",
	"Registrar",
	"Admissions Officer",
	"Academic Coordinator",
	"Dean",
	"Faculty",
	"Facilitator",
	"Formation Coordinator",
	"Accounts",
)


def _student_context(user):
	"""The student record and active enrollment behind a login, if any."""
	if user == "Guest":
		return None, None

	student = frappe.db.get_value("Student", {"user": user}, "name")
	if not student:
		return None, None

	enrollment = frappe.db.get_value(
		"Program Enrollment", {"student": student, "status": "Active"}, "name"
	)
	return student, enrollment


def session_payload():
	"""Plain dict, safe to embed in a page or return over HTTP."""
	user = frappe.session.user
	roles = frappe.get_roles(user)
	student, enrollment = _student_context(user)

	details = {}
	if user != "Guest":
		details = (
			frappe.db.get_value("User", user, ["full_name", "user_image"], as_dict=True) or {}
		)

	return {
		"user": user,
		"full_name": details.get("full_name") or user,
		"user_image": details.get("user_image") or "",
		"roles": roles,
		"is_staff": any(role in roles for role in STAFF_ROLES),
		"is_student": "Student" in roles,
		"student": student or "",
		"enrollment": enrollment or "",
		"site_name": frappe.local.site,
		"app_version": frappe.get_attr("sibbcs.__version__") or "",
	}


@frappe.whitelist(allow_guest=True)
def boot():
	return session_payload()
