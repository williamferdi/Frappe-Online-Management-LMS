# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""Row-level scoping for the teaching records.

`sibbcs.setup.permissions` says *what* a role may do with a DocType. It cannot
say *which rows*, and that missing half is a confidentiality gap:
`edit(FACULTY)` plus `level(FACULTY, 1)` on Course Registration means any
Faculty user may read and rewrite any student's marks in any course, and
`read(STUDENT)` means one student can fetch the whole cohort's grades through
`/api/resource/Course Registration`.

Closing it takes three things, because there are three ways in and each
ignores the other two:

    permission_query_conditions   lists, reports, /api/resource listings
    has_permission                one document fetched by name
    assert_may_teach              the /staff API, which reads through
                                  `frappe.get_all` and so is not subject to
                                  either of the above

The first on its own is a list that hides what a URL still hands over. The
first two on their own leave `academic_api.roster` answering for any offering
anybody asks about. Only `save_grades` was already safe, and by accident of
good manners: it calls `doc.check_permission("write")` and saves without
`ignore_permissions`, so the hook below is what that check consults.

Who sees what:

    System Manager, Registrar, Academic Coordinator   everything
    Accounts                                          every registration, but
                                                      they hold no permlevel-1
                                                      row, so the grade fields
                                                      stay dark
    Faculty, Facilitator                              the offerings they teach
                                                      or facilitate, the
                                                      courses those belong to,
                                                      and the students on them
    Student                                           their own records

A Faculty user with no Instructor record teaches nothing and so sees nothing.
That is deliberate. The tempting alternative -- fall back to showing
everything when no Instructor row names the user -- makes the absence of a
record into a master key, which is the opposite of a permission.

**Course Offering is deliberately not scoped.** It is the catalogue a student
browses before registering (`academic.portal.available_offerings`), so a row
filter there would break registration rather than protect anything: a title, a
term and a format are not confidential. What a teacher may not see is the
*roster* -- who is enrolled and what they scored -- and that is Course
Registration, which is scoped. "My courses" is a question `offerings_for`
answers for the UI, not one the permission layer answers by hiding the
prospectus.
"""

import frappe
from frappe import _

# Roles whose whole job is the register; scoping them would only mean they
# could not do it.
UNRESTRICTED = ("System Manager", "Registrar", "Academic Coordinator", "Accounts")

TEACHING_ROLES = ("Faculty", "Facilitator")

# A condition no row satisfies. Returning this rather than "" is the whole
# difference between "you see nothing" and "you see everything".
NOTHING = "1 = 0"

# What changes a record, as opposed to looking at it or picking it in a link.
CHANGES = {"write", "create", "delete", "submit", "cancel", "amend"}


def _cache():
	"""Per-request memo for the scoping lookups.

	`frappe.local` is request-scoped, so this is emptied for us between
	requests and between background jobs.
	"""
	store = getattr(frappe.local, "sibbcs_scope_cache", None)
	if store is None:
		store = {}
		frappe.local.sibbcs_scope_cache = store
	return store


# The only fields the scoping answer is derived from. A Course Offering whose
# enrolled_count moved says nothing about who teaches it.
SCOPE_FIELDS = {
	"Instructor": ("user",),
	"Course Offering": ("instructor", "facilitator"),
}


def clear_scope_cache(doc=None, method=None):
	"""Forget the memo, but only when the answer could have changed.

	Wired to Instructor and Course Offering in hooks.py. Hooked to every update
	it was useless: `Course Registration.refresh_offering_count` writes to the
	offering on every registration save, so the memo was dropped before it
	could ever answer a second question.
	"""
	if getattr(frappe.local, "sibbcs_scope_cache", None) is None:
		return

	watched = SCOPE_FIELDS.get(getattr(doc, "doctype", None))
	if doc is not None and watched and not doc.is_new():
		if not any(doc.has_value_changed(field) for field in watched):
			return

	frappe.local.sibbcs_scope_cache = {}


def _memo(key, build):
	store = _cache()
	if key not in store:
		store[key] = build()
	return store[key]


def _roles(user):
	return _memo(("roles", user), lambda: set(frappe.get_roles(user)))


def is_unrestricted(user=None):
	user = user or frappe.session.user
	return user == "Administrator" or bool(_roles(user) & set(UNRESTRICTED))


def _within(doctype, field, values):
	"""`tabDoctype`.`field` in (...), escaped, or a condition nothing meets."""
	if not values:
		return NOTHING
	listed = ", ".join(frappe.db.escape(value) for value in values)
	return f"`tab{doctype}`.`{field}` in ({listed})"


def _teaches(user):
	return bool(_roles(user) & set(TEACHING_ROLES))


def _only_a_student(user):
	"""True when Student is the only academic role this user holds.

	A registrar who also happens to be enrolled should not lose the register,
	so the narrow rule applies only when nothing wider does.
	"""
	roles = _roles(user)
	return "Student" in roles and not (roles & set(TEACHING_ROLES))


# --- who is who -----------------------------------------------------------


def instructors_for(user=None):
	"""Every Instructor record this user answers to.

	A list rather than one value: nothing stops the college holding two records
	for one person, and picking one arbitrarily would hide half their teaching.
	"""
	user = user or frappe.session.user
	if not user or user == "Guest":
		return []
	return _memo(
		("instructors", user),
		lambda: frappe.get_all("Instructor", filters={"user": user}, pluck="name"),
	)


def offerings_for(user=None):
	"""The offerings a user teaches or facilitates.

	`frappe.get_all` and not `get_list`, deliberately: `get_list` applies
	permissions, and this function is called *from* a permission check.
	"""
	user = user or frappe.session.user
	instructors = instructors_for(user)
	if not instructors:
		return []
	return _memo(
		("offerings", user),
		lambda: frappe.get_all(
			"Course Offering",
			or_filters=[
				["instructor", "in", instructors],
				["facilitator", "in", instructors],
			],
			pluck="name",
		),
	)


def courses_for(user=None):
	"""The courses a user teaches at least one offering of.

	Pages, files, rubrics, question banks and quizzes belong to the Course, not
	to one run of it, so every term reuses them. Teaching this term's offering
	is what makes them a teacher's to work on.
	"""
	user = user or frappe.session.user
	offerings = offerings_for(user)
	if not offerings:
		return []
	return _memo(
		("courses", user),
		lambda: sorted(
			{
				course
				for course in frappe.get_all(
					"Course Offering", filters={"name": ("in", offerings)}, pluck="course"
				)
				if course
			}
		),
	)


def students_for(user=None):
	"""The students registered on any offering a user teaches or facilitates."""
	user = user or frappe.session.user
	offerings = offerings_for(user)
	if not offerings:
		return []
	return _memo(
		("students", user),
		lambda: sorted(
			{
				student
				for student in frappe.get_all(
					"Course Registration",
					filters={"course_offering": ("in", offerings)},
					pluck="student",
				)
				if student
			}
		),
	)


def student_for(user=None):
	"""The Student record this user is, if they are one."""
	user = user or frappe.session.user
	if not user or user == "Guest":
		return None
	return _memo(
		("student", user),
		lambda: frappe.db.get_value("Student", {"user": user}, "name"),
	)


# --- the /staff API -------------------------------------------------------


def is_teaching_staff(user=None):
	"""Whether this user is staff at all, rather than a student.

	Not the same question as `offering_scope(user) is None`, which is also
	true of every student -- the scoping does not apply to them, which is not
	the same as it applying and finding no limit. Anything deciding "staff or
	student" must ask this; anything narrowing a teacher to their own courses
	asks `assert_may_teach` after it.
	"""
	user = user or frappe.session.user
	return bool(_roles(user) & (set(UNRESTRICTED) | set(TEACHING_ROLES)))


def offering_scope(user=None):
	"""The offerings this user may look into, or None meaning all of them.

	None and [] are different answers and the caller must keep them apart:
	None is the registrar, [] is a teacher who has been given no course.
	"""
	user = user or frappe.session.user
	if is_unrestricted(user) or not _teaches(user):
		return None
	return offerings_for(user)


def assert_may_teach(course_offering, user=None):
	"""Refuse an offering that is not this user's to look into.

	The /staff endpoints read with `frappe.get_all`, which bypasses
	permissions by design, so neither the query condition nor `has_permission`
	protects them. This is their guard and it has to be called by hand.
	"""
	scope = offering_scope(user)
	if scope is None or course_offering in scope:
		return
	frappe.throw(
		_("You are not teaching {0}.").format(course_offering), frappe.PermissionError
	)


def course_scope(user=None):
	"""The courses this user may work on, or None meaning all of them.

	The same None/[] distinction as `offering_scope`, and the same trap: None
	is also the answer for a student. This narrows staff; whether somebody is
	staff at all is the caller's to ask first.
	"""
	user = user or frappe.session.user
	if is_unrestricted(user) or not _teaches(user):
		return None
	return courses_for(user)


def assert_may_teach_course(course, user=None):
	"""Refuse a course this user teaches no offering of."""
	scope = course_scope(user)
	if scope is None or course in scope:
		return
	frappe.throw(_("You are not teaching {0}.").format(course), frappe.PermissionError)


def assert_may_see(course, user=None):
	"""Read a course's own rubric or bank as its teacher, or a shared one --
	no course -- as anyone who teaches."""
	if course:
		assert_may_teach_course(course, user)


def assert_may_change(course, what, user=None):
	"""Change a course's own rubric or bank as its teacher; a shared one only
	as the academic office, because one teacher's edit would change how every
	course using it is examined or marked."""
	if course:
		assert_may_teach_course(course, user)
		return
	if course_scope(user) is not None:
		frappe.throw(
			_("Only the academic office can change a shared {0}.").format(what),
			frappe.PermissionError,
		)


def course_record_filters(course=None, user=None):
	"""`or_filters` for the rubrics or banks this user may use.

	Their own courses' and the shared ones; None -- no filter at all -- for the
	office. Naming a course narrows to it and the shared ones, and a teacher
	may only name one they teach.
	"""
	if course:
		assert_may_teach_course(course, user)
	courses = [course] if course else course_scope(user)
	if courses is None:
		return None
	filters = [["course", "is", "not set"]]
	if courses:
		filters.append(["course", "in", courses])
	return filters


def student_scope(user=None):
	"""The students this user may look up, or None meaning all of them.

	Since 2026-09-11 a teacher's roll is their own students. [] is a teacher
	with nobody on their courses, and must read as "nobody", not as no filter.
	"""
	user = user or frappe.session.user
	if is_unrestricted(user) or not _teaches(user):
		return None
	return students_for(user)


# --- Course Registration --------------------------------------------------
# The marks live here, so this is the record that matters.


def course_registration_query(user=None):
	user = user or frappe.session.user
	if is_unrestricted(user):
		return ""

	if _teaches(user):
		return _within("Course Registration", "course_offering", offerings_for(user))

	if _only_a_student(user):
		student = student_for(user)
		return _within("Course Registration", "student", [student] if student else [])

	return ""


def course_registration_permission(doc, ptype="read", user=None):
	"""Guard a single registration fetched by name.

	Without this the list is filtered and the URL is not -- and this is what
	`save_grades`'s `check_permission("write")` ends up asking.
	"""
	user = user or frappe.session.user
	if not doc or is_unrestricted(user):
		return True

	if _teaches(user):
		return doc.get("course_offering") in offerings_for(user)

	if _only_a_student(user):
		return bool(doc.get("student")) and doc.get("student") == student_for(user)

	return True


# --- Course Assignment and Course Grade Scheme ----------------------------
# Both hang off an offering, so both scope the same way the roster does. A
# teacher who may not see who is enrolled has no business editing what they
# are set.


def _offering_scoped_query(doctype, user):
	if is_unrestricted(user):
		return ""
	if _teaches(user):
		return _within(doctype, "course_offering", offerings_for(user))
	return ""


def _offering_scoped_permission(doc, user):
	if not doc or is_unrestricted(user):
		return True
	if _teaches(user):
		return doc.get("course_offering") in offerings_for(user)
	return True


def course_assignment_query(user=None):
	return _offering_scoped_query("Course Assignment", user or frappe.session.user)


def course_assignment_permission(doc, ptype="read", user=None):
	return _offering_scoped_permission(doc, user or frappe.session.user)


def course_grade_scheme_query(user=None):
	return _offering_scoped_query("Course Grade Scheme", user or frappe.session.user)


def course_grade_scheme_permission(doc, ptype="read", user=None):
	return _offering_scoped_permission(doc, user or frappe.session.user)



def assignment_submission_query(user=None):
	"""Scoped on the offering the submission carries.

	`course_offering` is fetched onto the submission rather than looked up
	through the assignment, so this filters without a join on every list.
	"""
	return _offering_scoped_query("Assignment Submission", user or frappe.session.user)


def assignment_submission_permission(doc, ptype="read", user=None):
	return _offering_scoped_permission(doc, user or frappe.session.user)


def course_module_query(user=None):
	return _offering_scoped_query("Course Module", user or frappe.session.user)


def course_module_permission(doc, ptype="read", user=None):
	return _offering_scoped_permission(doc, user or frappe.session.user)


def course_module_item_query(user=None):
	return _offering_scoped_query("Course Module Item", user or frappe.session.user)


def course_module_item_permission(doc, ptype="read", user=None):
	return _offering_scoped_permission(doc, user or frappe.session.user)


def course_group_query(user=None):
	return _offering_scoped_query("Course Group", user or frappe.session.user)


def course_group_permission(doc, ptype="read", user=None):
	return _offering_scoped_permission(doc, user or frappe.session.user)


def course_group_set_query(user=None):
	return _offering_scoped_query("Course Group Set", user or frappe.session.user)


def course_group_set_permission(doc, ptype="read", user=None):
	return _offering_scoped_permission(doc, user or frappe.session.user)


def course_discussion_query(user=None):
	return _offering_scoped_query("Course Discussion", user or frappe.session.user)


def course_discussion_permission(doc, ptype="read", user=None):
	return _offering_scoped_permission(doc, user or frappe.session.user)


def assignment_override_query(user=None):
	return _offering_scoped_query("Assignment Override", user or frappe.session.user)


def assignment_override_permission(doc, ptype="read", user=None):
	return _offering_scoped_permission(doc, user or frappe.session.user)


def peer_review_query(user=None):
	return _offering_scoped_query("Peer Review", user or frappe.session.user)


def peer_review_permission(doc, ptype="read", user=None):
	return _offering_scoped_permission(doc, user or frappe.session.user)


def quiz_attempt_query(user=None):
	"""A teacher sees attempts on their own courses; nobody else sees any."""
	return _offering_scoped_query("Quiz Attempt", user or frappe.session.user)


def quiz_attempt_permission(doc, ptype="read", user=None):
	return _offering_scoped_permission(doc, user or frappe.session.user)


def module_item_progress_query(user=None):
	"""A teacher sees progress on their own courses; a student sees their own.

	Progress is the one Phase 3 record that is about a person rather than
	about the course, so it is scoped both ways.
	"""
	user = user or frappe.session.user
	if is_unrestricted(user):
		return ""

	if _teaches(user):
		return _within("Module Item Progress", "course_offering", offerings_for(user))

	if _only_a_student(user):
		student = student_for(user)
		registrations = (
			frappe.get_all(
				"Course Registration", filters={"student": student}, pluck="name"
			)
			if student
			else []
		)
		return _within("Module Item Progress", "course_registration", registrations)

	return ""


def module_item_progress_permission(doc, ptype="read", user=None):
	user = user or frappe.session.user
	if not doc or is_unrestricted(user):
		return True

	if _teaches(user):
		return doc.get("course_offering") in offerings_for(user)

	if _only_a_student(user):
		student = student_for(user)
		return bool(student) and frappe.db.get_value(
			"Course Registration", doc.get("course_registration"), "student"
		) == student

	return True


# --- Student and Program Enrollment ---------------------------------------
# Both carry `read(STUDENT)`, which without a row filter is the student
# directory and the cohort's levels handed to anyone holding the role.
#
# A teacher sees the students on the courses they teach, and nobody else.
# This was once left open -- "looking a student up is ordinary teaching
# work" -- until the college decided on 2026-09-11 that a teacher's roll is
# their own students: a name, a telephone number and a photograph are
# personal details, and a teacher has no reason to hold them for a student
# they never teach.


def student_query(user=None):
	user = user or frappe.session.user
	if is_unrestricted(user):
		return ""
	if _teaches(user):
		return _within("Student", "name", students_for(user))
	if _only_a_student(user):
		student = student_for(user)
		return _within("Student", "name", [student] if student else [])
	return ""


def student_permission(doc, ptype="read", user=None):
	user = user or frappe.session.user
	if not doc or is_unrestricted(user):
		return True
	if _teaches(user):
		return doc.get("name") in students_for(user)
	if _only_a_student(user):
		return doc.get("name") == student_for(user)
	return True


def program_enrollment_query(user=None):
	user = user or frappe.session.user
	if is_unrestricted(user):
		return ""
	if _teaches(user):
		return _within("Program Enrollment", "student", students_for(user))
	if _only_a_student(user):
		student = student_for(user)
		return _within("Program Enrollment", "student", [student] if student else [])
	return ""


def program_enrollment_permission(doc, ptype="read", user=None):
	user = user or frappe.session.user
	if not doc or is_unrestricted(user):
		return True
	if _teaches(user):
		return doc.get("student") in students_for(user)
	if _only_a_student(user):
		return doc.get("student") == student_for(user)
	return True


# --- what belongs to a Course rather than to one run of it ---------------
# Pages, files, rubrics, question banks and quizzes are the Course's, so every
# term reuses them. Faculty hold full rights on all of them, and until
# 2026-09-11 nothing narrowed that to *which* course: any teacher could
# rewrite another course's quiz answers, through Desk or the API. A teacher
# now works on the courses they teach an offering of.
#
# A rubric or bank with no course is shared: every teacher may read it and use
# it, and only the office may change it -- one teacher's edit would change how
# every course using it is examined or marked.


def _may_touch_course(course, ptype, user, shared):
	if not course:
		return shared and ptype not in CHANGES
	return course in courses_for(user)


def _course_scoped_query(doctype, user, shared=False):
	if is_unrestricted(user) or not _teaches(user):
		return ""
	condition = _within(doctype, "course", courses_for(user))
	if shared:
		condition = f"({condition} or ifnull(`tab{doctype}`.`course`, '') = '')"
	return condition


def _course_scoped_permission(doc, ptype, user, shared=False):
	if not doc or is_unrestricted(user) or not _teaches(user):
		return True
	return _may_touch_course(doc.get("course"), ptype, user, shared)


def _within_parent(child, link, parent, user):
	"""Rows whose parent is on the teacher's courses, or is shared."""
	inner = _within(parent, "course", courses_for(user))
	return (
		f"`tab{child}`.`{link}` in (select `name` from `tab{parent}` "
		f"where {inner} or ifnull(`tab{parent}`.`course`, '') = '')"
	)


def _parent_scoped_permission(doc, ptype, user, link, parent):
	if not doc or is_unrestricted(user) or not _teaches(user):
		return True
	course = frappe.db.get_value(parent, doc.get(link), "course")
	return _may_touch_course(course, ptype, user, shared=True)


def course_page_query(user=None):
	return _course_scoped_query("Course Page", user or frappe.session.user)


def course_page_permission(doc, ptype="read", user=None):
	return _course_scoped_permission(doc, ptype, user or frappe.session.user)


def course_file_query(user=None):
	return _course_scoped_query("Course File", user or frappe.session.user)


def course_file_permission(doc, ptype="read", user=None):
	return _course_scoped_permission(doc, ptype, user or frappe.session.user)


def course_quiz_query(user=None):
	return _course_scoped_query("Course Quiz", user or frappe.session.user)


def course_quiz_permission(doc, ptype="read", user=None):
	return _course_scoped_permission(doc, ptype, user or frappe.session.user)


def course_rubric_query(user=None):
	return _course_scoped_query("Course Rubric", user or frappe.session.user, shared=True)


def course_rubric_permission(doc, ptype="read", user=None):
	return _course_scoped_permission(doc, ptype, user or frappe.session.user, shared=True)


def question_bank_query(user=None):
	return _course_scoped_query("Question Bank", user or frappe.session.user, shared=True)


def question_bank_permission(doc, ptype="read", user=None):
	return _course_scoped_permission(doc, ptype, user or frappe.session.user, shared=True)


def rubric_criterion_query(user=None):
	user = user or frappe.session.user
	if is_unrestricted(user) or not _teaches(user):
		return ""
	return _within_parent("Rubric Criterion", "rubric", "Course Rubric", user)


def rubric_criterion_permission(doc, ptype="read", user=None):
	return _parent_scoped_permission(
		doc, ptype, user or frappe.session.user, "rubric", "Course Rubric"
	)


def bank_question_query(user=None):
	user = user or frappe.session.user
	if is_unrestricted(user) or not _teaches(user):
		return ""
	return _within_parent("Bank Question", "bank", "Question Bank", user)


def bank_question_permission(doc, ptype="read", user=None):
	return _parent_scoped_permission(
		doc, ptype, user or frappe.session.user, "bank", "Question Bank"
	)
