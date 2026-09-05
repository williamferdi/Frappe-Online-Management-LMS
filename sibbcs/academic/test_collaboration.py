# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""One test per rule about groups, differentiated dates, discussions and
peer review.

The rule worth most here is that an override changes dates and nothing else,
and that it reaches every place a date is decided from -- what a student sees,
what counts as late, and whether a quiz will open.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, now_datetime

from sibbcs.academic import overrides
from sibbcs.academic.doctype.academic_term.test_academic_term import make_term
from sibbcs.academic.doctype.course.test_course import make_course
from sibbcs.academic.doctype.course_offering.test_course_offering import make_offering
from sibbcs.academic.doctype.program_enrollment.test_program_enrollment import (
	make_enrollment,
	make_student,
)
from sibbcs.academic.test_gradebook import make_assignment, make_scheme
from sibbcs.api import collaboration, comms, coursework


class TestCollaboration(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.term = make_term(
			f"TST-CO-{frappe.generate_hash(length=6)}", status="Open"
		).name

	def setUp(self):
		frappe.set_user("Administrator")
		suffix = frappe.generate_hash(length=6)
		self.course = make_course(f"TCO {suffix[:4]}").name
		self.offering = make_offering(self.course, self.term, status="Published").name
		make_scheme(self.offering, [{"component": "Assignment", "weight_pct": 100}])
		self.assignment = make_assignment(
			self.offering,
			title=f"Essay {suffix[:4]}",
			points_possible=20,
			published=1,
			due_date=add_days(now_datetime(), -2),
			late_policy="Accept with penalty",
			late_penalty_pct_per_day=10,
		).name

		self.email, self.registration = self._enrol(f"co.{suffix}")
		self.other_email, self.other_registration = self._enrol(f"co2.{suffix}")

	def tearDown(self):
		frappe.set_user("Administrator")

	def _enrol(self, tag):
		email = f"{tag}@example.invalid"
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": "Collab",
					"user_type": "System User",
					"send_welcome_email": 0,
					"roles": [{"role": "Student"}],
				}
			).insert(ignore_permissions=True)
		student = make_student(f"Collab {tag}", user=email).name
		registration = frappe.get_doc(
			{
				"doctype": "Course Registration",
				"program_enrollment": make_enrollment(student).name,
				"course_offering": self.offering,
				"status": "Registered",
			}
		).insert(ignore_permissions=True).name
		return email, registration

	def _group_set(self, **kw):
		return frappe.get_doc(
			{
				"doctype": "Course Group Set",
				"course_offering": self.offering,
				"title": kw.pop("title", "Seminar groups"),
				**kw,
			}
		).insert(ignore_permissions=True)

	def _group(self, group_set, members, title="Group A"):
		return frappe.get_doc(
			{
				"doctype": "Course Group",
				"group_set": group_set,
				"title": title,
				"members": [{"course_registration": name} for name in members],
			}
		).insert(ignore_permissions=True)

	# --- groups ------------------------------------------------------------

	def test_a_group_holds_students_from_its_own_course(self):
		other_offering = make_offering(
			make_course(f"TCO X{frappe.generate_hash(length=4)}").name,
			self.term,
			status="Published",
		).name
		stranger = frappe.get_doc(
			{
				"doctype": "Course Registration",
				"program_enrollment": make_enrollment(
					make_student(f"Stranger {frappe.generate_hash(length=5)}").name
				).name,
				"course_offering": other_offering,
				"status": "Registered",
			}
		).insert(ignore_permissions=True).name

		group_set = self._group_set().name
		with self.assertRaises(frappe.ValidationError):
			self._group(group_set, [stranger])

	def test_a_group_set_is_a_partition_not_a_set_of_clubs(self):
		"""Two groups in one set both holding a student would make a
		differentiated date depend on which was read first."""
		group_set = self._group_set().name
		self._group(group_set, [self.registration], title="A")

		with self.assertRaises(frappe.ValidationError):
			self._group(group_set, [self.registration], title="B")

	def test_the_same_student_may_be_in_two_different_sets(self):
		first = self._group_set(title="Seminar").name
		second = self._group_set(title="Projects").name

		self._group(first, [self.registration], title="A")
		group = self._group(second, [self.registration], title="Alpha")

		self.assertTrue(group.name)

	def test_a_group_cannot_exceed_the_set_limit(self):
		group_set = self._group_set(group_limit=1).name

		with self.assertRaises(frappe.ValidationError):
			self._group(group_set, [self.registration, self.other_registration])

	def test_nobody_is_listed_twice(self):
		group_set = self._group_set().name
		with self.assertRaises(frappe.ValidationError):
			self._group(group_set, [self.registration, self.registration])

	# --- differentiated dates ---------------------------------------------

	def _override(self, **kw):
		values = {
			"doctype": "Assignment Override",
			"assignment": self.assignment,
			**kw,
		}
		return frappe.get_doc(values).insert(ignore_permissions=True)

	def test_an_override_needs_a_target_and_only_one(self):
		with self.assertRaises(frappe.ValidationError):
			self._override(due_date=now_datetime())

		group_set = self._group_set().name
		group = self._group(group_set, [self.registration]).name
		with self.assertRaises(frappe.ValidationError):
			self._override(
				course_registration=self.registration,
				course_group=group,
				due_date=now_datetime(),
			)

	def test_an_override_needs_at_least_one_date(self):
		with self.assertRaises(frappe.ValidationError):
			self._override(course_registration=self.registration, reason="No dates")

	def test_an_override_for_somebody_on_another_course_is_refused(self):
		other_offering = make_offering(
			make_course(f"TCO Y{frappe.generate_hash(length=4)}").name,
			self.term,
			status="Published",
		).name
		stranger = frappe.get_doc(
			{
				"doctype": "Course Registration",
				"program_enrollment": make_enrollment(
					make_student(f"Elsewhere {frappe.generate_hash(length=5)}").name
				).name,
				"course_offering": other_offering,
				"status": "Registered",
			}
		).insert(ignore_permissions=True).name

		with self.assertRaises(frappe.ValidationError):
			self._override(course_registration=stranger, due_date=now_datetime())

	def test_an_extension_changes_what_the_student_sees(self):
		later = add_days(now_datetime(), 7)
		self._override(course_registration=self.registration, due_date=later)

		frappe.set_user(self.email)
		row = coursework.coursework(self.registration)["rows"][0]

		self.assertTrue(row["open"]["open"])
		self.assertIsNone(row["open"]["reason"], "not late any more")

	def test_an_extension_stops_the_work_counting_as_late(self):
		"""The penalty is computed from days late, so an extension that did not
		reach this would deduct marks from work handed in on time."""
		later = add_days(now_datetime(), 7)
		self._override(course_registration=self.registration, due_date=later)

		submission = frappe.get_doc(
			{
				"doctype": "Assignment Submission",
				"assignment": self.assignment,
				"course_registration": self.registration,
				"status": "Submitted",
				"submitted_on": now_datetime(),
			}
		).insert(ignore_permissions=True)

		self.assertEqual(submission.late_days, 0)

	def test_a_student_without_the_extension_is_still_late(self):
		self._override(
			course_registration=self.registration, due_date=add_days(now_datetime(), 7)
		)

		submission = frappe.get_doc(
			{
				"doctype": "Assignment Submission",
				"assignment": self.assignment,
				"course_registration": self.other_registration,
				"status": "Submitted",
				"submitted_on": now_datetime(),
			}
		).insert(ignore_permissions=True)

		self.assertGreater(submission.late_days, 0)

	def test_a_group_override_reaches_its_members(self):
		group_set = self._group_set().name
		group = self._group(group_set, [self.registration]).name
		later = add_days(now_datetime(), 5)

		self._override(course_group=group, due_date=later)

		self.assertEqual(
			overrides.due_for(self.assignment, self.registration), later
		)
		self.assertIsNotNone(
			overrides.due_for(self.assignment, self.other_registration)
		)

	def test_a_students_own_override_beats_their_groups(self):
		"""It was set with them in mind."""
		group_set = self._group_set().name
		group = self._group(group_set, [self.registration]).name

		self._override(course_group=group, due_date=add_days(now_datetime(), 5))
		mine = add_days(now_datetime(), 10)
		self._override(course_registration=self.registration, due_date=mine)

		self.assertEqual(overrides.due_for(self.assignment, self.registration), mine)

	def test_an_override_that_says_nothing_about_a_date_leaves_it_alone(self):
		original = frappe.db.get_value("Course Assignment", self.assignment, "due_date")
		self._override(
			course_registration=self.registration,
			available_until=add_days(now_datetime(), 20),
		)

		self.assertEqual(
			overrides.due_for(self.assignment, self.registration), original
		)

	# --- graded discussions ------------------------------------------------

	def test_publishing_a_discussion_opens_a_room(self):
		"""The room is Frappe's own Discussion Topic against the offering --
		the same rooms comms.discussion_topics already lists."""
		result = collaboration.save_discussion(
			self.offering, {"title": "Week one reading", "published": 1, "min_posts": 1}
		)

		self.assertTrue(result["topic"])
		reference = frappe.db.get_value(
			"Discussion Topic",
			result["topic"],
			["reference_doctype", "reference_docname"],
			as_dict=True,
		)
		self.assertEqual(reference.reference_doctype, "Course Offering")
		self.assertEqual(reference.reference_docname, self.offering)

	def test_an_unpublished_discussion_opens_no_room(self):
		result = collaboration.save_discussion(
			self.offering, {"title": "Draft", "published": 0}
		)
		self.assertIsNone(result["topic"])

	def test_taking_part_enough_puts_a_student_in_the_marking_queue(self):
		"""A graded discussion is still marked by a person. What this does is
		stop participation being something a teacher has to go looking for."""
		created = collaboration.save_discussion(
			self.offering,
			{
				"title": "Graded thread",
				"published": 1,
				"min_posts": 1,
				"assignment": self.assignment,
			},
		)

		frappe.set_user(self.email)
		comms.post_reply(created["topic"], "My reading of it")
		result = collaboration.record_participation(self.registration, created["discussion"])

		self.assertTrue(result["enough"])
		self.assertTrue(result["submission"])

		frappe.set_user("Administrator")
		submission = frappe.get_doc("Assignment Submission", result["submission"])
		self.assertEqual(submission.status, "Submitted")
		self.assertFalse(submission.scored, "a person still marks it")

	def test_not_taking_part_enough_submits_nothing(self):
		created = collaboration.save_discussion(
			self.offering,
			{
				"title": "Graded thread",
				"published": 1,
				"min_posts": 3,
				"assignment": self.assignment,
			},
		)

		frappe.set_user(self.email)
		comms.post_reply(created["topic"], "One post only")
		result = collaboration.record_participation(self.registration, created["discussion"])

		self.assertFalse(result["enough"])
		self.assertIsNone(result["submission"])

	def test_participation_counts_every_student_on_the_roster(self):
		created = collaboration.save_discussion(
			self.offering, {"title": "Open thread", "published": 1, "min_posts": 1}
		)

		frappe.set_user(self.email)
		comms.post_reply(created["topic"], "Here")

		frappe.set_user("Administrator")
		data = collaboration.participation(created["discussion"])

		self.assertEqual(len(data["rows"]), 2)
		spoke = [row for row in data["rows"] if row["posts"] > 0]
		self.assertEqual(len(spoke), 1)

	# --- peer review -------------------------------------------------------

	def _submit_both(self):
		for registration in (self.registration, self.other_registration):
			frappe.get_doc(
				{
					"doctype": "Assignment Submission",
					"assignment": self.assignment,
					"course_registration": registration,
					"status": "Submitted",
					"submitted_on": now_datetime(),
					"body": f"Work by {registration}",
				}
			).insert(ignore_permissions=True)

	def test_reviews_are_assigned_without_anybody_reviewing_themselves(self):
		self._submit_both()

		result = collaboration.assign_reviews(self.assignment, per_submission=1)

		self.assertEqual(result["assigned"], 2)
		for review in frappe.get_all(
			"Peer Review",
			filters={"assignment": self.assignment},
			fields=["submission", "reviewer"],
		):
			author = frappe.db.get_value(
				"Assignment Submission", review.submission, "course_registration"
			)
			self.assertNotEqual(review.reviewer, author)

	def test_assigning_twice_does_not_double_the_work(self):
		self._submit_both()
		collaboration.assign_reviews(self.assignment, per_submission=1)
		again = collaboration.assign_reviews(self.assignment, per_submission=1)

		self.assertEqual(again["assigned"], 0)

	def test_one_submission_cannot_be_peer_reviewed(self):
		frappe.get_doc(
			{
				"doctype": "Assignment Submission",
				"assignment": self.assignment,
				"course_registration": self.registration,
				"status": "Submitted",
				"submitted_on": now_datetime(),
			}
		).insert(ignore_permissions=True)

		with self.assertRaises(frappe.ValidationError):
			collaboration.assign_reviews(self.assignment)

	def test_a_reviewer_sees_the_work_and_not_the_author(self):
		"""A review is about the work."""
		self._submit_both()
		collaboration.assign_reviews(self.assignment, per_submission=1)

		frappe.set_user(self.email)
		rows = collaboration.my_reviews(self.registration)["rows"]

		self.assertEqual(len(rows), 1)
		self.assertIn("body", rows[0])
		self.assertNotIn("student_name", rows[0])
		self.assertNotIn("course_registration", rows[0])

	def test_a_review_is_not_somebody_elses_to_submit(self):
		self._submit_both()
		collaboration.assign_reviews(self.assignment, per_submission=1)

		mine = frappe.get_all(
			"Peer Review",
			filters={"assignment": self.assignment, "reviewer": self.other_registration},
			pluck="name",
		)[0]

		frappe.set_user(self.email)
		with self.assertRaises(frappe.PermissionError):
			collaboration.submit_review(self.registration, mine, "Not mine to write")

	# --- announcements, which already worked -------------------------------

	def test_a_course_announcement_reaches_its_own_students_only(self):
		"""Announcement.audience has had "Course Offering" all along, and
		comms handles it. This pins it rather than rebuilding it."""
		frappe.get_doc(
			{
				"doctype": "Announcement",
				"title": "Seminar moved",
				"body": "<p>To Thursday.</p>",
				"audience": "Course Offering",
				"course_offering": self.offering,
				"published": 1,
				"publish_on": now_datetime(),
			}
		).insert(ignore_permissions=True)

		frappe.set_user(self.email)
		mine = [row["title"] for row in comms.announcements()["rows"]]
		self.assertIn("Seminar moved", mine)

		# Somebody on another course does not get it.
		other_offering = make_offering(
			make_course(f"TCO Z{frappe.generate_hash(length=4)}").name,
			self.term,
			status="Published",
		).name
		frappe.set_user("Administrator")
		outsider_email = f"outsider.{frappe.generate_hash(length=6)}@example.invalid"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": outsider_email,
				"first_name": "Outsider",
				"user_type": "System User",
				"send_welcome_email": 0,
				"roles": [{"role": "Student"}],
			}
		).insert(ignore_permissions=True)
		outsider = make_student(f"Outsider {frappe.generate_hash(length=5)}", user=outsider_email).name
		frappe.get_doc(
			{
				"doctype": "Course Registration",
				"program_enrollment": make_enrollment(outsider).name,
				"course_offering": other_offering,
				"status": "Registered",
			}
		).insert(ignore_permissions=True)

		frappe.set_user(outsider_email)
		theirs = [row["title"] for row in comms.announcements()["rows"]]
		self.assertNotIn("Seminar moved", theirs)
