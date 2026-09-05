# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""What a student may reach, and why not when they may not.

Three things can hold a module shut, and they are checked in the order a
student would ask about them:

    published            nobody outside the staff room can see it at all
    unlock_at            it opens on a date
    prerequisites        another module has to be finished first

and inside an open module, `require_sequential_progress` holds each item until
the one before it is done.

**A lock always carries a reason.** "Why can't I open this?" is the question
the registrar otherwise answers by email, and it is the same judgement the
registration engine already makes for blocked offerings -- `eligibility.explain`
returns a verdict with a reason rather than a bare no.

Nothing here writes a grade. Completing an item records progress; whether that
progress is worth marks is the gradebook's business, and the two never meet.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime, now_datetime

# Requirements that a student satisfies by doing something we can observe.
VIEWED = "View it"
MARKED_DONE = "Mark it done"
HANDED_IN = "Hand it in"
SCORED = "Score at least"
NOTHING = "Nothing"


def modules_for(course_offering, published_only=True):
	filters = {"course_offering": course_offering}
	if published_only:
		filters["published"] = 1
	return frappe.get_all(
		"Course Module",
		filters=filters,
		fields=[
			"name", "title", "position", "published", "unlock_at",
			"require_sequential_progress",
		],
		order_by="position asc, creation asc",
	)


def items_for(modules, published_only=True):
	"""Every item in the given modules, keyed by module."""
	if not modules:
		return {}

	filters = {"module": ("in", modules)}
	if published_only:
		filters["published"] = 1

	by_module = {}
	for item in frappe.get_all(
		"Course Module Item",
		filters=filters,
		fields=[
			"name", "module", "item_type", "title", "position", "indent",
			"published", "lesson", "assignment", "page", "file", "url",
			"completion_requirement", "min_score",
		],
		order_by="position asc, creation asc",
	):
		by_module.setdefault(item.module, []).append(item)
	return by_module


def progress_for(course_registration, items):
	"""What this student has already done, keyed by item."""
	if not items:
		return {}
	return {
		row.module_item: row
		for row in frappe.get_all(
			"Module Item Progress",
			filters={
				"course_registration": course_registration,
				"module_item": ("in", items),
			},
			fields=["name", "module_item", "status", "completed_on", "score"],
		)
	}


def _prerequisites(modules):
	if not modules:
		return {}
	needed = {}
	for row in frappe.get_all(
		"Module Prerequisite",
		filters={"parent": ("in", modules), "parenttype": "Course Module"},
		fields=["parent", "module"],
	):
		needed.setdefault(row.parent, []).append(row.module)
	return needed


def _item_is_complete(item, progress):
	"""Whether one item counts as finished.

	An item asking nothing of the student is complete the moment it exists --
	a sub-header should never hold a sequential module shut.
	"""
	requirement = item.get("completion_requirement") or NOTHING
	if requirement == NOTHING:
		return True

	record = progress.get(item["name"])
	if not record:
		return False

	if requirement == SCORED:
		# A recorded score below the bar is not a pass, however complete the
		# attempt was.
		return flt(record.get("score")) >= flt(item.get("min_score"))

	return record.get("status") == "Complete"


def module_state(module, items, progress, completed_modules, now=None):
	"""Whether a module is open, and the reason when it is not."""
	now = now or now_datetime()

	if module.get("unlock_at") and now < get_datetime(module["unlock_at"]):
		when = get_datetime(module["unlock_at"]).strftime("%d %b %Y, %H:%M")
		return {"open": False, "reason": _("This opens on {0}.").format(when)}

	missing = [
		name for name in module.get("_prerequisites", []) if name not in completed_modules
	]
	if missing:
		titles = [
			frappe.db.get_value("Course Module", name, "title") or name for name in missing
		]
		return {
			"open": False,
			"reason": _("Finish {0} first.").format(", ".join(titles)),
		}

	return {"open": True, "reason": None}


def _module_is_complete(items, progress):
	return all(_item_is_complete(item, progress) for item in items)


def outline(course_offering, course_registration=None, for_staff=False):
	"""The whole course as a student sees it, locks and reasons included.

	Four queries whatever the size of the course: modules, their items, their
	prerequisites, and this student's progress.
	"""
	modules = modules_for(course_offering, published_only=not for_staff)
	names = [module.name for module in modules]
	items = items_for(names, published_only=not for_staff)

	needed = _prerequisites(names)
	for module in modules:
		module["_prerequisites"] = needed.get(module.name, [])

	every_item = [item["name"] for rows in items.values() for item in rows]
	progress = (
		progress_for(course_registration, every_item) if course_registration else {}
	)

	# Completion has to be worked out in order, because a module can require
	# one that comes before it.
	completed = set()
	for module in modules:
		if _module_is_complete(items.get(module.name, []), progress):
			completed.add(module.name)

	now = now_datetime()
	out = []
	for module in modules:
		rows = items.get(module.name, [])
		state = (
			{"open": True, "reason": None}
			if for_staff
			else module_state(module, rows, progress, completed, now)
		)

		sequential = cint(module.get("require_sequential_progress"))
		blocked_from = None
		if sequential and not for_staff:
			for index, item in enumerate(rows):
				if not _item_is_complete(item, progress):
					blocked_from = index + 1
					break

		out.append(
			{
				"name": module.name,
				"title": module.title,
				"position": module.position,
				"published": cint(module.published),
				"unlock_at": module.unlock_at,
				"require_sequential_progress": sequential,
				"prerequisites": module["_prerequisites"],
				"state": state,
				"complete": module.name in completed,
				"items": [
					{
						**item,
						"progress": progress.get(item["name"]),
						"complete": _item_is_complete(item, progress),
						"locked": bool(
							not state["open"]
							or (blocked_from is not None and index >= blocked_from)
						),
						"lock_reason": (
							state["reason"]
							if not state["open"]
							else _("Finish the item before this one first.")
							if blocked_from is not None and index >= blocked_from
							else None
						),
					}
					for index, item in enumerate(rows)
				],
			}
		)

	return out


def item_is_reachable(module_item, course_registration):
	"""Whether this student may open this item, and why not.

	Asked by every endpoint that hands over content, because a lock a student
	can walk around by typing a URL is decoration.
	"""
	item = frappe.db.get_value(
		"Course Module Item",
		module_item,
		["name", "module", "course_offering", "published"],
		as_dict=True,
	)
	if not item:
		return {"open": False, "reason": _("Not found.")}

	# The item has to be on the course this registration is for. Without this
	# the outline below is built from the *item's* offering, which asks "is
	# this unlocked in its own course" rather than "is this unlocked for you"
	# -- and every published item in the college answers yes.
	offering = frappe.db.get_value(
		"Course Registration", course_registration, "course_offering"
	)
	if not offering or offering != item.course_offering:
		return {"open": False, "reason": _("This is not part of your course.")}

	if not cint(item.published):
		return {"open": False, "reason": _("This is not published.")}

	for module in outline(item.course_offering, course_registration):
		for row in module["items"]:
			if row["name"] == module_item:
				if row["locked"]:
					return {"open": False, "reason": row["lock_reason"]}
				return {"open": True, "reason": None}

	return {"open": False, "reason": _("This is not part of your course.")}


def record_progress(module_item, course_registration, status="Complete", score=None):
	"""Note that a student has done something.

	One row per item per registration, so viewing a lesson twice does not
	create a second record and re-completing is not a new fact.
	"""
	existing = frappe.db.exists(
		"Module Item Progress",
		{"module_item": module_item, "course_registration": course_registration},
	)

	if existing:
		doc = frappe.get_doc("Module Item Progress", existing)
	else:
		doc = frappe.new_doc("Module Item Progress")
		doc.module_item = module_item
		doc.course_registration = course_registration

	# Completion does not un-complete: a student who finished a lesson and
	# opens it again has not gone backwards.
	if doc.status != "Complete" or status == "Complete":
		doc.status = status
	if status == "Complete" and not doc.completed_on:
		doc.completed_on = now_datetime()
	if score is not None:
		doc.score = flt(score)

	doc.save(ignore_permissions=True)
	return doc.name
