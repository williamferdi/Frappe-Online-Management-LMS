"""Renumber existing checklist rows after the steps were reordered.

The college moved Scholarship Form Review from second in the list to after the
Zoom interview, because the interview is where they learn whether a candidate
needs a scholarship at all. That pushed Mentor Form, LMS Account, Entrance Exam
and the interview each up by one.

`step_no` is a position, so every stored row now points at a different step.
The row's `step` **label** is what survives a renumbering, so that is what this
matches on -- never the old number, which would map each row onto whatever
happens to sit at that position now.

Safe to re-run: a row already sitting at the number its label calls for is left
alone. A label this code does not recognise is reported and skipped rather than
guessed at, because a wrong guess here silently rewrites somebody's admission
record.
"""

import frappe

from sibbcs.admissions.checklist import NO_BY_LABEL


def execute():
	rows = frappe.get_all(
		"Admission Checklist Item",
		filters={"parenttype": "Admission Application"},
		fields=["name", "parent", "step_no", "step"],
		ignore_permissions=True,
	)

	moved = 0
	already = 0
	unknown = {}

	for row in rows:
		wanted = NO_BY_LABEL.get(row.step)
		if wanted is None:
			unknown.setdefault(row.step, 0)
			unknown[row.step] += 1
			continue

		if int(row.step_no or 0) == wanted:
			already += 1
			continue

		frappe.db.set_value(
			"Admission Checklist Item",
			row.name,
			"step_no",
			wanted,
			update_modified=False,
		)
		moved += 1

	# idx drives the order the grid draws rows in, so it has to follow.
	applications = {row.parent for row in rows}
	for application in applications:
		ordered = frappe.get_all(
			"Admission Checklist Item",
			filters={"parent": application, "parenttype": "Admission Application"},
			fields=["name", "step_no"],
			order_by="step_no asc",
			ignore_permissions=True,
		)
		for index, row in enumerate(ordered, start=1):
			frappe.db.set_value(
				"Admission Checklist Item", row.name, "idx", index, update_modified=False
			)

	print(
		f"Checklist rows: {moved} renumbered, {already} already correct, "
		f"across {len(applications)} applications."
	)
	if unknown:
		print("Labels not recognised (left untouched):")
		for label, count in sorted(unknown.items()):
			print(f"  {label!r} x{count}")
