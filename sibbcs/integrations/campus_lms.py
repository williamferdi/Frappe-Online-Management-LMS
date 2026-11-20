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
# Who the LMS is told teaches a run of a course, and under which of its own
# staff roles. The registrar draws no line between the two: `SCOPE_FIELDS` in
# `academic.permissions` scopes an offering by `instructor` *or* `facilitator`,
# and the staff course list says as much -- "A course appears here once you are
# named as its instructor or facilitator". The LMS has two staff roles where
# the registrar has one kind of access, so the instructor of record gets
# `teacher`, which may also manage the course, and the facilitator gets `ta`,
# which marks and edits content but cannot. Neither is wider than what the
# registrar already grants the same person here.
TEACHING_ROLE = {"instructor": "teacher", "facilitator": "ta"}


def _setting(key):
	return (frappe.conf.get(key) or "").strip()


def configured():
	return bool(_setting("campus_lms_url") and _setting("campus_lms_token"))


def base_url():
	"""Where a person signs in. Their courses are whatever they are enrolled on."""
	return _setting("campus_lms_url").rstrip("/")


def course_url(course_id=None):
	"""Where somebody opens their learning over there.

	Without an id this is the LMS front door, which is a real answer rather
	than a lazy one: the LMS lands a person on the courses they are enrolled
	on and shows them nothing else, so an applicant arrives at their exam and
	their orientation and a student at the courses they registered for.

	With an id it is the course itself, which is the difference between "sign
	in and find it" and a link that opens the thing the email is about. The id
	has to be the LMS's own: `/courses/:courseId` over there is validated as a
	UUID, so `BISTO502-2026-T6` is not an address anybody can open -- which is
	why `lms_course_id` is kept on the offering as the sync learns it.
	"""
	base = base_url()
	if not base:
		return None
	return f"{base}/courses/{course_id}" if course_id else base


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


# What Campus LMS Lite's not-found *handler* says, as against what its own
# `notFound("Person")` says. Both come back as code `not_found`, so this is the
# only thing that tells "you asked for an address I do not serve" apart from
# "I have never heard of this person". Pinned on the LMS side by
# `the not-found handler keeps the message the registrar reads`.
ROUTE_MISSING = "Route not found."


def reissue_activation_link(application):
	"""A fresh activation link for a candidate who never used their first one.

	`enrol_applicant` gets one only when the account is new: the LMS issues the
	token once, because issuing a second invalidates the first and a routine
	re-sync would break the link somebody was about to use. That link lasts
	seven days, so a resend after it lapses has to ask for a new one.

	Answers `{"url": ...}` or `{"error": "..."}` and never raises. The officer
	pressing Resend needs to be told what happened -- that the candidate has
	already set a password, or that the LMS has never heard of them -- not
	shown a Frappe traceback with our internals in it.
	"""
	if not configured():
		return {"error": "Campus LMS is not configured."}

	import requests

	from urllib.parse import quote

	try:
		response = requests.post(
			_url(f"/sync/people/{quote(str(application))}/activation-link"),
			json={},
			headers=_headers(),
			timeout=TIMEOUT,
		)
	except Exception as exception:
		frappe.log_error(title=f"Campus LMS activation link failed for {application}")
		return {"error": f"Campus LMS could not be reached: {exception}"}

	# The LMS writes its refusals for a person to read -- a 422 is "they have
	# already set a password" -- so they are passed on rather than paraphrased.
	detail = ""
	try:
		body = response.json() or {}
		detail = ((body.get("error") or {}) if isinstance(body.get("error"), dict) else {}).get(
			"message"
		) or ""
	except ValueError:
		body = {}

	if response.status_code == 404:
		# Two different 404s, and they are the same shape: the LMS routes its
		# own `notFound("Person")` and its not-found *handler* through one error
		# body, so both arrive as `{"error": {"code": "not_found"}}`. Only the
		# message separates them, and `ROUTE_MISSING` is the handler's own
		# constant -- pinned by a test on that side, because reading it as the
		# other is how an LMS that has not been restarted since this endpoint
		# was added reports itself as a candidate who does not exist.
		if detail.strip() == ROUTE_MISSING:
			return {
				"error": (
					"Campus LMS does not offer this endpoint. It is running a build from "
					"before activation links could be reissued -- restart it after deploying."
				)
			}
		return {"error": detail or "Campus LMS has no account for this applicant yet."}

	if response.status_code >= 400:
		return {"error": detail or f"Campus LMS refused the request ({response.status_code})."}

	data = response.json() or {}
	return {"url": data.get("url"), "expires_in_hours": data.get("expiresInHours")}


def enrol_in_course(application, course_external_id, email, full_name):
	"""Put an applicant on one of the admissions courses, keeping their account.

	`enrol_applicant` above is the entrance-exam case and keeps its own
	`EXAM-{application}` key, which is already stored against every candidate
	who has sat one -- reusing this key shape for the exam would make a second
	enrolment rather than find the first. So the exam keeps its key and
	everything else is filed by course and application.

	Idempotent: both endpoints upsert on `externalId`.
	"""
	if not configured():
		return None
	_post(
		"/sync/people",
		{"externalId": application, "email": email, "name": full_name or email, "role": "student"},
	)
	return _post(
		"/sync/enrollments",
		{
			"externalId": f"{course_external_id}-{application}",
			"personExternalId": application,
			"courseExternalId": course_external_id,
			"role": "student",
		},
	)


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


def course_grades(course_external_id, person_external_id=None):
	"""Course results on one offering, or None when unconfigured.

	Two totals come back per student and the choice between them is ours, not
	the LMS's -- it does not know when a term ended:

	- `current` counts only work that has been marked and released. It is the
	  running average and it climbs as marking happens.
	- `final` treats unreleased and unsubmitted work as zero, so it is only the
	  truth once the course is over.

	`awaitingMarking` and `gradedUnposted` are why a caller must look before it
	records anything. The transcript is the one place a wrong figure is hardest
	to undo, and the rule here is the same one the entrance exam already
	follows: a mark nobody has finished is not a mark of zero.
	"""
	if not configured():
		return None
	params = {"courseExternalId": course_external_id}
	if person_external_id:
		params["personExternalId"] = person_external_id
	return _get("/sync/grades", params, allow_missing=True)


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
	"""One run of a course, as the LMS needs to show it.

	The level and the programmes belong to the **Course**, not to this run of
	it, so they are read from there rather than from the offering's own
	`course_level` -- which is a mirrored Data field and goes stale the moment
	somebody corrects the catalogue.

	They are sent every time, including when empty. The LMS distinguishes "not
	sent" from "sent as empty": a course that stops counting towards a
	programme has to be able to say so, and leaving the key out would mean the
	old list stood for ever.
	"""
	row = frappe.db.get_value(
		"Course Offering", name, ["name", "course", "course_title", "term", "status"], as_dict=True
	)
	if not row:
		return None

	course = (
		frappe.db.get_value("Course", row.course, ["level", "course_title"], as_dict=True) or {}
	)
	programs = frappe.get_all(
		"Course Program Link",
		filters={"parent": row.course, "parenttype": "Course"},
		pluck="program",
		order_by="idx asc",
	)

	return {
		"externalId": row.name,
		"code": row.course,
		"name": row.course_title or course.get("course_title") or row.course,
		"term": row.term,
		"status": OFFERING_STATUS.get(row.status, "unpublished"),
		"level": course.get("level") or None,
		"programs": programs,
	}


def teaching_external_id(instructor, offering):
	"""The id a teaching enrolment is filed under over there.

	It names the **person**, not just the slot. `/sync/enrollments` finds its
	row by `externalId` and then sets the role and the status on it; it never
	moves that row to somebody else. So an id of `{offering}-TEACHER` would
	leave the outgoing instructor teaching the course for ever and never let
	the new one in. Naming the person means replacing an instructor writes a
	second row and deactivates the first, which is also the truthful record of
	what happened.

	Deliberately the same shape as the markers `phase6_admissions_lms` puts on
	the entrance exam, so every teaching enrolment over there reads alike
	whichever side of admissions it came from.
	"""
	return f"MARKER-{instructor}-{offering}"


def teaching_staff(offering):
	"""Who teaches one offering, as `{instructor: LMS role}`.

	Takes a name or a document, because a deletion has to read the staff off
	the copy in front of it rather than from a row that is about to go.
	"""
	row = offering
	if isinstance(offering, str):
		row = frappe.db.get_value(
			"Course Offering", offering, ["instructor", "facilitator"], as_dict=True
		)
	if not row:
		return {}

	staff = {}
	for field, role in TEACHING_ROLE.items():
		instructor = row.get(field)
		# One person in both slots keeps the wider role, rather than whichever
		# field happened to be read second. Saving that only warns, so such
		# records do exist.
		if instructor and instructor not in staff:
			staff[instructor] = role
	return staff


def teaching_payloads(offering):
	"""The enrolments that put an offering's staff on the course over there.

	The LMS reads a course's teachers from its *enrolments* -- the same table
	the students are in -- so an instructor named on the offering and never
	enrolled is a course with nobody teaching it. Which is what
	BISTO502-2026-T6 was until 20 Nov 2026: instructor set here, blank there.
	"""
	name = offering if isinstance(offering, str) else offering.name
	return [
		{
			"externalId": teaching_external_id(instructor, name),
			"personExternalId": instructor,
			"courseExternalId": name,
			"role": role,
			"status": "active",
		}
		for instructor, role in teaching_staff(offering).items()
	]
def registration_payload(name):
	row = frappe.db.get_value(
		"Course Registration", name, ["name", "student", "course_offering", "status"], as_dict=True
	)
	if not row or not row.student or not row.course_offering:
		return None

	status = REGISTRATION_STATUS.get(row.status, "inactive")
	# The course opens on payment, not on Register: registering is the student
	# saying yes, paying is what buys the seat. That rule used to live in
	# `Course Registration.maybe_sync_lms`, which gated enrolment into the
	# bundled LMS and went with it in Phase 7 -- so it is applied here instead,
	# or removing that method would have quietly dropped the college's rule.
	#
	# Only ever narrowing. A settled fee does not make a withdrawn
	# registration active again.
	if status == "active":
		from sibbcs.academic.doctype.course_registration.course_registration import (
			registration_fee_settled,
			require_fee_before_lms,
		)

		if require_fee_before_lms() and not registration_fee_settled(row.name):
			status = "inactive"

	return {
		"externalId": row.name,
		"personExternalId": row.student,
		"courseExternalId": row.course_offering,
		"role": "student",
		"status": status,
	}


# ---------------------------------------------------------------------------
# pushing
# ---------------------------------------------------------------------------


def _remember_course_id(offering, answer):
	"""Keep the LMS's own id for a course, so a link can open the course itself.

	`/sync/courses` answers with the record it wrote. Its `id` is the only
	address the LMS's own routes accept -- `/courses/:courseId` is validated as
	a UUID over there, so the registrar's `BISTO502-2026-T6` opens nothing, and
	without this every link to a course could only be the front door.

	`update_modified=False`, and no `save`: this runs inside the push job, and
	stamping `modified` here would make every offering look edited by the sync
	it had just triggered -- and re-trigger `on_update`, which enqueues the
	push again.
	"""
	answer = answer if isinstance(answer, dict) else {}
	course = answer.get("course")
	course_id = course.get("id") if isinstance(course, dict) else None
	# Typed, not merely truthy. This is another system's answer, and what it
	# sends is what would be written into a link we hand a student -- so a
	# shape we did not expect is passed over rather than stored.
	if not isinstance(course_id, str) or not course_id:
		return
	# The field arrives with a migration, and the push runs from a worker that
	# may still be holding the schema from before it.
	if not frappe.db.has_column("Course Offering", "lms_course_id"):
		return
	if frappe.db.get_value("Course Offering", offering, "lms_course_id") == course_id:
		return
	frappe.db.set_value(
		"Course Offering", offering, "lms_course_id", course_id, update_modified=False
	)
def push_teaching(offering):
	"""Put an offering's staff on the course over there.

	The person goes first, for the reason `push` gives about a registration:
	`/sync/enrollments` refuses an enrolment naming somebody the LMS has not
	heard of, and an instructor who has not been saved since this integration
	was switched on has never been sent. `person_payload` returns None without
	an address, which is the right answer too -- no address, no account to
	enrol.
	"""
	for enrolment in teaching_payloads(offering):
		person = person_payload("Instructor", enrolment["personExternalId"])
		if not person:
			continue
		_post("/sync/people", person)
		_post("/sync/enrollments", enrolment)
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
			_remember_course_id(name, _post("/sync/courses", payload))
			push_teaching(name)
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
		_remember_course_id(
			registration["courseExternalId"], _post("/sync/courses", offering)
		)
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


def send(path, payload):
	"""Post one prepared payload. Runs in a background job."""
	if not configured():
		return
	_post(path, payload)


def queue_payload(path, payload):
	"""Queue a payload that was built before the job ran.

	`queue` sends a doctype and a name and lets `push` read the document in the
	job, which is right for a save: the job then sends what was actually
	stored. It cannot work for a deletion -- by the time the job runs there is
	nothing left to read -- so a deletion has to say what it means while the
	document is still in front of it.
	"""
	if not configured():
		return
	frappe.enqueue(
		"sibbcs.integrations.campus_lms.send",
		queue="short",
		enqueue_after_commit=True,
		path=path,
		payload=payload,
	)


# ---------------------------------------------------------------------------
# hook handlers
# ---------------------------------------------------------------------------


def _stops_teaching(instructor, offering, role):
	"""Somebody taken off a course they no longer teach.

	Inactive rather than deleted, for the reason `on_registration_trash`
	gives: they may have marked work, and the LMS's record of who marked it
	refers to the enrolment.

	**The role is sent, and it is the one they held.** `/sync/enrollments`
	defaults a missing role to `student`, so leaving it out would not retire
	an instructor; it would re-file them as a student of their own course.
	"""
	return {
		"externalId": teaching_external_id(instructor, offering),
		"personExternalId": instructor,
		"courseExternalId": offering,
		"role": role,
		"status": "inactive",
	}
def on_student_change(doc, method=None):
	queue("Student", doc.name)


def on_instructor_change(doc, method=None):
	queue("Instructor", doc.name)


def on_offering_change(doc, method=None):
	"""Send the offering, and take off anybody who has stopped teaching it.

	A leaver has to be named while the previous version is still in front of
	us. `push` reads the offering inside the job and can only see who teaches
	it *now*, so by the time it runs the person who no longer does is
	invisible -- the same problem `queue_payload` exists to solve for
	deletions.

	Moving somebody between the two slots is not leaving. The enrolment is
	filed under the person, so the push rewrites the role on the row they
	already have.
	"""
	queue("Course Offering", doc.name)

	before = getattr(doc, "_doc_before_save", None)
	if not before:
		return
	teaching_now = teaching_staff(doc)
	for field, role in TEACHING_ROLE.items():
		was = before.get(field)
		if was and was not in teaching_now:
			queue_payload("/sync/enrollments", _stops_teaching(was, doc.name, role))


def _mirrored_from_course(doc):
	"""The parts of a Course the LMS is shown, as a comparable value.

	The programmes are a child table, so `has_value_changed` cannot be trusted
	with them -- it compares the rows as documents, which differ on every save
	whether or not a programme was added. Comparing the sorted codes answers
	the question actually being asked.
	"""
	if not doc:
		return None
	rows = doc.get("programs") or []
	return (
		doc.get("level"),
		doc.get("course_title"),
		tuple(sorted(row.program for row in rows if getattr(row, "program", None))),
	)


def on_course_change(doc, method=None):
	"""Re-send every run of a course when the catalogue entry changes.

	The level and the programmes belong to the Course and travel with the
	offering, so without this, correcting a level in the catalogue would leave
	the LMS showing the old one until somebody happened to save the offering --
	which might be never.

	A course is saved for many reasons and most are not the LMS's business, so
	nothing is sent unless one of the mirrored fields actually moved. An
	insert has no previous version and no offerings yet, so it falls through
	the loop and sends nothing either way.
	"""
	if not configured():
		return
	before = _mirrored_from_course(getattr(doc, "_doc_before_save", None))
	if before is not None and before == _mirrored_from_course(doc):
		return
	for offering in frappe.get_all("Course Offering", filters={"course": doc.name}, pluck="name"):
		queue("Course Offering", offering)


def on_registration_change(doc, method=None):
	queue("Course Registration", doc.name)


def on_student_trash(doc, method=None):
	"""A deleted student should not keep an account over there.

	Their courses have already closed: Frappe refuses to delete a Student while
	a registration exists, so each registration went first and fired
	`on_registration_trash`. What was left was an account that could still sign
	in and see an empty dashboard.

	Deactivated, not deleted. They may have done work, and the LMS's own audit
	trail refers to them.

	`onlyIfPresent` is what makes this safe: `/sync/people` upserts, so without
	it a student who was never pushed would have an account *created* for them
	on the way out. Not hypothetical -- clearing the demo data deleted a seeded
	student who had no account over there at all.
	"""
	email = (doc.email or "").strip() or (doc.user or "").strip()
	if not email or "@" not in email:
		return
	queue_payload(
		"/sync/people",
		{
			"externalId": doc.name,
			"email": email,
			"name": doc.full_name or email,
			"role": "student",
			"status": "deactivated",
			"onlyIfPresent": True,
		},
	)


def on_offering_trash(doc, method=None):
	"""A deleted offering is not a course anybody should still open.

	Archived rather than unpublished: unpublished reads as "not ready yet",
	which is the opposite of what happened. Same `onlyIfPresent` reasoning as
	above -- and on this endpoint it also stops a no-op creating the term.
	"""
	queue_payload(
		"/sync/courses",
		{
			"externalId": doc.name,
			"code": doc.course,
			"name": doc.course_title or doc.course,
			"term": doc.term,
			"status": "archived",
			"onlyIfPresent": True,
		},
	)

	# And take the staff off it. Archived already stops anybody opening the
	# course, but an offering can be re-created under the same name -- a
	# BISTO502-2026-T6 keyed in again means the same run of the same course --
	# and the next sync would publish it with a teacher nobody chose.
	for enrolment in teaching_payloads(doc):
		queue_payload("/sync/enrollments", dict(enrolment, status="inactive"))


def on_registration_trash(doc, method=None):
	"""A deleted registration is not an enrolment any more. Say so.

	Without this, deleting or purging a registration left the student with an
	**active** enrolment in a course the registrar no longer knows about: the
	push fires on `on_update` and `after_insert`, and nothing fired on delete.
	Found while clearing TEST COURSE, whose LMS enrolment had to be removed by
	hand afterwards.

	**Inactive, not deleted.** There is no delete over there and there should
	not be: the student may have done work on the course, and a withdrawal
	already means inactive, so a deletion meaning the same thing keeps one
	answer to "can they still get in".

	`/sync/enrollments` upserts, so this can in principle *create* an inactive
	enrolment where none existed. It cannot invent one out of nothing -- the
	endpoint 404s unless both the person and the course are already over there
	-- and an inactive enrolment grants no access, which is the same outcome a
	withdrawal has always had.
	"""
	if not doc.student or not doc.course_offering:
		return
	queue_payload(
		"/sync/enrollments",
		{
			"externalId": doc.name,
			"personExternalId": doc.student,
			"courseExternalId": doc.course_offering,
			"role": "student",
			"status": "inactive",
		},
	)
