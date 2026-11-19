# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""One test per rule about talking to Campus LMS Lite.

The HTTP call itself is mocked throughout: what is worth testing here is what we
decide to send and when, not that `requests` posts. The LMS has its own tests for
the receiving end.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.academic.doctype.academic_term.test_academic_term import make_term
from sibbcs.academic.doctype.course.test_course import make_course
from sibbcs.academic.doctype.course_offering.test_course_offering import make_offering
from sibbcs.academic.doctype.program_enrollment.test_program_enrollment import (
	make_enrollment,
	make_student,
)
from sibbcs.academic.test_gradebook import make_scheme
from sibbcs.api import lms_bridge
from sibbcs.integrations import campus_lms

LIVE = {"campus_lms_url": "https://lms.example.invalid", "campus_lms_token": "t0ken"}


def _ours(call):
	"""Is this enqueue ours, or one of Frappe's own?

	`frappe.delete_doc` enqueues `delete_dynamic_links` itself. A test about
	what we send has no business counting that, and no business guessing at its
	signature either.
	"""
	return str(call.args[0] if call.args else "").startswith("sibbcs.")


def _inline_enqueue(method, **kwargs):
	"""Run one of our queued jobs now, so a test can see what it sent.

	The real job is enqueued `after_commit`, which a test rolling back never
	reaches -- so without this the queue swallows the thing being tested.
	Frappe's own jobs are left alone: passing their keywords on to a function
	that does not take them is how this helper first broke the delete it was
	meant to observe.
	"""
	if not str(method).startswith("sibbcs."):
		return
	for internal in ("queue", "enqueue_after_commit", "now", "timeout", "job_name", "at_front"):
		kwargs.pop(internal, None)
	frappe.get_attr(method)(**kwargs)


class TestCampusLms(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.term = make_term(f"TST-CL-{frappe.generate_hash(length=6)}", status="Open").name

	def setUp(self):
		frappe.set_user("Administrator")
		suffix = frappe.generate_hash(length=6)
		self.course = make_course(f"TCL {suffix[:4]}").name
		self.offering = make_offering(self.course, self.term, status="Published").name
		self.student = make_student(
			f"Campus Student {suffix}", email=f"campus.{suffix}@example.invalid"
		).name
		self.registration = frappe.get_doc(
			{
				"doctype": "Course Registration",
				"program_enrollment": make_enrollment(self.student).name,
				"course_offering": self.offering,
				"status": "Registered",
			}
		).insert(ignore_permissions=True).name

	# --- silent until configured ------------------------------------------

	def test_nothing_is_sent_until_both_settings_exist(self):
		"""Shipping this ahead of the switch must not touch the live site."""
		with patch.dict(frappe.conf, {"campus_lms_url": "", "campus_lms_token": ""}):
			self.assertFalse(campus_lms.configured())
			with patch.object(campus_lms, "_post") as post:
				campus_lms.push("Course Registration", self.registration)
				post.assert_not_called()

	def test_a_half_configured_site_is_not_configured(self):
		with patch.dict(frappe.conf, {"campus_lms_url": "https://x.invalid", "campus_lms_token": ""}):
			self.assertFalse(campus_lms.configured())

	def test_saving_a_record_queues_rather_than_calling_out(self):
		"""A registrar must never wait on another system, nor fail with it."""
		with patch.dict(frappe.conf, LIVE):
			with patch.object(frappe, "enqueue") as enqueue:
				campus_lms.queue("Student", self.student)
				self.assertTrue(enqueue.called)
				self.assertTrue(enqueue.call_args.kwargs["enqueue_after_commit"])

	# --- what each record looks like over there ---------------------------

	def test_a_student_becomes_a_student_account(self):
		payload = campus_lms.person_payload("Student", self.student)
		self.assertEqual(payload["externalId"], self.student)
		self.assertEqual(payload["role"], "student")
		self.assertIn("@", payload["email"])
		# No status on an ordinary student: the LMS creates the account pending
		# and issues the activation link, which naming a status would skip.
		self.assertNotIn("status", payload)

	def test_a_withdrawn_student_is_closed_rather_than_left_open(self):
		frappe.db.set_value("Student", self.student, "status", "Withdrawn")
		self.assertEqual(campus_lms.person_payload("Student", self.student)["status"], "deactivated")

	def test_somebody_with_no_address_gets_no_account(self):
		frappe.db.set_value("Student", self.student, {"email": "", "user": ""})
		self.assertIsNone(campus_lms.person_payload("Student", self.student))

	def test_an_offering_carries_its_term_and_whether_students_may_see_it(self):
		payload = campus_lms.offering_payload(self.offering)
		self.assertEqual(payload["externalId"], self.offering)
		self.assertEqual(payload["code"], self.course)
		self.assertEqual(payload["term"], self.term)
		self.assertEqual(payload["status"], "published")

		frappe.db.set_value("Course Offering", self.offering, "status", "Draft")
		self.assertEqual(campus_lms.offering_payload(self.offering)["status"], "unpublished")

	def test_a_withdrawn_registration_is_not_an_active_enrolment(self):
		# The fee gate is off here so that this test is about the status alone;
		# the gate has its own tests below.
		with patch.dict(frappe.conf, {"require_fee_for_lms_access": 0}):
			self.assertEqual(
				campus_lms.registration_payload(self.registration)["status"], "active"
			)
			frappe.db.set_value("Course Registration", self.registration, "status", "Withdrawn")
			self.assertEqual(
				campus_lms.registration_payload(self.registration)["status"], "inactive"
			)

	# --- the fee gate ------------------------------------------------------
	#
	# "The course opens on payment, not on Register." That rule used to live in
	# `Course Registration.maybe_sync_lms`, which gated enrolment into the
	# bundled LMS and went with it in Phase 7. It is applied in the payload
	# now, and these are here because deleting the method is exactly how such a
	# rule gets lost.

	def test_an_unpaid_registration_is_pushed_as_inactive(self):
		with patch.dict(frappe.conf, {"require_fee_for_lms_access": 1}):
			self.assertEqual(
				campus_lms.registration_payload(self.registration)["status"], "inactive"
			)

	def test_the_gate_can_be_turned_off(self):
		"""It is a setting because the gate is only as good as the gateway
		behind it, and no gateway is configured yet."""
		with patch.dict(frappe.conf, {"require_fee_for_lms_access": 0}):
			self.assertEqual(
				campus_lms.registration_payload(self.registration)["status"], "active"
			)

	def test_the_gate_only_ever_narrows(self):
		"""A settled fee must not make a withdrawn registration active."""
		frappe.db.set_value("Course Registration", self.registration, "status", "Withdrawn")
		for gate in (0, 1):
			with patch.dict(frappe.conf, {"require_fee_for_lms_access": gate}):
				self.assertEqual(
					campus_lms.registration_payload(self.registration)["status"],
					"inactive",
					f"gate={gate}",
				)

	def test_a_settled_fee_opens_the_course(self):
		from sibbcs.academic.doctype.course_registration.course_registration import (
			registration_fee_settled,
		)

		with patch.dict(frappe.conf, {"require_fee_for_lms_access": 1}):
			with patch(
				"sibbcs.academic.doctype.course_registration.course_registration.registration_fee_settled",
				return_value=True,
			):
				self.assertEqual(
					campus_lms.registration_payload(self.registration)["status"], "active"
				)
		# Guard against the import above being the thing that passes.
		self.assertTrue(callable(registration_fee_settled))

	# --- pushing -----------------------------------------------------------

	def test_a_registration_carries_its_student_and_course_with_it(self):
		with patch.dict(frappe.conf, LIVE):
			with patch.object(campus_lms, "_post") as post:
				campus_lms.push("Course Registration", self.registration)

		paths = [call.args[0] for call in post.call_args_list]
		self.assertEqual(paths, ["/sync/people", "/sync/courses", "/sync/enrollments"])

	def test_a_student_with_no_address_stops_the_whole_enrolment(self):
		frappe.db.set_value("Student", self.student, {"email": "", "user": ""})
		with patch.dict(frappe.conf, LIVE):
			with patch.object(campus_lms, "_post") as post:
				campus_lms.push("Course Registration", self.registration)
				post.assert_not_called()


class TestFinalMarkComingBack(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.term = make_term(f"TST-CB-{frappe.generate_hash(length=6)}", status="Open").name

	def setUp(self):
		frappe.set_user("Administrator")
		suffix = frappe.generate_hash(length=6)
		self.course = make_course(f"TCB {suffix[:4]}").name
		self.offering = make_offering(self.course, self.term, status="Published").name
		make_scheme(self.offering, [{"component": "Assignment", "weight_pct": 100}])
		self.registration = frappe.get_doc(
			{
				"doctype": "Course Registration",
				"program_enrollment": make_enrollment(
					make_student(f"Bridge Student {suffix}").name
				).name,
				"course_offering": self.offering,
				"status": "Registered",
			}
		).insert(ignore_permissions=True).name

	def test_a_released_result_becomes_a_grade_and_a_transcript_line(self):
		result = lms_bridge.post_final_mark(self.registration, 82)

		self.assertEqual(result["component"], "Assignment")
		self.assertEqual(result["final_marks"], 82.0)
		self.assertTrue(result["grade"])

	def test_sending_the_same_mark_again_changes_nothing(self):
		lms_bridge.post_final_mark(self.registration, 82)
		first = frappe.db.get_value("Course Registration", self.registration, "grade")
		lms_bridge.post_final_mark(self.registration, 82)
		self.assertEqual(
			frappe.db.get_value("Course Registration", self.registration, "grade"), first
		)

	def test_a_mark_outside_the_scale_is_refused(self):
		for bad in (-1, 101):
			with self.assertRaises(frappe.ValidationError):
				lms_bridge.post_final_mark(self.registration, bad)

	def test_the_component_weighting_set_here_is_kept(self):
		make_scheme(
			self.offering,
			[
				{"component": "Assignment", "weight_pct": 60},
				{"component": "Attendance", "weight_pct": 40},
			],
		)
		lms_bridge.post_final_mark(self.registration, 90, component="Assignment")

		doc = frappe.get_doc("Course Registration", self.registration)
		row = next(c for c in doc.grade_components if c.component == "Assignment")
		self.assertEqual(row.weight_pct, 60)
		self.assertEqual(row.obtained_marks, 90)
		# Both buckets survive. Sending one on its own used to make it the whole
		# set, so a 60/40 course awarded a final mark out of 60 and graded it.
		self.assertEqual(len(doc.grade_components), 2)
		# Attendance is still unmarked, so no letter yet: a blank is not a zero.
		self.assertFalse(doc.grade)

	def test_several_buckets_and_no_name_is_refused_rather_than_guessed(self):
		make_scheme(
			self.offering,
			[
				{"component": "Assignment", "weight_pct": 60},
				{"component": "Attendance", "weight_pct": 40},
			],
		)
		with self.assertRaises(frappe.ValidationError):
			lms_bridge.post_final_mark(self.registration, 90)


class TestTheHandshake(FrappeTestCase):
	"""`check()` is what somebody runs when the sync looks wrong, so it has to
	tell them which of the three things is broken, not merely that it failed."""

	def test_an_unconfigured_site_says_so_rather_than_failing(self):
		with patch.dict(frappe.conf, {"campus_lms_url": "", "campus_lms_token": ""}):
			result = campus_lms.check()
		self.assertFalse(result["configured"])
		self.assertFalse(result["ok"])

	def test_a_reachable_lms_reports_which_token_it_recognised(self):
		with patch.dict(frappe.conf, LIVE):
			with patch("requests.get") as get:
				get.return_value.status_code = 200
				get.return_value.json.return_value = {"service": {"label": "Frappe registrar"}}
				result = campus_lms.check()

		self.assertTrue(result["ok"])
		self.assertEqual(result["service"], "Frappe registrar")
		self.assertEqual(get.call_args.args[0], "https://lms.example.invalid/api/v1/sync/whoami")
		self.assertIn("Bearer", get.call_args.kwargs["headers"]["Authorization"])

	def test_a_refused_token_is_reported_with_its_reason(self):
		with patch.dict(frappe.conf, LIVE):
			with patch("requests.get") as get:
				get.return_value.status_code = 401
				get.return_value.text = '{"error":{"code":"unauthorized"}}'
				result = campus_lms.check()

		self.assertTrue(result["configured"])
		self.assertFalse(result["ok"])
		self.assertIn("401", result["detail"])

	def test_an_unreachable_lms_does_not_raise_into_the_caller(self):
		"""A diagnostic that throws is a diagnostic nobody can read."""
		with patch.dict(frappe.conf, LIVE):
			with patch("requests.get", side_effect=OSError("name or service not known")):
				result = campus_lms.check()

		self.assertFalse(result["ok"])
		self.assertIn("OSError", result["detail"])


class TestReadingBack(FrappeTestCase):
	"""Frappe pulls; the LMS never calls us. No second credential, and a pull
	that fails simply runs again."""

	def test_a_pull_does_nothing_until_configured(self):
		with patch.dict(frappe.conf, {"campus_lms_url": "", "campus_lms_token": ""}):
			self.assertIsNone(campus_lms.progress("APP-1", campus_lms.ORIENTATION_COURSE))
			self.assertIsNone(campus_lms.quiz_results(campus_lms.EXAM_COURSE))

	def test_progress_asks_about_one_person_on_one_course(self):
		with patch.dict(frappe.conf, LIVE):
			with patch("requests.get") as get:
				get.return_value.status_code = 200
				get.return_value.json.return_value = {"required": 49, "completed": 49, "complete": True}
				result = campus_lms.progress("APP-0001", campus_lms.ORIENTATION_COURSE)

		self.assertTrue(result["complete"])
		self.assertEqual(get.call_args.args[0], "https://lms.example.invalid/api/v1/sync/progress")
		self.assertEqual(
			get.call_args.kwargs["params"],
			{"personExternalId": "APP-0001", "courseExternalId": campus_lms.ORIENTATION_COURSE},
		)

	def test_exam_results_can_be_asked_for_one_candidate(self):
		with patch.dict(frappe.conf, LIVE):
			with patch("requests.get") as get:
				get.return_value.status_code = 200
				get.return_value.json.return_value = {"attempts": []}
				campus_lms.quiz_results(campus_lms.EXAM_COURSE, "APP-0001")

		self.assertEqual(get.call_args.kwargs["params"]["personExternalId"], "APP-0001")

	def test_a_refusal_is_raised_rather_than_returned_as_data(self):
		"""A 500, or a refused token, is a misconfiguration somebody must see."""
		with patch.dict(frappe.conf, LIVE):
			with patch("requests.get") as get:
				get.return_value.status_code = 500
				get.return_value.text = "boom"
				with self.assertRaises(frappe.ValidationError):
					campus_lms.quiz_results(campus_lms.EXAM_COURSE)

	def test_a_person_the_lms_has_never_heard_of_is_an_answer_not_a_fault(self):
		"""An applicant has no account over there until an officer makes one,
		and an admitted one is re-filed under their student number -- so asking
		by application number stops resolving the moment they convert. Left
		raising, it put a Frappe validation error on the officer screen for
		every application on the site."""
		with patch.dict(frappe.conf, LIVE):
			with patch("requests.get") as get:
				get.return_value.status_code = 404
				get.return_value.text = "{}"
				self.assertIsNone(campus_lms.quiz_results(campus_lms.EXAM_COURSE, "APP-0001"))
				self.assertIsNone(
					campus_lms.progress("APP-0001", campus_lms.ORIENTATION_COURSE)
				)


class TestAnAdmittedApplicantKeepsTheirAccount(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		suffix = frappe.generate_hash(length=6)
		self.student = make_student(
			f"Admitted {suffix}", email=f"admitted.{suffix}@example.invalid"
		).name

	def test_a_student_made_from_an_application_carries_the_old_key(self):
		"""Over there they are still filed under their application. Without
		this the LMS refuses the address as already linked, and the candidate
		would need a second account -- losing the exam they had already sat."""
		frappe.db.set_value("Student", self.student, "admission_application", "APP-2026-09999")

		payload = campus_lms.person_payload("Student", self.student)

		self.assertEqual(payload["externalId"], self.student)
		self.assertEqual(payload["replacesExternalId"], "APP-2026-09999")

	def test_a_student_who_never_applied_carries_no_old_key(self):
		payload = campus_lms.person_payload("Student", self.student)
		self.assertNotIn("replacesExternalId", payload)


class TestADeletedRegistrationStopsTheEnrolment(FrappeTestCase):
	"""Deleting a registration used to tell the LMS nothing.

	The push fires on `on_update` and `after_insert`, and nothing fired on
	delete -- so a purged or deleted registration left the student with an
	**active** enrolment in a course the registrar no longer knows about. Found
	while clearing TEST COURSE, whose enrolment had to be removed by hand.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.term = make_term(f"TST-TR-{frappe.generate_hash(length=6)}", status="Open").name

	def setUp(self):
		frappe.set_user("Administrator")
		suffix = frappe.generate_hash(length=6)
		self.course = make_course(f"TTR {suffix[:4]}").name
		self.offering = make_offering(self.course, self.term, status="Published").name
		self.student = make_student(
			f"Trash Student {suffix}", email=f"trash.{suffix}@example.invalid"
		).name
		self.enrollment = make_enrollment(self.student).name
		self.registration = frappe.get_doc(
			{
				"doctype": "Course Registration",
				"program_enrollment": self.enrollment,
				"course_offering": self.offering,
				"status": "Registered",
			}
		).insert(ignore_permissions=True).name

	def _cut_the_fee_cycle(self):
		"""Registering raises a Rs 350 fee invoice, and it links back.

		The registration points at the invoice through
		`registration_fee_invoice` and the invoice points back through
		`course_registration`, so neither can be deleted first -- the same
		cycle that refused 21 records when the DEMO data was cleared. One side
		is cut, which is what makes the delete under test possible at all.
		"""
		for inv in frappe.get_all(
			"Fee Invoice", filters={"course_registration": self.registration}, pluck="name"
		):
			frappe.db.set_value(
				"Course Registration",
				self.registration,
				"registration_fee_invoice",
				None,
				update_modified=False,
			)
			frappe.delete_doc("Fee Invoice", inv, ignore_permissions=True)

	def _delete(self):
		"""Delete it with the queue running inline, so the payload is visible."""
		self._cut_the_fee_cycle()
		with patch.dict(frappe.conf, LIVE):
			with patch.object(campus_lms, "_post") as post:
				with patch("frappe.enqueue", side_effect=_inline_enqueue):
					frappe.delete_doc(
						"Course Registration", self.registration, ignore_permissions=True
					)
		return post

	def test_the_enrolment_is_sent_inactive(self):
		post = self._delete()

		calls = [c for c in post.call_args_list if c.args[0] == "/sync/enrollments"]
		self.assertEqual(len(calls), 1, "the deletion said nothing to the LMS")
		sent = calls[0].args[1]
		self.assertEqual(sent["status"], "inactive")
		self.assertEqual(sent["externalId"], self.registration)
		self.assertEqual(sent["personExternalId"], self.student)
		self.assertEqual(sent["courseExternalId"], self.offering)

	def test_it_is_never_a_delete_over_there(self):
		"""The student may have done work on the course, and a withdrawal
		already means inactive -- so a deletion meaning the same thing keeps
		one answer to whether they can still get in."""
		post = self._delete()

		for call in post.call_args_list:
			self.assertNotIn("delete", call.args[0])
			self.assertNotEqual(call.args[1].get("status"), "deactivated")

	def test_the_payload_is_built_before_the_job_runs(self):
		"""A queued job cannot read a row that has gone. `queue` sends a
		doctype and a name and lets `push` read the document, which is right
		for a save and impossible for a delete."""
		captured = {}

		def capture(method, **kwargs):
			if str(method).startswith("sibbcs."):
				captured.update(kwargs)

		self._cut_the_fee_cycle()
		with patch.dict(frappe.conf, LIVE):
			with patch("frappe.enqueue", side_effect=capture):
				frappe.delete_doc(
					"Course Registration", self.registration, ignore_permissions=True
				)

		self.assertIn("payload", captured, "the job was given a name to read, not a payload")
		self.assertEqual(captured["payload"]["externalId"], self.registration)
		self.assertFalse(frappe.db.exists("Course Registration", self.registration))

	def test_nothing_is_sent_when_the_lms_is_not_configured(self):
		self._cut_the_fee_cycle()
		with patch.dict(frappe.conf, {"campus_lms_url": "", "campus_lms_token": ""}):
			with patch("frappe.enqueue") as enqueue:
				frappe.delete_doc(
					"Course Registration", self.registration, ignore_permissions=True
				)
		ours = [c for c in enqueue.call_args_list if _ours(c)]
		self.assertEqual(ours, [], "something was sent with no LMS configured")


class TestADeletedStudentAndOfferingAreReported(FrappeTestCase):
	"""Deleting a Student or a Course Offering told the LMS nothing either.

	Less exposed than the registration case -- Frappe refuses to delete either
	while a registration exists, so the enrolments have already closed -- but
	an account that can still sign in, and a course still published, are both
	left behind.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.term = make_term(f"TST-TS-{frappe.generate_hash(length=6)}", status="Open").name

	def setUp(self):
		frappe.set_user("Administrator")
		suffix = frappe.generate_hash(length=6)
		self.email = f"gone.{suffix}@example.invalid"
		self.student = make_student(f"Gone Student {suffix}", email=self.email).name
		self.course = make_course(f"TTS {suffix[:4]}").name
		self.offering = make_offering(self.course, self.term, status="Published").name

	def _delete(self, doctype, name):
		with patch.dict(frappe.conf, LIVE):
			with patch.object(campus_lms, "_post") as post:
				with patch("frappe.enqueue", side_effect=_inline_enqueue):
					frappe.delete_doc(doctype, name, ignore_permissions=True)
		return post

	def _sent(self, post, path):
		return [c.args[1] for c in post.call_args_list if c.args[0] == path]

	# --- the student -------------------------------------------------------

	def test_a_deleted_student_is_deactivated_over_there(self):
		post = self._delete("Student", self.student)

		sent = self._sent(post, "/sync/people")
		self.assertEqual(len(sent), 1, "the deletion said nothing to the LMS")
		self.assertEqual(sent[0]["status"], "deactivated")
		self.assertEqual(sent[0]["externalId"], self.student)
		self.assertEqual(sent[0]["email"], self.email)

	def test_it_cannot_create_an_account_for_somebody_just_removed(self):
		"""`/sync/people` upserts. Clearing the demo data deleted a seeded
		student with no account over there; without this flag that delete would
		have made them one."""
		post = self._delete("Student", self.student)

		for payload in self._sent(post, "/sync/people"):
			self.assertTrue(payload.get("onlyIfPresent"), payload)

	def test_a_student_with_no_address_says_nothing(self):
		frappe.db.set_value("Student", self.student, {"email": "", "user": ""})
		post = self._delete("Student", self.student)

		self.assertEqual(self._sent(post, "/sync/people"), [])

	# --- the offering -----------------------------------------------------

	def test_a_deleted_offering_is_archived_over_there(self):
		post = self._delete("Course Offering", self.offering)

		sent = self._sent(post, "/sync/courses")
		self.assertEqual(len(sent), 1)
		self.assertEqual(sent[0]["status"], "archived")
		self.assertEqual(sent[0]["externalId"], self.offering)
		self.assertTrue(sent[0].get("onlyIfPresent"))

	def test_archived_and_not_unpublished(self):
		"""Unpublished reads as "not ready yet", which is the opposite of what
		happened to it."""
		post = self._delete("Course Offering", self.offering)

		for payload in self._sent(post, "/sync/courses"):
			self.assertNotEqual(payload["status"], "unpublished")

	def test_nothing_is_sent_when_the_lms_is_not_configured(self):
		with patch.dict(frappe.conf, {"campus_lms_url": "", "campus_lms_token": ""}):
			with patch("frappe.enqueue") as enqueue:
				frappe.delete_doc("Course Offering", self.offering, ignore_permissions=True)
				frappe.delete_doc("Student", self.student, ignore_permissions=True)

		self.assertEqual([c for c in enqueue.call_args_list if _ours(c)], [])


class TestTheCatalogueTravelsWithTheOffering(FrappeTestCase):
	"""The level and the programmes are the Course's, and the LMS only ever
	hears about a course through one of its runs."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.term = make_term(f"TST-CAT-{frappe.generate_hash(length=6)}", status="Open").name

	def setUp(self):
		frappe.set_user("Administrator")
		suffix = frappe.generate_hash(length=6)
		self.course = make_course(f"TCAT {suffix[:4]}", level="2").name
		self.offering = make_offering(self.course, self.term, status="Published").name

	def programs(self, *codes):
		doc = frappe.get_doc("Course", self.course)
		doc.set("programs", [])
		for code in codes:
			doc.append("programs", {"program": code})
		doc.save(ignore_permissions=True)
		return doc

	def test_the_level_comes_from_the_course_not_the_offering(self):
		payload = campus_lms.offering_payload(self.offering)
		self.assertEqual(payload["level"], "2")

	def test_the_programmes_come_across_in_order(self):
		self.programs("MDIV", "GDCS")
		self.assertEqual(campus_lms.offering_payload(self.offering)["programs"], ["MDIV", "GDCS"])

	def test_a_course_counting_towards_nothing_says_so(self):
		"""Sent as empty, never left out -- omitting it would mean the last
		list the LMS saw stood for ever."""
		payload = campus_lms.offering_payload(self.offering)
		self.assertIn("programs", payload)
		self.assertEqual(payload["programs"], [])

	def test_a_corrected_level_reaches_the_offering(self):
		"""Nobody saves an offering when they fix the catalogue."""
		with patch.dict(frappe.conf, LIVE):
			with patch.object(frappe, "enqueue", side_effect=_inline_enqueue) as enqueue:
				with patch.object(campus_lms, "_post") as post:
					doc = frappe.get_doc("Course", self.course)
					doc.level = "3"
					doc.save(ignore_permissions=True)
					self.assertTrue(any(_ours(call) for call in enqueue.call_args_list))
					sent = [c.args[1] for c in post.call_args_list if c.args[0] == "/sync/courses"]
					self.assertTrue(sent, "the run of the course should have been re-sent")
					self.assertEqual(sent[-1]["level"], "3")

	def test_saving_a_course_for_another_reason_sends_nothing(self):
		"""A course is saved for many reasons; most are not the LMS's business."""
		with patch.dict(frappe.conf, LIVE):
			with patch.object(frappe, "enqueue", side_effect=_inline_enqueue) as enqueue:
				doc = frappe.get_doc("Course", self.course)
				doc.description = "Reworded, which the LMS does not mirror."
				doc.save(ignore_permissions=True)
				self.assertFalse([c for c in enqueue.call_args_list if _ours(c)])

	def test_adding_a_programme_counts_as_a_change(self):
		"""`has_value_changed` cannot see this: the rows differ on every save."""
		with patch.dict(frappe.conf, LIVE):
			with patch.object(frappe, "enqueue", side_effect=_inline_enqueue):
				with patch.object(campus_lms, "_post") as post:
					self.programs("MDIV")
					sent = [c.args[1] for c in post.call_args_list if c.args[0] == "/sync/courses"]
					self.assertTrue(sent)
					self.assertEqual(sent[-1]["programs"], ["MDIV"])
