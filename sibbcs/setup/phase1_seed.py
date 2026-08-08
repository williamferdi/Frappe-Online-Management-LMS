"""Phase 1 seed data.

    bench --site online.sibbc.org execute sibbcs.setup.phase1_seed.seed_all
    bench --site online.sibbc.org execute sibbcs.setup.phase1_seed.import_courses \
        --kwargs "{'path': '/home/theiox/frappe-bench/apps/sibbcs/sibbcs/setup/data/courses.csv'}"

Everything here is idempotent -- existing records are left alone.

What is grounded in SIBBCS_ERP_Architecture.md and what is not:

  grounded   the four program abbreviations; M.Div has 32 courses; ATA fee is
             M.Div only; the five 2026 application deadlines; term duration
             defaults to 2 months; pass mark is 60%
  inferred   the expanded program names, and every term's start/end date
             (the document publishes application deadlines only)
  missing    total_credits, min/max years, internship hours, the grade scale
             bands and grade points (open decisions #2 and #3), and the course
             catalog itself

`seed_all` prints a REVIEW list of every field it could not fill, so nothing
inferred goes unnoticed.
"""

import csv
import os

import frappe

from sibbcs.academic.doctype.academic_term.academic_term import derive_term_dates

# --- grounded in the architecture document -------------------------------

PROGRAMS = [
	{
		"abbr": "MDIV",
		"program_name": "Master of Divinity",
		"total_courses": 32,
		"requires_ata_fee": 1,
	},
	{"abbr": "MACS", "program_name": "Master of Arts in Christian Studies"},
	{"abbr": "GDCS", "program_name": "Graduate Diploma in Christian Studies"},
	{"abbr": "BTH-TAM", "program_name": "Bachelor of Theology (Tamil)"},
]

# Published application deadlines, architecture doc §2.2.
TERM_DEADLINES_2026 = [
	("2026-T1", "2026-01-24"),
	("2026-T2", "2026-03-21"),
	("2026-T3", "2026-06-13"),
	("2026-T4", "2026-08-08"),
	("2026-T5", "2026-10-03"),
]

NEEDS_REVIEW = []


def _review(item):
	NEEDS_REVIEW.append(item)


# ---------------------------------------------------------------------------
# programs
# ---------------------------------------------------------------------------


def seed_programs():
	created = []
	for spec in PROGRAMS:
		if frappe.db.exists("Program", spec["abbr"]):
			continue

		doc = frappe.get_doc({"doctype": "Program", "is_active": 1, **spec})
		doc.insert(ignore_permissions=True)
		created.append(doc.name)

		_review(
			f"Program {doc.name}: confirm the full name \"{doc.program_name}\"; "
			"set total_credits, min_years, max_years, internship_hours"
		)
		if not spec.get("total_courses"):
			_review(f"Program {doc.name}: set total_courses")

	print(f"Programs: {len(created)} created, {len(PROGRAMS) - len(created)} already present")
	return created


# ---------------------------------------------------------------------------
# academic terms
# ---------------------------------------------------------------------------


def seed_terms(duration_months=2):
	created = []
	for term_name, deadline in TERM_DEADLINES_2026:
		if frappe.db.exists("Academic Term", term_name):
			continue

		dates = derive_term_dates(deadline, duration_months=duration_months)
		doc = frappe.get_doc(
			{
				"doctype": "Academic Term",
				"term_name": term_name,
				"term_code": term_name.replace("-", ""),
				"application_deadline": deadline,
				"duration_months": duration_months,
				"status": "Planned",
				**dates,
			}
		)
		doc.insert(ignore_permissions=True)
		created.append(doc.name)

	if created:
		_review(
			"Academic Terms "
			+ ", ".join(created)
			+ ": start_date and end_date are DERIVED from the application deadline "
			f"(deadline + {duration_months} months). Replace with the real teaching "
			"dates before opening registration."
		)

	print(
		f"Academic Terms: {len(created)} created, "
		f"{len(TERM_DEADLINES_2026) - len(created)} already present"
	)
	return created


# ---------------------------------------------------------------------------
# courses -- CSV import
# ---------------------------------------------------------------------------

COURSE_COLUMNS = [
	"course_code",
	"course_title",
	"credits",
	"level",
	"course_type",
	"department",
	"default_format",
	"programs",
	"prerequisites",
	"description",
]


def _split_list(value):
	if not value:
		return []
	return [part.strip() for part in value.replace(",", ";").split(";") if part.strip()]


def import_courses(path, dry_run=0):
	"""Import the course catalog from CSV.

	Two passes so prerequisites may refer to courses defined later in the file:
	every course is created first, then prerequisite rows are attached.

	`prerequisites` holds course codes separated by `;`. Suffix a code with `*`
	to mark it a hard prerequisite (blocks registration until passed).
	`programs` holds program abbreviations separated by `;`.
	"""
	dry_run = int(dry_run)
	if not os.path.exists(path):
		frappe.throw(f"No such file: {path}")

	with open(path, newline="", encoding="utf-8-sig") as handle:
		rows = [r for r in csv.DictReader(handle) if (r.get("course_code") or "").strip()]

	if not rows:
		print(f"{path} has no data rows.")
		return

	missing_columns = [c for c in ("course_code", "course_title", "credits", "level") if c not in rows[0]]
	if missing_columns:
		frappe.throw(f"CSV is missing required columns: {', '.join(missing_columns)}")

	created, skipped, problems = [], [], []

	# pass 1 -- the courses themselves
	for line, row in enumerate(rows, start=2):
		code = row["course_code"].strip().upper()
		if frappe.db.exists("Course", code):
			skipped.append(code)
			continue

		programs = _split_list(row.get("programs"))
		unknown = [p for p in programs if not frappe.db.exists("Program", p.upper())]
		if unknown:
			problems.append(f"line {line} ({code}): unknown program(s) {', '.join(unknown)}")
			programs = [p for p in programs if p.upper() not in {u.upper() for u in unknown}]

		doc = frappe.get_doc(
			{
				"doctype": "Course",
				"course_code": code,
				"course_title": (row.get("course_title") or "").strip(),
				"credits": row.get("credits") or 3,
				"level": (row.get("level") or "").strip(),
				"course_type": (row.get("course_type") or "Core").strip(),
				"department": (row.get("department") or "").strip().upper(),
				"default_format": (row.get("default_format") or "").strip(),
				"description": row.get("description") or "",
				"is_active": 1,
				"programs": [{"program": p.upper()} for p in programs],
			}
		)

		if dry_run:
			try:
				doc.run_method("validate")
				created.append(code)
			except Exception as exc:
				problems.append(f"line {line} ({code}): {exc}")
			continue

		try:
			doc.insert(ignore_permissions=True)
			created.append(code)
		except Exception as exc:
			problems.append(f"line {line} ({code}): {exc}")

	# pass 2 -- prerequisites, once every code exists
	if not dry_run:
		for line, row in enumerate(rows, start=2):
			code = row["course_code"].strip().upper()
			prereqs = _split_list(row.get("prerequisites"))
			if not prereqs or not frappe.db.exists("Course", code):
				continue

			doc = frappe.get_doc("Course", code)
			existing = {r.prerequisite_course for r in doc.course_prerequisites}
			changed = False

			for token in prereqs:
				is_hard = token.endswith("*")
				target = token.rstrip("*").strip().upper()

				if not frappe.db.exists("Course", target):
					problems.append(f"line {line} ({code}): unknown prerequisite {target}")
					continue
				if target in existing:
					continue

				doc.append(
					"course_prerequisites",
					{"prerequisite_course": target, "is_hard": 1 if is_hard else 0},
				)
				changed = True

			if changed:
				try:
					doc.save(ignore_permissions=True)
				except Exception as exc:
					problems.append(f"line {line} ({code}): prerequisites rejected -- {exc}")

	if not dry_run:
		frappe.db.commit()

	label = "would create" if dry_run else "created"
	print(f"Courses: {len(created)} {label}, {len(skipped)} already present")
	if problems:
		print(f"\n{len(problems)} problem(s):")
		for problem in problems:
			print(f"  ! {problem}")

	return {"created": created, "skipped": skipped, "problems": problems}


def write_course_template(path=None):
	"""Write a CSV template with the expected headers and two example rows."""
	path = path or os.path.join(
		frappe.get_app_path("sibbcs"), "setup", "data", "courses_template.csv"
	)
	os.makedirs(os.path.dirname(path), exist_ok=True)

	with open(path, "w", newline="", encoding="utf-8") as handle:
		writer = csv.DictWriter(handle, fieldnames=COURSE_COLUMNS)
		writer.writeheader()
		writer.writerow(
			{
				"course_code": "GEST O501",
				"course_title": "Orientation to Online Theological Study",
				"credits": "3",
				"level": "1",
				"course_type": "General Studies",
				"department": "GEST",
				"default_format": "Pre-Recorded",
				"programs": "MDIV;MACS;GDCS;BTH-TAM",
				"prerequisites": "",
				"description": "Required of every incoming student.",
			}
		)
		writer.writerow(
			{
				"course_code": "BIST O502",
				"course_title": "Introduction to the Old Testament",
				"credits": "3",
				"level": "1",
				"course_type": "Core",
				"department": "BIST",
				"default_format": "Zoom Live",
				"programs": "MDIV;MACS",
				"prerequisites": "GEST O501*",
				"description": "",
			}
		)

	print(f"Template written to {path}")
	print("Columns: " + ", ".join(COURSE_COLUMNS))
	print("  programs      -- program abbreviations separated by ';'")
	print("  prerequisites -- course codes separated by ';', suffix '*' for hard")
	return path


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def seed_all():
	NEEDS_REVIEW.clear()

	seed_programs()
	seed_terms()
	write_course_template()

	# Grade Scale is deliberately not seeded: grade letters, percentage bands
	# and grade points are open decisions #2 and #3 in the architecture doc.
	if not frappe.db.count("Grade Scale"):
		_review(
			"Grade Scale: not seeded. Needs the letter grades, percentage bands and "
			"grade points (open decisions #2/#3). Pass mark is confirmed at 60%."
		)

	if not frappe.db.count("Course"):
		_review(
			"Courses: none imported. Fill in setup/data/courses_template.csv and run "
			"sibbcs.setup.phase1_seed.import_courses."
		)

	if not frappe.db.count("Instructor"):
		_review("Instructors: none created. Add the faculty list.")

	frappe.db.commit()

	print("\n" + "=" * 72)
	print(f"REVIEW -- {len(NEEDS_REVIEW)} item(s) need your input")
	print("=" * 72)
	for item in NEEDS_REVIEW:
		print(f"  * {item}")
