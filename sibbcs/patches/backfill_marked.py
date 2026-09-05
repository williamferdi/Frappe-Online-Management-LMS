"""Say which existing components have actually been marked.

`Grade Component.marked` arrives defaulting to 0, so without this every mark
entered before today reads as "not marked yet" and `compute_grade` would stop
producing a letter for a course that already has one.

The rule has to be a guess, because the information genuinely is not there:
`obtained_marks` is decimal NOT NULL DEFAULT 0, so a component nobody marked
and a component marked zero are the same row. The guess is **a score above
zero was marked**, which errs towards holding a letter back rather than
awarding one -- a marker who sees a grade missing goes and looks, where a
marker who sees a wrong grade may not.

Any genuine zero therefore needs its `marked` box ticking once. On the day
this ran there were five registrations on the live site, all of them DEMO.
"""

import frappe


def execute():
	if not frappe.db.has_column("Grade Component", "marked"):
		return

	marked = frappe.db.sql(
		"""
		UPDATE `tabGrade Component`
		SET `marked` = 1
		WHERE `marked` = 0 AND `obtained_marks` > 0
		"""
	)

	zeros = frappe.db.count("Grade Component", {"obtained_marks": 0, "marked": 0})

	print(f"Grade Component.marked backfilled; {zeros} row(s) left as unmarked.")
	print("Any of those that were a genuine zero need ticking by hand.")
	return marked
