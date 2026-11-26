# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""Read everything the import needs out of Zoho Creator. Read-only on Zoho.

    cd ~/frappe-bench && ./env/bin/python -m sibbcs.setup.zoho_import.extract [--no-files]

Writes to `~/zoho-export/<date>/`, created with mode 0700 and files 0600:

  records/<name>.json   every record of each report, every field
  files/...             the documents of *onboarded* students only
  manifest.json         one line per file: where it came from, size, sha256
  summary.json          counts and field names -- no personal values

Re-running the same day resumes: a file already on disk with the size Zoho
reported is not fetched again. The printed summary holds counts and field
names only, so it can be shown to anybody.
"""

import hashlib
import json
import os
import shutil
import sys
from datetime import date

from sibbcs.setup.zoho_import.client import Client, ZohoError, file_references

EXPORT_ROOT = os.path.expanduser("~/zoho-export")

# what we call it -> the Zoho report that lists every record of that form
REPORTS = {
	"students": "students_Report",
	"programs": "All_Programs",
	"courses": "courses_Report",
	"program_courses": "All_Program_Course_Structures",
	"terms": "All_Terms",
	"offerings": "terms_by_status",
	"faculty": "faculty_Report",
	"grades": "Grades_Report",
	"rosters": "Course_Enrollments_Report",
	"registrations": "Course_Registrations_Report",
	"documents": "All_Document_Submissions",
	"document_reviews": "All_Student_Document_Submissions",
}

ONBOARDED = "Onboarded"


def _plain(value):
	"""A picklist or lookup value as text: Creator gives some as dicts."""
	if isinstance(value, dict):
		return str(value.get("display_value") or value.get("value") or "")
	return "" if value is None else str(value)


def onboarded(students):
	return [row for row in students if _plain(row.get("Onboarding_Status")).strip() == ONBOARDED]


def _emails(row):
	"""Every email-looking value on a record, lower-cased."""
	found = set()
	for key, value in row.items():
		if "mail" in key.lower():
			text = _plain(value).strip().lower()
			if "@" in text:
				found.add(text)
	return found


def _safe(name):
	name = os.path.basename(str(name)).replace(os.sep, "_")
	return "".join(c if c.isalnum() or c in "._-" else "_" for c in name)[:150] or "file"


def _write_json(path, data):
	with open(path, "w", encoding="utf-8") as handle:
		json.dump(data, handle, ensure_ascii=False, indent=1, default=str)


def _fetch_files(client, report, rows, out, subfolder, manifest, done_paths):
	folder = os.path.join(out, "files", subfolder)
	for row in rows:
		record_id = str(row.get("ID") or "")
		if not record_id:
			continue
		for field, value in row.items():
			for filepath in file_references(value):
				target_dir = os.path.join(folder, record_id, _safe(field))
				os.makedirs(target_dir, exist_ok=True)
				target = os.path.join(target_dir, _safe(filepath))
				entry = {
					"report": report,
					"record_id": record_id,
					"field": field,
					"filepath": filepath,
					"path": os.path.relpath(target, out),
				}
				if target in done_paths and os.path.exists(target) and os.path.getsize(target) == done_paths[target]["size"]:
					entry.update(done_paths[target])
					manifest.append(entry)
					continue
				try:
					content = client.download(report, record_id, field, filepath)
					with open(target, "wb") as handle:
						handle.write(content)
					entry.update(size=len(content), sha256=hashlib.sha256(content).hexdigest())
				except ZohoError as exc:
					entry["error"] = str(exc)
				manifest.append(entry)


def run(with_files=True, day=None):
	os.umask(0o077)
	out = os.path.join(EXPORT_ROOT, day or date.today().isoformat())
	os.makedirs(os.path.join(out, "records"), exist_ok=True)
	os.chmod(EXPORT_ROOT, 0o700)
	os.chmod(out, 0o700)

	client = Client()
	summary = {"reports": {}}
	data = {}

	for name, report in REPORTS.items():
		try:
			rows = client.records(report)
		except ZohoError as exc:
			summary["reports"][name] = {"report": report, "error": str(exc)}
			print(f"  {name:18} {report:36} ERROR {exc}")
			continue
		data[name] = rows
		_write_json(os.path.join(out, "records", f"{name}.json"), rows)
		fields = sorted({key for row in rows for key in row})
		summary["reports"][name] = {"report": report, "records": len(rows), "fields": fields}
		print(f"  {name:18} {report:36} {len(rows):>6} records, {len(fields)} fields")

	students = data.get("students") or []
	keep = onboarded(students)
	summary["onboarded_students"] = len(keep)
	print(f"\nonboarded students: {len(keep)} of {len(students)}")

	if with_files:
		free = shutil.disk_usage(out).free
		print(f"free disk: {free / 1e9:.1f} GB")
		previous = {}
		manifest_path = os.path.join(out, "manifest.json")
		if os.path.exists(manifest_path):
			with open(manifest_path) as handle:
				for entry in json.load(handle):
					if "sha256" in entry:
						previous[os.path.join(out, entry["path"])] = {
							"size": entry["size"],
							"sha256": entry["sha256"],
						}

		manifest = []
		_fetch_files(client, REPORTS["students"], keep, out, "students", manifest, previous)

		# Resubmitted documents name the student by email, not by lookup.
		wanted = set().union(*(_emails(row) for row in keep)) if keep else set()
		documents = [row for row in data.get("documents") or [] if _emails(row) & wanted]
		_fetch_files(client, REPORTS["documents"], documents, out, "documents", manifest, previous)

		_write_json(manifest_path, manifest)
		ok = [e for e in manifest if "sha256" in e]
		failed = [e for e in manifest if "error" in e]
		summary["files"] = {
			"downloaded": len(ok),
			"failed": len(failed),
			"bytes": sum(e["size"] for e in ok),
			"by_field": {},
		}
		for entry in ok:
			summary["files"]["by_field"][entry["field"]] = summary["files"]["by_field"].get(entry["field"], 0) + 1
		print(f"files: {len(ok)} downloaded ({summary['files']['bytes'] / 1e6:.1f} MB), {len(failed)} failed")
		for field, count in sorted(summary["files"]["by_field"].items()):
			print(f"  {field:40} {count}")
		for entry in failed[:10]:
			print(f"  FAILED {entry['field']}: {entry['error']}")

	summary["api_calls"] = client.calls
	_write_json(os.path.join(out, "summary.json"), summary)
	print(f"\nAPI calls: {client.calls}\nwritten to {out}")
	return out


if __name__ == "__main__":
	try:
		run(with_files="--no-files" not in sys.argv)
	except ZohoError as exc:
		sys.exit(str(exc))
