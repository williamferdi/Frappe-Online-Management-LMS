# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""The two admissions courses in Campus LMS Lite, and who marks the exam.

Phase 6 moved admissions across: the entrance exam and the preliminary
orientation course. The content half of this module -- reading `Course Lesson`
out of the bundled `lms` app and converting EditorJS blocks into Markdown
pages -- went when that app was uninstalled in Phase 7, along with the
`phase7_course_content` builder that carried the taught courses. 196 pages are
over there now; the commit history is where the conversion lives if it is ever
needed again.

What remains is the part with no dependency on the old app, and the part worth
being able to run again: making sure the two courses exist, and putting the
markers on the exam.

    bench --site online.sibbc.org execute sibbcs.setup.phase6_admissions_lms.build

Idempotent -- both sync endpoints upsert on `externalId`.
"""

import frappe
from frappe import _

from sibbcs.integrations import campus_lms


def _markers():
	"""Instructors who can actually sign in, and so can actually mark.

	Every active instructor is the wrong rule: the demo fixtures are active and
	carry `@example.invalid` addresses with no login, so the first run of this
	made them accounts nobody could activate and put them on the real entrance
	exam as teachers. A marker is somebody with a working account.
	"""
	markers = []
	for row in frappe.get_all("Instructor", filters={"is_active": 1}, fields=["name", "user"]):
		if row.user and frappe.db.get_value("User", row.user, "enabled"):
			markers.append(row.name)
	return markers


def ensure_courses(status="unpublished"):
	"""The two courses over there, and the markers on them.

	Unpublished by default: an applicant enrolled before the content lands
	would open an empty course and conclude the college had sent them nothing.
	Both are published on the live site now, so pass `status="published"` to
	reconcile rather than quietly closing them.
	"""
	if not campus_lms.configured():
		frappe.throw(_("Campus LMS is not configured on this site."))

	made = {}
	for external_id, code, name in (
		(campus_lms.EXAM_COURSE, "ENTRANCE", "Entrance Exam"),
		(campus_lms.ORIENTATION_COURSE, "ORIENTATION", "Preliminary Orientation"),
	):
		made[external_id] = campus_lms._post(
			"/sync/courses",
			{"externalId": external_id, "code": code, "name": name, "status": status},
		)

	enrolled = []
	for instructor in _markers():
		person = campus_lms.person_payload("Instructor", instructor)
		if not person:
			continue
		campus_lms._post("/sync/people", person)
		for external_id in made:
			campus_lms._post(
				"/sync/enrollments",
				{
					"externalId": f"MARKER-{instructor}-{external_id}",
					"personExternalId": instructor,
					"courseExternalId": external_id,
					"role": "teacher",
				},
			)
		enrolled.append(instructor)

	return {"courses": list(made), "markers": enrolled}


def build():
	return {"courses": ensure_courses()}
