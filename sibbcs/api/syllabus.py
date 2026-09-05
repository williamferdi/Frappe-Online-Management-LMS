# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""Building a course's modules (staff), and walking through them (student).

Both halves live here because they answer the same question from two sides,
and keeping the outline in one place is what stops a teacher's preview and a
student's screen disagreeing.

The staff endpoints call `permissions.assert_may_teach`, since these read
through `frappe.get_all` and the DocType hooks never see them. The student
endpoints take no student argument and resolve the registration from the
session -- and every one of them asks `modules.item_is_reachable` before
handing over content, because a lock a student can walk around by typing a URL
is decoration.
"""

import frappe
from frappe import _
from frappe.utils import cint

from sibbcs.academic import lesson_content, modules
from sibbcs.academic import permissions as academic_permissions
from sibbcs.academic.portal import get_student
from sibbcs.api.academic_api import ACADEMIC_ROLES

MODULE_FIELDS = ("title", "position", "published", "unlock_at",
				 "require_sequential_progress")

ITEM_FIELDS = ("item_type", "title", "position", "indent", "published",
			   "lesson", "assignment", "page", "file", "url",
			   "completion_requirement", "min_score")


def _require_teaching():
	if not set(frappe.get_roles()).intersection(ACADEMIC_ROLES):
		frappe.throw(
			_("You do not have access to academic records."), frappe.PermissionError
		)


def _my_registration(course_registration):
	"""The registration, if it is this session's own."""
	student = get_student()
	if not student:
		frappe.throw(_("No student record for your account."), frappe.PermissionError)

	row = frappe.db.get_value(
		"Course Registration",
		course_registration,
		["name", "student", "course_offering", "course_title", "status"],
		as_dict=True,
	)
	if not row or row.student != student:
		# The same message either way, so the endpoint does not answer
		# questions about other people's registrations by how it fails.
		frappe.throw(_("Registration not found."), frappe.PermissionError)
	return row


# ---------------------------------------------------------------------------
# staff: building the thing
# ---------------------------------------------------------------------------


@frappe.whitelist()
def outline(course_offering):
	"""Every module and item, published or not."""
	_require_teaching()
	academic_permissions.assert_may_teach(course_offering)

	course = frappe.db.get_value("Course Offering", course_offering, "course")

	return {
		"modules": modules.outline(course_offering, for_staff=True),
		# What a module item can be pointed at, so the builder does not have to
		# guess and a teacher does not have to type a document name.
		"choices": {
			"lessons": _lessons_for(course),
			"assignments": frappe.get_all(
				"Course Assignment",
				filters={"course_offering": course_offering},
				fields=["name", "title"],
				order_by="due_date asc, creation asc",
			),
			"pages": frappe.get_all(
				"Course Page",
				filters={"course": course},
				fields=["name", "title", "published"],
				order_by="title asc",
			),
			"files": frappe.get_all(
				"Course File",
				filters={"course": course, "is_folder": 0},
				fields=["name", "title"],
				order_by="title asc",
			),
			"item_types": _options("Course Module Item", "item_type"),
			"completion_rules": _options("Course Module Item", "completion_requirement"),
		},
	}


def _options(doctype, fieldname):
	options = frappe.get_meta(doctype).get_field(fieldname).options or ""
	return [line.strip() for line in options.split("\n") if line.strip()]


def _lessons_for(course):
	"""The LMS lessons belonging to this course, in their own order.

	Read through the LMS's chapter tables rather than by guessing at names --
	and read only, because the LMS app is vendored.
	"""
	lms_course = frappe.db.get_value("Course", course, "lms_course")
	if not lms_course:
		return []

	# Reference rows carry the order, but a chapter created by a script may
	# have none -- `lms_copy` documents the same thing. Falling back to the
	# documents means a lesson that exists is never invisible to the builder.
	chapter_names = [
		row.chapter
		for row in frappe.get_all(
			"Chapter Reference",
			filters={"parent": lms_course, "parenttype": "LMS Course"},
			fields=["chapter"],
			order_by="idx asc",
		)
	] or frappe.get_all(
		"Course Chapter", filters={"course": lms_course}, pluck="name", order_by="creation asc"
	)

	if not chapter_names:
		return []

	lessons = []
	for chapter in chapter_names:
		title = frappe.db.get_value("Course Chapter", chapter, "title")
		lesson_names = [
			row.lesson
			for row in frappe.get_all(
				"Lesson Reference",
				filters={"parent": chapter, "parenttype": "Course Chapter"},
				fields=["lesson"],
				order_by="idx asc",
			)
		] or frappe.get_all(
			"Course Lesson", filters={"chapter": chapter}, pluck="name", order_by="creation asc"
		)

		for lesson in lesson_names:
			lessons.append(
				{
					"name": lesson,
					"title": frappe.db.get_value("Course Lesson", lesson, "title"),
					"chapter": title,
				}
			)
	return lessons


@frappe.whitelist()
def preview(course_offering, course_registration=None):
	"""The course as a student sees it, for a teacher to check.

	The same `modules.outline` the portal calls, so a preview cannot drift
	from what it previews -- an unpublished module is absent here exactly as
	it is absent there, which is usually the answer to "why can't they see
	it?".

	A registration is optional. With one, the locks and ticks are that
	student's real ones; without, it is a student who has just arrived.
	"""
	_require_teaching()
	academic_permissions.assert_may_teach(course_offering)

	if course_registration:
		theirs = frappe.db.get_value(
			"Course Registration", course_registration, "course_offering"
		)
		if theirs != course_offering:
			frappe.throw(_("That student is not on this course."), frappe.PermissionError)

	return {
		"modules": modules.outline(course_offering, course_registration),
		"roster": frappe.get_all(
			"Course Registration",
			filters={"course_offering": course_offering},
			fields=["name", "student_name"],
			order_by="student_name asc",
		),
		# What a student would not see at all, so the difference is a number
		# rather than something to spot by comparing two screens.
		"unpublished_modules": frappe.db.count(
			"Course Module", {"course_offering": course_offering, "published": 0}
		),
		"unpublished_items": frappe.db.count(
			"Course Module Item", {"course_offering": course_offering, "published": 0}
		),
	}


@frappe.whitelist()
def preview_item(course_offering, module_item):
	"""One item's content, for a teacher checking the course.

	Writes nothing. `read_item` is the student's call and records progress --
	opening a "View it" item completes it -- so previewing through it would
	tick boxes for whichever student was being previewed as.

	Locks are ignored here on purpose: a teacher checking a module that opens
	next week needs to see inside it. The preview still reports the lock
	beside the item, so what a student would meet is not misrepresented.
	"""
	_require_teaching()
	academic_permissions.assert_may_teach(course_offering)

	item = frappe.db.get_value(
		"Course Module Item",
		module_item,
		["name", "course_offering", "item_type", "title", "lesson", "assignment",
		 "page", "file", "url", "completion_requirement", "min_score"],
		as_dict=True,
	)
	if not item:
		frappe.throw(_("Item not found."))
	if item.course_offering != course_offering:
		frappe.throw(_("That item is not on this course."), frappe.PermissionError)

	payload = {"item": item, "content": None}

	if item.item_type == "Lesson" and item.lesson:
		payload["content"] = lesson_content.lesson_payload(item.lesson)
	elif item.item_type == "Page" and item.page:
		page_row = frappe.db.get_value(
			"Course Page", item.page, ["title", "body", "published"], as_dict=True
		)
		if page_row:
			payload["content"] = {"title": page_row.title, "body": page_row.body}
			# A teacher should know an unpublished page reaches nobody.
			payload["unpublished"] = not cint(page_row.published)
	elif item.item_type == "File" and item.file:
		payload["content"] = frappe.db.get_value(
			"Course File", item.file, ["title", "file", "description"], as_dict=True
		)
	elif item.item_type == "Assignment" and item.assignment:
		payload["content"] = frappe.db.get_value(
			"Course Assignment",
			item.assignment,
			["title", "description", "points_possible", "due_date", "published"],
			as_dict=True,
		)

	return payload


@frappe.whitelist(methods=["POST"])
def save_module(course_offering, values, module=None):
	_require_teaching()
	academic_permissions.assert_may_teach(course_offering)

	if isinstance(values, str):
		values = frappe.parse_json(values)
	if not isinstance(values, dict):
		frappe.throw(_("A module must be a set of fields."))

	if module:
		doc = frappe.get_doc("Course Module", module)
		if doc.course_offering != course_offering:
			frappe.throw(_("That module belongs to another course."), frappe.PermissionError)
	else:
		doc = frappe.new_doc("Course Module")
		doc.course_offering = course_offering
		doc.position = _next_position("Course Module", {"course_offering": course_offering})

	for field in MODULE_FIELDS:
		if field in values:
			doc.set(field, values[field])

	if "prerequisites" in values:
		doc.set("prerequisites", [])
		for name in values["prerequisites"] or []:
			if name == doc.name:
				# A module cannot wait for itself.
				continue
			doc.append("prerequisites", {"module": name})

	doc.save()
	frappe.db.commit()
	return {"module": doc.name}


def _next_position(doctype, filters):
	rows = frappe.get_all(
		doctype, filters=filters, fields=["position"], order_by="position desc", limit=1
	)
	return (cint(rows[0].position) + 1) if rows else 0


@frappe.whitelist(methods=["POST"])
def save_item(module, values, item=None):
	_require_teaching()

	offering = frappe.db.get_value("Course Module", module, "course_offering")
	if not offering:
		frappe.throw(_("Module not found."))
	academic_permissions.assert_may_teach(offering)

	if isinstance(values, str):
		values = frappe.parse_json(values)
	if not isinstance(values, dict):
		frappe.throw(_("An item must be a set of fields."))

	if item:
		doc = frappe.get_doc("Course Module Item", item)
		if doc.module != module:
			frappe.throw(_("That item belongs to another module."), frappe.PermissionError)
	else:
		doc = frappe.new_doc("Course Module Item")
		doc.module = module
		doc.position = _next_position("Course Module Item", {"module": module})

	for field in ITEM_FIELDS:
		if field in values:
			doc.set(field, values[field])

	doc.save()
	frappe.db.commit()
	return {"item": doc.name}


@frappe.whitelist(methods=["POST"])
def reorder(module=None, course_offering=None, order=None):
	"""Move modules, or items within a module, into the given order.

	Positions are rewritten from the list rather than swapped in pairs, so a
	half-applied reorder cannot leave two things claiming the same place.
	"""
	_require_teaching()

	if isinstance(order, str):
		order = frappe.parse_json(order)
	if not isinstance(order, list):
		frappe.throw(_("An order must be a list of names."))

	if module:
		offering = frappe.db.get_value("Course Module", module, "course_offering")
		doctype, parent = "Course Module Item", {"module": module}
	else:
		offering = course_offering
		doctype, parent = "Course Module", {"course_offering": course_offering}

	academic_permissions.assert_may_teach(offering)

	allowed = set(frappe.get_all(doctype, filters=parent, pluck="name"))
	for position, name in enumerate(order):
		if name not in allowed:
			# A name from another course would move somebody else's module.
			continue
		frappe.db.set_value(doctype, name, "position", position, update_modified=False)

	frappe.db.commit()
	return {"ordered": len([name for name in order if name in allowed])}


@frappe.whitelist(methods=["POST"])
def delete_module(module):
	_require_teaching()
	offering = frappe.db.get_value("Course Module", module, "course_offering")
	if not offering:
		frappe.throw(_("Module not found."))
	academic_permissions.assert_may_teach(offering)

	for item in frappe.get_all("Course Module Item", filters={"module": module}, pluck="name"):
		frappe.delete_doc("Course Module Item", item)
	frappe.delete_doc("Course Module", module)
	frappe.db.commit()
	return {"deleted": module}


@frappe.whitelist(methods=["POST"])
def delete_item(item):
	_require_teaching()
	offering = frappe.db.get_value("Course Module Item", item, "course_offering")
	if not offering:
		frappe.throw(_("Item not found."))
	academic_permissions.assert_may_teach(offering)

	frappe.delete_doc("Course Module Item", item)
	frappe.db.commit()
	return {"deleted": item}


# ---------------------------------------------------------------------------
# staff: pages
# ---------------------------------------------------------------------------


@frappe.whitelist()
def pages(course):
	_require_teaching()
	return {
		"rows": frappe.get_all(
			"Course Page",
			filters={"course": course},
			fields=["name", "title", "published", "modified"],
			order_by="title asc",
		)
	}


@frappe.whitelist()
def page(name):
	_require_teaching()
	row = frappe.db.get_value(
		"Course Page", name, ["name", "course", "title", "body", "published"], as_dict=True
	)
	if not row:
		frappe.throw(_("Page not found."))
	return row


@frappe.whitelist(methods=["POST"])
def save_page(course, title, body=None, published=None, name=None):
	_require_teaching()

	doc = frappe.get_doc("Course Page", name) if name else frappe.new_doc("Course Page")
	doc.course = course
	doc.title = title
	doc.body = body
	if published is not None:
		doc.published = cint(published)

	doc.save()
	frappe.db.commit()
	return {"page": doc.name}


# ---------------------------------------------------------------------------
# students: walking through it
# ---------------------------------------------------------------------------


@frappe.whitelist()
def my_course(course_registration):
	"""The course as this student sees it: modules, locks and reasons."""
	registration = _my_registration(course_registration)

	return {
		"registration": {
			"name": registration.name,
			"course_title": registration.course_title,
			"course_offering": registration.course_offering,
			"status": registration.status,
		},
		"modules": modules.outline(registration.course_offering, registration.name),
	}


@frappe.whitelist()
def read_item(course_registration, module_item):
	"""Open one item, if this student may.

	Viewing is itself progress when the item asks for it, which is why this
	both checks the lock and records the visit.
	"""
	registration = _my_registration(course_registration)

	state = modules.item_is_reachable(module_item, registration.name)
	if not state["open"]:
		frappe.throw(state["reason"] or _("This is locked."), frappe.PermissionError)

	item = frappe.db.get_value(
		"Course Module Item",
		module_item,
		["name", "item_type", "title", "lesson", "assignment", "page", "file", "url",
		 "completion_requirement", "min_score"],
		as_dict=True,
	)

	payload = {"item": item, "content": None}

	if item.item_type == "Lesson" and item.lesson:
		payload["content"] = lesson_content.lesson_payload(item.lesson)
	elif item.item_type == "Page" and item.page:
		page_row = frappe.db.get_value(
			"Course Page", item.page, ["title", "body", "published"], as_dict=True
		)
		if page_row and cint(page_row.published):
			payload["content"] = {"title": page_row.title, "body": page_row.body}
	elif item.item_type == "File" and item.file:
		payload["content"] = frappe.db.get_value(
			"Course File", item.file, ["title", "file", "description"], as_dict=True
		)

	# Opening it is what "View it" asks for; anything stricter is recorded by
	# whatever actually satisfies it.
	if item.completion_requirement == modules.VIEWED:
		modules.record_progress(module_item, registration.name)
	elif item.completion_requirement != modules.NOTHING:
		modules.record_progress(module_item, registration.name, status="In progress")

	return payload


@frappe.whitelist(methods=["POST"])
def mark_done(course_registration, module_item):
	"""The student says they have finished something.

	Only for items that ask to be marked done. Anything scored or handed in is
	completed by the scoring or the handing in, and letting a student declare
	those finished would be letting them mark their own work.
	"""
	registration = _my_registration(course_registration)

	state = modules.item_is_reachable(module_item, registration.name)
	if not state["open"]:
		frappe.throw(state["reason"] or _("This is locked."), frappe.PermissionError)

	requirement = frappe.db.get_value(
		"Course Module Item", module_item, "completion_requirement"
	)
	if requirement != modules.MARKED_DONE:
		frappe.throw(_("This one is not finished by saying so."))

	modules.record_progress(module_item, registration.name)
	frappe.db.commit()
	return {"item": module_item, "complete": True}
