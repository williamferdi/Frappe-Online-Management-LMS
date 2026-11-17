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
import re

import frappe
from frappe import _

from sibbcs.api.content import _chapters_in_order, _lessons_in_order
from sibbcs.finance import gateway
from sibbcs.integrations import campus_lms

# What the courses are called over there, and where they come from here.
ORIENTATION_SOURCE = "m-div-preliminary-orientation"
EXAM_SOURCE = "entrance-exam"
EXPORT_PATH = "/tmp/sibbcs-work/admissions-content.json"


# A lesson written here links to its handbook as `/files/program_manual.pdf`.
# Relative to this site, and so broken over there: the page is served from
# lms.sibbc.org while the file sits on the registrar's host. Every one of the 49
# orientation pages carries one of these.
_SITE_FILE = re.compile(r"\]\((/(?:private/)?files/[^)\s]+)\)")


def _absolutise(markdown, found, private):
	"""Point site-relative file links at this site, and say which ones moved.

	Absolute rather than copied: the handbooks are revised, and a second copy of
	a 9.5 MB PDF is a second copy to keep in step. `gateway.public_url` and not
	`frappe.utils.get_url`, which appends :8000 on this deployment -- see its
	docstring.

	A `/private/files/` link is recorded in `private` as well as rewritten:
	fetching one needs a session on *this* site, which a candidate working in
	the LMS does not have, so the link would only send them to a login page for
	the wrong system. There are none today; this is here so that the day a
	lesson gains one, the export reports it rather than shipping a dead link
	across 49 pages.
	"""

	def swap(match):
		path = match.group(1)
		(private if path.startswith("/private/") else found).append(path)
		return "](" + gateway.public_url(path) + ")"

	return _SITE_FILE.sub(swap, markdown or "")


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


def lesson_markdown(name, found=None, private=None):
	"""One lesson as Markdown, from whichever half of it is filled in.

	`found` and `private` collect the file links rewritten on the way out, so
	the export can report them; pass neither when the counts are not wanted.

	`content` is the EditorJS document the LMS editor writes; `body` is the
	plain text the handbook importer left. Most of these lessons are body only,
	and the reader prefers `content` when both exist -- so this does too, or a
	lesson edited since the import would be exported in its older form.
	"""
	row = frappe.db.get_value(
		"Course Lesson", name, ["title", "content", "body", "instructor_content"], as_dict=True
	)
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

	# The marking rubric lives here, and the LMS shows it to instructors only.
	# A candidate reading the mark scheme is not sitting the same exam, so it
	# travels as its own page and that page is never published.
	rubric = ""
	if row.instructor_content:
		try:
			rubric = _blocks_to_markdown(json.loads(row.instructor_content).get("blocks") or [])
		except (ValueError, TypeError):
			rubric = ""

	found = found if found is not None else []
	private = private if private is not None else []
	return {
		"title": row.title,
		"markdown": _absolutise(markdown, found, private),
		"rubric": _absolutise(rubric, found, private),
	}


def _course_export(source, found=None, private=None):
	"""A course as modules of pages, in the order a student meets them."""
	modules = []
	for chapter in _chapters_in_order(source):
		title = frappe.db.get_value("Course Chapter", chapter, "title")
		pages = []
		for lesson in _lessons_in_order(chapter):
			page = lesson_markdown(lesson, found, private)
			if not page:
				continue
			pages.append({"title": page["title"], "markdown": page["markdown"], "published": True})
			if page["rubric"]:
				pages.append(
					{
						"title": f"{page['title']} — marking rubric",
						"markdown": page["rubric"],
						"published": False,
					}
				)
		modules.append({"title": title, "pages": pages})
	return modules


def _exam_quiz():
	"""The three essays, in the order the paper asks them.

	Read from the quiz itself rather than restated here, so a reworded prompt
	moves across with everything else.

	The quiz is found by title, in one query here rather than through a helper
	in `entrance_exam` or `phase2m_entrance_exam`. The first of those lost its
	copy when the exam moved to the LMS -- which left this builder raising
	`ImportError` and so not re-runnable at all -- and the second is one of the
	modules Phase 7 deletes. Returns None once the bundled quiz is gone, which
	leaves the import to keep the quiz it already has.
	"""
	from sibbcs.admissions.entrance_exam import QUIZ_TITLE

	if not frappe.db.exists("DocType", "LMS Quiz"):
		return None
	names = sorted(frappe.get_all("LMS Quiz", filters={"title": QUIZ_TITLE}, pluck="name"))
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
	found, private = [], []
	payload = {
		"orientation": {
			"externalId": campus_lms.ORIENTATION_COURSE,
			"modules": _course_export(ORIENTATION_SOURCE, found, private),
		},
		"exam": {
			"externalId": campus_lms.EXAM_COURSE,
			"modules": _course_export(EXAM_SOURCE, found, private),
			"quiz": _exam_quiz(),
		},
	}

	every = [p for side in ("orientation", "exam") for m in payload[side]["modules"] for p in m["pages"]]
	pages = sum(len(m["pages"]) for m in payload["orientation"]["modules"])
	empty = [p["title"] for p in every if not p["markdown"]]
	rubrics = [p["title"] for p in every if not p["published"]]
	with open(path, "w", encoding="utf-8") as handle:
		json.dump(payload, handle, ensure_ascii=False, indent=1)

	return {
		"path": path,
		"orientation_modules": len(payload["orientation"]["modules"]),
		"orientation_pages": pages,
		"exam_questions": len(payload["exam"]["quiz"]["questions"]) if payload["exam"]["quiz"] else 0,
		# A page that came across empty is the quiet failure worth naming.
		"empty_pages": empty,
		# And these must stay unpublished: they are the mark schemes.
		"unpublished_pages": rubrics,
		# Links made absolute, by file, so a handbook that stopped being linked
		# is visible as a count that moved rather than as a 404 a candidate
		# finds first.
		"linked_files": {path: found.count(path) for path in sorted(set(found))},
		# These would need a session on this site, which the candidate has not
		# got. None today; non-empty means somebody must look.
		"private_links": sorted(set(private)),
	}


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

	markers = _markers()
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
