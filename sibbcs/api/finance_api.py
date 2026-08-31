# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""The finance console: invoices, payments and scholarship decisions.

`fee_invoice.py` derives paid and outstanding from the allocations pointing at
it, `payment_entry.py` knows how to spread one payment across the oldest
invoices, and `scholarship.decide` enforces the programme cap. None of that is
repeated here.

Recording a payment is the one thing this module creates, and it does so
through the document so `validate_allocations` runs -- over-allocating an
invoice is exactly the mistake worth refusing.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, today

MONEY_ROLES = ("System Manager", "Registrar", "Accounts")
SETTLED = ("Paid", "Waived", "Cancelled")

INVOICE_FIELDS = (
	"name", "student", "student_name", "status", "category", "fee_type", "term",
	"gross_amount", "discount_amount", "net_amount", "paid_amount",
	"outstanding_amount", "due_date", "payment_link", "course_registration",
	"admission_application", "creation",
)


def _require_money():
	roles = set(frappe.get_roles())
	if not roles.intersection(MONEY_ROLES):
		frappe.throw(_("You do not have access to finance."), frappe.PermissionError)


# ---------------------------------------------------------------------------
# invoices
# ---------------------------------------------------------------------------


@frappe.whitelist()
def invoices(status=None, category=None, student=None, search=None, overdue=0, limit=200):
	"""The ledger, filtered the way the office actually asks for it."""
	_require_money()

	filters = {}
	if status:
		filters["status"] = status
	if category:
		filters["category"] = category
	if student:
		filters["student"] = student
	if cint(overdue):
		filters["status"] = ("not in", SETTLED)
		filters["due_date"] = ("<", today())

	or_filters = None
	if search:
		like = f"%{search}%"
		or_filters = {
			field: ("like", like) for field in ("name", "student", "student_name")
		}

	rows = frappe.get_all(
		"Fee Invoice",
		filters=filters,
		or_filters=or_filters,
		fields=list(INVOICE_FIELDS),
		order_by="due_date asc, creation desc",
		limit_page_length=cint(limit),
	)

	for row in rows:
		row["overdue"] = bool(
			row.status not in SETTLED
			and row.due_date
			and getdate(row.due_date) < getdate(today())
		)

	return {
		"rows": rows,
		"statuses": _statuses("Fee Invoice"),
		"categories": sorted(
			{row.category for row in frappe.get_all("Fee Invoice", fields=["category"]) if row.category}
		),
		"summary": _summary(),
	}


def _statuses(doctype, fieldname="status"):
	field = frappe.get_meta(doctype).get_field(fieldname)
	return [choice for choice in (field.options or "").split("\n") if choice]


def _summary():
	"""Billed, collected, outstanding -- and the part that is actually late.

	Outstanding on its own reads as a problem when most of it is not due yet.
	"""
	totals = frappe.db.sql(
		"""
		SELECT SUM(net_amount) AS billed,
		       SUM(paid_amount) AS collected,
		       SUM(outstanding_amount) AS outstanding
		FROM `tabFee Invoice` WHERE status != 'Cancelled'
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

	return {
		"billed": flt(totals.billed, 2),
		"collected": flt(totals.collected, 2),
		"outstanding": flt(totals.outstanding, 2),
		"overdue": flt(overdue.amount, 2),
		"overdue_count": cint(overdue.count),
	}


@frappe.whitelist()
def invoice(name):
	"""One invoice, and every payment that has touched it."""
	_require_money()

	record = frappe.db.get_value("Fee Invoice", name, list(INVOICE_FIELDS), as_dict=True)
	if not record:
		frappe.throw(_("Invoice not found."))

	allocations = frappe.get_all(
		"Payment Allocation",
		filters={"fee_invoice": name, "parenttype": "Payment Entry"},
		fields=["name", "parent", "allocated_amount"],
	)

	payments = []
	if allocations:
		entries = {
			row.name: row
			for row in frappe.get_all(
				"Payment Entry",
				filters={"name": ("in", [a.parent for a in allocations])},
				fields=["name", "amount", "mode", "reference_no", "received_on", "reconciled_by"],
			)
		}
		for allocation in allocations:
			entry = entries.get(allocation.parent)
			if entry:
				payments.append({**entry, "allocated_amount": allocation.allocated_amount})
		payments.sort(key=lambda row: row["received_on"] or "", reverse=True)

	return {"invoice": record, "payments": payments}


# ---------------------------------------------------------------------------
# payments
# ---------------------------------------------------------------------------


@frappe.whitelist()
def payments(search=None, days=90, limit=200):
	"""Money received, most recent first."""
	_require_money()

	filters = {}
	if cint(days):
		filters["received_on"] = (">=", add_days(today(), -cint(days)))

	or_filters = None
	if search:
		like = f"%{search}%"
		or_filters = {
			field: ("like", like)
			for field in ("name", "student", "student_name", "reference_no")
		}

	rows = frappe.get_all(
		"Payment Entry",
		filters=filters,
		or_filters=or_filters,
		fields=[
			"name", "student", "student_name", "amount", "mode", "reference_no",
			"received_on", "allocated_amount", "unallocated_amount", "reconciled_by",
		],
		order_by="received_on desc, creation desc",
		limit_page_length=cint(limit),
	)

	return {"rows": rows, "modes": _statuses("Payment Entry", "mode")}


@frappe.whitelist()
def outstanding_for(student):
	"""What a student still owes, oldest first -- the compose screen's list."""
	_require_money()

	return frappe.get_all(
		"Fee Invoice",
		filters={"student": student, "status": ("not in", SETTLED)},
		fields=["name", "fee_type", "category", "term", "net_amount",
		        "outstanding_amount", "due_date"],
		order_by="due_date asc, creation asc",
	)


@frappe.whitelist(methods=["POST"])
def record_payment(student, amount, mode, received_on=None, reference_no=None,
                   remarks=None, allocations=None):
	"""Record money received, and apply it to the invoices it settles.

	Created through the document, so `validate_allocations` runs: allocating
	more than an invoice is owed, or more than the payment is worth, is exactly
	the mistake worth refusing rather than reconciling later.

	With no allocations given, the payment settles the oldest invoices first --
	`auto_allocate` on the document already knows how.
	"""
	_require_money()

	if not frappe.has_permission("Payment Entry", "create"):
		frappe.throw(_("You may not record payments."), frappe.PermissionError)

	if flt(amount) <= 0:
		frappe.throw(_("A payment must be for more than nothing."))

	if isinstance(allocations, str):
		allocations = frappe.parse_json(allocations)

	rows = []
	for row in allocations or []:
		if not (row or {}).get("fee_invoice") or flt(row.get("allocated_amount")) <= 0:
			continue
		rows.append(
			{
				"fee_invoice": row["fee_invoice"],
				"allocated_amount": flt(row["allocated_amount"]),
			}
		)

	doc = frappe.get_doc(
		{
			"doctype": "Payment Entry",
			"student": student,
			"amount": flt(amount),
			"mode": mode,
			"received_on": received_on or today(),
			"reference_no": reference_no,
			"remarks": remarks,
			"allocations": rows,
		}
	)

	if not rows:
		doc.auto_allocate()

	doc.insert()
	frappe.db.commit()

	return {
		"payment": doc.name,
		"amount": doc.amount,
		"allocated": flt(doc.allocated_amount),
		"unallocated": flt(doc.unallocated_amount),
		"settled": [
			{"fee_invoice": row.fee_invoice, "allocated_amount": row.allocated_amount}
			for row in doc.allocations
		],
	}


# ---------------------------------------------------------------------------
# scholarships
# ---------------------------------------------------------------------------


@frappe.whitelist()
def scholarships(status=None):
	"""Requests waiting on the Registrar, and those already decided."""
	_require_money()

	filters = {"status": status} if status else {}
	rows = frappe.get_all(
		"Scholarship Request",
		filters=filters,
		fields=[
			"name", "application", "student", "program", "status",
			"requested_amount", "approved_amount", "monthly_discount",
			"approved_by", "approved_on", "submitted_on", "justification",
		],
		order_by="submitted_on desc, creation desc",
	)

	# The cap is per programme and the Registrar needs it in front of them --
	# `decide` refuses anything above it, and finding that out after typing an
	# amount is a poor way to learn the rule.
	from sibbcs.admissions.scholarship import program_cap

	caps = {}
	for program in {row.program for row in rows if row.program}:
		caps[program] = program_cap(program)

	return {
		"rows": rows,
		"statuses": _statuses("Scholarship Request"),
		"caps": caps,
		"may_decide": bool(frappe.has_permission("Scholarship Request", "write")),
	}
