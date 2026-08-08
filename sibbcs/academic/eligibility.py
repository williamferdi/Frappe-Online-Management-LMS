"""The eligibility rule engine -- architecture doc §3.

Pure decision functions, deliberately free of document mutation, so every rule
can be tested on its own and reused by the student portal to grey out offerings
before anyone clicks Register.

The level rules, exactly as specified and confirmed:

    L = enrollment.current_level      the student's sticky level
    C = course.level                  the course's own level

    1. C == L                     -> allow
    2. {L, C} subset of {1, 2}    -> allow  (levels 1 and 2 interchangeable)
    3. {L, C} subset of {3, 4}    -> BLOCK  (3 and 4 never collaborate)
    4. anything else              -> BLOCK unless an Academic Coordinator
                                     override is supplied

Rule 3 is a *hard* block: no override clears it. Rule 4 is overridable. A Level
2 student taking a Level 3 course falls under rule 4 -- blocked by default,
which is the confirmed behaviour.

The point of keeping the student's level separate from the course's level is
that "a Level 1 student sits in a Level 2 course but stays Level 1" needs no
special case anywhere.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

OVERRIDE_ROLES = {"Academic Coordinator", "System Manager", "Administrator"}

# Registration states that mean the seat is taken / the course is in progress.
OCCUPYING_STATUSES = ("Registered", "Active", "Completed")


class Decision:
	"""The outcome of an eligibility check.

	`allowed` says whether registration may proceed. `needs_override` marks the
	case where an Academic Coordinator *could* clear it, so the UI can offer
	that instead of a dead end. `hard` marks rules no override can clear.
	"""

	def __init__(self, allowed, reason=None, needs_override=False, hard=False, code=None):
		self.allowed = allowed
		self.reason = reason
		self.needs_override = needs_override
		self.hard = hard
		self.code = code

	def __bool__(self):
		return self.allowed

	def __repr__(self):
		state = "allow" if self.allowed else ("hard-block" if self.hard else "block")
		return f"<Decision {state} {self.code or ''}: {self.reason or ''}>"

	@classmethod
	def allow(cls, code="ok"):
		return cls(True, code=code)

	@classmethod
	def block(cls, reason, code, hard=False, needs_override=False):
		return cls(False, reason=reason, code=code, hard=hard, needs_override=needs_override)


# ---------------------------------------------------------------------------
# rule 1-4: levels
# ---------------------------------------------------------------------------


def check_level(student_level, course_level):
	"""The four level rules. Pure -- takes two ints, returns a Decision."""
	student_level = cint(student_level)
	course_level = cint(course_level)

	if not student_level or not course_level:
		return Decision.block(
			_("Student level or course level is not set."),
			code="level_missing",
		)

	# Rule 1 -- same level always allowed
	if student_level == course_level:
		return Decision.allow("same_level")

	pair = {student_level, course_level}

	# Rule 2 -- levels 1 and 2 are mutually interchangeable
	if pair <= {1, 2}:
		return Decision.allow("level_1_2_interchangeable")

	# Rule 3 -- levels 3 and 4 never collaborate, and no override clears it
	if pair <= {3, 4}:
		return Decision.block(
			_(
				"Level {0} students may not take Level {1} courses. "
				"Levels 3 and 4 do not mix, and this cannot be overridden."
			).format(student_level, course_level),
			code="level_3_4_never",
			hard=True,
		)

	# Rule 4 -- everything else needs an Academic Coordinator override.
	# This is the branch a Level 2 student hits for a Level 3 course.
	return Decision.block(
		_(
			"A Level {0} student cannot take a Level {1} course without an "
			"Academic Coordinator override."
		).format(student_level, course_level),
		code="level_needs_override",
		needs_override=True,
	)


def may_override(user=None):
	user = user or frappe.session.user
	return bool(OVERRIDE_ROLES & set(frappe.get_roles(user)))


# ---------------------------------------------------------------------------
# additional gates
# ---------------------------------------------------------------------------


def check_duplicate(program_enrollment, course, exclude=None):
	"""Block re-taking a course already passed.

	This is what stops a Level 1 student re-registering for a Level 2 course
	after promotion. A failed or withdrawn attempt may of course be retaken.
	"""
	filters = {
		"program_enrollment": program_enrollment,
		"course": course,
		"passed": 1,
	}
	if exclude:
		filters["name"] = ("!=", exclude)

	existing = frappe.db.exists("Course Registration", filters)
	if existing:
		return Decision.block(
			_("{0} has already been passed ({1}).").format(course, existing),
			code="already_passed",
			hard=True,
		)

	filters.pop("passed")
	filters["status"] = ("in", ("Registered", "Active"))
	in_progress = frappe.db.exists("Course Registration", filters)
	if in_progress:
		return Decision.block(
			_("{0} is already in progress ({1}).").format(course, in_progress),
			code="already_registered",
			hard=True,
		)

	return Decision.allow()


def check_prerequisites(program_enrollment, course):
	"""Hard prerequisites must have been passed. Soft ones only warn."""
	hard = frappe.get_all(
		"Course Prerequisite",
		filters={"parent": course, "parenttype": "Course", "is_hard": 1},
		pluck="prerequisite_course",
	)
	if not hard:
		return Decision.allow()

	passed = set(
		frappe.get_all(
			"Course Registration",
			filters={"program_enrollment": program_enrollment, "passed": 1},
			pluck="course",
		)
	)

	missing = [c for c in hard if c not in passed]
	if missing:
		return Decision.block(
			_("Prerequisite not met: {0} must be passed first.").format(", ".join(missing)),
			code="prerequisite_missing",
			needs_override=True,
		)

	return Decision.allow()


def check_offering_open(course_offering):
	"""The offering must be published and have room; the term must be open."""
	offering = frappe.db.get_value(
		"Course Offering",
		course_offering,
		["status", "capacity", "enrolled_count", "term"],
		as_dict=True,
	)
	if not offering:
		return Decision.block(_("Course Offering not found."), code="no_offering", hard=True)

	if offering.status in ("Draft", "Completed"):
		return Decision.block(
			_("This offering is {0} and not open for registration.").format(offering.status),
			code="offering_not_open",
		)

	if cint(offering.capacity) and cint(offering.enrolled_count) >= cint(offering.capacity):
		return Decision.block(
			_("This offering is full ({0} of {1} seats taken).").format(
				offering.enrolled_count, offering.capacity
			),
			code="offering_full",
			needs_override=True,
		)

	term_status = frappe.db.get_value("Academic Term", offering.term, "status")
	if term_status == "Closed":
		return Decision.block(
			_("Term {0} is closed.").format(offering.term),
			code="term_closed",
		)

	return Decision.allow()


def check_enrollment_active(program_enrollment):
	status = frappe.db.get_value("Program Enrollment", program_enrollment, "status")
	if status != "Active":
		return Decision.block(
			_("This enrollment is {0}, not Active.").format(status or _("missing")),
			code="enrollment_inactive",
		)
	return Decision.allow()


def check_fees(program_enrollment):
	"""Overdue fees.

	Deliberately a **warning by default** -- it matches the practice of chasing
	students rather than locking them out. `block_registration_on_overdue` in
	site config flips it to a hard gate with no code change, per §3.
	"""
	if not frappe.db.exists("DocType", "Fee Invoice"):
		return Decision.allow("fees_not_tracked_yet")

	student = frappe.db.get_value("Program Enrollment", program_enrollment, "student")
	overdue = frappe.get_all(
		"Fee Invoice",
		filters={
			"student": student,
			"status": ("in", ("Unpaid", "Partly Paid")),
			"due_date": ("<", frappe.utils.nowdate()),
		},
		pluck="name",
	)
	if not overdue:
		return Decision.allow()

	reason = _("{0} overdue invoice(s): {1}").format(len(overdue), ", ".join(overdue[:5]))

	if cint(frappe.db.get_single_value("System Settings", "block_registration_on_overdue")) or cint(
		frappe.conf.get("block_registration_on_overdue")
	):
		return Decision.block(reason, code="fees_overdue")

	return Decision(True, reason=reason, code="fees_overdue_warning")


# ---------------------------------------------------------------------------
# the whole check
# ---------------------------------------------------------------------------


def evaluate(program_enrollment, course_offering, has_override=False, user=None, exclude=None):
	"""Run every gate. Returns (Decision, warnings).

	`has_override` is only honoured when the acting user actually holds an
	override role -- a student cannot grant themselves one by setting a field.
	"""
	warnings = []

	active = check_enrollment_active(program_enrollment)
	if not active:
		return active, warnings

	offering = frappe.db.get_value(
		"Course Offering", course_offering, ["course", "term"], as_dict=True
	)
	if not offering:
		return Decision.block(_("Course Offering not found."), code="no_offering", hard=True), warnings

	open_check = check_offering_open(course_offering)

	student_level = frappe.db.get_value("Program Enrollment", program_enrollment, "current_level")
	course_level = frappe.db.get_value("Course", offering.course, "level")

	duplicate = check_duplicate(program_enrollment, offering.course, exclude=exclude)
	if not duplicate:
		return duplicate, warnings

	level_decision = check_level(student_level, course_level)
	prereq = check_prerequisites(program_enrollment, offering.course)

	fees = check_fees(program_enrollment)
	if fees.reason:
		warnings.append(fees.reason)
	if not fees:
		return fees, warnings

	override_ok = bool(has_override) and may_override(user)

	for decision in (level_decision, prereq, open_check):
		if decision:
			continue
		if decision.hard:
			return decision, warnings
		if decision.needs_override and override_ok:
			warnings.append(_("Overridden: {0}").format(decision.reason))
			continue
		return decision, warnings

	return Decision.allow(), warnings


def explain(program_enrollment, course_offering):
	"""Why a student can or cannot take an offering. Used by the portal."""
	decision, warnings = evaluate(program_enrollment, course_offering)
	return {
		"allowed": decision.allowed,
		"reason": decision.reason,
		"code": decision.code,
		"needs_override": decision.needs_override,
		"hard": decision.hard,
		"warnings": warnings,
	}
