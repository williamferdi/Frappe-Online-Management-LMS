# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""Writing course content without leaving this app.

Lessons, pages and files, authored here. Until now a lesson could only be
written in the LMS's own editor, and pages and files could not be created
anywhere at all -- so those module item types were decorative.

**Lessons are still stored in the LMS.** A lesson written here is an ordinary
`Course Lesson` with EditorJS JSON in `content`, filed under a `Course Chapter`
and referenced from the `LMS Course` exactly as the LMS's own editor does. That
matters twice over: the LMS keeps working as the content store, and a lesson
written here is still readable and editable there.

Writing LMS *data* is what `lms_copy` and `lms_sync` already do. What nobody
does, here or anywhere, is change the vendored LMS *app* -- `bench update`
replaces it.

**Both reference tables are maintained.** `Chapter Reference` on the course and
`Lesson Reference` on the chapter are what carry the order, and the LMS editor
reads them. Writing a chapter without its reference row produces a chapter that
this app can find and the LMS cannot.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint

from sibbcs.academic import permissions as academic_permissions
from sibbcs.api.academic_api import ACADEMIC_ROLES

# The block types the renderer draws. A lesson may only be saved out of these,
# so the editor cannot write something the reader would have to apologise for.
BLOCK_TYPES = (
	"header",
	"paragraph",
	"list",
	"quote",
	"code",
	"image",
	"embed",
	"delimiter",
)


def _require_teaching():
	if not set(frappe.get_roles()).intersection(ACADEMIC_ROLES):
		frappe.throw(
			_("You do not have access to academic records."), frappe.PermissionError
		)


def _course_of(course_offering):
	course = frappe.db.get_value("Course Offering", course_offering, "course")
	if not course:
		frappe.throw(_("Course Offering not found."))
	academic_permissions.assert_may_teach(course_offering)
	return course


def _lms_course_of(course):
	lms_course = frappe.db.get_value("Course", course, "lms_course")
	if not lms_course or not frappe.db.exists("LMS Course", lms_course):
		frappe.throw(
			_("This course has nowhere to keep lessons yet. Set up lessons first.")
		)
	return lms_course


# ---------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------


@frappe.whitelist()
def outline(course_offering):
	"""Every chapter and lesson, plus the course's pages and files.

	Read from the reference tables where they exist and from the documents
	themselves where they do not -- the same fallback `lms_copy` uses, because
	a chapter created by a script may have no reference row and would
	otherwise be invisible.
	"""
	_require_teaching()
	course = _course_of(course_offering)
	lms_course = frappe.db.get_value("Course", course, "lms_course")

	chapters = []
	if lms_course and frappe.db.exists("LMS Course", lms_course):
		for name in _chapters_in_order(lms_course):
			chapters.append(
				{
					"name": name,
					"title": frappe.db.get_value("Course Chapter", name, "title"),
					"lessons": [
						frappe.db.get_value(
							"Course Lesson", lesson, ["name", "title"], as_dict=True
						)
						for lesson in _lessons_in_order(name)
					],
				}
			)

	return {
		"course": course,
		"lms_course": lms_course,
		"chapters": chapters,
		"pages": frappe.get_all(
			"Course Page",
			filters={"course": course},
			fields=["name", "title", "published", "modified"],
			order_by="title asc",
		),
		"files": frappe.get_all(
			"Course File",
			filters={"course": course},
			fields=["name", "title", "file", "is_folder", "description"],
			order_by="title asc",
		),
		"block_types": list(BLOCK_TYPES),
	}


def _chapters_in_order(lms_course):
	referenced = frappe.get_all(
		"Chapter Reference",
		filters={"parent": lms_course, "parenttype": "LMS Course"},
		fields=["chapter"],
		order_by="idx asc",
	)
	if referenced:
		return [row.chapter for row in referenced]
	return frappe.get_all(
		"Course Chapter", filters={"course": lms_course}, pluck="name", order_by="creation asc"
	)


def _lessons_in_order(chapter):
	referenced = frappe.get_all(
		"Lesson Reference",
		filters={"parent": chapter, "parenttype": "Course Chapter"},
		fields=["lesson"],
		order_by="idx asc",
	)
	if referenced:
		return [row.lesson for row in referenced]
	return frappe.get_all(
		"Course Lesson", filters={"chapter": chapter}, pluck="name", order_by="creation asc"
	)


@frappe.whitelist()
def lesson(name):
	"""One lesson, as blocks the editor can work on."""
	_require_teaching()

	row = frappe.db.get_value(
		"Course Lesson", name, ["name", "title", "chapter", "content"], as_dict=True
	)
	if not row:
		frappe.throw(_("Lesson not found."))

	blocks = []
	if row.content:
		try:
			parsed = json.loads(row.content)
			blocks = parsed.get("blocks") or []
		except (ValueError, TypeError):
			# Content written by something else, or damaged. An empty editor
			# beats an exception, and the original is not overwritten until
			# the author saves.
			blocks = []

	return {"name": row.name, "title": row.title, "chapter": row.chapter, "blocks": blocks}


# ---------------------------------------------------------------------------
# writing
# ---------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def save_chapter(course_offering, title, name=None):
	"""Create or rename a chapter, keeping the course's reference row."""
	_require_teaching()
	course = _course_of(course_offering)
	lms_course = _lms_course_of(course)

	if name:
		chapter = frappe.get_doc("Course Chapter", name)
		if chapter.course != lms_course:
			frappe.throw(_("That chapter belongs to another course."), frappe.PermissionError)
		chapter.title = title
		chapter.save(ignore_permissions=True)
	else:
		chapter = frappe.get_doc(
			{"doctype": "Course Chapter", "course": lms_course, "title": title}
		).insert(ignore_permissions=True)

		# Refetched after the insert: a document held across one is stale and
		# its save is refused. `lms_copy` learned this the hard way.
		course_doc = frappe.get_doc("LMS Course", lms_course)
		course_doc.append("chapters", {"chapter": chapter.name})
		course_doc.save(ignore_permissions=True)

	frappe.db.commit()
	return {"chapter": chapter.name, "title": chapter.title}


@frappe.whitelist(methods=["POST"])
def save_lesson(course_offering, chapter, title, blocks, name=None):
	"""Write a lesson as EditorJS content.

	The blocks are rebuilt here rather than trusted: an unknown type is
	dropped, so the editor cannot save something the reader would meet as an
	"unrecognised block" notice.
	"""
	_require_teaching()
	course = _course_of(course_offering)
	lms_course = _lms_course_of(course)

	if frappe.db.get_value("Course Chapter", chapter, "course") != lms_course:
		frappe.throw(_("That chapter belongs to another course."), frappe.PermissionError)

	if isinstance(blocks, str):
		blocks = frappe.parse_json(blocks)
	if not isinstance(blocks, list):
		frappe.throw(_("A lesson is a list of blocks."))

	kept = [
		{"type": block.get("type"), "data": block.get("data") or {}}
		for block in blocks
		if isinstance(block, dict) and block.get("type") in BLOCK_TYPES
	]

	content = json.dumps({"time": 0, "blocks": kept, "version": "2.28.0"})

	if name:
		doc = frappe.get_doc("Course Lesson", name)
		if doc.course != lms_course:
			frappe.throw(_("That lesson belongs to another course."), frappe.PermissionError)
		doc.title = title
		doc.content = content
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc(
			{
				"doctype": "Course Lesson",
				"course": lms_course,
				"chapter": chapter,
				"title": title,
				"content": content,
			}
		).insert(ignore_permissions=True)

		# The chapter's own reference row, which is what carries lesson order
		# and what the LMS editor reads.
		chapter_doc = frappe.get_doc("Course Chapter", chapter)
		chapter_doc.append("lessons", {"lesson": doc.name})
		chapter_doc.save(ignore_permissions=True)

	frappe.db.commit()
	return {"lesson": doc.name, "title": doc.title, "blocks": kept}


@frappe.whitelist(methods=["POST"])
def delete_lesson(course_offering, name):
	"""Remove a lesson, and anything pointing at it.

	A module item left pointing at a deleted lesson is an item a student
	cannot open and a teacher cannot explain, so it goes with it.
	"""
	_require_teaching()
	course = _course_of(course_offering)
	lms_course = _lms_course_of(course)

	if frappe.db.get_value("Course Lesson", name, "course") != lms_course:
		frappe.throw(_("That lesson belongs to another course."), frappe.PermissionError)

	orphaned = frappe.get_all(
		"Course Module Item", filters={"item_type": "Lesson", "lesson": name}, pluck="name"
	)
	for item in orphaned:
		frappe.delete_doc("Course Module Item", item, ignore_permissions=True)

	# The chapter's reference row points at this lesson, and Frappe refuses to
	# delete something still linked. Unpicked in the order it was built:
	# reference first, document second.
	chapter = frappe.db.get_value("Course Lesson", name, "chapter")
	if chapter and frappe.db.exists("Course Chapter", chapter):
		doc = frappe.get_doc("Course Chapter", chapter)
		remaining = [row.lesson for row in doc.lessons if row.lesson != name]
		if len(remaining) != len(doc.lessons):
			doc.set("lessons", [{"lesson": lesson} for lesson in remaining])
			doc.save(ignore_permissions=True)

	frappe.delete_doc("Course Lesson", name, ignore_permissions=True)
	frappe.db.commit()
	return {"deleted": name, "module_items_removed": len(orphaned)}


@frappe.whitelist(methods=["POST"])
def delete_chapter(course_offering, name):
	"""Remove a chapter, its lessons, and everything pointing at them.

	A chapter is not deletable while the course still references it, and its
	lessons are not deletable while it references them -- so it comes apart
	from the inside out.
	"""
	_require_teaching()
	course = _course_of(course_offering)
	lms_course = _lms_course_of(course)

	if frappe.db.get_value("Course Chapter", name, "course") != lms_course:
		frappe.throw(_("That chapter belongs to another course."), frappe.PermissionError)

	removed = 0
	for lesson in _lessons_in_order(name):
		removed += delete_lesson(course_offering, lesson)["module_items_removed"]

	course_doc = frappe.get_doc("LMS Course", lms_course)
	remaining = [row.chapter for row in course_doc.chapters if row.chapter != name]
	if len(remaining) != len(course_doc.chapters):
		course_doc.set("chapters", [{"chapter": chapter} for chapter in remaining])
		course_doc.save(ignore_permissions=True)

	frappe.delete_doc("Course Chapter", name, ignore_permissions=True)
	frappe.db.commit()
	return {"deleted": name, "module_items_removed": removed}


# ---------------------------------------------------------------------------
# pages and files -- the item types that had no way to exist
# ---------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def save_page(course_offering, title, body=None, published=None, name=None):
	_require_teaching()
	course = _course_of(course_offering)

	doc = frappe.get_doc("Course Page", name) if name else frappe.new_doc("Course Page")
	if name and doc.course != course:
		frappe.throw(_("That page belongs to another course."), frappe.PermissionError)

	doc.course = course
	doc.title = title
	doc.body = body
	if published is not None:
		doc.published = cint(published)

	doc.save()
	frappe.db.commit()
	return {"page": doc.name, "published": cint(doc.published)}


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
def delete_page(course_offering, name):
	_require_teaching()
	course = _course_of(course_offering)
	if frappe.db.get_value("Course Page", name, "course") != course:
		frappe.throw(_("That page belongs to another course."), frappe.PermissionError)

	for item in frappe.get_all(
		"Course Module Item", filters={"item_type": "Page", "page": name}, pluck="name"
	):
		frappe.delete_doc("Course Module Item", item, ignore_permissions=True)

	frappe.delete_doc("Course Page", name, ignore_permissions=True)
	frappe.db.commit()
	return {"deleted": name}


@frappe.whitelist(methods=["POST"])
def save_file(course_offering, title, file=None, description=None, name=None):
	"""Register a file against the course.

	The bytes are uploaded by Frappe's own upload endpoint, which stores a
	`File` and hands back its URL; this records what that file is for.
	"""
	_require_teaching()
	course = _course_of(course_offering)

	doc = frappe.get_doc("Course File", name) if name else frappe.new_doc("Course File")
	if name and doc.course != course:
		frappe.throw(_("That file belongs to another course."), frappe.PermissionError)

	doc.course = course
	doc.title = title
	if file is not None:
		doc.file = file
	doc.description = description
	doc.save()
	frappe.db.commit()
	return {"file": doc.name}


@frappe.whitelist(methods=["POST"])
def delete_file(course_offering, name):
	_require_teaching()
	course = _course_of(course_offering)
	if frappe.db.get_value("Course File", name, "course") != course:
		frappe.throw(_("That file belongs to another course."), frappe.PermissionError)

	for item in frappe.get_all(
		"Course Module Item", filters={"item_type": "File", "file": name}, pluck="name"
	):
		frappe.delete_doc("Course Module Item", item, ignore_permissions=True)

	frappe.delete_doc("Course File", name, ignore_permissions=True)
	frappe.db.commit()
	return {"deleted": name}
