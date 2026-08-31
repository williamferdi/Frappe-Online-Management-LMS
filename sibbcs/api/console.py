# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""The staff console's front page.

Each panel is guarded by role, so a Faculty member sees the academic figures
and no fee collection, and an Accounts user sees the money and no candidate
names. A panel the caller may not have simply is not in the response -- the
console omits the card rather than drawing an empty one that reads as "the
college has no money" instead of "you may not see this".
"""

import frappe

from frappe.utils import add_days, flt, today

from sibbcs.api.admissions_api import funnel
from sibbcs.api.session import STAFF_ROLES

SETTLED_FEE_STATES = ("Paid", "Waived", "Cancelled")
RECENT_DAYS = 30

# Who each panel is for.
#
# Gated on roles, not on `frappe.has_permission(doctype, "read")`. Students hold
# read on Fee Invoice and Program Enrollment -- they have to, to see their own --
# and these panels are SQL aggregates over every row, so a permission check that
# passes for a student would hand them the whole college's billing totals.
PANEL_ROLES = {
	"admissions": ("System Manager", "Registrar", "Admissions Officer", "Academic Coordinator", "Dean"),
	"academic": (
		"System Manager", "Registrar", "Academic Coordinator", "Dean", "Faculty", "Facilitator",
	),
	"finance": ("System Manager", "Registrar", "Accounts"),
}


def _may_see(panel, roles):
	return any(role in roles for role in PANEL_ROLES[panel])


@frappe.whitelist()
def dashboard():
	"""Whatever this user is allowed to see, and nothing else."""
	if frappe.session.user == "Guest":
		frappe.throw(frappe._("Please sign in."), frappe.PermissionError)

	roles = set(frappe.get_roles())
	if not roles.intersection(STAFF_ROLES):
		frappe.throw(
			frappe._("The console is for college staff."), frappe.PermissionError
		)

	panels = {}
	if _may_see("admissions", roles):
		panels["admissions"] = funnel()
	if _may_see("academic", roles):
		panels["academic"] = _academic()
	if _may_see("finance", roles):
		panels["finance"] = _finance()

	return {"panels": panels, "user": frappe.session.user}


def _academic():
	"""Enrolment by level, and how many are actually studying right now."""
	by_level = {
		str(row.current_level or "?"): row.n
		for row in frappe.get_all(
			"Program Enrollment",
			filters={"status": "Active"},
			fields=["current_level", "count(name) as n"],
			group_by="current_level",
		)
	}

	by_program = [
		{"program": row.program, "count": row.n}
		for row in frappe.get_all(
			"Program Enrollment",
			filters={"status": "Active"},
			fields=["program", "count(name) as n"],
			group_by="program",
			order_by="n desc",
		)
	]

	registrations = {
		row.status: row.n
		for row in frappe.get_all(
			"Course Registration",
			fields=["status", "count(name) as n"],
			group_by="status",
		)
	}

	return {
		"students": frappe.db.count("Student", {"status": "Active"}),
		"enrollments": frappe.db.count("Program Enrollment", {"status": "Active"}),
		"by_level": [
			{"level": str(level), "count": by_level.get(str(level), 0)}
			for level in (1, 2, 3, 4)
		],
		"by_program": by_program,
		"registrations": registrations,
		"open_terms": frappe.get_all(
			"Academic Term",
			filters={"status": ("in", ("Open", "Active"))},
			fields=["name", "term_name", "registration_closes"],
			order_by="start_date",
		),
	}


def _finance():
	"""Billed, collected and outstanding -- plus what is actually overdue.

	Outstanding on its own reads as a problem when most of it is not due yet.
	The overdue figure is the one worth chasing.
	"""
	totals = frappe.db.sql(
		"""
		SELECT
			SUM(net_amount)         AS billed,
			SUM(paid_amount)        AS collected,
			SUM(outstanding_amount) AS outstanding
		FROM `tabFee Invoice`
		WHERE status != 'Cancelled'
		""",
		as_dict=True,
	)[0]

	overdue = frappe.db.sql(
		"""
		SELECT SUM(outstanding_amount) AS amount, COUNT(name) AS count
		FROM `tabFee Invoice`
		WHERE status NOT IN ('Paid', 'Waived', 'Cancelled')
		  AND due_date IS NOT NULL AND due_date < %(today)s
		""",
		{"today": today()},
		as_dict=True,
	)[0]

	by_category = [
		{"category": row.category or row.fee_type or "Other", "outstanding": flt(row.amount, 2)}
		for row in frappe.get_all(
			"Fee Invoice",
			filters={"status": ("not in", SETTLED_FEE_STATES)},
			fields=["category", "fee_type", "sum(outstanding_amount) as amount"],
			group_by="category, fee_type",
			order_by="amount desc",
		)
	]

	recent = frappe.get_all(
		"Payment Entry",
		filters={"received_on": (">=", add_days(today(), -RECENT_DAYS))},
		fields=["name", "student_name", "amount", "mode", "received_on"],
		order_by="received_on desc",
		limit_page_length=8,
	)

	return {
		"billed": flt(totals.billed, 2),
		"collected": flt(totals.collected, 2),
		"outstanding": flt(totals.outstanding, 2),
		"overdue": flt(overdue.amount, 2),
		"overdue_count": overdue.count or 0,
		"by_category": by_category,
		"recent_payments": recent,
		"days": RECENT_DAYS,
	}
