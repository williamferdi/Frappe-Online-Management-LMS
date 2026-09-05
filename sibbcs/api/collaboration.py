# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""Graded discussions, groups, differentiated dates and peer review.

The staff half builds them; the student half takes part. As everywhere else,
staff endpoints ask `permissions.assert_may_teach` because they read through
`frappe.get_all`, and student endpoints resolve the registration from the
session and take no student argument.

**A graded discussion is a Course Assignment whose submission is
participation.** The room is Frappe's own Discussion Topic, which
`api/comms.py` already serves per offering -- so posting uses the machinery
that exists, and reaching a grade uses the one route everything else uses.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

from sibbcs.academic import permissions as academic_permissions
from sibbcs.academic.portal import get_student
from sibbcs.api.academic_api import ACADEMIC_ROLES


def _require_teaching():
	if not set(frappe.get_roles()).intersection(ACADEMIC_ROLES):
		frappe.throw(
			_("You do not have access to academic records."), frappe.PermissionError
		)


def _my_registration(course_registration):
	student = get_student()
	if not student:
		frappe.throw(_("No student record for your account."), frappe.PermissionError)

	row = frappe.db.get_value(
		"Course Registration",
		course_registration,
		["name", "student", "course_offering"],
		as_dict=True,
	)
	if not row or row.student != student:
		frappe.throw(_("Registration not found."), frappe.PermissionError)
	return row


# ---------------------------------------------------------------------------
# groups
# ---------------------------------------------------------------------------


@frappe.whitelist()
def group_sets(course_offering):
	_require_teaching()
	academic_permissions.assert_may_teach(course_offering)

	sets = frappe.get_all(
		"Course Group Set",
		filters={"course_offering": course_offering},
		fields=["name", "title", "self_signup", "group_limit"],
		order_by="title asc",
	)

	for group_set in sets:
		group_set["groups"] = _groups_of_set(group_set.name)

	return {
		"sets": sets,
		"roster": frappe.get_all(
			"Course Registration",
			filters={"course_offering": course_offering},
			fields=["name", "student_name"],
			order_by="student_name asc",
		),
	}


def _groups_of_set(group_set):
	groups = frappe.get_all(
		"Course Group",
		filters={"group_set": group_set},
		fields=["name", "title", "position"],
		order_by="position asc, title asc",
	)
	if not groups:
		return []

	members = {}
	for row in frappe.get_all(
		"Course Group Member",
		filters={"parent": ("in", [g.name for g in groups]), "parenttype": "Course Group"},
		fields=["parent", "course_registration", "student_name"],
	):
		members.setdefault(row.parent, []).append(
			{"course_registration": row.course_registration, "student_name": row.student_name}
		)

	for group in groups:
		group["members"] = members.get(group.name, [])
	return groups


@frappe.whitelist(methods=["POST"])
def save_group_set(course_offering, title, self_signup=0, group_limit=0, name=None):
	_require_teaching()
	academic_permissions.assert_may_teach(course_offering)

	doc = (
		frappe.get_doc("Course Group Set", name)
		if name
		else frappe.new_doc("Course Group Set")
	)
	doc.course_offering = course_offering
	doc.title = title
	doc.self_signup = cint(self_signup)
	doc.group_limit = cint(group_limit)
	doc.save()
	frappe.db.commit()
	return {"group_set": doc.name}


@frappe.whitelist(methods=["POST"])
def save_group(group_set, title, members=None, name=None):
	_require_teaching()

	offering = frappe.db.get_value("Course Group Set", group_set, "course_offering")
	if not offering:
		frappe.throw(_("Group set not found."))
	academic_permissions.assert_may_teach(offering)

	if isinstance(members, str):
		members = frappe.parse_json(members)

	doc = frappe.get_doc("Course Group", name) if name else frappe.new_doc("Course Group")
	doc.group_set = group_set
	doc.title = title

	if members is not None:
		doc.set("members", [])
		for registration in members or []:
			doc.append("members", {"course_registration": registration})

	doc.save()
	frappe.db.commit()
	return {"group": doc.name}


@frappe.whitelist(methods=["POST"])
def delete_group(group):
	_require_teaching()
	offering = frappe.db.get_value("Course Group", group, "course_offering")
	if not offering:
		frappe.throw(_("Group not found."))
	academic_permissions.assert_may_teach(offering)

	frappe.delete_doc("Course Group", group)
	frappe.db.commit()
	return {"deleted": group}


@frappe.whitelist()
def my_groups(course_registration):
	"""The groups this student is in, and who else is in them."""
	registration = _my_registration(course_registration)

	names = frappe.get_all(
		"Course Group Member",
		filters={"course_registration": registration.name, "parenttype": "Course Group"},
		pluck="parent",
	)
	if not names:
		return {"groups": []}

	groups = frappe.get_all(
		"Course Group",
		filters={"name": ("in", names)},
		fields=["name", "title", "group_set"],
	)
	for group in groups:
		group["set_title"] = frappe.db.get_value("Course Group Set", group.group_set, "title")
		group["members"] = frappe.get_all(
			"Course Group Member",
			filters={"parent": group.name, "parenttype": "Course Group"},
			fields=["student_name"],
		)
	return {"groups": groups}


# ---------------------------------------------------------------------------
# differentiated dates
# ---------------------------------------------------------------------------


@frappe.whitelist()
def overrides_for(assignment):
	_require_teaching()
	offering = frappe.db.get_value("Course Assignment", assignment, "course_offering")
	if not offering:
		frappe.throw(_("Assignment not found."))
	academic_permissions.assert_may_teach(offering)

	return {
		"rows": frappe.get_all(
			"Assignment Override",
			filters={"assignment": assignment},
			fields=[
				"name", "course_registration", "course_group", "available_from",
				"due_date", "available_until", "reason",
			],
		)
	}


@frappe.whitelist(methods=["POST"])
def save_override(assignment, values, name=None):
	_require_teaching()
	offering = frappe.db.get_value("Course Assignment", assignment, "course_offering")
	if not offering:
		frappe.throw(_("Assignment not found."))
	academic_permissions.assert_may_teach(offering)

	if isinstance(values, str):
		values = frappe.parse_json(values)
	if not isinstance(values, dict):
		frappe.throw(_("An override must be a set of fields."))

	doc = (
		frappe.get_doc("Assignment Override", name)
		if name
		else frappe.new_doc("Assignment Override")
	)
	doc.assignment = assignment
	for field in (
		"course_registration", "course_group", "available_from", "due_date",
		"available_until", "reason",
	):
		if field in values:
			doc.set(field, values[field] or None)

	doc.save()
	frappe.db.commit()
	return {"override": doc.name}


@frappe.whitelist(methods=["POST"])
def delete_override(name):
	_require_teaching()
	offering = frappe.db.get_value("Assignment Override", name, "course_offering")
	if not offering:
		frappe.throw(_("Override not found."))
	academic_permissions.assert_may_teach(offering)

	frappe.delete_doc("Assignment Override", name)
	frappe.db.commit()
	return {"deleted": name}


# ---------------------------------------------------------------------------
# graded discussions
# ---------------------------------------------------------------------------


@frappe.whitelist()
def discussions(course_offering):
	_require_teaching()
	academic_permissions.assert_may_teach(course_offering)

	return {
		"rows": frappe.get_all(
			"Course Discussion",
			filters={"course_offering": course_offering},
			fields=[
				"name", "title", "assignment", "published", "min_posts",
				"min_replies_to_peers", "discussion_topic", "prompt",
			],
			order_by="creation asc",
		)
	}


@frappe.whitelist(methods=["POST"])
def save_discussion(course_offering, values, name=None):
	"""Create or change a discussion, opening its room when it is published.

	The room is a Discussion Topic against the offering -- the same rooms
	`comms.discussion_topics` already lists -- so a graded discussion is an
	ordinary thread that happens to be attached to an assignment.
	"""
	_require_teaching()
	academic_permissions.assert_may_teach(course_offering)

	if isinstance(values, str):
		values = frappe.parse_json(values)
	if not isinstance(values, dict):
		frappe.throw(_("A discussion must be a set of fields."))

	doc = (
		frappe.get_doc("Course Discussion", name)
		if name
		else frappe.new_doc("Course Discussion")
	)
	doc.course_offering = course_offering
	for field in (
		"title", "prompt", "assignment", "published", "min_posts",
		"min_replies_to_peers",
	):
		if field in values:
			doc.set(field, values[field])

	doc.save()

	if cint(doc.published) and not doc.discussion_topic:
		topic = frappe.get_doc(
			{
				"doctype": "Discussion Topic",
				"title": doc.title,
				"reference_doctype": "Course Offering",
				"reference_docname": course_offering,
			}
		).insert(ignore_permissions=True)
		doc.db_set("discussion_topic", topic.name, update_modified=False)

	frappe.db.commit()
	return {"discussion": doc.name, "topic": doc.discussion_topic}


@frappe.whitelist()
def participation(discussion):
	"""Who has taken part, and whether they have done enough.

	Two queries whatever the size of the class: the replies, and the roster.
	"""
	_require_teaching()
	row = frappe.db.get_value(
		"Course Discussion",
		discussion,
		["name", "course_offering", "discussion_topic", "min_posts",
		 "min_replies_to_peers", "assignment"],
		as_dict=True,
	)
	if not row:
		frappe.throw(_("Discussion not found."))
	academic_permissions.assert_may_teach(row.course_offering)

	registrations = frappe.get_all(
		"Course Registration",
		filters={"course_offering": row.course_offering},
		fields=["name", "student", "student_name"],
		order_by="student_name asc",
	)

	counts = _post_counts(row.discussion_topic)

	rows = []
	for registration in registrations:
		user = frappe.db.get_value("Student", registration.student, "user")
		posts = counts.get(user, 0)
		rows.append(
			{
				"course_registration": registration.name,
				"student_name": registration.student_name,
				"posts": posts,
				"enough": posts >= cint(row.min_posts),
			}
		)

	return {"discussion": row, "rows": rows}


def _post_counts(topic):
	if not topic:
		return {}
	counts = {}
	for reply in frappe.get_all(
		"Discussion Reply", filters={"topic": topic}, fields=["owner"]
	):
		counts[reply.owner] = counts.get(reply.owner, 0) + 1
	return counts


@frappe.whitelist()
def my_discussions(course_registration):
	"""The published discussions on my course, and how I am doing in them."""
	registration = _my_registration(course_registration)

	rows = frappe.get_all(
		"Course Discussion",
		filters={"course_offering": registration.course_offering, "published": 1},
		fields=[
			"name", "title", "prompt", "assignment", "discussion_topic",
			"min_posts", "min_replies_to_peers",
		],
		order_by="creation asc",
	)

	user = frappe.session.user
	for row in rows:
		counts = _post_counts(row.discussion_topic)
		row["my_posts"] = counts.get(user, 0)
		row["enough"] = row["my_posts"] >= cint(row["min_posts"])

	return {"rows": rows}


@frappe.whitelist(methods=["POST"])
def record_participation(course_registration, discussion):
	"""Turn taking part into a submission the marker can see.

	A graded discussion is still marked by a person -- what this does is put
	the student in the marking queue once they have done what was asked, so
	participation is not something a teacher has to go looking for. It writes
	no score.
	"""
	registration = _my_registration(course_registration)

	row = frappe.db.get_value(
		"Course Discussion",
		discussion,
		["name", "course_offering", "discussion_topic", "min_posts", "assignment"],
		as_dict=True,
	)
	if not row or row.course_offering != registration.course_offering:
		frappe.throw(_("Discussion not found."), frappe.PermissionError)
	if not row.assignment:
		# An ungraded discussion has nothing to submit to.
		return {"submission": None}

	posts = _post_counts(row.discussion_topic).get(frappe.session.user, 0)
	if posts < cint(row.min_posts):
		return {"submission": None, "posts": posts, "enough": False}

	existing = frappe.get_all(
		"Assignment Submission",
		filters={
			"assignment": row.assignment,
			"course_registration": registration.name,
		},
		pluck="name",
		limit=1,
	)
	if existing:
		submission = frappe.get_doc("Assignment Submission", existing[0])
	else:
		submission = frappe.new_doc("Assignment Submission")
		submission.assignment = row.assignment
		submission.course_registration = registration.name
		submission.attempt = 1

	submission.status = "Submitted"
	submission.submitted_on = submission.submitted_on or now_datetime()
	submission.body = _("Took part in {0}: {1} post(s).").format(row.title, posts)
	submission.save(ignore_permissions=True)
	frappe.db.commit()

	return {"submission": submission.name, "posts": posts, "enough": True}


# ---------------------------------------------------------------------------
# peer review
# ---------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def assign_reviews(assignment, per_submission=1):
	"""Give every submission somebody else's to read.

	A rotation rather than random pairing: with the roster in a fixed order,
	student *n* reviews *n+1*, *n+2* and so on. Nobody reviews their own, the
	load is even, and re-running it produces the same pairs rather than a
	second set.
	"""
	_require_teaching()
	offering = frappe.db.get_value("Course Assignment", assignment, "course_offering")
	if not offering:
		frappe.throw(_("Assignment not found."))
	academic_permissions.assert_may_teach(offering)

	submissions = frappe.get_all(
		"Assignment Submission",
		filters={"assignment": assignment, "status": ("!=", "Draft")},
		fields=["name", "course_registration"],
		order_by="course_registration asc",
	)
	if len(submissions) < 2:
		frappe.throw(_("There has to be more than one submission to review."))

	per_submission = min(cint(per_submission) or 1, len(submissions) - 1)

	created = 0
	for index, submission in enumerate(submissions):
		for step in range(1, per_submission + 1):
			reviewer = submissions[(index + step) % len(submissions)]
			if reviewer.course_registration == submission.course_registration:
				continue
			if frappe.db.exists(
				"Peer Review",
				{
					"submission": submission.name,
					"reviewer": reviewer.course_registration,
				},
			):
				continue
			frappe.get_doc(
				{
					"doctype": "Peer Review",
					"assignment": assignment,
					"submission": submission.name,
					"reviewer": reviewer.course_registration,
					"status": "Assigned",
				}
			).insert(ignore_permissions=True)
			created += 1

	frappe.db.commit()
	return {"assigned": created}


@frappe.whitelist()
def my_reviews(course_registration):
	"""What this student has been asked to read.

	The work is included; the author is not. A review is about the work.
	"""
	registration = _my_registration(course_registration)

	reviews = frappe.get_all(
		"Peer Review",
		filters={"reviewer": registration.name},
		fields=["name", "assignment", "submission", "status", "comments"],
	)

	for review in reviews:
		review["assignment_title"] = frappe.db.get_value(
			"Course Assignment", review.assignment, "title"
		)
		work = frappe.db.get_value(
			"Assignment Submission", review.submission, ["body", "url"], as_dict=True
		)
		review["body"] = work.body if work else None
		review["url"] = work.url if work else None

	return {"rows": reviews}


@frappe.whitelist(methods=["POST"])
def submit_review(course_registration, review, comments):
	_require_teaching_or_own_review(course_registration, review)

	doc = frappe.get_doc("Peer Review", review)
	doc.comments = comments
	doc.status = "Submitted"
	doc.submitted_on = now_datetime()
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	return {"review": doc.name, "status": doc.status}


def _require_teaching_or_own_review(course_registration, review):
	registration = _my_registration(course_registration)
	reviewer = frappe.db.get_value("Peer Review", review, "reviewer")
	if reviewer != registration.name:
		frappe.throw(_("That review is not yours."), frappe.PermissionError)
