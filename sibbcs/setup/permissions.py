"""The canonical role/permission matrix -- architecture doc §7.

    bench --site online.sibbc.org execute sibbcs.setup.permissions.apply_all

This is the single source of truth. The phase builders create DocTypes but skip
ones that already exist, so permissions have to be re-appliable on their own.

Why this module exists: the original builders passed only the flags they meant
to grant. Frappe's DocPerm fields carry their own defaults, so the unstated
flags came back as 1 -- which quietly gave **Student** create rights on Course,
Program, Academic Term, Course Offering and Level Promotion. A student could
have promoted themselves to Level 4. `schema._perm` now writes every flag
explicitly, and `apply_all` rewrites the rows on every existing DocType.

Read the matrix as: role -> what they may do with this DocType.
  full  create, read, write, delete
  edit  read and write existing records, but not create or delete
  read  read only
"""

import frappe

from sibbcs.setup.schema import edit, full, level, read

SM = "System Manager"
REGISTRAR = "Registrar"
OFFICER = "Admissions Officer"
COORDINATOR = "Academic Coordinator"
FACULTY = "Faculty"
FACILITATOR = "Facilitator"
FORMATION = "Formation Coordinator"
ACCOUNTS = "Accounts"
STUDENT = "Student"

# doctype -> permission rows
MATRIX = {
	# --- Academic masters -------------------------------------------------
	"Program": [full(SM), full(REGISTRAR), read(COORDINATOR), read(FACULTY), read(STUDENT)],
	"Course": [full(SM), full(COORDINATOR), read(REGISTRAR), read(FACULTY), read(STUDENT)],
	"Academic Term": [
		full(SM), full(COORDINATOR), read(REGISTRAR), read(FACULTY), read(STUDENT)
	],
	"Course Offering": [
		full(SM), full(COORDINATOR), read(REGISTRAR), read(FACULTY),
		read(FACILITATOR), read(STUDENT),
	],
	"Instructor": [full(SM), full(COORDINATOR), read(REGISTRAR), read(FACULTY)],

	# --- the gradebook ----------------------------------------------------
	# Faculty build their own courses, which is the point of the phase; the
	# row-level scoping in `academic.permissions` is what keeps "their own"
	# meaning something. No Student row at all: an unpublished assignment is
	# not yet an announcement, and the portal reads through endpoints that
	# filter on `published` rather than through the DocType.
	"Course Grade Scheme": [
		full(SM), full(COORDINATOR), full(FACULTY),
		read(REGISTRAR), read(FACILITATOR),
	],
	"Course Assignment": [
		full(SM), full(COORDINATOR), full(FACULTY),
		read(REGISTRAR), read(FACILITATOR),
	],
	# No Student row on Assignment Submission, deliberately. Permlevel cannot
	# say "your own score, once it is posted" -- Student holds level-1 read on
	# Course Registration and would inherit it here. The portal reads through
	# session-scoped endpoints that filter on `posted` instead.
	"Assignment Submission": [
		full(SM), full(COORDINATOR), full(FACULTY),
		read(REGISTRAR), read(FACILITATOR),
		level(SM, 1), level(COORDINATOR, 1), level(FACULTY, 1),
		level(REGISTRAR, 1, write=0), level(FACILITATOR, 1, write=0),
	],
	"Course Rubric": [
		full(SM), full(COORDINATOR), full(FACULTY),
		read(REGISTRAR), read(FACILITATOR),
	],
	"Rubric Criterion": [
		full(SM), full(COORDINATOR), full(FACULTY),
		read(REGISTRAR), read(FACILITATOR),
	],
	"Grade Scale": [full(SM), edit(REGISTRAR), read(COORDINATOR), read(FACULTY)],
	"Weekday": [full(SM), read(COORDINATOR), read(REGISTRAR)],

	# --- Students and enrollment -----------------------------------------
	"Student": [
		full(SM), full(REGISTRAR), read(OFFICER), read(COORDINATOR),
		read(FACULTY), read(ACCOUNTS), read(FORMATION), read(STUDENT),
	],
	"Program Enrollment": [
		full(SM), full(REGISTRAR), edit(COORDINATOR),
		read(ACCOUNTS), read(FACULTY), read(STUDENT),
		# permlevel 1 gates current_level
		level(SM, 1), level(REGISTRAR, 1), level(COORDINATOR, 1),
	],
	"Course Registration": [
		# Students deliberately cannot create these in Desk. Registration goes
		# through portal.register, which runs the §3 rule engine; a hand-made
		# document would bypass it.
		full(SM), full(REGISTRAR), full(COORDINATOR), edit(FACULTY),
		read(FACILITATOR), read(ACCOUNTS), read(STUDENT),
		# permlevel 1 gates the grade fields
		level(SM, 1), level(REGISTRAR, 1), level(COORDINATOR, 1), level(FACULTY, 1),
		level(FACILITATOR, 1, write=0), level(STUDENT, 1, write=0),
	],
	"Level Promotion": [
		full(SM), full(REGISTRAR), full(COORDINATOR), read(FACULTY), read(STUDENT)
	],

	# --- Admissions -------------------------------------------------------
	"Lead": [full(SM), full(OFFICER), read(REGISTRAR)],
	"Admission Application": [
		full(SM), full(OFFICER), full(REGISTRAR), read(COORDINATOR), read(ACCOUNTS)
	],
	"Scholarship Request": [full(SM), full(REGISTRAR), edit(OFFICER), read(ACCOUNTS)],
	"Qualifying Exam Result": [
		full(SM), full(OFFICER), read(REGISTRAR), read(COORDINATOR)
	],
	"Interview Record": [full(SM), full(OFFICER), read(REGISTRAR), read(COORDINATOR)],
	"Reading Manual": [
		full(SM), full(REGISTRAR), read(OFFICER), read(COORDINATOR), read(STUDENT)
	],

	# --- Finance ----------------------------------------------------------
	"Fee Type": [full(SM), full(ACCOUNTS), read(REGISTRAR)],
	"Fee Invoice": [full(SM), full(ACCOUNTS), read(REGISTRAR), read(STUDENT)],
	"Payment Entry": [full(SM), full(ACCOUNTS), read(REGISTRAR), read(STUDENT)],
}

# Roles that must never be able to create these, whatever else changes.
FORBIDDEN_CREATE = {
	"Program": [STUDENT, FACULTY, FACILITATOR],
	"Course": [STUDENT, FACULTY, FACILITATOR],
	"Academic Term": [STUDENT, FACULTY, FACILITATOR],
	"Course Offering": [STUDENT, FACULTY, FACILITATOR],
	"Grade Scale": [STUDENT, FACULTY, FACILITATOR],
	"Level Promotion": [STUDENT, FACULTY, FACILITATOR],
	"Student": [STUDENT, FACULTY, FACILITATOR],
	"Program Enrollment": [STUDENT, FACULTY, FACILITATOR],
	"Course Registration": [STUDENT],
	"Course Grade Scheme": [STUDENT],
	"Course Assignment": [STUDENT],
	"Assignment Submission": [STUDENT],
	"Course Rubric": [STUDENT, FACILITATOR],
	"Rubric Criterion": [STUDENT, FACILITATOR],
	"Fee Invoice": [STUDENT],
	"Payment Entry": [STUDENT],
	"Reading Manual": [STUDENT, FACULTY, FACILITATOR],
}


def apply_to(doctype, rows):
	"""Replace a DocType's permission rows with the canonical set."""
	doc = frappe.get_doc("DocType", doctype)
	doc.permissions = []
	for row in rows:
		doc.append("permissions", row)
	doc.save(ignore_permissions=True)


def apply_all():
	applied, missing = [], []

	for doctype, rows in MATRIX.items():
		if not frappe.db.exists("DocType", doctype):
			missing.append(doctype)
			continue
		apply_to(doctype, rows)
		applied.append(doctype)

	frappe.db.commit()
	frappe.clear_cache()

	print(f"Permissions applied to {len(applied)} DocTypes.")
	if missing:
		print(f"  not installed yet: {', '.join(missing)}")

	problems = audit()
	print("Audit:", "clean" if not problems else f"{len(problems)} PROBLEM(S)")
	for problem in problems:
		print("  !", problem)
	return applied


def audit():
	"""Report any role that can create something it must not."""
	problems = []
	for doctype, forbidden in FORBIDDEN_CREATE.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		meta = frappe.get_meta(doctype)
		creators = {p.role for p in meta.permissions if p.permlevel == 0 and p.create}
		for role in forbidden:
			if role in creators:
				problems.append(f"{doctype}: {role} can create")
	return problems
