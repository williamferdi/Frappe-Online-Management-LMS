# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""Announcements, the Inbox, discussions, To Do and the Calendar.

The interesting question in this module is not what a student can see. It is
what they cannot: a notice addressed to another cohort, a conversation they are
not part of, a discussion room for a course they never registered on.
"""

import inspect

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, now_datetime, today

from sibbcs.api import agenda, comms
from sibbcs.api.test_student_api import make_student


def make_announcement(**overrides):
	values = {
		"doctype": "Announcement",
		"title": "Notice",
		"body": "<p>Body</p>",
		"category": "General",
		"audience": "All Students",
		"published": 1,
		"publish_on": now_datetime(),
	}
	values.update(overrides)
	return frappe.get_doc(values).insert(ignore_permissions=True)


class TestAnnouncementAudience(FrappeTestCase):
	"""A notice for one cohort must never be fetched for another."""

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_everyone_sees_an_all_students_notice(self):
		notice = make_announcement(title="Chapel times")
		_, _, email = make_student()
		frappe.set_user(email)

		titles = [row["name"] for row in comms.announcements()["rows"]]
		self.assertIn(notice.name, titles)

	def test_a_programme_notice_reaches_only_that_programme(self):
		mine = make_announcement(title="MDiv only", audience="Programme", program="MDIV")
		theirs = make_announcement(title="MACS only", audience="Programme", program="MACS")

		_, _, email = make_student()  # enrolled on MDIV
		frappe.set_user(email)

		names = [row["name"] for row in comms.announcements()["rows"]]
		self.assertIn(mine.name, names)
		self.assertNotIn(theirs.name, names)

	def test_a_level_notice_reaches_only_that_level(self):
		level_one = make_announcement(title="Level 1", audience="Level", level="1")
		level_four = make_announcement(title="Level 4", audience="Level", level="4")

		_, _, email = make_student()  # current_level 1
		frappe.set_user(email)

		names = [row["name"] for row in comms.announcements()["rows"]]
		self.assertIn(level_one.name, names)
		self.assertNotIn(level_four.name, names)

	def test_an_unpublished_notice_reaches_nobody(self):
		draft = make_announcement(title="Draft", published=0)
		_, _, email = make_student()
		frappe.set_user(email)

		self.assertNotIn(draft.name, [row["name"] for row in comms.announcements()["rows"]])

	def test_a_notice_dated_in_the_future_waits(self):
		later = make_announcement(title="Later", publish_on=add_days(today(), 5))
		_, _, email = make_student()
		frappe.set_user(email)

		self.assertNotIn(later.name, [row["name"] for row in comms.announcements()["rows"]])

	def test_an_expired_notice_drops_off(self):
		gone = make_announcement(
			title="Expired",
			publish_on=add_days(today(), -10),
			expires_on=add_days(today(), -1),
		)
		_, _, email = make_student()
		frappe.set_user(email)

		self.assertNotIn(gone.name, [row["name"] for row in comms.announcements()["rows"]])

	def test_an_unknown_audience_reaches_nobody(self):
		"""A future audience type must fail closed. Defaulting to 'show it' is
		how a notice for one course ends up on every student's screen."""
		notice = make_announcement(title="Odd")
		frappe.db.set_value("Announcement", notice.name, "audience", "Some New Audience")

		_, _, email = make_student()
		frappe.set_user(email)
		self.assertNotIn(notice.name, [row["name"] for row in comms.announcements()["rows"]])

	def test_marking_someone_elses_notice_read_is_refused(self):
		theirs = make_announcement(title="MACS only", audience="Programme", program="MACS")
		_, _, email = make_student()
		frappe.set_user(email)

		with self.assertRaises(frappe.PermissionError):
			comms.mark_announcement_read(theirs.name)

	def test_marking_read_is_idempotent(self):
		notice = make_announcement(title="Read twice")
		_, _, email = make_student()
		frappe.set_user(email)

		comms.mark_announcement_read(notice.name)
		comms.mark_announcement_read(notice.name)

		self.assertEqual(
			frappe.db.count("Announcement Read", {"announcement": notice.name, "user": email}),
			1,
		)

	def test_read_state_is_per_student(self):
		notice = make_announcement(title="Shared")
		_, _, mine = make_student()
		_, _, theirs = make_student()

		def flag_for(user):
			"""Read state of this notice, not the global unread count --
			other tests leave their own announcements behind, and inserting a
			User commits, so those outlive the test that made them."""
			frappe.set_user(user)
			row = next(
				r for r in comms.announcements()["rows"] if r["name"] == notice.name
			)
			return row["read"]

		frappe.set_user(mine)
		comms.mark_announcement_read(notice.name)

		self.assertTrue(flag_for(mine))
		self.assertFalse(flag_for(theirs))


class TestInbox(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_a_student_cannot_name_recipients(self):
		"""Without this the portal becomes a way to message every account on
		the site. A new message goes to the office; a reply goes to whoever is
		already on the thread."""
		parameters = list(inspect.signature(comms.send_message).parameters)
		self.assertEqual(parameters, ["subject", "body", "reply_to"])

	def test_a_conversation_the_user_is_not_on_is_not_found(self):
		_, _, mine = make_student()
		_, _, theirs = make_student()

		message = frappe.get_doc(
			{
				"doctype": "Portal Message",
				"subject": "Private",
				"body": "<p>Not for you</p>",
				"sender": "Administrator",
				"sent_on": now_datetime(),
				"recipients": [{"recipient": theirs}],
			}
		).insert(ignore_permissions=True)

		frappe.set_user(mine)
		with self.assertRaises(frappe.PermissionError):
			comms.thread(message.name)
		self.assertEqual(comms.inbox()["threads"], [])

	def test_a_recipient_sees_the_conversation(self):
		_, _, email = make_student()
		message = frappe.get_doc(
			{
				"doctype": "Portal Message",
				"subject": "Your enrolment",
				"body": "<p>Welcome</p>",
				"sender": "Administrator",
				"sent_on": now_datetime(),
				"recipients": [{"recipient": email}],
			}
		).insert(ignore_permissions=True)

		frappe.set_user(email)
		inbox = comms.inbox()
		self.assertEqual(len(inbox["threads"]), 1)
		self.assertEqual(inbox["unread"], 1)

		opened = comms.thread(message.name)
		self.assertEqual(len(opened["messages"]), 1)

	def test_opening_a_conversation_marks_it_read(self):
		_, _, email = make_student()
		message = frappe.get_doc(
			{
				"doctype": "Portal Message",
				"subject": "Read me",
				"body": "<p>Body</p>",
				"sender": "Administrator",
				"sent_on": now_datetime(),
				"recipients": [{"recipient": email}],
			}
		).insert(ignore_permissions=True)

		frappe.set_user(email)
		self.assertEqual(comms.inbox()["unread"], 1)
		comms.thread(message.name)
		self.assertEqual(comms.inbox()["unread"], 0)

	def test_a_reply_joins_the_same_thread(self):
		_, _, email = make_student()
		root = frappe.get_doc(
			{
				"doctype": "Portal Message",
				"subject": "Question",
				"body": "<p>Ask</p>",
				"sender": "Administrator",
				"sent_on": now_datetime(),
				"recipients": [{"recipient": email}],
			}
		).insert(ignore_permissions=True)

		frappe.set_user(email)
		result = comms.send_message(body="<p>Answer</p>", reply_to=root.name)
		self.assertEqual(result["thread"], root.name)

		opened = comms.thread(root.name)
		self.assertEqual(len(opened["messages"]), 2)
		# The reply reaches whoever was already on the conversation.
		self.assertIn(
			"Administrator",
			frappe.get_all(
				"Portal Message Recipient",
				filters={"parent": result["message"]},
				pluck="recipient",
			),
		)

	def test_replying_to_a_stranger_thread_is_refused(self):
		_, _, mine = make_student()
		_, _, theirs = make_student()
		root = frappe.get_doc(
			{
				"doctype": "Portal Message",
				"subject": "Private",
				"body": "<p>Body</p>",
				"sender": "Administrator",
				"sent_on": now_datetime(),
				"recipients": [{"recipient": theirs}],
			}
		).insert(ignore_permissions=True)

		frappe.set_user(mine)
		with self.assertRaises(frappe.PermissionError):
			comms.send_message(body="<p>Butting in</p>", reply_to=root.name)

	def test_an_empty_message_is_refused(self):
		_, _, email = make_student()
		frappe.set_user(email)
		with self.assertRaises(frappe.ValidationError):
			comms.send_message(subject="Hello", body="   ")


class TestDiscussions(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_a_room_needs_a_registration(self):
		"""Course Offering names are guessable, so the room is checked against
		what the student is actually registered on."""
		_, _, email = make_student()
		frappe.set_user(email)

		offering = frappe.get_all("Course Offering", limit=1, pluck="name")
		if not offering:
			self.skipTest("no offerings on this site")

		with self.assertRaises(frappe.PermissionError):
			comms.discussion_topics(offering[0])
		with self.assertRaises(frappe.PermissionError):
			comms.post_topic(offering[0], "Sneaking in", "Hello")

	def test_a_topic_outside_a_course_offering_is_not_found(self):
		"""Discussion Topic is a shared core DocType -- Frappe uses it for blog
		comments too. A topic that is not a course room must not open here."""
		topic = frappe.get_doc(
			{
				"doctype": "Discussion Topic",
				"title": "Elsewhere",
				"reference_doctype": "User",
				"reference_docname": "Administrator",
			}
		).insert(ignore_permissions=True)

		_, _, email = make_student()
		frappe.set_user(email)
		with self.assertRaises(frappe.PermissionError):
			comms.discussion_replies(topic.name)


class TestTodoAndCalendar(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_a_guest_is_refused(self):
		frappe.set_user("Guest")
		for endpoint in (agenda.todo, agenda.calendar, comms.announcements, comms.inbox):
			with self.subTest(endpoint=endpoint.__name__):
				with self.assertRaises(frappe.PermissionError):
					endpoint()

	def test_the_empty_answer_has_the_same_shape_as_a_full_one(self):
		"""A short empty branch is how a screen reads undefined for a key it
		always expects."""
		email = "todo.noenrol@example.invalid"
		if not frappe.db.exists("User", email):
			frappe.get_doc({
				"doctype": "User",
				"email": email,
				"first_name": "NoEnrol",
				"send_welcome_email": 0,
				"roles": [{"role": "Student"}],
			}).insert(ignore_permissions=True)

		frappe.set_user(email)
		empty = agenda.todo()
		self.assertEqual(set(empty), {"items", "count", "urgent"})

		frappe.set_user("Administrator")
		_, _, enrolled = make_student()
		frappe.set_user(enrolled)
		self.assertEqual(set(agenda.todo()), {"items", "count", "urgent"})

	def test_dated_work_sorts_above_undated(self):
		"""Sorting by a missing date would put every assignment above an
		overdue fee."""
		_, _, email = make_student()
		frappe.set_user(email)

		items = agenda.todo()["items"]
		dated = [i for i, item in enumerate(items) if item["due"]]
		undated = [i for i, item in enumerate(items) if not item["due"]]
		if dated and undated:
			self.assertLess(max(dated), min(undated))

	def test_the_calendar_window_is_bounded(self):
		"""An open-ended range would expand the weekly recurrence forever."""
		_, _, email = make_student()
		frappe.set_user(email)

		result = agenda.calendar(start="2020-01-01", end="2030-01-01")
		self.assertIsNotNone(result["start"])
		span = frappe.utils.date_diff(result["end"], result["start"])
		self.assertLessEqual(span, 400)

	def test_a_reversed_window_is_corrected_not_rejected(self):
		_, _, email = make_student()
		frappe.set_user(email)

		result = agenda.calendar(start="2026-06-01", end="2026-01-01")
		self.assertLessEqual(result["start"], result["end"])

	def test_every_event_carries_a_kind_the_screen_knows(self):
		_, _, email = make_student()
		frappe.set_user(email)

		known = {"class", "timetable", "session", "fee", "term"}
		for event in agenda.calendar()["events"]:
			self.assertIn(event["kind"], known)
			self.assertTrue(event["start"])
