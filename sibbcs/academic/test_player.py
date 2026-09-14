# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""One test per rule the course player rests on.

The one worth most is that the sidebar, the Next button and the percentage all
count the same things — three places disagreeing about how far through you are
is worse than showing no figure at all.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, now_datetime

from sibbcs.academic.doctype.academic_term.test_academic_term import make_term
from sibbcs.academic.doctype.course.test_course import make_course
from sibbcs.academic.doctype.course_offering.test_course_offering import make_offering
from sibbcs.academic.doctype.program_enrollment.test_program_enrollment import (
	make_enrollment,
	make_student,
)
from sibbcs.academic.test_modules import make_item, make_module


def make_step(module, **kw):
	"""An item the player walks past.

	`make_item` defaults to Sub-header, which is furniture and deliberately
	skipped, so a test about sequence or progress has to ask for something
	else. URL is the one item type that needs no other document to point at.
	"""
	kw.setdefault("item_type", "URL")
	kw.setdefault("url", "https://example.invalid/reading")
	return make_item(module, **kw)
from sibbcs.api import player


class TestCoursePlayer(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.term = make_term(
			f"TST-PL-{frappe.generate_hash(length=6)}", status="Open"
		).name

	def setUp(self):
		frappe.set_user("Administrator")
		suffix = frappe.generate_hash(length=6)
		self.offering = make_offering(
			make_course(f"TPL {suffix[:4]}").name, self.term, status="Published"
		).name

		email = f"player.{suffix}@example.invalid"
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": "Player",
					"user_type": "System User",
					"send_welcome_email": 0,
					"roles": [{"role": "Student"}],
				}
			).insert(ignore_permissions=True)
		self.email = email
		self.student = make_student(f"Player {suffix}", user=email).name
		self.registration = frappe.get_doc(
			{
				"doctype": "Course Registration",
				"program_enrollment": make_enrollment(self.student).name,
				"course_offering": self.offering,
				"status": "Registered",
			}
		).insert(ignore_permissions=True).name

		self.module = make_module(self.offering, "Week One").name

	def tearDown(self):
		frappe.set_user("Administrator")

	# --- the sequence ------------------------------------------------------

	def test_the_sequence_skips_furniture(self):
		"""Stepping onto a sub-header and having to press Next again is a
		button that did nothing."""
		make_item(self.module, title="Heading", position=0)
		first = make_step(
			self.module, title="One", position=1, completion_requirement="Mark it done"
		)
		second = make_step(
			self.module, title="Two", position=2, completion_requirement="Mark it done"
		)

		frappe.set_user(self.email)
		data = player.course(self.registration)

		self.assertEqual(data["sequence"], [first.name, second.name])

	def test_an_item_knows_what_sits_either_side(self):
		first = make_step(self.module, title="One", position=0)
		second = make_step(self.module, title="Two", position=1)
		third = make_step(self.module, title="Three", position=2)

		frappe.set_user(self.email)
		middle = player.item(self.registration, second.name)

		self.assertEqual(middle["previous"], first.name)
		self.assertEqual(middle["next"], third.name)
		self.assertEqual(middle["position"], {"index": 2, "total": 3})

	def test_the_ends_of_the_course_have_no_neighbour(self):
		only = make_step(self.module, title="Only", position=0)

		frappe.set_user(self.email)
		data = player.item(self.registration, only.name)

		self.assertIsNone(data["previous"])
		self.assertIsNone(data["next"])

	# --- progress ----------------------------------------------------------

	def test_progress_counts_only_what_the_course_asks_for(self):
		"""An item requiring nothing is not something a student can fail to
		do, so it does not belong in the denominator."""
		make_step(self.module, title="Just reading", position=0)
		asked = make_step(
			self.module, title="Do this", position=1, completion_requirement="Mark it done"
		)

		frappe.set_user(self.email)
		before = player.course(self.registration)["progress"]
		self.assertEqual(before, {"done": 0, "total": 1, "percent": 0})

		from sibbcs.academic import modules

		frappe.set_user("Administrator")
		modules.record_progress(asked.name, self.registration)

		frappe.set_user(self.email)
		after = player.course(self.registration)["progress"]
		self.assertEqual(after, {"done": 1, "total": 1, "percent": 100})

	def test_a_course_that_asks_nothing_shows_no_percentage(self):
		"""Rather than a permanent 100%, which says the student is finished."""
		make_step(self.module, title="Just reading", position=0)

		frappe.set_user(self.email)
		self.assertIsNone(player.course(self.registration)["progress"]["percent"])

	# --- opening -----------------------------------------------------------

	def test_opening_a_view_item_completes_it(self):
		item = make_step(self.module, title="Read me", completion_requirement="View it")

		frappe.set_user(self.email)
		player.item(self.registration, item.name)

		data = player.course(self.registration)
		self.assertEqual(data["progress"]["done"], 1)

	def _assignment_item(self, published):
		from sibbcs.academic.test_gradebook import make_assignment, make_scheme

		make_scheme(self.offering, [{"component": "Assignment", "weight_pct": 100}])
		essay = make_assignment(
			self.offering,
			title="Essay",
			published=published,
			description="<p>1500 words on Romans 8.</p>",
		).name
		return make_item(
			self.module,
			item_type="Assignment",
			assignment=essay,
			title="Essay",
			course_offering=self.offering,
		)

	def test_an_assignment_opens_with_its_brief(self):
		item = self._assignment_item(published=1)

		frappe.set_user(self.email)
		content = player.item(self.registration, item.name)["content"]

		self.assertEqual(content["description"], "<p>1500 words on Romans 8.</p>")
		self.assertNotIn("published", content)

	def test_an_unpublished_assignment_shows_nothing_in_the_player(self):
		"""A module item can be published while the work it points at is not.
		The coursework list and hand-in already hid it; the player handed its
		brief to anyone who opened the item."""
		item = self._assignment_item(published=0)

		frappe.set_user(self.email)
		self.assertIsNone(player.item(self.registration, item.name)["content"])

	def test_a_locked_item_cannot_be_opened(self):
		locked_module = make_module(
			self.offering, "Later", unlock_at=add_days(now_datetime(), 7)
		).name
		item = make_step(locked_module, title="Locked")

		frappe.set_user(self.email)
		with self.assertRaises(frappe.PermissionError):
			player.item(self.registration, item.name)

	def test_an_item_from_another_course_is_refused(self):
		other = make_offering(
			make_course(f"TPL X{frappe.generate_hash(length=4)}").name,
			self.term,
			status="Published",
		).name
		theirs = make_step(make_module(other, "Theirs").name, title="Not mine")

		frappe.set_user(self.email)
		with self.assertRaises(frappe.PermissionError):
			player.item(self.registration, theirs.name)

	def test_somebody_elses_course_is_refused(self):
		other = make_student(f"Another {frappe.generate_hash(length=6)}").name
		theirs = frappe.get_doc(
			{
				"doctype": "Course Registration",
				"program_enrollment": make_enrollment(other).name,
				"course_offering": self.offering,
				"status": "Registered",
			}
		).insert(ignore_permissions=True).name

		frappe.set_user(self.email)
		with self.assertRaises(frappe.PermissionError):
			player.course(theirs)

	# --- notes and bookmarks ------------------------------------------------

	def test_a_note_is_kept_and_comes_back(self):
		item = make_step(self.module, title="Read me")

		frappe.set_user(self.email)
		player.save_note(self.registration, item.name, "This bit is hard")

		data = player.item(self.registration, item.name)
		self.assertEqual(data["note"]["body"], "This bit is hard")

	def test_saving_a_note_twice_keeps_one_row(self):
		item = make_step(self.module, title="Read me")

		frappe.set_user(self.email)
		player.save_note(self.registration, item.name, "First")
		player.save_note(self.registration, item.name, "Second")

		frappe.set_user("Administrator")
		self.assertEqual(
			frappe.db.count(
				"Lesson Note",
				{"course_registration": self.registration, "module_item": item.name},
			),
			1,
		)

	def test_a_bookmark_toggles(self):
		item = make_step(self.module, title="Read me")

		frappe.set_user(self.email)
		self.assertEqual(player.toggle_bookmark(self.registration, item.name)["bookmarked"], 1)
		self.assertEqual(player.toggle_bookmark(self.registration, item.name)["bookmarked"], 0)

	def test_a_note_is_not_somebody_elses_to_write(self):
		item = make_step(self.module, title="Read me")
		other = make_student(f"Another {frappe.generate_hash(length=6)}").name
		theirs = frappe.get_doc(
			{
				"doctype": "Course Registration",
				"program_enrollment": make_enrollment(other).name,
				"course_offering": self.offering,
				"status": "Registered",
			}
		).insert(ignore_permissions=True).name

		frappe.set_user(self.email)
		with self.assertRaises(frappe.PermissionError):
			player.save_note(theirs, item.name, "Not mine to write")

	def test_the_sidebar_shows_which_items_are_annotated(self):
		item = make_step(self.module, title="Read me")

		frappe.set_user(self.email)
		player.save_note(self.registration, item.name, "A note")
		player.toggle_bookmark(self.registration, item.name)

		data = player.course(self.registration)
		row = data["modules"][0]["items"][0]
		self.assertTrue(row["has_note"])
		self.assertTrue(row["bookmarked"])

	# --- the lesson's own thread -------------------------------------------

	def test_a_thread_is_made_on_the_first_thing_anybody_says(self):
		"""Not up front: a topic per item on every course would be thousands
		of empty threads, and an empty thread reads as a room nobody came to."""
		from sibbcs.api import comms

		item = make_step(self.module, title="Read me")

		frappe.set_user(self.email)
		self.assertIsNone(comms.lesson_discussion(item.name)["topic"])

		comms.post_lesson_reply(item.name, "What does verse 14 mean?")
		thread = comms.lesson_discussion(item.name)

		self.assertIsNotNone(thread["topic"])
		self.assertEqual(len(thread["replies"]), 1)

	def test_a_thread_hangs_off_the_item_not_the_course(self):
		"""A question about one lesson buried in a course-wide thread is a
		question nobody finds again."""
		from sibbcs.api import comms

		first = make_step(self.module, title="One", position=0)
		second = make_step(self.module, title="Two", position=1)

		frappe.set_user(self.email)
		comms.post_lesson_reply(first.name, "About the first")

		self.assertEqual(len(comms.lesson_discussion(first.name)["replies"]), 1)
		self.assertEqual(comms.lesson_discussion(second.name)["replies"], [])

	def test_a_locked_lessons_thread_is_locked_with_it(self):
		"""Otherwise the thread is a way to read about a lesson you cannot
		open -- the lock working everywhere except where somebody would look."""
		from sibbcs.api import comms

		later = make_module(
			self.offering, "Later", unlock_at=add_days(now_datetime(), 7)
		).name
		item = make_step(later, title="Locked")

		frappe.set_user(self.email)
		with self.assertRaises(frappe.PermissionError):
			comms.lesson_discussion(item.name)
		with self.assertRaises(frappe.PermissionError):
			comms.post_lesson_reply(item.name, "Sneaking a look")

	def test_a_student_on_another_course_is_kept_out(self):
		from sibbcs.api import comms

		item = make_step(self.module, title="Read me")

		other_email = f"outsider.{frappe.generate_hash(length=6)}@example.invalid"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": other_email,
				"first_name": "Outsider",
				"user_type": "System User",
				"send_welcome_email": 0,
				"roles": [{"role": "Student"}],
			}
		).insert(ignore_permissions=True)
		outsider = make_student(
			f"Outsider {frappe.generate_hash(length=5)}", user=other_email
		).name
		make_enrollment(outsider)

		frappe.set_user(other_email)
		with self.assertRaises(frappe.PermissionError):
			comms.lesson_discussion(item.name)

	def test_a_teacher_is_in_the_room(self):
		"""A lesson question with no teacher in it is a suggestion box."""
		from sibbcs.academic.doctype.course_offering.test_course_offering import (
			make_instructor,
		)
		from sibbcs.api import comms

		item = make_step(self.module, title="Read me")

		suffix = frappe.generate_hash(length=6)
		teacher = f"teacher.{suffix}@example.invalid"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": teacher,
				"first_name": "Teacher",
				"user_type": "System User",
				"send_welcome_email": 0,
				"roles": [{"role": "Faculty"}],
			}
		).insert(ignore_permissions=True)
		instructor = make_instructor(f"Teacher {suffix}", user=teacher).name
		frappe.db.set_value("Course Offering", self.offering, "instructor", instructor)

		frappe.set_user(teacher)
		comms.post_lesson_reply(item.name, "Verse 14 is about the covenant.")

		frappe.set_user(self.email)
		replies = comms.lesson_discussion(item.name)["replies"]
		self.assertEqual(len(replies), 1)
		self.assertTrue(
			replies[0]["from_staff"],
			"an answer from whoever teaches the course is marked as such",
		)

	def test_an_empty_reply_is_refused(self):
		from sibbcs.api import comms

		item = make_step(self.module, title="Read me")

		frappe.set_user(self.email)
		with self.assertRaises(frappe.ValidationError):
			comms.post_lesson_reply(item.name, "   ")

	def test_a_teacher_cannot_read_a_students_notes(self):
		"""A note is where somebody writes "I don't understand this", and a
		teacher who can read that changes what students write."""
		self.assertNotIn(
			"Lesson Note",
			[row["doctype"] for row in _perm_rows()],
			"no role but System Manager should hold Lesson Note",
		)


def _perm_rows():
	return frappe.get_all(
		"Custom DocPerm", filters={"parent": "Lesson Note"}, fields=["parent as doctype"]
	) + [
		{"doctype": row.parent}
		for row in frappe.get_all(
			"DocPerm",
			filters={"parent": "Lesson Note", "role": ("!=", "System Manager")},
			fields=["parent"],
		)
	]
