# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""The course player: one screen a student works through a course in.

Everything here resolves the registration from the session and takes no
student argument, like the rest of the portal.

**The sequence is the point.** `modules.outline` answers "what is in this
course and what is locked"; a player also needs "what comes next", so the
outline is flattened once into the order a student meets things in, and each
entry knows its neighbours. Doing that on the server means the sidebar, the
Previous/Next buttons and the progress figure all count the same things --
three places that disagree about how far through you are is worse than no
figure at all.

**Progress counts what was asked for.** An item with no completion requirement
is not something a student can fail to do, so it is not in the denominator. A
course that asks nothing shows no percentage rather than a permanent 100%.
"""

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from sibbcs.academic import lesson_content, modules
from sibbcs.academic.portal import get_student

# Items that are furniture rather than work.
FURNITURE = ("Sub-header",)


def _my_registration(course_registration):
	student = get_student()
	if not student:
		frappe.throw(_("No student record for your account."), frappe.PermissionError)

	row = frappe.db.get_value(
		"Course Registration",
		course_registration,
		["name", "student", "course_offering", "course_title", "course"],
		as_dict=True,
	)
	if not row or row.student != student:
		frappe.throw(_("Registration not found."), frappe.PermissionError)
	return row


def _flatten(outline):
	"""The order a student meets things in, ignoring furniture.

	Previous and Next skip sub-headers, because stepping onto a heading and
	having to press again is a button that did nothing.
	"""
	sequence = []
	for module in outline:
		for item in module["items"]:
			if item["item_type"] in FURNITURE:
				continue
			sequence.append({"module": module["name"], "item": item})
	return sequence


def _progress(sequence):
	"""How far through, counting only what the course actually asks for."""
	required = [
		entry
		for entry in sequence
		if (entry["item"].get("completion_requirement") or "Nothing") != "Nothing"
	]
	if not required:
		return {"done": 0, "total": 0, "percent": None}

	done = sum(1 for entry in required if entry["item"]["complete"])
	return {
		"done": done,
		"total": len(required),
		"percent": round(done * 100 / len(required)),
	}


def _notes_for(course_registration, items):
	if not items:
		return {}
	return {
		row.module_item: row
		for row in frappe.get_all(
			"Lesson Note",
			filters={
				"course_registration": course_registration,
				"module_item": ("in", items),
			},
			fields=["name", "module_item", "body", "bookmarked"],
		)
	}


@frappe.whitelist()
def course(course_registration):
	"""Everything the player's sidebar and header need, in one call."""
	registration = _my_registration(course_registration)
	outline = modules.outline(registration.course_offering, registration.name)
	sequence = _flatten(outline)

	notes = _notes_for(
		registration.name, [entry["item"]["name"] for entry in sequence]
	)

	for module in outline:
		for item in module["items"]:
			note = notes.get(item["name"])
			item["bookmarked"] = bool(note and cint(note.bookmarked))
			item["has_note"] = bool(note and (note.body or "").strip())

	return {
		"registration": {
			"name": registration.name,
			"course_title": registration.course_title,
			"course_offering": registration.course_offering,
		},
		"modules": outline,
		"progress": _progress(sequence),
		# The order the buttons walk, so the client does not rebuild it and
		# risk disagreeing with the server about what comes next.
		"sequence": [entry["item"]["name"] for entry in sequence],
	}


@frappe.whitelist()
def item(course_registration, module_item):
	"""One item to work on, with what sits either side of it.

	This is the student's own read, so it records progress -- opening a "View
	it" item is what completes it. `syllabus.preview_item` is the staff read
	that does not.
	"""
	registration = _my_registration(course_registration)

	state = modules.item_is_reachable(module_item, registration.name)
	if not state["open"]:
		frappe.throw(state["reason"] or _("This is locked."), frappe.PermissionError)

	outline = modules.outline(registration.course_offering, registration.name)
	sequence = _flatten(outline)
	names = [entry["item"]["name"] for entry in sequence]

	if module_item not in names:
		frappe.throw(_("This is not part of your course."), frappe.PermissionError)

	index = names.index(module_item)
	row = next(entry for entry in sequence if entry["item"]["name"] == module_item)
	item_row = row["item"]

	payload = {
		"item": item_row,
		"module": row["module"],
		"previous": names[index - 1] if index > 0 else None,
		"next": names[index + 1] if index < len(names) - 1 else None,
		"position": {"index": index + 1, "total": len(names)},
		"content": None,
		"resources": [],
		"note": None,
	}

	if item_row["item_type"] == "Lesson" and item_row.get("lesson"):
		payload["content"] = lesson_content.lesson_payload(item_row["lesson"])
	elif item_row["item_type"] == "Page" and item_row.get("page"):
		page = frappe.db.get_value(
			"Course Page", item_row["page"], ["title", "body", "published"], as_dict=True
		)
		if page and cint(page.published):
			payload["content"] = {"title": page.title, "body": page.body}
	elif item_row["item_type"] == "File" and item_row.get("file"):
		payload["content"] = frappe.db.get_value(
			"Course File", item_row["file"], ["title", "file", "description"], as_dict=True
		)
	elif item_row["item_type"] == "Assignment" and item_row.get("assignment"):
		payload["content"] = frappe.db.get_value(
			"Course Assignment",
			item_row["assignment"],
			["name", "title", "description", "points_possible", "due_date", "submission_type"],
			as_dict=True,
		)

	payload["resources"] = _resources_for(registration, row["module"], module_item)

	note = _notes_for(registration.name, [module_item]).get(module_item)
	if note:
		payload["note"] = {"body": note.body, "bookmarked": cint(note.bookmarked)}

	# Same rule as `syllabus.read_item`: opening it is what "View it" asks for,
	# and anything stricter is completed by whatever actually satisfies it.
	requirement = item_row.get("completion_requirement")
	if requirement == modules.VIEWED:
		modules.record_progress(module_item, registration.name)
	elif requirement and requirement != modules.NOTHING:
		modules.record_progress(module_item, registration.name, status="In progress")

	frappe.db.commit()
	return payload


def _resources_for(registration, module_name, module_item):
	"""The files in this module, offered beside whatever is being read.

	A reading list belongs next to the reading, not three clicks away in a
	files tab.
	"""
	rows = frappe.get_all(
		"Course Module Item",
		filters={"module": module_name, "item_type": "File", "published": 1},
		fields=["name", "title", "file"],
		order_by="position asc",
	)

	resources = []
	for row in rows:
		if row.name == module_item or not row.file:
			continue
		record = frappe.db.get_value(
			"Course File", row.file, ["title", "file", "description"], as_dict=True
		)
		if record and record.file:
			resources.append(
				{
					"item": row.name,
					"title": row.title or record.title,
					"url": record.file,
					"description": record.description,
				}
			)
	return resources


# ---------------------------------------------------------------------------
# the student's own marks on the page
# ---------------------------------------------------------------------------


def _note_doc(course_registration, module_item):
	existing = frappe.db.exists(
		"Lesson Note",
		{"course_registration": course_registration, "module_item": module_item},
	)
	if existing:
		return frappe.get_doc("Lesson Note", existing)

	doc = frappe.new_doc("Lesson Note")
	doc.course_registration = course_registration
	doc.module_item = module_item
	return doc


@frappe.whitelist(methods=["POST"])
def save_note(course_registration, module_item, body):
	"""Keep a student's note. One row per item, rewritten rather than added to.

	Written with `ignore_permissions`: a student holds nothing on Lesson Note
	by design, because a note is private and the check that matters is
	`_my_registration` above.
	"""
	registration = _my_registration(course_registration)
	_must_be_on_this_course(module_item, registration)

	doc = _note_doc(registration.name, module_item)
	doc.body = body
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	return {"saved": True, "at": now_datetime()}


@frappe.whitelist(methods=["POST"])
def toggle_bookmark(course_registration, module_item):
	registration = _my_registration(course_registration)
	_must_be_on_this_course(module_item, registration)

	doc = _note_doc(registration.name, module_item)
	doc.bookmarked = 0 if cint(doc.bookmarked) else 1
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	return {"bookmarked": cint(doc.bookmarked)}


def _must_be_on_this_course(module_item, registration):
	offering = frappe.db.get_value("Course Module Item", module_item, "course_offering")
	if offering != registration.course_offering:
		frappe.throw(_("That is not part of your course."), frappe.PermissionError)


@frappe.whitelist()
def bookmarks(course_registration):
	"""Everything this student has marked on this course."""
	registration = _my_registration(course_registration)

	rows = frappe.get_all(
		"Lesson Note",
		filters={"course_registration": registration.name, "bookmarked": 1},
		fields=["module_item", "body"],
	)
	for row in rows:
		row["title"] = frappe.db.get_value("Course Module Item", row.module_item, "title")
	return {"rows": rows}
