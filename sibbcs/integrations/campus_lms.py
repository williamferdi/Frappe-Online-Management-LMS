# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""Pushing registrar facts into Campus LMS Lite.

Teaching lives in Campus LMS Lite; who the students are, which courses run this
term and who is registered for them stays here. This is the one direction that
travel happens, so nobody is enrolled twice and the two never argue about who
is on a course.

**Silent until configured.** Both `campus_lms_url` and `campus_lms_token` must
be in site config. Until they are, every call here does nothing -- the live site
runs exactly as it did before, which is what lets this ship ahead of the switch.

**Queued, never inline.** A registrar saving a record must not wait on another
system, nor fail because it is down. Each push is a background job, enqueued
after the commit so the job reads what was actually saved.

The marks that come back the other way arrive at `sibbcs.api.lms_bridge`.
"""

import frappe
from frappe import _
from frappe.utils import cint

TIMEOUT = 20

# The admissions courses over there, by the id this system files them under.
# Applicants are enrolled in these and in nothing else, which is the whole of
# their isolation: the LMS shows a student only the courses they are on.
EXAM_COURSE = "ADMISSIONS-ENTRANCE-EXAM"
ORIENTATION_COURSE = "ADMISSIONS-ORIENTATION"

# What a `Reading Manual` still names, and where that course now lives. Those
# records hold the old slug, and rewriting stored data to match a move is how
# a restored backup stops working.
MOVED_COURSES = {
	"entrance-exam": EXAM_COURSE,
	"m-div-preliminary-orientation": ORIENTATION_COURSE,
	"orientation-to-online-study": ORIENTATION_COURSE,
}


def course_for(source):
	"""The LMS course a stored slug refers to, or None if it did not move."""
	return MOVED_COURSES.get((source or "").strip())

# Registrar status -> what it means in the LMS.
OFFERING_STATUS = {
	"Draft": "unpublished",
	"Published": "published",
	"Running": "published",
	"Completed": "archived",
}
REGISTRATION_STATUS = {
	"Draft": "inactive",
	"Registered": "active",
	"Active": "active",
	"Completed": "completed",
	"Failed": "completed",
	"Withdrawn": "inactive",
}
# Only the statuses that should close an account. Anything else is left alone:
# marking somebody "active" who has not set a password yet would strand them,
# because the LMS issues an activation link only while the account is pending.
CLOSED_STUDENT_STATUS = {"Withdrawn", "Dismissed"}


def _setting(key):
	return (frappe.conf.get(key) or "").strip()


def configured():
	return bool(_setting("campus_lms_url") and _setting("campus_lms_token"))


def base_url():
	"""Where a person signs in. Their courses are whatever they are enrolled on."""
	return _setting("campus_lms_url").rstrip("/")


def enrol_applicant(application, email, full_name):
	"""Give an applicant an account and a place in the entrance exam.

	Filed under the application, which is how they are known over there until
	they are admitted and re-filed as a student. Returns the activation link
	when the account was new -- the LMS sends no email, so the invitation goes
	out from here.
	"""
	if not configured():
		return None
	person = _post(
		"/sync/people",
		{"externalId": application, "email": email, "name": full_name or email, "role": "student"},
	)
	_post(
		"/sync/enrollments",
		{
			"externalId": f"EXAM-{application}",
			"personExternalId": application,
			"courseExternalId": EXAM_COURSE,
			"role": "student",
		},
	)
	return person.get("activationUrl")


def _url(path):
	return f"{_setting('campus_lms_url').rstrip('/')}/api/v1{path}"


def _headers():
	return {"Authorization": f"Bearer {_setting('campus_lms_token')}"}


def check():
	"""Can we reach the LMS, and does it accept our token? Writes nothing.

	For `bench execute sibbcs.integrations.campus_lms.check` when something
	looks wrong. Deliberately not whitelisted: it is a diagnostic for whoever
	administers the site, not an endpoint.
	"""
	if not configured():
		return {
			"configured": False,
			"ok": False,
			"detail": "campus_lms_url and campus_lms_token are not both set.",
		}

	import requests

	try:
		response = requests.get(_url("/sync/whoami"), headers=_headers(), timeout=TIMEOUT)
	except Exception as exc:
		return {"configured": True, "ok": False, "detail": f"{type(exc).__name__}: {exc}"[:300]}

	if response.status_code != 200:
		return {
			"configured": True,
			"ok": False,
			"detail": f"{response.status_code} {response.text[:200]}",
		}
	return {
		"configured": True,
		"ok": True,
		"url": _setting("campus_lms_url"),
		"service": (response.json().get("service") or {}).get("label"),
	}


def _get(path, params, allow_missing=False):
	"""Read something back. Raises on refusal, as `_post` does.

	`allow_missing` turns a 404 into None, and only the caller knows whether
	that is an answer or a fault. For both reads here it is an answer: the LMS
	has never heard of this person, so they have got nowhere and have sat
	nothing. It is the ordinary case, not the exceptional one -- an applicant
	has no account there until an officer makes one, and an admitted one is
	re-filed under their student number, so asking by application number stops
	resolving the moment they are converted. Left raising, it put a Frappe
	validation error on the officer's screen for every application on the site.

	A 500, or a refused token, still raises: that is a misconfiguration and
	somebody has to see it.
	"""
	import requests

	response = requests.get(_url(path), params=params, headers=_headers(), timeout=TIMEOUT)
	if allow_missing and response.status_code == 404:
		return None
	if response.status_code >= 400:
		frappe.throw(
			_("Campus LMS refused {0}: {1} {2}").format(path, response.status_code, response.text[:400])
		)
	return response.json()


def progress(person_external_id, course_external_id):
	"""How far one person has got through one course, or None when unconfigured.

	`complete` is the LMS's answer, not ours: it counts the items that ask
	something of the student against the ones they have done.
	"""
	if not configured():
		return None
	return _get(
		"/sync/progress",
		{"personExternalId": person_external_id, "courseExternalId": course_external_id},
		allow_missing=True,
	)


def quiz_results(course_external_id, person_external_id=None):
	"""Attempts on a course's quizzes, newest marking included.

	Each attempt says whether anybody has marked it yet, which is the
	distinction the entrance exam turns on.
	"""
	if not configured():
		return None
	params = {"courseExternalId": course_external_id}
	if person_external_id:
		params["personExternalId"] = person_external_id
	return _get("/sync/quiz-results", params, allow_missing=True)


def _post(path, payload):
	"""One call to the LMS. Raises on refusal, so a queued job records it."""
	import requests

	response = requests.post(_url(path), json=payload, headers=_headers(), timeout=TIMEOUT)
	if response.status_code >= 400:
		frappe.throw(
			_("Campus LMS refused {0}: {1} {2}").format(path, response.status_code, response.text[:400])
		)
	return response.json()


# ---------------------------------------------------------------------------
# what each record looks like over there
# ---------------------------------------------------------------------------


def person_payload(doctype, name):
	"""A Student or an Instructor as an LMS account, or None without an address.

	No email means no account: the LMS identifies people by address, and a
	placeholder would be a second account for somebody who already has one.
	"""
	fields = ["name", "full_name", "email", "user"]
	fields += ["status", "admission_application"] if doctype == "Student" else ["is_active"]
	row = frappe.db.get_value(doctype, name, fields, as_dict=True)
	if not row:
		return None
	email = (row.get("email") or "").strip() or (row.get("user") or "").strip()
	if not email or "@" not in email:
		return None

	payload = {
		"externalId": row.name,
		"email": email,
		"name": row.full_name or email,
		"role": "student" if doctype == "Student" else "instructor",
	}
	if doctype == "Student":
		if row.get("status") in CLOSED_STUDENT_STATUS:
			payload["status"] = "deactivated"
		# An admitted applicant keeps the account they sat the entrance exam
		# with. Over there they are still filed under their application, so the
		# key has to be moved deliberately -- the LMS refuses to adopt an
		# address that is already linked unless we say it is the same person.
		if row.get("admission_application"):
			payload["replacesExternalId"] = row.admission_application
	elif not cint(row.get("is_active")):
		payload["status"] = "deactivated"
	return payload


def offering_payload(name):
	row = frappe.db.get_value(
		"Course Offering", name, ["name", "course", "course_title", "term", "status"], as_dict=True
	)
	if not row:
		return None
	return {
		"externalId": row.name,
		"code": row.course,
		"name": row.course_title or row.course,
		"term": row.term,
		"status": OFFERING_STATUS.get(row.status, "unpublished"),
	}


def registration_payload(name):
	row = frappe.db.get_value(
		"Course Registration", name, ["name", "student", "course_offering", "status"], as_dict=True
	)
	if not row or not row.student or not row.course_offering:
		return None
	return {
		"externalId": row.name,
		"personExternalId": row.student,
		"courseExternalId": row.course_offering,
		"role": "student",
		"status": REGISTRATION_STATUS.get(row.status, "inactive"),
	}


# ---------------------------------------------------------------------------
# pushing
# ---------------------------------------------------------------------------


def push(doctype, name):
	"""Send one record. Runs in a background job; safe to run again at any time.

	A registration carries its student and its offering with it: the LMS refuses
	an enrolment naming people or courses it has not heard of, and the registrar
	is the only one who knows they exist.
	"""
	if not configured():
		return

	if doctype in ("Student", "Instructor"):
		payload = person_payload(doctype, name)
		if payload:
			_post("/sync/people", payload)
		return

	if doctype == "Course Offering":
		payload = offering_payload(name)
		if payload:
			_post("/sync/courses", payload)
		return

	if doctype == "Course Registration":
		registration = registration_payload(name)
		if not registration:
			return
		student = person_payload("Student", registration["personExternalId"])
		if not student:
			return
		offering = offering_payload(registration["courseExternalId"])
		if not offering:
			return
		_post("/sync/people", student)
		_post("/sync/courses", offering)
		_post("/sync/enrollments", registration)


def queue(doctype, name):
	if not configured():
		return
	frappe.enqueue(
		"sibbcs.integrations.campus_lms.push",
		queue="short",
		enqueue_after_commit=True,
		doctype=doctype,
		name=name,
	)


# ---------------------------------------------------------------------------
# hook handlers
# ---------------------------------------------------------------------------


def on_student_change(doc, method=None):
	queue("Student", doc.name)


def on_instructor_change(doc, method=None):
	queue("Instructor", doc.name)


def on_offering_change(doc, method=None):
	queue("Course Offering", doc.name)


def on_registration_change(doc, method=None):
	queue("Course Registration", doc.name)
