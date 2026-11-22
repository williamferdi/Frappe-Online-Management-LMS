# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""Take the Desk away from students, which nobody meant to give them.

`conversion._create_user` asks for `"user_type": "Website User"` in as many
words. Frappe overrode it: a user who holds **any** role with `desk_access`
is promoted to System User on save, and the Student role was created with
the `ensure_role` default of 1. So every student the college has onboarded
could open `/app`, and on 21 Nov 2026 both of them could.

Two steps, in this order. The role first, or Frappe re-promotes the users
from under us on the next save.

**Who is demoted is deliberately narrow.** Only a user whose roles are
*nothing but* Student. A registrar who is also enrolled, or staff who were
given the Student role to see the portal, keep their desk -- losing it would
lock a member of staff out of their own console, which is a worse fault than
the one being fixed. `_only_a_student` in `academic.permissions` is not the
test to use here: it asks whether anything **teaching** outranks Student, so
a Registrar passes it, and a patch that trusted it would demote the registrar.
"""

import frappe

# Roles that say nothing about a person: everybody has them.
BACKGROUND_ROLES = {"All", "Guest", "Desk User"}


def execute():
	if frappe.db.exists("Role", "Student"):
		frappe.db.set_value("Role", "Student", "desk_access", 0, update_modified=False)

	for user in frappe.get_all(
		"User", filters={"enabled": 1, "user_type": "System User"}, pluck="name"
	):
		if user == "Administrator":
			continue

		roles = set(frappe.get_roles(user)) - BACKGROUND_ROLES
		if roles != {"Student"}:
			continue

		frappe.db.set_value("User", user, "user_type", "Website User", update_modified=False)

	# The roles are cached per user, and a stale cache would let somebody who
	# has just been demoted keep a desk session until it expired.
	frappe.clear_cache()
