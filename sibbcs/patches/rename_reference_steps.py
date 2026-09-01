"""Rename the two reference steps to the names the college uses for them.

"Reference 1" and "Reference 2" said nothing about which reference was which,
so the apply form now asks for a **Spiritual & Ministerial Reference** and an
**Academic & Professional Reference** by name, and the referee's own form is
titled that way. The checklist was the last place still counting them.

The label is stored on every application's rows -- it is a Select, so a row
carrying an option the field no longer offers cannot be saved -- which is why
this is a patch and not simply an edit to `STEPS`.

Matched on the old label and nothing else. `step_no` is a position and would
have been the wrong key: if the steps are ever reordered again, 3 and 4 are
whatever happens to sit there. Safe to re-run -- a row already renamed does not
match the old label, so it is left alone.
"""

import frappe

from sibbcs.admissions.checklist import RENAMED_LABELS


def execute():
	renamed = {}

	for old, new in RENAMED_LABELS.items():
		rows = frappe.get_all(
			"Admission Checklist Item",
			filters={"parenttype": "Admission Application", "step": old},
			pluck="name",
			ignore_permissions=True,
		)
		for name in rows:
			# Written straight to the row: saving the parent would run the
			# application's validation, and an application that is mid-workflow
			# has no business being re-validated by a rename.
			frappe.db.set_value(
				"Admission Checklist Item", name, "step", new, update_modified=False
			)
		if rows:
			renamed[old] = len(rows)

	if renamed:
		for old, count in renamed.items():
			print(f"Checklist step renamed on {count} rows: {old!r} -> {RENAMED_LABELS[old]!r}")
	else:
		print("Checklist steps: nothing to rename.")

	left = frappe.get_all(
		"Admission Checklist Item",
		filters={"parenttype": "Admission Application", "step": ("in", list(RENAMED_LABELS))},
		limit=1,
		ignore_permissions=True,
	)
	if left:
		frappe.throw("Some checklist rows still carry an old reference label.")
