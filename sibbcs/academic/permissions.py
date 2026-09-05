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
                                                      or facilitate
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


def _roles(user):
	return set(frappe.get_roles(user))


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
	return frappe.get_all("Instructor", filters={"user": user}, pluck="name")


def offerings_for(user=None):
	"""The offerings a user teaches or facilitates.

	`frappe.get_all` and not `get_list`, deliberately: `get_list` applies
	permissions, and this function is called *from* a permission check.
	"""
	user = user or frappe.session.user
	instructors = instructors_for(user)
	if not instructors:
		return []
	return frappe.get_all(
		"Course Offering",
		or_filters=[
			["instructor", "in", instructors],
			["facilitator", "in", instructors],
		],
		pluck="name",
	)


def student_for(user=None):
	"""The Student record this user is, if they are one."""
	user = user or frappe.session.user
	if not user or user == "Guest":
		return None
	return frappe.db.get_value("Student", {"user": user}, "name")


# --- the /staff API -------------------------------------------------------


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


# --- Student and Program Enrollment ---------------------------------------
# Both carry `read(STUDENT)`, which without a row filter is the student
# directory and the cohort's levels handed to anyone holding the role.
# Faculty are left unscoped here: looking a student up is ordinary teaching
# work, and neither record carries a mark.


def student_query(user=None):
	user = user or frappe.session.user
	if not _only_a_student(user) or is_unrestricted(user):
		return ""
	student = student_for(user)
	return _within("Student", "name", [student] if student else [])


def student_permission(doc, ptype="read", user=None):
	user = user or frappe.session.user
	if not doc or is_unrestricted(user) or not _only_a_student(user):
		return True
	return doc.get("name") == student_for(user)


def program_enrollment_query(user=None):
	user = user or frappe.session.user
	if not _only_a_student(user) or is_unrestricted(user):
		return ""
	student = student_for(user)
	return _within("Program Enrollment", "student", [student] if student else [])


def program_enrollment_permission(doc, ptype="read", user=None):
	user = user or frappe.session.user
	if not doc or is_unrestricted(user) or not _only_a_student(user):
		return True
	return doc.get("student") == student_for(user)
