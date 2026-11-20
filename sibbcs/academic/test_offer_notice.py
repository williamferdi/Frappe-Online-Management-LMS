# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""Telling students a course they can take is open for registration.

The college asked to be notified "when courses are offered with associated
student levels, so they can register". The level is the request: a Level 1
student should hear about Level 1 and Level 2 courses and about nothing else.

These tests never assert on a count of recipients. The test site carries
fixtures from every other suite, so the roll is whatever has accumulated; what
matters is that *this* student is written to, or is not.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from sibbcs.academic import offer_notice
from sibbcs.academic.doctype.academic_term.test_academic_term import make_term
from sibbcs.academic.doctype.course.test_course import make_course
from sibbcs.academic.doctype.course_offering.test_course_offering import make_offering
from sibbcs.academic.doctype.course_registration.test_course_registration import (
	make_registration,
)
from sibbcs.academic.doctype.program.test_program import make_program
from sibbcs.academic.doctype.program_enrollment.test_program_enrollment import (
	make_enrollment,
	make_student,
)


def _tag():
	return frappe.generate_hash(length=6)


def _own_program():
	"""A programme nobody else's fixtures are enrolled in.

	`recipients` scopes the roll to the programmes a course counts toward, so
	this is what keeps these tests reading two students rather than every
	M.Div. enrollment every other suite has left behind -- and it exercises
	that scoping at the same time.
	"""
	return make_program(f"TPN{_tag()[:4]}".upper()).name


class TestWhoIsTold(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.term = make_term(
			f"TST-OFFER-{_tag()}",
			status="Open",
			registration_closes=add_days(today(), 7),
		).name

	def setUp(self):
		frappe.set_user("Administrator")
		self.tag = _tag()
		self.program = _own_program()

	def _student_at(self, level):
		student = make_student(
			f"Notice {self.tag} L{level}", email=f"notice.{self.tag}.{level}@example.invalid"
		)
		enrollment = make_enrollment(
			student.name, program=self.program, current_level=str(level)
		)
		return enrollment.name, student.name

	def _offering_at(self, level):
		course = make_course(
			f"TNO{level} {self.tag[:4]}",
			level=str(level),
			programs=[{"program": self.program}],
		)
		return make_offering(course.name, self.term, status="Published").name

	def _recipients(self, offering):
		return {person["student"] for person in offer_notice.recipients(offering)}

	def test_a_level_1_student_hears_about_a_level_1_course(self):
		enrollment, student = self._student_at(1)

		self.assertIn(student, self._recipients(self._offering_at(1)))

	def test_a_level_1_student_hears_about_a_level_2_course(self):
		"""Rule 2: levels 1 and 2 are interchangeable, so it is open to them."""
		_enrollment, student = self._student_at(1)

		self.assertIn(student, self._recipients(self._offering_at(2)))

	def test_a_level_1_student_does_not_hear_about_a_level_3_course(self):
		"""Blocked without an Academic Coordinator override. Writing to them
		would point at a course the Register page then refuses."""
		_enrollment, student = self._student_at(1)

		self.assertNotIn(student, self._recipients(self._offering_at(3)))

	def test_a_level_3_student_does_not_hear_about_a_level_4_course(self):
		"""The hard rule. No override clears it, so nobody should be invited."""
		_enrollment, student = self._student_at(3)

		self.assertNotIn(student, self._recipients(self._offering_at(4)))

	def test_somebody_already_registered_is_not_invited_again(self):
		enrollment, student = self._student_at(1)
		offering = self._offering_at(1)
		make_registration(enrollment, offering, status="Registered")

		self.assertNotIn(student, self._recipients(offering))

	def test_a_student_with_no_address_is_left_out(self):
		"""Nothing to send to. It is the registrar's record to fix, and this
		job raising over it would stop everybody else being told."""
		student = make_student(f"Notice {self.tag} silent")
		make_enrollment(student.name, program=self.program, current_level="1")

		self.assertNotIn(student.name, self._recipients(self._offering_at(1)))

	def test_a_student_reading_another_programme_is_not_told(self):
		"""The course counts toward one programme, so it is news to the people
		reading that one and to nobody else."""
		student = make_student(
			f"Notice {self.tag} other", email=f"other.{self.tag}@example.invalid"
		)
		make_enrollment(student.name, program=_own_program(), current_level="1")

		self.assertNotIn(student.name, self._recipients(self._offering_at(1)))

	def test_a_course_tied_to_no_programme_is_news_to_everybody(self):
		"""`Course.counts_toward` reads an empty list as universal, and a
		partly-seeded catalogue must not silently write to nobody."""
		_enrollment, student = self._student_at(1)
		course = make_course(f"TNU {self.tag[:4]}", level="1")
		offering = make_offering(course.name, self.term, status="Published").name

		self.assertIn(student, self._recipients(offering))

	def test_an_inactive_enrollment_is_left_out(self):
		student = make_student(
			f"Notice {self.tag} gone", email=f"gone.{self.tag}@example.invalid"
		)
		make_enrollment(
			student.name, program=self.program, current_level="1", status="Withdrawn"
		)

		self.assertNotIn(student.name, self._recipients(self._offering_at(1)))


class TestTheAnnouncement(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.tag = _tag()
		cls.term = make_term(
			f"TST-ANN-{cls.tag}", status="Open", registration_closes=add_days(today(), 7)
		).name
		cls.program = _own_program()
		student = make_student(
			f"Announce {cls.tag}", email=f"announce.{cls.tag}@example.invalid"
		)
		cls.student = student.name
		make_enrollment(student.name, program=cls.program, current_level="1")

	def setUp(self):
		frappe.set_user("Administrator")

	def _offering(self, **kw):
		# A fresh course each time: an offering is named `{course}-{term}`, so
		# two on one course in one term are the same document.
		term = kw.pop("term", self.term)
		course = make_course(
			f"TAN {_tag()[:4]}",
			level=kw.pop("level", "1"),
			programs=[{"program": self.program}],
		).name
		return make_offering(course, term, status=kw.pop("status", "Published"), **kw).name

	def _announce(self, offering, **kw):
		with patch.object(frappe, "sendmail") as sendmail:
			report = offer_notice.announce(offering, **kw)
		return report, sendmail

	def test_the_eligible_student_is_written_to(self):
		report, sendmail = self._announce(self._offering())

		self.assertIn(self.student, report["sent"])
		self.assertTrue(sendmail.called)

	def test_the_letter_says_the_level_and_how_to_register(self):
		offering = self._offering()
		context = offer_notice._offering_context(offering)

		self.assertEqual(context["course_level"], "1")
		self.assertEqual(
			context["course_code"],
			frappe.db.get_value("Course Offering", offering, "course"),
		)
		self.assertTrue(context["register_url"].endswith("/portal/courses/register"))
		self.assertNotIn(":8000", context["register_url"])

	def test_it_is_stamped_so_it_is_not_said_twice(self):
		offering = self._offering()
		self._announce(offering)

		self.assertTrue(
			frappe.db.get_value("Course Offering", offering, "students_notified_on")
		)

		report, sendmail = self._announce(offering)
		self.assertEqual(report["skipped"], "already announced")
		sendmail.assert_not_called()

	def test_force_says_it_again(self):
		"""What the Registrar wants after correcting a course level."""
		offering = self._offering()
		self._announce(offering)

		report, _sendmail = self._announce(offering, force=True)

		self.assertIn(self.student, report["sent"])

	def test_nobody_eligible_is_still_an_answer(self):
		"""Stamped even with an empty roll, or the nightly sweep would ask the
		same question of the same students every morning until the term shut."""
		offering = self._offering()

		with patch.object(offer_notice, "recipients", return_value=[]):
			report, sendmail = self._announce(offering)

		self.assertEqual(report["sent"], [])
		sendmail.assert_not_called()
		self.assertTrue(
			frappe.db.get_value("Course Offering", offering, "students_notified_on")
		)

	def test_a_draft_offering_announces_nothing(self):
		report, sendmail = self._announce(self._offering(status="Draft"))

		self.assertEqual(report["skipped"], "status is Draft")
		sendmail.assert_not_called()

	def test_a_term_that_has_not_opened_waits(self):
		"""And is deliberately not stamped: the term may open later, and the
		sweep has to find this offering again when it does."""
		shut = make_term(f"TST-SHUT-{_tag()}", status="Planned").name
		offering = self._offering(term=shut)

		report, sendmail = self._announce(offering)

		self.assertEqual(report["skipped"], "registration is not open in this term")
		sendmail.assert_not_called()
		self.assertFalse(
			frappe.db.get_value("Course Offering", offering, "students_notified_on")
		)

	def test_a_window_that_has_already_closed_announces_nothing(self):
		late = make_term(
			f"TST-LATE-{_tag()}", status="Open", registration_closes=add_days(today(), -1)
		).name

		report, _sendmail = self._announce(self._offering(term=late))

		self.assertEqual(report["skipped"], "registration is not open in this term")

	def test_the_sweep_picks_up_what_the_hook_could_not(self):
		"""Only the choosing is tested. Running every announcement on a test
		site would write to whatever the other suites have left lying about."""
		offering = self._offering()

		with patch.object(offer_notice, "announce") as announce:
			offer_notice.announce_open_offerings()

		self.assertIn(offering, [call.args[0] for call in announce.call_args_list])

	def test_the_sweep_leaves_alone_what_has_been_announced(self):
		offering = self._offering()
		frappe.db.set_value(
			"Course Offering",
			offering,
			"students_notified_on",
			frappe.utils.now_datetime(),
			update_modified=False,
		)

		with patch.object(offer_notice, "announce") as announce:
			offer_notice.announce_open_offerings()

		self.assertNotIn(offering, [call.args[0] for call in announce.call_args_list])

	def test_a_mail_that_fails_does_not_stop_the_rest(self):
		with patch.object(frappe, "sendmail", side_effect=Exception("no smtp")):
			with patch.object(frappe, "log_error"):
				report = offer_notice.announce(self._offering())

		self.assertEqual(report["sent"], [])


class TestPublishingQueuesIt(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.tag = _tag()
		cls.term = make_term(
			f"TST-HOOK-{cls.tag}", status="Open", registration_closes=add_days(today(), 7)
		).name

	def setUp(self):
		frappe.set_user("Administrator")
		self.course = make_course(f"THK {_tag()[:4]}", level="1").name

	def _ours(self, call):
		return call.args and call.args[0] == "sibbcs.academic.offer_notice.announce"

	def test_publishing_queues_the_announcement(self):
		with patch.object(frappe, "enqueue") as enqueue:
			make_offering(self.course, self.term, status="Published")

		self.assertTrue([c for c in enqueue.call_args_list if self._ours(c)])

	def test_a_draft_queues_nothing(self):
		with patch.object(frappe, "enqueue") as enqueue:
			make_offering(self.course, self.term, status="Draft")

		self.assertEqual([c for c in enqueue.call_args_list if self._ours(c)], [])

	def test_saving_an_announced_offering_again_queues_nothing(self):
		"""The stamp, read by the hook. Without it every save of a published
		offering would queue a job that found nothing to do."""
		offering = make_offering(self.course, self.term, status="Published")
		frappe.db.set_value(
			"Course Offering",
			offering.name,
			"students_notified_on",
			frappe.utils.now_datetime(),
			update_modified=False,
		)

		doc = frappe.get_doc("Course Offering", offering.name)
		with patch.object(frappe, "enqueue") as enqueue:
			doc.save(ignore_permissions=True)

		self.assertEqual([c for c in enqueue.call_args_list if self._ours(c)], [])
