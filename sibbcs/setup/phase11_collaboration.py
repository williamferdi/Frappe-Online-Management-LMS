"""Graded discussions, groups, differentiated dates and peer review.

    bench --site online.sibbc.org execute \\
        sibbcs.setup.phase11_collaboration.build

Idempotent.

**Discussions are not rebuilt.** `api/comms.py` already runs a room per Course
Offering on Frappe's own Discussion Topic and Discussion Reply, scoped by
`_may_use_room`. A graded discussion is one of those topics with a Course
Assignment attached, so participation lands in the marking queue beside every
other kind of work and reaches a grade by the same route. Ungraded threads are
untouched.

**Course-scoped announcements already work.** `Announcement.audience` has had
"Course Offering" all along, and `comms._audience_context` / `_addressed_to_me`
both handle it. Nothing to build; there is a test pinning it instead.

**An override changes dates, never marks.** Differentiating an assignment for a
student or a group moves when it opens, is due and closes -- and that is all.
Anything that touched the score would be a second grading path.
"""

import frappe

from sibbcs.setup.schema import (
	check,
	column,
	ensure_doctype,
	f,
	fetched,
	full,
	level,
	link,
	read,
	section,
	select,
	table,
)

MODULE = "Academic"

SM = "System Manager"
REGISTRAR = "Registrar"
COORDINATOR = "Academic Coordinator"
FACULTY = "Faculty"
FACILITATOR = "Facilitator"
STUDENT = "Student"

REVIEW_STATES = ["Assigned", "In progress", "Submitted"]


def _course_shape_perms():
	"""Read for students: a group they are in and a discussion prompt are the
	shape of the course, not somebody's mark."""
	return [
		full(SM), full(COORDINATOR), full(FACULTY),
		read(REGISTRAR), read(FACILITATOR), read(STUDENT),
	]


def _staff_only_perms(with_grades=False):
	rows = [
		full(SM), full(COORDINATOR), full(FACULTY),
		read(REGISTRAR), read(FACILITATOR),
	]
	if with_grades:
		rows += [
			level(SM, 1), level(COORDINATOR, 1), level(FACULTY, 1),
			level(REGISTRAR, 1, write=0), level(FACILITATOR, 1, write=0),
		]
	return rows


# ---------------------------------------------------------------------------
# groups
# ---------------------------------------------------------------------------


def _course_group_member():
	return ensure_doctype(
		"Course Group Member",
		MODULE,
		istable=1,
		fields=[
			link("course_registration", "Registration", "Course Registration",
				 reqd=1, in_list_view=1),
			fetched("student_name", "Student", "course_registration.student_name",
					in_list_view=1),
		],
	)


def _course_group_set():
	return ensure_doctype(
		"Course Group Set",
		MODULE,
		autoname="naming_series:",
		naming_rule='By "Naming Series" field',
		title_field="title",
		fields=[
			select("naming_series", "Series", ["CGS-.#####"], default="CGS-.#####",
				   hidden=1, print_hide=1),
			link("course_offering", "Course Offering", "Course Offering", reqd=1),
			f("title", "Title", "Data", reqd=1),
			column("cb_head"),
			check("self_signup", "Students may join a group themselves", 0),
			f("group_limit", "Members per group", "Int", default="0",
			  description="0 means no limit."),
		],
		permissions=_course_shape_perms(),
	)


def _course_group():
	return ensure_doctype(
		"Course Group",
		MODULE,
		autoname="naming_series:",
		naming_rule='By "Naming Series" field',
		title_field="title",
		fields=[
			select("naming_series", "Series", ["CGR-.#####"], default="CGR-.#####",
				   hidden=1, print_hide=1),
			link("group_set", "Group Set", "Course Group Set", reqd=1),
			fetched("course_offering", "Course Offering", "group_set.course_offering"),
			f("title", "Title", "Data", reqd=1),
			column("cb_head"),
			f("position", "Position", "Int", default="0"),
			section("sb_members"),
			table("members", "Members", "Course Group Member"),
		],
		permissions=_course_shape_perms(),
	)


# ---------------------------------------------------------------------------
# differentiated dates
# ---------------------------------------------------------------------------


def _assignment_override():
	return ensure_doctype(
		"Assignment Override",
		MODULE,
		autoname="naming_series:",
		naming_rule='By "Naming Series" field',
		fields=[
			section("sb_what"),
			select("naming_series", "Series", ["AOV-.#####"], default="AOV-.#####",
				   hidden=1, print_hide=1),
			link("assignment", "Assignment", "Course Assignment", reqd=1),
			fetched("course_offering", "Course Offering", "assignment.course_offering"),
			column("cb_what"),
			# One or the other, never both -- see the controller.
			link("course_registration", "Student", "Course Registration"),
			link("course_group", "Group", "Course Group"),

			section("sb_dates", "Instead of the assignment's own dates"),
			f("available_from", "Available From", "Datetime"),
			f("due_date", "Due", "Datetime"),
			column("cb_dates"),
			f("available_until", "Closes", "Datetime"),
			f("reason", "Reason", "Small Text",
			  description="Why this student or group has different dates."),
		],
		# Students never read these: a payload already carries the dates that
		# apply to them, and a list of everyone's extensions is nobody's
		# business.
		permissions=_staff_only_perms(),
	)


# ---------------------------------------------------------------------------
# graded discussions
# ---------------------------------------------------------------------------


def _course_discussion():
	return ensure_doctype(
		"Course Discussion",
		MODULE,
		autoname="naming_series:",
		naming_rule='By "Naming Series" field',
		title_field="title",
		fields=[
			section("sb_what"),
			select("naming_series", "Series", ["CDS-.#####"], default="CDS-.#####",
				   hidden=1, print_hide=1),
			link("course_offering", "Course Offering", "Course Offering", reqd=1),
			f("title", "Title", "Data", reqd=1),
			column("cb_what"),
			# A graded discussion is an assignment whose submission is
			# participation, so it reaches a grade the way everything else does.
			link("assignment", "Assignment", "Course Assignment",
				 description="Set to make this count towards the grade."),
			check("published", "Published", 0),

			section("sb_prompt"),
			f("prompt", "Prompt", "Text Editor"),

			section("sb_rules", "What counts as taking part"),
			f("min_posts", "Posts required", "Int", default="1"),
			column("cb_rules"),
			f("min_replies_to_peers", "Replies to others required", "Int", default="0"),

			section("sb_room"),
			# The room is Frappe's own Discussion Topic, which api/comms.py
			# already serves per offering. Created when the discussion is
			# published, and stored so both sides agree which thread this is.
			link("discussion_topic", "Topic", "Discussion Topic", read_only=1),
		],
		permissions=_course_shape_perms(),
	)


# ---------------------------------------------------------------------------
# peer review
# ---------------------------------------------------------------------------


def _peer_review():
	return ensure_doctype(
		"Peer Review",
		MODULE,
		autoname="naming_series:",
		naming_rule='By "Naming Series" field',
		fields=[
			section("sb_what"),
			select("naming_series", "Series", ["PRV-.#####"], default="PRV-.#####",
				   hidden=1, print_hide=1),
			link("assignment", "Assignment", "Course Assignment", reqd=1),
			fetched("course_offering", "Course Offering", "assignment.course_offering"),
			link("submission", "Submission", "Assignment Submission", reqd=1),
			column("cb_what"),
			# The reviewer is a registration, not a user: a reviewer has to be
			# on the course, and the same person may be on two.
			link("reviewer", "Reviewer", "Course Registration", reqd=1),
			fetched("reviewer_name", "Reviewer", "reviewer.student_name"),
			select("status", "Status", REVIEW_STATES, default="Assigned"),

			section("sb_review"),
			f("comments", "Comments", "Text Editor"),
			f("submitted_on", "Submitted", "Datetime", read_only=1),
			# permlevel 1: a peer's suggested mark is a mark, and the student
			# being reviewed must not read it out of the record.
			f("suggested_score", "Suggested Score", "Float", permlevel=1),
		],
		permissions=_staff_only_perms(with_grades=True),
	)


# ---------------------------------------------------------------------------


def build():
	_course_group_member()
	_course_group_set()
	_course_group()
	_assignment_override()
	_course_discussion()
	_peer_review()

	frappe.db.commit()
	frappe.clear_cache()

	for name in (
		"Course Group Member", "Course Group Set", "Course Group",
		"Assignment Override", "Course Discussion", "Peer Review",
	):
		print(f"  {name}: {'ok' if frappe.db.exists('DocType', name) else 'MISSING'}")
