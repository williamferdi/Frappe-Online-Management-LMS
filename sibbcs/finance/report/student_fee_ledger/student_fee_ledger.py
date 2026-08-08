# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""Student Fee Ledger -- the "who paid what" answer.

Architecture doc §2.4 is explicit that this is a **report, not a DocType**:
invoices and payments are the records; the ledger is a view over them with a
running balance.
"""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 100},
		{"label": _("Type"), "fieldname": "entry_type", "fieldtype": "Data", "width": 90},
		{
			"label": _("Reference"),
			"fieldname": "reference",
			"fieldtype": "Dynamic Link",
			"options": "reference_doctype",
			"width": 170,
		},
		{
			"label": _("Reference DocType"),
			"fieldname": "reference_doctype",
			"fieldtype": "Data",
			"hidden": 1,
		},
		{"label": _("Particulars"), "fieldname": "particulars", "fieldtype": "Data", "width": 220},
		{"label": _("Term"), "fieldname": "term", "fieldtype": "Link", "options": "Academic Term", "width": 100},
		{"label": _("Charge"), "fieldname": "charge", "fieldtype": "Currency", "width": 110},
		{"label": _("Credit"), "fieldname": "credit", "fieldtype": "Currency", "width": 110},
		{"label": _("Balance"), "fieldname": "balance", "fieldtype": "Currency", "width": 120},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
	]


def get_data(filters):
	if not filters.get("student"):
		frappe.throw(_("Select a student."))

	student = filters.student
	rows = []

	invoice_filters = {"student": student, "status": ("!=", "Cancelled")}
	if filters.get("from_date"):
		invoice_filters["due_date"] = (">=", filters.from_date)

	for invoice in frappe.get_all(
		"Fee Invoice",
		filters=invoice_filters,
		fields=[
			"name", "due_date", "creation", "fee_type", "term",
			"gross_amount", "discount_amount", "net_amount", "status",
		],
		order_by="due_date asc, creation asc",
	):
		particulars = invoice.fee_type
		if flt(invoice.discount_amount):
			particulars += _(" (scholarship −{0})").format(flt(invoice.discount_amount, 2))

		rows.append(
			{
				"date": invoice.due_date,
				"sort_key": (invoice.due_date, invoice.creation),
				"entry_type": _("Invoice"),
				"reference": invoice.name,
				"reference_doctype": "Fee Invoice",
				"particulars": particulars,
				"term": invoice.term,
				"charge": flt(invoice.net_amount),
				"credit": 0.0,
				"status": invoice.status,
			}
		)

	for payment in frappe.get_all(
		"Payment Entry",
		filters={"student": student},
		fields=["name", "received_on", "creation", "amount", "mode", "reference_no"],
		order_by="received_on asc, creation asc",
	):
		particulars = payment.mode or _("Payment")
		if payment.reference_no:
			particulars += f" · {payment.reference_no}"

		rows.append(
			{
				"date": payment.received_on,
				"sort_key": (payment.received_on, payment.creation),
				"entry_type": _("Payment"),
				"reference": payment.name,
				"reference_doctype": "Payment Entry",
				"particulars": particulars,
				"term": None,
				"charge": 0.0,
				"credit": flt(payment.amount),
				"status": "",
			}
		)

	rows.sort(key=lambda r: r["sort_key"])

	balance = 0.0
	for row in rows:
		balance += flt(row["charge"]) - flt(row["credit"])
		row["balance"] = flt(balance, 2)
		row.pop("sort_key", None)

	if rows:
		rows.append(
			{
				"particulars": _("Closing balance"),
				"charge": flt(sum(flt(r["charge"]) for r in rows), 2),
				"credit": flt(sum(flt(r["credit"]) for r in rows), 2),
				"balance": flt(balance, 2),
				"entry_type": "",
				"status": _("Outstanding") if balance > 0 else _("Settled"),
			}
		)

	return rows
