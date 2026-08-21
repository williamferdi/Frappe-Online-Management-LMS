"""The checklist board: one row per step, on the application form.

    bench --site online.sibbc.org execute sibbcs.setup.phase2g_board.build

Idempotent.

The 13 steps were only ever visible as a child-table grid, which is the wrong
shape for them: a grid shows fieldnames and truncated selects, gives no sense
of progress, says nothing about why a step cannot be completed, and puts the
action that advances a step in a toolbar menu three clicks away from the step
itself.

This adds an HTML field the form script draws the board into, and pushes the
raw grid down into a collapsed section. The grid stays -- it is where remarks
and the audit stamps are stored, and an officer occasionally needs the
unmediated view -- but it is no longer what you see first.
"""

import frappe

from sibbcs.setup.schema import add_fields, f, section


def _move_field(doctype, fieldname, after):
	"""Reorder an existing field. add_fields only ever appends new ones."""
	doc = frappe.get_doc("DocType", doctype)

	row = next((r for r in doc.fields if r.fieldname == fieldname), None)
	target = next((i for i, r in enumerate(doc.fields) if r.fieldname == after), None)
	if row is None or target is None:
		return False

	current = doc.fields.index(row)
	if current == target + 1:
		return False  # already in place

	doc.fields.remove(row)
	target = next(i for i, r in enumerate(doc.fields) if r.fieldname == after)
	doc.fields.insert(target + 1, row)
	for index, field in enumerate(doc.fields):
		field.idx = index + 1

	doc.save(ignore_permissions=True)
	return True


def build():
	added = add_fields(
		"Admission Application",
		[
			f(
				"checklist_board",
				"Checklist",
				"HTML",
				description="Drawn by the form script from admissions.checklist.board.",
			)
		],
		insert_after="sb_checklist",
	)

	added += add_fields(
		"Admission Application",
		[
			section(
				"sb_checklist_rows",
				"Checklist Rows",
				collapsible=1,
				description=(
					"The stored rows behind the board. Remarks and the audit stamps "
					"live here."
				),
			)
		],
		insert_after="checklist_board",
	)

	moved = _move_field("Admission Application", "checklist", "sb_checklist_rows")

	frappe.db.commit()
	frappe.clear_cache(doctype="Admission Application")

	meta = frappe.get_meta("Admission Application")
	order = [
		df.fieldname
		for df in meta.fields
		if df.fieldname in ("sb_checklist", "checklist_board", "sb_checklist_rows", "checklist")
	]
	print(f"Added: {added or 'nothing new'}")
	print(f"Grid moved below the board: {moved}")
	print(f"Order now: {' -> '.join(order)}")
