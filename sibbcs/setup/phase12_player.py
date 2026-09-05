"""A student's own notes and bookmarks on the things they are studying.

    bench --site online.sibbc.org execute \\
        sibbcs.setup.phase12_player.build

Idempotent.

**One DocType, not two.** A note and a bookmark are the same thing wearing
different hats: this student's private annotation of this item. Two tables
would mean two lookups on every lesson opened, two rows to keep in step, and
the same uniqueness rule written twice.

**Private, and enforced as such.** No role can read these but the student who
wrote them and the System Manager -- not the teacher, not the registrar. A
note is where somebody writes "I don't understand this", and a teacher who can
read that changes what students write. Marking uses submissions; this is not
marking.
"""

import frappe

from sibbcs.setup.schema import check, column, ensure_doctype, f, fetched, full, link, section, select

MODULE = "Academic"

SM = "System Manager"


def _lesson_note():
	return ensure_doctype(
		"Lesson Note",
		MODULE,
		autoname="naming_series:",
		naming_rule='By "Naming Series" field',
		fields=[
			select("naming_series", "Series", ["LNT-.#####"], default="LNT-.#####",
				   hidden=1, print_hide=1),
			link("course_registration", "Registration", "Course Registration", reqd=1),
			link("module_item", "Item", "Course Module Item", reqd=1),
			# Carried so a student's own notes can be listed without joining
			# through the item on every read.
			fetched("course_offering", "Course Offering", "module_item.course_offering"),
			column("cb_head"),
			check("bookmarked", "Bookmarked", 0),
			section("sb_body"),
			f("body", "Note", "Small Text"),
		],
		# Only the writer. `academic.permissions` scopes reads to the student's
		# own registrations; a teacher holds nothing here at all.
		permissions=[full(SM)],
	)


def build():
	_lesson_note()

	frappe.db.commit()
	frappe.clear_cache()

	print("  Lesson Note:", "ok" if frappe.db.exists("DocType", "Lesson Note") else "MISSING")
