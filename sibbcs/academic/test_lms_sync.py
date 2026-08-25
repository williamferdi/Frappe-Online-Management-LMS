# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""LMS integration -- architecture doc §6.

The phase's stated end state is "a student logs in once and sees their LMS
course", so these tests assert on the LMS records that actually grant access,
not just on our own `lms_enrollment_created` flag.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from sibbcs.academic.doctype.academic_term.test_academic_term import make_term
from sibbcs.academic.doctype.course.test_course import make_course
from sibbcs.academic.doctype.course_offering.test_course_offering import make_offering
from sibbcs.academic.doctype.program_enrollment.test_program_enrollment import (
	make_enrollment,
	make_student,
)
from sibbcs.academic.lms_sync import ensure_lms_batch, ensure_lms_course, sync_registration


def make_user(email, name="LMS Test User"):
	if frappe.db.exists("User", email):
		return email
	frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": name,
			"user_type": "Website User",
			"send_welcome_email": 0,
		}
	).insert(ignore_permissions=True)
	return email


class TestLMSSync(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.term = make_term("TST-LMS-TERM", status="Open").name

	def setUp(self):
		# These test how a registration reaches the LMS, not when it is allowed
		# to. The fee gate has its own tests in test_registration_payment.py;
		# leaving it on here would make every one of them a test of billing.
		self._conf = patch.dict(frappe.conf, {"require_fee_for_lms_access": 0})
		self._conf.start()
		self.addCleanup(self._conf.stop)

	def _student_with_login(self, email, code):
		user = make_user(email)
		student = make_student(full_name=f"LMS {email}", email=email)
		frappe.db.set_value("Student", student.name, "user", user, update_modified=False)
		enrollment = make_enrollment(student.name)
		course = make_course(code, level="1")
		offering = make_offering(course.name, self.term, status="Published")
		return user, enrollment, course, offering

	def _register(self, enrollment, offering):
		return frappe.get_doc(
			{
				"doctype": "Course Registration",
				"program_enrollment": enrollment.name,
				"course_offering": offering.name,
				"registration_date": today(),
				"status": "Registered",
			}
		).insert(ignore_permissions=True)

	def test_ensure_lms_course_creates_and_links(self):
		course = make_course("TST L100", level="1")
		lms_course = ensure_lms_course(course.name)

		self.assertTrue(frappe.db.exists("LMS Course", lms_course))
		self.assertEqual(
			frappe.db.get_value("Course", course.name, "lms_course"), lms_course
		)

	def test_ensure_lms_course_is_idempotent(self):
		course = make_course("TST L110", level="1")
		first = ensure_lms_course(course.name)
		second = ensure_lms_course(course.name)
		self.assertEqual(first, second)

	def test_ensure_lms_batch_creates_and_stores_on_the_offering(self):
		course = make_course("TST L120", level="1")
		offering = make_offering(course.name, self.term, status="Published")
		batch = ensure_lms_batch(offering.name)

		self.assertTrue(frappe.db.exists("LMS Batch", batch))
		self.assertEqual(
			frappe.db.get_value("Course Offering", offering.name, "lms_batch"), batch
		)

	def test_ensure_lms_batch_is_idempotent(self):
		course = make_course("TST L130", level="1")
		offering = make_offering(course.name, self.term, status="Published")
		self.assertEqual(ensure_lms_batch(offering.name), ensure_lms_batch(offering.name))

	def test_batch_contains_the_lms_course(self):
		course = make_course("TST L140", level="1")
		offering = make_offering(course.name, self.term, status="Published")
		batch = frappe.get_doc("LMS Batch", ensure_lms_batch(offering.name))

		lms_course = frappe.db.get_value("Course", course.name, "lms_course")
		self.assertIn(lms_course, [c.course for c in batch.courses])

	def test_registration_syncs_automatically(self):
		user, enrollment, _course, offering = self._student_with_login(
			"lms1@example.com", "TST L200"
		)
		registration = self._register(enrollment, offering)
		registration.reload()
		self.assertTrue(registration.lms_enrollment_created)

	def test_student_is_enrolled_in_the_batch(self):
		user, enrollment, _course, offering = self._student_with_login(
			"lms2@example.com", "TST L210"
		)
		self._register(enrollment, offering)

		batch = frappe.db.get_value("Course Offering", offering.name, "lms_batch")
		self.assertTrue(
			frappe.db.exists("LMS Batch Enrollment", {"member": user, "batch": batch})
		)

	def test_student_is_enrolled_in_the_course_itself(self):
		"""Batch membership alone does not open the course -- LMS Enrollment does.

		This is the record that makes "logs in once and sees their LMS course"
		actually true.
		"""
		user, enrollment, course, offering = self._student_with_login(
			"lms3@example.com", "TST L220"
		)
		self._register(enrollment, offering)

		lms_course = frappe.db.get_value("Course", course.name, "lms_course")
		self.assertTrue(
			frappe.db.exists("LMS Enrollment", {"member": user, "course": lms_course}),
			"student has batch access but no course access",
		)

	def test_sync_is_idempotent(self):
		user, enrollment, course, offering = self._student_with_login(
			"lms4@example.com", "TST L230"
		)
		registration = self._register(enrollment, offering)
		sync_registration(registration)
		sync_registration(registration)

		lms_course = frappe.db.get_value("Course", course.name, "lms_course")
		self.assertEqual(
			frappe.db.count("LMS Enrollment", {"member": user, "course": lms_course}), 1
		)

	def test_student_without_a_login_is_reported_not_crashed(self):
		student = make_student(full_name="No Login", email="lms5@example.com")
		enrollment = make_enrollment(student.name)
		course = make_course("TST L240", level="1")
		offering = make_offering(course.name, self.term, status="Published")
		registration = self._register(enrollment, offering)

		result = sync_registration(registration)
		self.assertFalse(result["synced"])
		self.assertIn("no linked User", result["reason"])

	def test_draft_registration_is_not_synced(self):
		user, enrollment, _course, offering = self._student_with_login(
			"lms6@example.com", "TST L250"
		)
		registration = frappe.get_doc(
			{
				"doctype": "Course Registration",
				"program_enrollment": enrollment.name,
				"course_offering": offering.name,
				"registration_date": today(),
				"status": "Draft",
			}
		).insert(ignore_permissions=True)

		result = sync_registration(registration)
		self.assertFalse(result["synced"])


class TestPortal(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.term = make_term("TST-PORTAL-TERM", status="Open").name

	def test_available_offerings_annotates_eligibility(self):
		from sibbcs.academic.portal import available_offerings

		student = make_student(full_name="Portal Student", email="portal1@example.com")
		enrollment = make_enrollment(student.name)

		make_offering(make_course("TST PT100", level="1").name, self.term, status="Published")
		make_offering(make_course("TST PT110", level="3").name, self.term, status="Published")

		rows = {o["course"]: o for o in available_offerings(enrollment.name)}
		self.assertTrue(rows["TST PT100"]["eligibility"]["allowed"])
		self.assertFalse(rows["TST PT110"]["eligibility"]["allowed"])
		self.assertTrue(rows["TST PT110"]["eligibility"]["reason"])

	def test_registering_twice_is_reflected(self):
		from sibbcs.academic.portal import available_offerings

		student = make_student(full_name="Portal Two", email="portal2@example.com")
		enrollment = make_enrollment(student.name)
		offering = make_offering(
			make_course("TST PT120", level="1").name, self.term, status="Published"
		)

		frappe.get_doc(
			{
				"doctype": "Course Registration",
				"program_enrollment": enrollment.name,
				"course_offering": offering.name,
				"registration_date": today(),
				"status": "Registered",
			}
		).insert(ignore_permissions=True)

		row = next(
			o for o in available_offerings(enrollment.name) if o["name"] == offering.name
		)
		self.assertTrue(row["already_registered"])
		self.assertFalse(row["eligibility"]["allowed"])


class TestFeeGateBlocksSync(FrappeTestCase):
	"""Registering is the student saying yes; paying is what buys the seat."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.term = make_term("TST-FEEGATE-TERM", status="Open").name

	def _registration(self, email, code):
		user = make_user(email)
		student = make_student(full_name=f"Gate {email}", email=email)
		frappe.db.set_value("Student", student.name, "user", user, update_modified=False)
		enrollment = make_enrollment(student.name)
		course = make_course(code, level="1")
		offering = make_offering(course.name, self.term, status="Published")
		return frappe.get_doc(
			{
				"doctype": "Course Registration",
				"program_enrollment": enrollment.name,
				"course_offering": offering.name,
				"registration_date": frappe.utils.today(),
				"status": "Registered",
			}
		)

	def test_an_unpaid_registration_does_not_open_the_course(self):
		with patch.dict(frappe.conf, {"require_fee_for_lms_access": 1}):
			registration = self._registration("feegate1@example.com", "TSTFEE101")
			registration.insert(ignore_permissions=True)
			registration.reload()

		self.assertFalse(
			registration.lms_enrollment_created,
			"the LMS opened before the registration fee was settled",
		)

	def test_settling_the_fee_opens_the_course(self):
		with patch.dict(frappe.conf, {"require_fee_for_lms_access": 1}):
			registration = self._registration("feegate2@example.com", "TSTFEE102")
			registration.insert(ignore_permissions=True)
			registration.reload()
			self.assertFalse(registration.lms_enrollment_created)

			# What Accounts marking the invoice paid amounts to.
			with patch(
				"sibbcs.academic.doctype.course_registration.course_registration"
				".registration_fee_settled",
				return_value=True,
			):
				registration.reload()
				registration.maybe_sync_lms()

		registration.reload()
		self.assertTrue(
			registration.lms_enrollment_created,
			"the course did not open once the fee was settled",
		)
