"""Remap the payment mode `Razorpay` onto the vendor-neutral `Online`.

`Payment Entry.mode` offered a brand as one of its five options. The builder
was corrected to `PAYMENT_MODES = ["Online", "UPI", ...]` when the gateway was
made pluggable, and `razorpay.webhook` writes `"mode": "Online"` -- but
`ensure_doctype` leaves an existing DocType untouched, so the option list in the
database never moved. The webhook therefore could not insert a Payment Entry at
all: `Online` is not one of the stored options and `_validate_selects` refuses
it. Nothing caught this because the whole of `razorpay.py` had no test.

A Select is validated on save, so a row holding an option the field no longer
offers cannot be saved again. This runs **pre_model_sync** -- before the new
option list lands -- so no row is left stranded.

Nothing holds `Razorpay` on either site today (checked 19 Nov 2026: 201 rows on
`test.local`, all Cash / UPI / Bank Transfer; none at all on production). The
patch exists for a restored backup, and because the next person to read
`PAYMENT_MODES` should not have to wonder whether the data was ever moved.
"""

import frappe

OLD = "Razorpay"
NEW = "Online"


def execute():
	if not frappe.db.has_column("Payment Entry", "mode"):
		return

	rows = frappe.get_all("Payment Entry", filters={"mode": OLD}, pluck="name")
	for name in rows:
		# Straight to the row. Saving the document would re-validate a payment
		# that was reconciled long ago, and the allocation rules have moved
		# since; renaming a mode is no reason to re-litigate the money.
		frappe.db.set_value("Payment Entry", name, "mode", NEW, update_modified=False)

	print(
		f"Payment mode {OLD!r} -> {NEW!r}: {len(rows)} row(s) remapped."
		if rows
		else f"Payment mode: no row holds {OLD!r}, nothing to remap."
	)
