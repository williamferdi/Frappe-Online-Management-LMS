# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""Turn an extract into the sheets the college fills in before the load.

    cd ~/frappe-bench/sites && ../env/bin/python -P -m sibbcs.setup.zoho_import.review [date]

Reads `~/zoho-export/<date>/records/` and writes `~/zoho-export/<date>/review/`:

  courses_review.csv     the catalogue, codes normalised, with the LEVEL and
                         TYPE each course should have here -- Zoho has no
                         level field, so these are proposals to confirm
  terms_review.csv       Zoho's terms, the name and status each gets here
  opening_balances.csv   one row per onboarded student; the money columns are
                         for the office to fill (personal data: stays on the
                         server unless the office takes it)
  exceptions.csv         every record the load would refuse or has to guess at

and prints a summary of counts only.
"""

import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime

from sibbcs.setup.zoho_import.extract import EXPORT_ROOT

ONBOARDED = "Onboarded"

# Zoho's programme names -> the Program here (by abbr). GDCS does not exist yet.
PROGRAMMES = {
	"Master of Divinity": "M.DIV.",
	"Master of Arts in Christian Studies": "MACS",
	"Graduate Diploma in Christian Studies": "GDCS",
	"Bachelor of Theology (Tamil)": None,
}

DEPARTMENTS = {"BIST", "THST", "CHMI", "HIST", "REMI", "GEST", "SPMF"}

TERM_LABEL = re.compile(r"Term\s*(\d)\s*-?\s*(\d{4})")


def display(value):
	if isinstance(value, dict):
		return value.get("zc_display_value") or value.get("display_value") or ""
	return "" if value is None else str(value)


def ref_id(value):
	return str((value or {}).get("ID") or "") if isinstance(value, dict) else ""


def course_code(zoho_code):
	"""`BIST O501` -> `BISTO501`: how codes are written here."""
	return re.sub(r"\s+", "", zoho_code or "").upper()


def zoho_date(text):
	"""Zoho writes dates as 01-May-2023."""
	return datetime.strptime(text.strip(), "%d-%b-%Y").date() if text and text.strip() else None


def term_name(label):
	"""`Term 6 - 2026` (or `Term 6 2026`) -> `2026-T6`, the name used here."""
	match = TERM_LABEL.search(label or "")
	return f"{match.group(2)}-T{match.group(1)}" if match else None


def months_between(start, end):
	days = (end - start).days + 1
	return max(1, round(days / 30.4))


def term_status(zoho_status, end, today):
	"""Every term that has ended -- and the one running now, which the office
	has already billed under the old system -- is Closed here: a Closed term is
	never offered to the tuition job. Upcoming ones are Planned."""
	if zoho_status == "Upcoming" and end and end >= today:
		return "Planned"
	return "Closed"


def level_guess(code, sequence_rank):
	"""A proposal only. O5xx is Level 1, O7xx Level 4, and the O6xx courses
	split between 2 and 3 in Zoho's own Sequence order."""
	number = re.search(r"(\d)(\d\d)$", code)
	if not number:
		return ""
	hundreds = number.group(1)
	if hundreds == "5":
		return "1"
	if hundreds == "7":
		return "4"
	return "2" if sequence_rank is not None and sequence_rank < 8 else "3"


def load(folder):
	records = {}
	for name in os.listdir(os.path.join(folder, "records")):
		if name.endswith(".json"):
			with open(os.path.join(folder, "records", name), encoding="utf-8") as handle:
				records[name[:-5]] = json.load(handle)
	return records


def _write(path, header, rows):
	with open(path, "w", newline="", encoding="utf-8") as handle:
		writer = csv.writer(handle)
		writer.writerow(header)
		writer.writerows(rows)


def build(folder, today=None, erp=None):
	"""Write the four sheets; return the summary dict. `erp` is what already
	exists here ({"courses": set, "terms": dict name->(start,end), "students":
	{email: name}}), passed in so this module needs no database to test."""
	today = today or date.today()
	erp = erp or {"courses": set(), "terms": {}, "students": {}}
	data = load(folder)
	out = os.path.join(folder, "review")
	os.makedirs(out, exist_ok=True)
	exceptions = []
	summary = {}

	# -- courses -------------------------------------------------------------
	programmes_of = defaultdict(set)
	for row in data.get("program_courses", []):
		programme = PROGRAMMES.get(display(row.get("Program")))
		for course in row.get("Course") or []:
			programmes_of[ref_id(course)].add(programme or display(row.get("Program")))

	sequence = {}
	for offering in data.get("offerings", []):
		for code, seq in zip(offering.get("Course.course_code") or [], offering.get("Course.Sequence") or []):
			if seq not in ("", None):
				sequence[course_code(code)] = int(float(seq))
	middle = sorted(
		(c for c in (course_code(r.get("course_code")) for r in data.get("courses", [])) if re.search(r"6\d\d$", c)),
		key=lambda c: sequence.get(c, 9999),
	)
	rank = {code: i for i, code in enumerate(middle)}

	course_rows = []
	for row in sorted(data.get("courses", []), key=lambda r: course_code(r.get("course_code"))):
		code = course_code(row.get("course_code"))
		department = re.match(r"[A-Z]+", code).group(0)[:-1] if re.match(r"[A-Z]+O\d", code) else code[:4]
		programmes = sorted(p for p in programmes_of.get(row["ID"], set()) if p)
		note = []
		if department not in DEPARTMENTS:
			note.append(f"department {department} is not one of {', '.join(sorted(DEPARTMENTS))} here")
		if code in erp["courses"]:
			note.append("already here: matched, not duplicated")
		course_rows.append(
			[
				row["ID"],
				row.get("course_code"),
				code,
				row.get("title"),
				row.get("credits"),
				department,
				level_guess(code, rank.get(code)),
				"Core",
				";".join(programmes),
				"; ".join(note),
			]
		)
	_write(
		os.path.join(out, "courses_review.csv"),
		["zoho_id", "zoho_code", "course_code", "course_title", "credits", "department",
		 "level (PROPOSED - confirm)", "course_type (PROPOSED - confirm)", "programs", "notes"],
		course_rows,
	)
	summary["courses"] = len(course_rows)

	# -- terms ---------------------------------------------------------------
	term_rows = []
	for row in sorted(data.get("terms", []), key=lambda r: zoho_date(r.get("Start_Date")) or date.min):
		name = term_name(f"{row.get('Term')} {row.get('Academic_Year')}")
		start, end = zoho_date(row.get("Start_Date")), zoho_date(row.get("End_Date"))
		status = term_status(row.get("Status"), end, today)
		note = ""
		if name in erp["terms"]:
			erp_start, erp_end = erp["terms"][name]
			if (erp_start, erp_end) != (start, end):
				note = f"already here with different dates ({erp_start} to {erp_end})"
				exceptions.append(["term", name, "dates differ", note + f"; Zoho says {start} to {end}"])
			else:
				note = "already here: matched"
		term_rows.append(
			[row["ID"], name, start, end, row.get("Status"), status, months_between(start, end) if start and end else "", note]
		)
	_write(
		os.path.join(out, "terms_review.csv"),
		["zoho_id", "term_name", "start_date", "end_date", "zoho_status", "status_here", "duration_months", "notes"],
		term_rows,
	)
	summary["terms"] = len(term_rows)

	# -- students ------------------------------------------------------------
	students = [s for s in data.get("students", []) if s.get("Onboarding_Status") == ONBOARDED]
	onboarded_ids = {s["ID"] for s in students}
	balance_rows = []
	for s in sorted(students, key=lambda r: display(r.get("full_name")).lower()):
		email = (s.get("email") or "").strip().lower()
		programme = PROGRAMMES.get(s.get("program_enrolled"))
		existing = erp["students"].get(email, "")
		if not programme:
			exceptions.append(["student", s["ID"], "no programme here", s.get("program_enrolled")])
		if existing:
			exceptions.append(["student", s["ID"], "already a student here", f"matched to {existing} by email; updated, not duplicated"])
		balance_rows.append(
			[s["ID"], existing, display(s.get("full_name")), email, s.get("program_enrolled"),
			 s.get("current_level"), s.get("enrollment_status"), "", "", "", "", "", "", "", ""]
		)
	_write(
		os.path.join(out, "opening_balances.csv"),
		["zoho_id", "student_here", "full_name", "email", "programme", "level", "enrollment_status",
		 "tuition_billed_before_erp", "tuition_paid_before_erp", "term_6_2026_tuition_covered (Y/N)",
		 "other_amount_outstanding", "scholarship_total_cap", "scholarship_monthly_discount",
		 "scholarship_used_to_date", "notes"],
		balance_rows,
	)
	summary["onboarded_students"] = len(balance_rows)
	summary["programmes"] = dict(Counter(s.get("program_enrolled") for s in students))
	summary["levels"] = dict(Counter(s.get("current_level") for s in students))

	# -- grades --------------------------------------------------------------
	offerings = {o["ID"]: o for o in data.get("offerings", [])}
	graded, awaiting, skipped = Counter(), Counter(), Counter()
	for g in data.get("grades", []):
		student = ref_id(g.get("Student"))
		offering = offerings.get(ref_id(g.get("Course_Name")))
		if not student:
			skipped["no student"] += 1
			exceptions.append(["grade", g["ID"], "no student", display(g.get("Course_Name"))])
			continue
		if student not in onboarded_ids:
			skipped["student not onboarded"] += 1
			continue
		if not offering:
			skipped["no offering"] += 1
			exceptions.append(["grade", g["ID"], "offering not found", display(g.get("Course_Name"))])
			continue
		label = term_name(display(offering.get("Term")))
		if g.get("Status") in ("Pass", "Fail"):
			graded[g["Status"]] += 1
		else:
			awaiting[label] += 1
	if awaiting:
		for label, count in sorted(awaiting.items()):
			exceptions.append(["grades", label, "no mark yet", f"{count} registrations load as Active, awaiting a mark"])
	summary["grades"] = {"graded": dict(graded), "awaiting_mark_by_term": dict(awaiting), "skipped": dict(skipped)}

	_write(os.path.join(out, "exceptions.csv"), ["kind", "zoho_id_or_name", "problem", "detail"], exceptions)
	summary["exceptions"] = len(exceptions)
	with open(os.path.join(out, "summary.json"), "w") as handle:
		json.dump(summary, handle, indent=1, default=str)
	return summary


def _erp_snapshot():
	import frappe

	return {
		"courses": set(frappe.get_all("Course", pluck="name")),
		"terms": {t.name: (t.start_date, t.end_date) for t in frappe.get_all("Academic Term", fields=["name", "start_date", "end_date"])},
		"students": {
			(s.email or "").strip().lower(): s.name
			for s in frappe.get_all("Student", fields=["name", "email"])
			if s.email
		},
	}


if __name__ == "__main__":
	import frappe

	day = sys.argv[1] if len(sys.argv) > 1 else sorted(os.listdir(EXPORT_ROOT))[-1]
	frappe.init(site="online.sibbc.org", sites_path=".")
	frappe.connect()
	try:
		print(json.dumps(build(os.path.join(EXPORT_ROOT, day), erp=_erp_snapshot()), indent=1, default=str))
	finally:
		frappe.destroy()
