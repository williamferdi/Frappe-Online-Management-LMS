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
		self.assertEqual(campus_lms.registration_payload(self.registration)["status"], "active")
		frappe.db.set_value("Course Registration", self.registration, "status", "Withdrawn")
		self.assertEqual(campus_lms.registration_payload(self.registration)["status"], "inactive")

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
