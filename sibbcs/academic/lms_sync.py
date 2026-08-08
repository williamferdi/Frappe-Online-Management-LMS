"""LMS integration -- architecture doc §6.

The "one login" promise resolves to a single hook:

    Course Registration reaches Registered
       -> ensure the Course has an LMS Course
       -> ensure the Course Offering has an LMS Batch (create and store if not)
       -> enroll student.user in that batch
       -> set lms_enrollment_created

One thing §6 does not spell out but the LMS model requires: batch membership
alone does not grant course access. `LMS Batch Enrollment` puts the student in
the batch; `LMS Enrollment` is what actually opens the course. We create both,
which is what makes "a student logs in once and sees their LMS course" true.

Every write is guarded so a broken LMS link can never roll back a registration
the registrar has already accepted -- failures are logged and reported, and the
sync can be re-run.
"""

import frappe
from frappe import _
from frappe.utils import add_months, nowdate


def _add_hours(time_string, hours):
	"""Advance a HH:MM:SS string, clamped inside the same day."""
	parts = [int(p) for p in str(time_string).split(":")[:3]]
	while len(parts) < 3:
		parts.append(0)
	total = parts[0] * 3600 + parts[1] * 60 + parts[2] + hours * 3600
	total = min(total, 23 * 3600 + 59 * 60)
	return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def _default_instructor(offering=None):
	"""LMS Course and LMS Batch both require at least one instructor.

	Prefer the offering's instructor if they have a login, else fall back to
	Administrator so sync is never blocked by missing staff data.
	"""
	if offering:
		instructor = frappe.db.get_value("Course Offering", offering, "instructor")
		if instructor:
			user = frappe.db.get_value("Instructor", instructor, "user")
			if user and frappe.db.exists("User", user):
				return user
	return "Administrator"


def ensure_lms_course(course):
	"""Return the LMS Course for a Course, creating one if needed."""
	existing = frappe.db.get_value("Course", course, "lms_course")
	if existing and frappe.db.exists("LMS Course", existing):
		return existing

	doc = frappe.db.get_value(
		"Course", course, ["course_title", "description", "course_code"], as_dict=True
	)

	lms_course = frappe.get_doc(
		{
			"doctype": "LMS Course",
			"title": doc.course_title or course,
			"short_introduction": (doc.course_title or course)[:140],
			"description": doc.description or doc.course_title or course,
			"published": 1,
			"instructors": [{"instructor": _default_instructor()}],
		}
	)
	lms_course.insert(ignore_permissions=True)

	frappe.db.set_value("Course", course, "lms_course", lms_course.name, update_modified=False)
	return lms_course.name


def ensure_lms_batch(course_offering):
	"""Return the LMS Batch for an offering, creating one if needed."""
	existing = frappe.db.get_value("Course Offering", course_offering, "lms_batch")
	if existing and frappe.db.exists("LMS Batch", existing):
		return existing

	offering = frappe.db.get_value(
		"Course Offering",
		course_offering,
		["course", "course_title", "term", "zoom_time", "format", "capacity"],
		as_dict=True,
	)
	term = frappe.db.get_value(
		"Academic Term", offering.term, ["start_date", "end_date"], as_dict=True
	)

	lms_course = ensure_lms_course(offering.course)

	start = (term and term.start_date) or nowdate()
	end = (term and term.end_date) or add_months(nowdate(), 2)

	# LMS Batch.validate_batch_time rejects start_time >= end_time, so the class
	# window needs a real duration. zoom_time is only the *start*; note that a
	# Time field is never empty in Frappe (it defaults to nowtime()), so this
	# always yields a sane two-hour slot rather than a zero-length one.
	start_time = str(offering.zoom_time or "09:00:00").split(".")[0]
	end_time = _add_hours(start_time, 2)

	batch = frappe.get_doc(
		{
			"doctype": "LMS Batch",
			"title": f"{offering.course} — {offering.term}",
			"start_date": start,
			"end_date": end,
			"start_time": start_time,
			"end_time": end_time,
			"description": f"{offering.course_title or offering.course} ({offering.term})",
			"batch_details": f"{offering.course_title or offering.course} — {offering.format}",
			"timezone": "Asia/Kolkata",
			"published": 1,
			"medium": "Online",
			"instructors": [{"instructor": _default_instructor(course_offering)}],
			"courses": [{"course": lms_course}],
		}
	)
	batch.insert(ignore_permissions=True)

	frappe.db.set_value(
		"Course Offering", course_offering, "lms_batch", batch.name, update_modified=False
	)
	return batch.name


def enroll_student(user, batch, lms_course):
	"""Put a user in a batch *and* in its course.

	Batch membership alone does not open the course, so both records are
	needed. Both are idempotent.
	"""
	created = {}

	if not frappe.db.exists("LMS Batch Enrollment", {"member": user, "batch": batch}):
		frappe.get_doc(
			{"doctype": "LMS Batch Enrollment", "member": user, "batch": batch}
		).insert(ignore_permissions=True)
		created["batch_enrollment"] = True

	if not frappe.db.exists("LMS Enrollment", {"member": user, "course": lms_course}):
		frappe.get_doc(
			{
				"doctype": "LMS Enrollment",
				"member": user,
				"course": lms_course,
				"member_type": "Student",
				"role": "Member",
				"enrollment_from_batch": batch,
			}
		).insert(ignore_permissions=True)
		created["course_enrollment"] = True

	return created


def sync_registration(registration, raise_on_error=False):
	"""Push one Course Registration into the LMS. Idempotent.

	Returns a dict describing what happened. Never raises by default: a
	registration the registrar has accepted must not be undone because the LMS
	is misconfigured.
	"""
	doc = (
		registration
		if isinstance(registration, frappe.model.document.Document)
		else frappe.get_doc("Course Registration", registration)
	)

	result = {"registration": doc.name, "synced": False, "reason": None, "created": {}}

	if doc.status not in ("Registered", "Active", "Completed"):
		result["reason"] = f"status is {doc.status}"
		return result

	student = frappe.db.get_value("Program Enrollment", doc.program_enrollment, "student")
	user = frappe.db.get_value("Student", student, "user") if student else None
	if not user:
		result["reason"] = "student has no linked User"
		return result

	try:
		lms_course = ensure_lms_course(doc.course)
		batch = ensure_lms_batch(doc.course_offering)
		result["created"] = enroll_student(user, batch, lms_course)
		result["lms_course"] = lms_course
		result["lms_batch"] = batch
		result["synced"] = True

		if not doc.lms_enrollment_created:
			doc.db_set("lms_enrollment_created", 1, update_modified=False)
	except Exception as exc:
		frappe.log_error(title=f"LMS sync failed for {doc.name}")
		result["reason"] = str(exc)
		if raise_on_error:
			raise

	return result


@frappe.whitelist()
def resync(registration):
	"""Desk button: retry a sync that previously failed."""
	doc = frappe.get_doc("Course Registration", registration)
	doc.check_permission("write")
	result = sync_registration(doc, raise_on_error=False)

	if result["synced"]:
		frappe.msgprint(
			_("Synced to LMS batch {0}.").format(result["lms_batch"]), indicator="green"
		)
	else:
		frappe.msgprint(
			_("Not synced: {0}").format(result["reason"]), indicator="orange"
		)
	return result


def sync_pending(limit=200):
	"""Scheduled sweep for registrations whose sync did not take.

	Registered but not yet in the LMS is exactly the state a student would
	report as "I can't see my course", so it is worth retrying automatically.
	"""
	pending = frappe.get_all(
		"Course Registration",
		filters={
			"status": ("in", ("Registered", "Active")),
			"lms_enrollment_created": 0,
		},
		pluck="name",
		limit=limit,
	)

	synced, failed = [], []
	for name in pending:
		result = sync_registration(name)
		(synced if result["synced"] else failed).append(name)

	if pending:
		frappe.logger("sibbcs").info(
			f"LMS sync sweep: {len(synced)} synced, {len(failed)} still pending"
		)
	return {"synced": synced, "failed": failed}
