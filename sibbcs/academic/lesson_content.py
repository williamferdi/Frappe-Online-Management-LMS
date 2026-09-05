# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""Reading a lesson out of the LMS, without writing anything back to it.

`Course Lesson.content` is EditorJS JSON: `{"blocks": [{"type": ..., "data":
{...}}]}`. We read it, drop the blocks that are interactive, and hand the rest
to a renderer in the front end.

**Read only.** The LMS app is vendored -- `bench update` replaces it and the
next `bench migrate` would drop anything we had added to it -- so nothing here
writes. The lesson stays the LMS's; the structure around it is ours.

**The interactive blocks are stripped rather than rendered.** A `quiz`,
`assignment` or `program` block embedded in lesson content would be a second
route to a grade, running on the LMS's own scoring instead of the gradebook.
Canvas's model is the right one and it is already ours: the quiz or the
assignment is a *sibling item in the module*, not something buried in a
lesson. A stripped block leaves a visible marker rather than vanishing, so a
lesson that relied on one degrades into a link instead of a hole.

Surveyed on 2026-09-05, the whole estate uses six block types: paragraph 118,
embed 4, list 3, markdown 1, header 1, quiz 1. The quiz is the entrance exam,
which is admissions-only.
"""

import json

import frappe
from frappe import _

# Blocks that would score a student. Named rather than guessed at, so a new
# interactive block type shows up as unknown and gets a visible marker instead
# of quietly grading somebody.
INTERACTIVE = ("quiz", "assignment", "program")

LESSON_FIELDS = ("name", "title", "chapter", "content", "instructor_content")


def _blocks(content):
	if not content:
		return []
	try:
		parsed = json.loads(content)
	except (ValueError, TypeError):
		return []
	blocks = parsed.get("blocks") if isinstance(parsed, dict) else None
	return blocks if isinstance(blocks, list) else []


def strip_interactive(content):
	"""Return the blocks worth rendering, and note what was taken out.

	Extends the idea in `lms_copy.strip_quizzes`, which already removes quiz
	blocks when copying a lesson -- there because `validate_quiz_id` *moves* a
	quiz rather than copying it, here because an embedded quiz is a second
	grade path.
	"""
	kept, removed = [], []
	for block in _blocks(content):
		if not isinstance(block, dict):
			continue
		if block.get("type") in INTERACTIVE:
			removed.append(block.get("type"))
			continue
		kept.append(block)
	return kept, removed


def block_types(content):
	"""Every distinct block type in one lesson, for the renderer's coverage test."""
	return {
		block.get("type")
		for block in _blocks(content)
		if isinstance(block, dict) and block.get("type")
	}


def estate_block_types():
	"""Every block type stored anywhere.

	The renderer has to have an entry for each, or a lesson renders blank --
	which is the failure mode worth a test rather than a bug report.
	"""
	found = set()
	for content in frappe.get_all("Course Lesson", pluck="content"):
		found |= block_types(content)
	return found


def lesson_payload(lesson):
	"""One lesson, ready to render.

	`instructor_content` is deliberately not returned: it is the LMS's field
	for notes a teacher keeps to themselves.
	"""
	row = frappe.db.get_value(
		"Course Lesson", lesson, ["name", "title", "chapter", "content"], as_dict=True
	)
	if not row:
		frappe.throw(_("Lesson not found."))

	blocks, removed = strip_interactive(row.content)

	return {
		"name": row.name,
		"title": row.title,
		"blocks": blocks,
		# What was taken out, so the reader can say so rather than showing a
		# gap where an exercise used to be.
		"removed": removed,
		"lms_url": _lms_lesson_url(row.name),
	}


def _lms_lesson_url(lesson):
	"""A deep link into the LMS, kept as the fallback.

	A lesson whose content we cannot render is still readable there, which is
	what stops an unrecognised block from being a dead end.
	"""
	chapter = frappe.db.get_value("Course Lesson", lesson, "chapter")
	if not chapter:
		return None
	course = frappe.db.get_value("Course Chapter", chapter, "course")
	if not course:
		return None
	return f"/lms/courses/{course}"
