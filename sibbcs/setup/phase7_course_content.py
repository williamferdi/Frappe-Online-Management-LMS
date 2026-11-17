# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""Phase 7, step one: carry the academic course content out of the bundled LMS.

Phase 6 moved admissions. This moves what the college actually taught with --
135 lessons across four courses -- so that removing the bundled `lms` app does
not take them with it.

**Imported as its own course, unpublished, not merged.** Two of these have a
counterpart in Campus LMS Lite that somebody is building by hand right now
(`HIST 0507` has five assignments and three quizzes on it, authored in
November). Merging 86 migrated lessons into that would either bury their work
or duplicate it, and neither is repairable by re-running anything. So each old
course arrives beside it as a separate, unpublished course that no student can
see, and the college copies across whatever is still wanted at its own pace.

That is also why the external ids are prefixed `LEGACY-`: these are archives,
not courses the registrar runs, and the registrar must never match an enrolment
onto one.

Two steps, as in Phase 6: the courses go through the sync endpoints, the content
is exported here and imported by the LMS's own script, because a service token
deliberately cannot author pages.

    bench --site online.sibbc.org execute sibbcs.setup.phase7_course_content.build

Idempotent. `orientation-to-online-study` is deliberately NOT here: it is a
49-lesson duplicate of the orientation course Phase 6 already moved, and
importing it would put those pages in twice.
"""

import json

import frappe
from frappe import _

from sibbcs.integrations import campus_lms
from sibbcs.setup.phase6_admissions_lms import _course_export

EXPORT_PATH = "/tmp/sibbcs-work/academic-content.json"

# On a taught course `instructor_content` is the lecturer's own notes, not a
# mark scheme -- and on `church-history` it is where the material actually is:
# 7.6 KB under a lesson with nothing student-facing at all. It still travels
# unpublished, so only staff see it.
NOTES_LABEL = "instructor notes"

# bundled slug -> (external id over there, code, name)
#
# `introduction-to-the-old-testament` is absent on purpose: 8 chapters and zero
# lessons, so there is nothing in it to carry.
LEGACY_COURSES = {
	"history-of-christianity": (
		"LEGACY-HIST-0507",
		"HIST0507-OLD",
		"History of Christianity (from the old LMS)",
	),
	"introduction-to-the-new-testament": (
		"LEGACY-BIST503",
		"BIST503-OLD",
		"Introduction to the New Testament (from the old LMS)",
	),
	"church-history": (
		"LEGACY-CHURCH-HISTORY",
		"CHURCHHIST-OLD",
		"Church History (from the old LMS)",
	),
	"biblical-hermeneutics": (
		"LEGACY-HERMENEUTICS",
		"HERM-OLD",
		"Biblical Hermeneutics (from the old LMS)",
	),
}


def ensure_courses():
	"""The archive courses over there, unpublished.

	Nobody is enrolled on them and nobody should be: an archive a student can
	open is a second place to read the syllabus, which is how two versions of a
	course end up in front of one cohort.
	"""
	if not campus_lms.configured():
		frappe.throw(_("Campus LMS is not configured on this site."))

	made = {}
	for source, (external_id, code, name) in LEGACY_COURSES.items():
		if not frappe.db.exists("LMS Course", source):
			continue
		campus_lms._post(
			"/sync/courses",
			{"externalId": external_id, "code": code, "name": name, "status": "unpublished"},
		)
		made[source] = external_id
	return made


def export_content(path=EXPORT_PATH):
	"""Write what the LMS importer reads, and say what is in it.

	The payload is keyed by the old slug so the importer's own output names the
	course it is working on. Shape is exactly what Phase 6 produced, so the
	same import script reads it with no changes.
	"""
	payload = {}
	found, private, renamed = [], [], []
	missing = []

	for source, (external_id, _code, _name) in LEGACY_COURSES.items():
		if not frappe.db.exists("LMS Course", source):
			missing.append(source)
			continue
		payload[source] = {
			"externalId": external_id,
			"modules": _course_export(
				source, found, private, notes_label=NOTES_LABEL, renamed=renamed
			),
		}

	with open(path, "w", encoding="utf-8") as handle:
		json.dump(payload, handle, ensure_ascii=False, indent=1)

	report = {"path": path, "courses": {}, "missing": missing}
	for source, side in payload.items():
		pages = [p for m in side["modules"] for p in m["pages"]]
		report["courses"][source] = {
			"externalId": side["externalId"],
			"modules": len(side["modules"]),
			"pages": len(pages),
			# A page that came across empty is the quiet failure worth naming:
			# a lesson whose content did not convert looks like a successful
			# import until somebody opens it.
			"empty_pages": [p["title"] for p in pages if not p["markdown"]],
			# Instructor notes travel as unpublished pages, staff-only.
			"unpublished_pages": len([p for p in pages if not p["published"]]),
		}

	report["linked_files"] = {p: found.count(p) for p in sorted(set(found))}
	report["private_links"] = sorted(set(private))
	# Titles that had to be numbered to stay distinct. A collision is otherwise
	# silent: the importer keys a page on (course, title), so the second lesson
	# overwrites the first.
	report["renamed_pages"] = renamed
	return report


def build():
	return {"courses": ensure_courses(), "content": export_content()}
