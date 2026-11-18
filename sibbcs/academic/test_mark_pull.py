# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""One test per rule about pulling course results back from Campus LMS Lite.

`course_grades` is mocked throughout. The endpoint has its own tests on the LMS
side; what is worth pinning here is which answers we are willing to act on -- and
above all which ones we refuse, because a wrong figure on a transcript is the
hardest thing in this system to undo.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from sibbcs.academic import mark_pull
from sibbcs.academic.doctype.academic_term.test_academic_term import make_term
from sibbcs.academic.doctype.course.test_course import make_course
from sibbcs.academic.doctype.course_offering.test_course_offering import make_offering
from sibbcs.academic.doctype.program_enrollment.test_program_enrollment import (
	make_enrollment,
	make_student,
)
from sibbcs.academic.gradebook import use_single_component

LIVE = {"campus_lms_url": "https://lms.example.invalid", "campus_lms_token": "t0ken"}


def fresh_offering(term, **kw):
	"""An offering on a course of its own.

	A Course Offering is named `{course}-{term}`, so two offerings of the same
	course in the same term cannot both exist -- every fixture here needs its
	own course or the second insert collides on the primary key.
	"""
	course = make_course(f"TMPX {frappe.generate_hash(length=4)}").name
	return make_offering(course, term, **kw).name


def one_student(registration, percent=72, **over):
	"""What the LMS says about a single student on a finished course."""
	student = {
		"personExternalId": "SIB-TEST-0001",
		"enrollmentExternalId": registration,
		"email": "probe@example.invalid",
		"current": {"earned": percent, "possible": 100, "percent": percent, "letter": None},
		"final": {"earned": percent, "possible": 100, "percent": percent, "letter": None},
		"assignments": 2,
		"posted": 2,
		"awaitingMarking": 0,
		"gradedUnposted": 0,
	}
	student.update(over)
	return {"course": {"externalId": "x"}, "unmanagedStudents": 0, "students": [student]}


class TestMarkPull(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# A term whose dates have passed, which is what makes its offerings
		# askable. Left Active rather than Closed on purpose: a closed term
		# refuses a Published offering, and "ended but not yet closed" is
		# exactly the state in which marks are still coming in.
		cls.ended = make_term(
			f"TST-MP-DONE-{frappe.generate_hash(length=6)}",
			start_date="2026-01-01",
			end_date="2026-02-28",
			status="Active",
		).name

	def setUp(self):
		frappe.set_user("Administrator")
		suffix = frappe.generate_hash(length=6)
		self.course = make_course(f"TMP {suffix[:4]}").name
		self.offering = make_offering(self.course, self.ended, status="Published").name
		# A course taught in the LMS is graded as one bucket; without a scheme a
		# release has nowhere to land and is refused, which is its own test.
		use_single_component(self.offering)
		student = make_student(
			f"Mark Pull {suffix}", email=f"markpull.{suffix}@example.invalid"
		).name
		self.registration = (
			frappe.get_doc(
				{
					"doctype": "Course Registration",
					"program_enrollment": make_enrollment(student).name,
					"course_offering": self.offering,
					"status": "Registered",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def pull(self, answer):
		"""Run the pull with the LMS answering `answer` for every offering."""
		with patch.dict(frappe.conf, LIVE):
			with patch.object(mark_pull.campus_lms, "course_grades", return_value=answer):
				with patch.object(
					mark_pull, "offerings_to_ask_about", return_value=[self.offering]
				):
					return mark_pull.pull_released_marks()

	def reread(self):
		return frappe.get_doc("Course Registration", self.registration)

	# --- the happy path ----------------------------------------------------

	def test_a_finished_course_reaches_the_transcript(self):
		report = self.pull(one_student(self.registration, 72))

		row = self.reread()
		self.assertEqual(row.final_marks, 72)
		self.assertEqual(row.status, "Completed")
		self.assertTrue(row.grade, "a released mark must produce a letter")
		self.assertIn((self.registration, 72.0), report["recorded"])

	def test_the_registration_is_completed_so_it_lands_on_the_transcript(self):
		"""`completed_registrations` filters on Completed; Registered is invisible."""
		from sibbcs.academic.doctype.course_registration.course_registration import (
			completed_registrations,
		)

		enrollment = frappe.db.get_value(
			"Course Registration", self.registration, "program_enrollment"
		)
		self.pull(one_student(self.registration, 65))
		transcript = [r.name for r in completed_registrations(enrollment)]
		self.assertIn(self.registration, transcript)

	def test_a_failing_mark_is_still_completed_and_still_recorded(self):
		"""A fail belongs on a transcript. Routing it to Failed would hide it."""
		self.pull(one_student(self.registration, 31))

		row = self.reread()
		self.assertEqual(row.status, "Completed")
		self.assertEqual(row.final_marks, 31)
		self.assertFalse(row.passed)

	# --- what we refuse to record -----------------------------------------

	def test_a_course_still_being_marked_is_left_alone(self):
		"""The entrance exam's rule, applied to coursework: sat is not marked.

		`final` counts unmarked work as zero, so recording this would tell a
		student they scored 40 on a course half of which nobody has read.
		"""
		report = self.pull(one_student(self.registration, 40, awaitingMarking=1))

		row = self.reread()
		self.assertEqual(row.status, "Registered")
		self.assertFalse(row.final_marks)
		self.assertIn((self.registration, "still being marked"), report["skipped"])

	def test_a_mark_withheld_from_the_student_is_withheld_from_us(self):
		"""Graded and not released is a decision in progress, not a result."""
		report = self.pull(one_student(self.registration, 55, gradedUnposted=1))

		self.assertEqual(self.reread().status, "Registered")
		self.assertIn((self.registration, "marked but not released"), report["skipped"])

	def test_a_course_with_nothing_gradable_is_not_a_zero(self):
		report = self.pull(
			one_student(self.registration, 0, final={"percent": None}, assignments=0, posted=0)
		)

		self.assertEqual(self.reread().status, "Registered")
		self.assertIn((self.registration, "nothing gradable on the course"), report["skipped"])

	def test_a_withdrawal_is_never_walked_back(self):
		"""A withdrawal is a decision made here; a mark must not undo it."""
		frappe.db.set_value(
			"Course Registration", self.registration, "status", "Withdrawn", update_modified=False
		)
		report = self.pull(one_student(self.registration, 88))

		self.assertEqual(self.reread().status, "Withdrawn")
		self.assertIn((self.registration, "registration is Withdrawn"), report["skipped"])

	def test_an_enrolment_made_by_hand_over_there_is_ignored(self):
		"""No registration behind it means no fee, no eligibility check, no mark."""
		report = self.pull(one_student(self.registration, 90, enrollmentExternalId=None))

		self.assertEqual(self.reread().status, "Registered")
		self.assertEqual(report["recorded"], [])

	def test_a_result_for_a_registration_we_do_not_have_is_reported(self):
		report = self.pull(one_student("SIB-9999-MDIV-NOWHERE", 90))

		self.assertIn(("SIB-9999-MDIV-NOWHERE", "no registration here"), report["skipped"])

	# --- running it again --------------------------------------------------

	def test_the_same_result_twice_is_recorded_once(self):
		first = self.pull(one_student(self.registration, 72))
		second = self.pull(one_student(self.registration, 72))

		self.assertEqual(len(first["recorded"]), 1)
		self.assertEqual(second["recorded"], [])
		self.assertEqual(self.reread().final_marks, 72)

	def test_a_corrected_mark_replaces_the_one_on_file(self):
		"""A marker fixing a mistake is the one case where the LMS should win."""
		self.pull(one_student(self.registration, 72))
		report = self.pull(one_student(self.registration, 81))

		self.assertEqual(self.reread().final_marks, 81)
		self.assertIn((self.registration, 81.0), report["recorded"])

	# --- when the other side is unhelpful ----------------------------------

	def test_an_offering_the_lms_has_never_heard_of_is_an_answer_not_a_fault(self):
		report = self.pull(None)

		self.assertEqual(self.reread().status, "Registered")
		self.assertIn((self.offering, "not in the LMS"), report["skipped"])

	def test_nothing_is_asked_until_the_lms_is_configured(self):
		with patch.dict(frappe.conf, {"campus_lms_url": "", "campus_lms_token": ""}):
			with patch.object(mark_pull.campus_lms, "course_grades") as ask:
				report = mark_pull.pull_released_marks()
				ask.assert_not_called()
		self.assertEqual(report["offerings"], 0)

	def test_one_offering_failing_does_not_stop_the_next(self):
		"""A hundred transcripts must not wait on one broken course."""
		other = fresh_offering(self.ended, status="Published")
		use_single_component(other)
		student = make_student(
			f"Second Course {frappe.generate_hash(length=6)}",
			email=f"second.{frappe.generate_hash(length=6)}@example.invalid",
		).name
		elsewhere = (
			frappe.get_doc(
				{
					"doctype": "Course Registration",
					"program_enrollment": make_enrollment(student).name,
					"course_offering": other,
					"status": "Registered",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		answers = {other: one_student(elsewhere, 72)}

		def flaky(offering, *args, **kwargs):
			if offering not in answers:
				raise RuntimeError("the LMS fell over")
			return answers[offering]

		with patch.dict(frappe.conf, LIVE):
			with patch.object(mark_pull.campus_lms, "course_grades", side_effect=flaky):
				with patch.object(
					mark_pull, "offerings_to_ask_about", return_value=[self.offering, other]
				):
					with patch.object(frappe, "log_error"):
						report = mark_pull.pull_released_marks()

		self.assertEqual(report["offerings"], 2)
		self.assertEqual(len(report["recorded"]), 1)
		self.assertTrue(any("error" in reason for _, reason in report["skipped"]))


class TestWhichOfferingsAreAsked(FrappeTestCase):
	"""The registrar decides a course is over; the LMS never could."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		suffix = frappe.generate_hash(length=6)
		cls.ended = make_term(
			f"TST-MPW-DONE-{suffix}", start_date="2026-01-01", end_date="2026-02-28"
		).name
		cls.running = make_term(
			f"TST-MPW-LIVE-{suffix}", start_date="2026-01-01", end_date="2099-12-31", status="Open"
		).name

	def register(self, offering):
		student = make_student(
			f"Asked {frappe.generate_hash(length=6)}",
			email=f"asked.{frappe.generate_hash(length=6)}@example.invalid",
		).name
		return (
			frappe.get_doc(
				{
					"doctype": "Course Registration",
					"program_enrollment": make_enrollment(student).name,
					"course_offering": offering,
					"status": "Registered",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def test_an_offering_whose_term_has_ended_is_asked_about(self):
		offering = fresh_offering(self.ended, status="Published")
		self.register(offering)
		self.assertIn(offering, mark_pull.offerings_to_ask_about(limit=5000))

	def test_an_offering_still_running_is_not(self):
		"""Mid-term, `final` counts work nobody has handed in yet as zero."""
		offering = fresh_offering(self.running, status="Running")
		self.register(offering)
		self.assertNotIn(offering, mark_pull.offerings_to_ask_about(limit=5000))

	def test_marking_an_offering_completed_closes_it_early(self):
		"""The explicit signal, for a term that over-runs its own dates."""
		offering = fresh_offering(self.running, status="Published")
		# Registered first: the rule engine refuses to put anybody onto a
		# Completed offering, which is the whole point of that status.
		self.register(offering)
		frappe.db.set_value(
			"Course Offering", offering, "status", "Completed", update_modified=False
		)
		self.assertIn(offering, mark_pull.offerings_to_ask_about(limit=5000))

	def test_an_offering_nobody_is_registered_on_is_not_asked_about(self):
		offering = fresh_offering(self.ended, status="Published")
		self.assertNotIn(offering, mark_pull.offerings_to_ask_about(limit=5000))

	def test_an_offering_with_only_withdrawals_is_not_asked_about(self):
		offering = fresh_offering(self.ended, status="Published")
		registration = self.register(offering)
		frappe.db.set_value(
			"Course Registration", registration, "status", "Withdrawn", update_modified=False
		)
		self.assertNotIn(offering, mark_pull.offerings_to_ask_about(limit=5000))

	def test_a_draft_offering_is_never_asked_about(self):
		offering = fresh_offering(self.ended, status="Draft")
		self.assertNotIn(offering, mark_pull.offerings_to_ask_about(limit=5000))

	def test_an_offering_whose_marks_are_all_in_ages_ago_is_left_behind(self):
		"""Nothing is coming. Re-reading it for ever would be work for nobody."""
		offering = fresh_offering(self.ended, status="Published")
		registration = self.register(offering)
		frappe.db.set_value(
			"Course Registration", registration, "status", "Completed", update_modified=False
		)
		self.assertNotIn(offering, mark_pull.offerings_to_ask_about(limit=5000))

	def test_a_recorded_result_is_still_re_read_for_a_while(self):
		"""So a marker correcting a mistake still reaches the transcript."""
		recent = make_term(
			f"TST-MPW-NEW-{frappe.generate_hash(length=6)}",
			start_date=add_days(nowdate(), -60),
			end_date=add_days(nowdate(), -10),
			status="Active",
		).name
		offering = fresh_offering(recent, status="Published")
		registration = self.register(offering)
		frappe.db.set_value(
			"Course Registration", registration, "status", "Completed", update_modified=False
		)
		self.assertIn(offering, mark_pull.offerings_to_ask_about(limit=5000))

	def test_an_offering_still_outstanding_is_asked_about_however_old(self):
		"""The window never strands unrecorded work: that failure is silent."""
		ancient = make_term(
			f"TST-MPW-OLD-{frappe.generate_hash(length=6)}",
			start_date="2020-01-01",
			end_date="2020-02-28",
			status="Active",
		).name
		offering = fresh_offering(ancient, status="Published")
		self.register(offering)
		self.assertIn(offering, mark_pull.offerings_to_ask_about(limit=5000))


class TestOneBadRegistration(FrappeTestCase):
	"""A class of thirty must not lose its results to one odd row."""

	def test_a_registration_that_will_not_save_does_not_cost_the_others(self):
		term = make_term(
			f"TST-MPB-{frappe.generate_hash(length=6)}",
			start_date="2026-01-01",
			end_date="2026-02-28",
			status="Active",
		).name
		offering = fresh_offering(term, status="Published")
		use_single_component(offering)

		names = []
		for _ in range(2):
			student = make_student(
				f"Classmate {frappe.generate_hash(length=6)}",
				email=f"classmate.{frappe.generate_hash(length=6)}@example.invalid",
			).name
			names.append(
				frappe.get_doc(
					{
						"doctype": "Course Registration",
						"program_enrollment": make_enrollment(student).name,
						"course_offering": offering,
						"status": "Registered",
					}
				)
				.insert(ignore_permissions=True)
				.name
			)

		answer = one_student(names[0], 70)
		answer["students"].append(one_student(names[1], 55)["students"][0])

		calls = {"n": 0}

		from sibbcs.api import lms_bridge

		# Held before the patch goes on, or calling it back would land on the
		# mock again and recurse.
		genuine = lms_bridge.post_final_mark

		def flaky(registration, percent, **kwargs):
			calls["n"] += 1
			if registration == names[0]:
				raise RuntimeError("this one will not save")
			return genuine(registration, percent, **kwargs)

		with patch.dict(frappe.conf, LIVE):
			with patch.object(mark_pull.campus_lms, "course_grades", return_value=answer):
				with patch.object(mark_pull, "offerings_to_ask_about", return_value=[offering]):
					with patch("sibbcs.api.lms_bridge.post_final_mark", side_effect=flaky):
						with patch.object(frappe, "log_error"):
							report = mark_pull.pull_released_marks()

		self.assertEqual(calls["n"], 2, "it must have gone on to the second student")
		self.assertEqual(
			frappe.db.get_value("Course Registration", names[1], "status"), "Completed"
		)
		self.assertEqual(frappe.db.get_value("Course Registration", names[0], "status"), "Registered")
		self.assertIn((names[0], "could not be recorded -- see the error log"), report["skipped"])
		self.assertIn((names[1], 55.0), report["recorded"])
