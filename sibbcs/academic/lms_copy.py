# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""Copy a course's chapters and lessons into another course.

    bench --site online.sibbc.org execute sibbcs.academic.lms_copy.copy_lessons \
        --kwargs "{'source': 'a-course', 'target': 'another', 'apply': False}"

Written as a utility rather than a one-off because duplicating a course is a
thing a college does: the same orientation runs every intake, and a new term
wants last term's material with this term's dates.

Ordering is taken from the child tables, not from the lesson names. A lesson is
named `{####} {title}` by Frappe's autoname, so the numbers are the order the
lessons were *created* site-wide, not their order within a chapter -- sorting
by name would shuffle a course that had ever been edited.
"""

import json

import frappe
from frappe import _

# Everything that makes a lesson what it is. Deliberately a named list: `course`
# and `chapter` must point at the copy, and `name` must not be carried over at
# all.
LESSON_FIELDS = (
	"title",
	"body",
	"content",
	"instructor_notes",
	"instructor_content",
	"include_in_preview",
	"youtube",
	"question",
	"file_type",
	"is_scorm_package",
	# `quiz_id` is deliberately absent for the same reason as the quiz
	# blocks: it would point the copy at the original's quiz.
)

COPY_ROLES = ("System Manager", "Course Creator", "Registrar", "Academic Coordinator")


def _require():
	roles = set(frappe.get_roles())
	if not roles.intersection(COPY_ROLES):
		frappe.throw(_("You may not copy course content."), frappe.PermissionError)


def strip_quizzes(content):
	"""Remove quiz blocks from a lesson body being copied.

	A quiz belongs to one lesson: `Course Lesson.validate_quiz_id` writes the
	saving lesson's name onto `LMS Quiz.course` and `.lesson`. Copying a lesson
	that embeds a quiz would therefore not duplicate the quiz -- it would move
	it, leaving the original lesson pointing at a quiz that now says it lives
	somewhere else. Stripped rather than carried, and the caller is told.
	"""
	if not content:
		return content, 0

	try:
		document = json.loads(content)
	except (TypeError, ValueError):
		return content, 0

	blocks = document.get("blocks")
	if not isinstance(blocks, list):
		return content, 0

	kept = [block for block in blocks if block.get("type") != "quiz"]
	removed = len(blocks) - len(kept)
	if not removed:
		return content, 0

	document["blocks"] = kept
	return json.dumps(document), removed


def _chapters_in_order(course):
	"""Chapters as the course lists them, falling back to the chapter table.

	A course built through the LMS editor keeps its order in Chapter Reference;
	one built by a script may not have those rows at all.
	"""
	referenced = frappe.get_all(
		"Chapter Reference",
		filters={"parent": course, "parenttype": "LMS Course"},
		fields=["chapter", "idx"],
		order_by="idx asc",
	)
	if referenced:
		return [row.chapter for row in referenced]

	return frappe.get_all(
		"Course Chapter", filters={"course": course}, pluck="name", order_by="name asc"
	)


def _lessons_in_order(chapter):
	referenced = frappe.get_all(
		"Lesson Reference",
		filters={"parent": chapter, "parenttype": "Course Chapter"},
		fields=["lesson", "idx"],
		order_by="idx asc",
	)
	if referenced:
		return [row.lesson for row in referenced]

	return frappe.get_all(
		"Course Lesson", filters={"chapter": chapter}, pluck="name", order_by="name asc"
	)


def survey(source, target):
	"""What a copy would move, and what is already there."""
	for course in (source, target):
		if not frappe.db.exists("LMS Course", course):
			frappe.throw(_("LMS Course {0} not found.").format(course))

	chapters = _chapters_in_order(source)
	plan = []
	for chapter in chapters:
		lessons = _lessons_in_order(chapter)
		plan.append(
			{
				"chapter": chapter,
				"title": frappe.db.get_value("Course Chapter", chapter, "title"),
				"lessons": [
					{"lesson": name, "title": frappe.db.get_value("Course Lesson", name, "title")}
					for name in lessons
				],
			}
		)

	existing = _chapters_in_order(target)
	return {
		"source": source,
		"target": target,
		"chapters": plan,
		"lesson_count": sum(len(entry["lessons"]) for entry in plan),
		"target_chapters": [
			{"chapter": name, "title": frappe.db.get_value("Course Chapter", name, "title")}
			for name in existing
		],
	}


@frappe.whitelist()
def copy_lessons(source, target, apply=False):
	"""Copy every chapter and lesson from one course into another.

	Idempotent by chapter title: a chapter already on the target is left alone
	rather than duplicated, so a re-run after a failure finishes the job
	instead of doubling what already landed.
	"""
	_require()

	plan = survey(source, target)
	already = {entry["title"] for entry in plan["target_chapters"]}

	pending = [entry for entry in plan["chapters"] if entry["title"] not in already]
	skipped = [entry for entry in plan["chapters"] if entry["title"] in already]

	report = {
		"source": source,
		"target": target,
		"applied": bool(apply),
		"chapters_to_copy": [entry["title"] for entry in pending],
		"chapters_already_there": [entry["title"] for entry in skipped],
		"lessons_to_copy": sum(len(entry["lessons"]) for entry in pending),
		"copied": [],
		"quizzes_dropped": [],
	}

	if not apply:
		return report

	# The course document is fetched *after* the inserts, not before:
	# creating a lesson touches the course row, so a copy loaded up front is
	# stale by the time the chapters are appended and the save is refused
	# with a timestamp mismatch.
	new_chapters = []

	for entry in pending:
		chapter = frappe.get_doc(
			{
				"doctype": "Course Chapter",
				"course": target,
				"title": entry["title"],
			}
		)
		chapter.insert(ignore_permissions=True)

		lesson_names = []
		for lesson_entry in entry["lessons"]:
			source_lesson = frappe.get_doc("Course Lesson", lesson_entry["lesson"])
			values = {field: source_lesson.get(field) for field in LESSON_FIELDS}

			dropped = 0
			for body in ("content", "instructor_content"):
				values[body], removed = strip_quizzes(values.get(body))
				dropped += removed
			if dropped:
				report["quizzes_dropped"].append(
					{"lesson": source_lesson.name, "blocks": dropped}
				)

			copy = frappe.get_doc(
				{
					"doctype": "Course Lesson",
					"course": target,
					"chapter": chapter.name,
					**values,
				}
			)
			copy.insert(ignore_permissions=True)
			lesson_names.append(copy.name)
			report["copied"].append({"from": source_lesson.name, "to": copy.name})

		# Reloaded for the same reason, then given its lessons in one go.
		chapter = frappe.get_doc("Course Chapter", chapter.name)
		chapter.set("lessons", [{"lesson": name} for name in lesson_names])
		chapter.save(ignore_permissions=True)
		new_chapters.append(chapter.name)

	if new_chapters:
		course = frappe.get_doc("LMS Course", target)
		for name in new_chapters:
			course.append("chapters", {"chapter": name})
		course.save(ignore_permissions=True)
		frappe.db.commit()
	return report
