# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""Move the admissions courses into Campus LMS Lite.

The entrance exam and the preliminary orientation course are the last things
running on the bundled LMS app. This builds their counterparts over there and
exports their content, so the bundled app can go.

**Two steps on purpose.** Courses, people and enrolments go through the sync
endpoints, which a service token may use. Pages, modules and quizzes may not be
authored with a token -- that is session-only, and widening it for a one-off
import would leave a standing door open. So the content is *exported* here and
*imported* by a one-off script inside the LMS, which has its own database.

Idempotent, like every builder here: run it twice and nothing doubles.
"""

import json

import frappe
from frappe import _

from sibbcs.api.content import _chapters_in_order, _lessons_in_order
from sibbcs.integrations import campus_lms

# What the courses are called over there, and where they come from here.
ORIENTATION_SOURCE = "m-div-preliminary-orientation"
EXAM_SOURCE = "entrance-exam"
EXPORT_PATH = "/tmp/sibbcs-work/admissions-content.json"


def _inline(value):
	"""EditorJS text, kept as it is.

	The inline markup is `<b>`, `<i>` and `<a>`, which Markdown passes through
	and the LMS sanitises on render -- so keeping it loses nothing, where
	stripping it would lose emphasis the college wrote deliberately.
	"""
	return (value or "").strip()


def _blocks_to_markdown(blocks):
	out = []
	for block in blocks:
		kind = block.get("type")
		data = block.get("data") or {}
		if kind == "header":
			out.append("#" * max(1, min(6, int(data.get("level") or 2))) + " " + _inline(data.get("text")))
		elif kind == "paragraph":
			out.append(_inline(data.get("text")))
		elif kind == "list":
			bullet = "1." if data.get("style") == "ordered" else "-"
			items = data.get("items") or []
			out.append(
				"\n".join(
					f"{bullet} {_inline(item if isinstance(item, str) else (item or {}).get('content'))}"
					for item in items
				)
			)
		elif kind == "quote":
			out.append("> " + _inline(data.get("text")))
		elif kind == "code":
			out.append("```\n" + (data.get("code") or "") + "\n```")
		elif kind == "delimiter":
			out.append("---")
		elif kind == "image":
			url = (data.get("file") or {}).get("url") or data.get("url") or ""
			if url:
				out.append(f"![]({url})")
		elif kind == "embed":
			source = data.get("source") or data.get("embed") or ""
			if source:
				out.append(source)
	return "\n\n".join(part for part in out if part)


def lesson_markdown(name):
	"""One lesson as Markdown, from whichever half of it is filled in.

	`content` is the EditorJS document the LMS editor writes; `body` is the
	plain text the handbook importer left. Most of these lessons are body only,
	and the reader prefers `content` when both exist -- so this does too, or a
	lesson edited since the import would be exported in its older form.
	"""
	row = frappe.db.get_value("Course Lesson", name, ["title", "content", "body"], as_dict=True)
	if not row:
		return None
	markdown = ""
	if row.content:
		try:
			markdown = _blocks_to_markdown(json.loads(row.content).get("blocks") or [])
		except (ValueError, TypeError):
			markdown = ""
	if not markdown:
		markdown = (row.body or "").strip()
	return {"title": row.title, "markdown": markdown}


def _course_export(source):
	"""A course as modules of pages, in the order a student meets them."""
	modules = []
	for chapter in _chapters_in_order(source):
		title = frappe.db.get_value("Course Chapter", chapter, "title")
		pages = [lesson_markdown(lesson) for lesson in _lessons_in_order(chapter)]
		modules.append({"title": title, "pages": [p for p in pages if p]})
	return modules


def _exam_quiz():
	"""The three essays, in the order the paper asks them.

	Read from the quiz itself rather than restated here, so a reworded prompt
	moves across with everything else.
	"""
	from sibbcs.admissions.entrance_exam import QUIZ_TITLE, quiz_names

	names = quiz_names()
	if not names:
		return None
	doc = frappe.get_doc("LMS Quiz", names[0])
	questions = []
	for row in doc.questions:
		prompt = frappe.db.get_value("LMS Question", row.question, "question")
		questions.append({"prompt": (prompt or "").strip(), "points": int(row.marks or 25)})
	return {"title": QUIZ_TITLE, "questions": questions}


def export_content(path=EXPORT_PATH):
	"""Write what the LMS importer needs, and say what is in it."""
	payload = {
		"orientation": {
			"externalId": campus_lms.ORIENTATION_COURSE,
			"modules": _course_export(ORIENTATION_SOURCE),
		},
		"exam": {
			"externalId": campus_lms.EXAM_COURSE,
			"modules": _course_export(EXAM_SOURCE),
			"quiz": _exam_quiz(),
		},
	}

	pages = sum(len(m["pages"]) for m in payload["orientation"]["modules"])
	empty = [
		p["title"]
		for m in payload["orientation"]["modules"] + payload["exam"]["modules"]
		for p in m["pages"]
		if not p["markdown"]
	]
	with open(path, "w", encoding="utf-8") as handle:
		json.dump(payload, handle, ensure_ascii=False, indent=1)

	return {
		"path": path,
		"orientation_modules": len(payload["orientation"]["modules"]),
		"orientation_pages": pages,
		"exam_questions": len(payload["exam"]["quiz"]["questions"]) if payload["exam"]["quiz"] else 0,
		# A page that came across empty is the quiet failure worth naming.
		"empty_pages": empty,
	}


def ensure_courses():
	"""The two courses over there, and the marker on them.

	Unpublished to begin with: an applicant enrolled before the content lands
	would open an empty course and conclude the college had sent them nothing.
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
			{"externalId": external_id, "code": code, "name": name, "status": "unpublished"},
		)

	markers = frappe.get_all("Instructor", filters={"is_active": 1}, pluck="name")
	enrolled = []
	for instructor in markers:
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
	"""Both halves of this side: the courses, then the content to import."""
	return {"courses": ensure_courses(), "content": export_content()}
