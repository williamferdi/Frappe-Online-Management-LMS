# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""The course shell a teacher builds: its grade scheme and its assignments.

Everything here is faculty-facing. There is no portal route to any of it in
this phase and `published` defaults to 0, so a student sees nothing until the
screens that show them arrive.

Two habits carried over from the rest of the API. Reads go through
`frappe.get_all`, which bypasses permissions, so every endpoint asks
`permissions.assert_may_teach` for itself -- the DocType hooks never see these
calls. And writes go through the document rather than around it: the
controllers hold the rules about weights totalling a hundred and dates running
forwards, and `ignore_permissions` here would quietly remove them.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from sibbcs.academic import gradebook
from sibbcs.academic import permissions as academic_permissions
from sibbcs.api.academic_api import ACADEMIC_ROLES

# What a teacher may set on a piece of work. Named rather than accepted
# wholesale: a dict straight from the browser is how `name`, `owner` or
# `course_offering` gets rewritten by a payload nobody looked at.
ASSIGNMENT_FIELDS = (
	"title",
	"description",
	"component",
	"points_possible",
	"grading_type",
	"submission_type",
	"due_date",
	"available_from",
	"available_until",
	"late_policy",
	"late_penalty_pct_per_day",
	"allowed_attempts",
	"published",
)

ASSIGNMENT_LIST_FIELDS = (
	"name",
	"title",
	"component",
	"points_possible",
	"submission_type",
	"grading_type",
	"due_date",
	"available_from",
	"available_until",
	"late_policy",
	"late_penalty_pct_per_day",
	"allowed_attempts",
	"published",
	"description",
)


def _require_teaching():
	roles = set(frappe.get_roles())
	if not roles.intersection(ACADEMIC_ROLES):
		frappe.throw(
			_("You do not have access to academic records."), frappe.PermissionError
		)


def _options(doctype, fieldname):
	options = frappe.get_meta(doctype).get_field(fieldname).options or ""
	return [line.strip() for line in options.split("\n") if line.strip()]


# ---------------------------------------------------------------------------
# the shelf
# ---------------------------------------------------------------------------


@frappe.whitelist()
def courses(term=None):
	"""Every offering this user may build, with how far each has got.

	Scoped the same way the offerings list is: None means the whole register,
	a list means these and no others, and an empty list is a teacher who has
	been given no course.
	"""
	_require_teaching()

	filters = {}
	if term:
		filters["term"] = term

	scope = academic_permissions.offering_scope()
	if scope is not None:
		filters["name"] = ("in", scope)

	rows = frappe.get_all(
		"Course Offering",
		filters=filters,
		fields=[
			"name", "course", "course_title", "term", "status", "format",
			"instructor", "facilitator", "enrolled_count", "credits", "course_level",
		],
		order_by="term desc, course asc",
	)

	names = [row.name for row in rows]
	schemed = set(
		frappe.get_all(
			"Course Grade Scheme",
			filters={"course_offering": ("in", names)} if names else {"name": ("in", [])},
			pluck="course_offering",
		)
	)

	counts, published = {}, {}
	if names:
		for row in frappe.get_all(
			"Course Assignment",
			filters={"course_offering": ("in", names)},
			fields=["course_offering", "published", "count(name) as n"],
			group_by="course_offering, published",
		):
			counts[row.course_offering] = counts.get(row.course_offering, 0) + cint(row.n)
			if cint(row.published):
				published[row.course_offering] = cint(row.n)

	for row in rows:
		row["has_scheme"] = row.name in schemed
		row["assignments"] = counts.get(row.name, 0)
		row["published_assignments"] = published.get(row.name, 0)

	return {
		"rows": rows,
		"terms": frappe.get_all(
			"Academic Term",
			fields=["name", "term_name", "status"],
			order_by="start_date desc",
		),
	}


@frappe.whitelist()
def course(course_offering):
	"""One offering: what it is, how it is weighted, and what has been set."""
	_require_teaching()
	academic_permissions.assert_may_teach(course_offering)

	offering = frappe.db.get_value(
		"Course Offering",
		course_offering,
		["name", "course", "course_title", "term", "status", "format", "instructor",
		 "facilitator", "capacity", "enrolled_count", "credits", "course_level"],
		as_dict=True,
	)
	if not offering:
		frappe.throw(_("Course Offering not found."))

	return {
		"offering": offering,
		"scheme": _scheme_payload(course_offering),
		"assignments": frappe.get_all(
			"Course Assignment",
			filters={"course_offering": course_offering},
			fields=list(ASSIGNMENT_LIST_FIELDS),
			order_by="due_date asc, creation asc",
		),
		"choices": choices(),
	}


@frappe.whitelist()
def choices():
	"""The option lists, read from the DocTypes rather than repeated here.

	A component added in Desk has to reach the scheme editor, or a teacher can
	build a scheme that no assignment can ever count towards.
	"""
	return {
		"components": _options("Grade Component", "component"),
		"submission_types": _options("Course Assignment", "submission_type"),
		"grading_types": _options("Course Assignment", "grading_type"),
		"late_policies": _options("Course Assignment", "late_policy"),
		"posting_policies": _options("Grade Scheme Row", "posting_policy"),
	}


def _scheme_payload(course_offering):
	if not frappe.db.exists("Course Grade Scheme", course_offering):
		return None

	doc = frappe.get_doc("Course Grade Scheme", course_offering)
	return {
		"name": doc.name,
		"total_weight": flt(doc.total_weight),
		"rows": [
			{
				"component": row.component,
				"weight_pct": flt(row.weight_pct),
				"drop_lowest": cint(row.drop_lowest),
				"posting_policy": row.posting_policy,
			}
			for row in doc.rows
		],
	}


# ---------------------------------------------------------------------------
# the scheme
# ---------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def save_scheme(course_offering, rows):
	"""Create or rewrite an offering's grade scheme.

	Saved through the document, so the weights-total-a-hundred rule and the
	re-sync of every registration on the offering both happen where they
	belong.
	"""
	_require_teaching()
	academic_permissions.assert_may_teach(course_offering)

	if isinstance(rows, str):
		rows = frappe.parse_json(rows)
	if not isinstance(rows, list):
		frappe.throw(_("A grade scheme must be a list of components."))

	if frappe.db.exists("Course Grade Scheme", course_offering):
		doc = frappe.get_doc("Course Grade Scheme", course_offering)
	else:
		doc = frappe.new_doc("Course Grade Scheme")
		doc.course_offering = course_offering

	doc.set("rows", [])
	for row in rows:
		if not (row or {}).get("component"):
			continue
		doc.append(
			"rows",
			{
				"component": row["component"],
				"weight_pct": flt(row.get("weight_pct")),
				"drop_lowest": cint(row.get("drop_lowest")),
				"posting_policy": row.get("posting_policy") or "Manual",
			},
		)

	doc.save()
	frappe.db.commit()

	return {"scheme": _scheme_payload(course_offering)}


@frappe.whitelist(methods=["POST"])
def delete_scheme(course_offering):
	"""Hand the offering back to hand marking.

	The marks are left exactly where they are; what stops is the recomputing.
	"""
	_require_teaching()
	academic_permissions.assert_may_teach(course_offering)

	if not frappe.db.exists("Course Grade Scheme", course_offering):
		return {"scheme": None}

	frappe.delete_doc("Course Grade Scheme", course_offering)
	frappe.db.commit()
	return {"scheme": None}


# ---------------------------------------------------------------------------
# the work
# ---------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def save_assignment(course_offering, values, assignment=None):
	"""Set a new piece of work, or change one already set."""
	_require_teaching()
	academic_permissions.assert_may_teach(course_offering)

	if isinstance(values, str):
		values = frappe.parse_json(values)
	if not isinstance(values, dict):
		frappe.throw(_("An assignment must be a set of fields."))

	if assignment:
		doc = frappe.get_doc("Course Assignment", assignment)
		if doc.course_offering != course_offering:
			frappe.throw(
				_("That assignment belongs to another course."), frappe.PermissionError
			)
	else:
		doc = frappe.new_doc("Course Assignment")
		doc.course_offering = course_offering

	for field in ASSIGNMENT_FIELDS:
		if field in values:
			doc.set(field, values[field])

	doc.save()
	frappe.db.commit()

	return {
		"assignment": frappe.db.get_value(
			"Course Assignment", doc.name, list(ASSIGNMENT_LIST_FIELDS), as_dict=True
		)
	}


@frappe.whitelist(methods=["POST"])
def delete_assignment(assignment):
	_require_teaching()

	offering = frappe.db.get_value("Course Assignment", assignment, "course_offering")
	if not offering:
		frappe.throw(_("Assignment not found."))
	academic_permissions.assert_may_teach(offering)

	frappe.delete_doc("Course Assignment", assignment)
	frappe.db.commit()
	return {"deleted": assignment}


@frappe.whitelist(methods=["POST"])
def set_published(assignment, published):
	"""Publish or withdraw one piece of work.

	Its own endpoint because it is the one change a teacher makes without
	opening the editor, and because publishing is the moment work becomes
	visible to a student.
	"""
	_require_teaching()

	offering = frappe.db.get_value("Course Assignment", assignment, "course_offering")
	if not offering:
		frappe.throw(_("Assignment not found."))
	academic_permissions.assert_may_teach(offering)

	doc = frappe.get_doc("Course Assignment", assignment)
	doc.published = cint(published)
	doc.save()
	frappe.db.commit()

	return {"assignment": assignment, "published": cint(doc.published)}
