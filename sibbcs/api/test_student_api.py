# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""The student portal's own endpoints.

Every one of these answers for `frappe.session.user` and takes no argument
naming a student, so the tests care as much about what cannot be asked for as
about what comes back.
"""

import base64
import inspect
import itertools

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.api import student as api

_seq = itertools.count(1)

STUDENT_ENDPOINTS = (
	api.dashboard,
	api.grades,
	api.profile,
	api.my_courses,
	api.registration_options,
)


def make_student(**overrides):
	"""A student with a login, and an active MDIV enrollment."""
	tag = next(_seq)
	email = overrides.pop("email", f"portal.student{tag}@example.invalid")

	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": f"Portal{tag}",
				"send_welcome_email": 0,
				"roles": [{"role": "Student"}],
			}
		).insert(ignore_permissions=True)

	values = {
		"doctype": "Student",
		"full_name": f"Portal Student {tag}",
		"email": email,
		"mobile": "+91 90000 00000",
		"status": "Active",
		"user": email,
	}
	values.update(overrides)
	student = frappe.get_doc(values).insert(ignore_permissions=True)

	enrollment = frappe.get_doc(
		{
			"doctype": "Program Enrollment",
			"student": student.name,
			"program": "MDIV",
			"status": "Active",
			"enrollment_date": frappe.utils.today(),
			"current_level": "1",
		}
	).insert(ignore_permissions=True)

	return student, enrollment, email


class TestScoping(FrappeTestCase):
	"""None of these may be pointed at somebody else's record."""

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_a_guest_is_refused_everywhere(self):
		frappe.set_user("Guest")
		for endpoint in STUDENT_ENDPOINTS:
			with self.subTest(endpoint=endpoint.__name__):
				with self.assertRaises(frappe.PermissionError):
					endpoint()

	def test_none_of_them_accept_a_student_argument(self):
		"""A `student` or `enrollment` parameter would be a way to read another
		person's marks by guessing a name."""
		for endpoint in STUDENT_ENDPOINTS:
			with self.subTest(endpoint=endpoint.__name__):
				self.assertEqual(list(inspect.signature(endpoint).parameters), [])

	def test_they_are_whitelisted_but_never_for_guests(self):
		for endpoint in (*STUDENT_ENDPOINTS, api.update_profile, api.update_photo):
			with self.subTest(endpoint=endpoint.__name__):
				self.assertIn(endpoint, frappe.whitelisted)
				self.assertNotIn(endpoint, frappe.guest_methods)

	def test_a_student_sees_their_own_enrollment_and_no_other(self):
		_, mine, my_email = make_student()
		_, theirs, _ = make_student()

		frappe.set_user(my_email)
		self.assertEqual(api.dashboard()["enrollment"]["name"], mine.name)
		self.assertNotEqual(mine.name, theirs.name)

	def test_a_signed_in_user_with_no_enrollment_is_not_an_error(self):
		"""An admitted applicant waiting on the Registrar is an ordinary state."""
		email = f"noenrol{next(_seq)}@example.invalid"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "NoEnrol",
				"send_welcome_email": 0,
				"roles": [{"role": "Student"}],
			}
		).insert(ignore_permissions=True)

		frappe.set_user(email)
		self.assertIsNone(api.dashboard()["enrollment"])
		self.assertEqual(api.grades()["terms"], [])
		self.assertEqual(api.my_courses()["registrations"], [])


class TestDashboard(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_it_reports_the_programme_by_name_not_by_code(self):
		"""Program Enrollment stores MDIV; the student knows it as Master of
		Divinity, and every screen shows this header."""
		_, _, email = make_student()
		frappe.set_user(email)

		header = api.dashboard()["enrollment"]
		self.assertEqual(header["program"], "MDIV")
		self.assertEqual(
			header["program_name"],
			frappe.db.get_value("Program", "MDIV", "program_name"),
		)

	def test_the_shape_is_stable_for_a_student_with_nothing_yet(self):
		"""The screen reads five nested keys; a missing one is a blank panel."""
		_, _, email = make_student()
		frappe.set_user(email)

		data = api.dashboard()
		self.assertEqual(data["in_progress"], [])
		self.assertEqual(data["fees"]["outstanding"], 0)
		self.assertEqual(data["fees"]["overdue_count"], 0)
		self.assertIn("terms", data["registration"])


class TestGrades(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_it_returns_the_scale_so_a_letter_means_something(self):
		_, _, email = make_student()
		frappe.set_user(email)

		scale = api.grades()["scale"]
		if scale:  # a site with no Grade Scale is legitimate before setup
			self.assertIn("rows", scale)
			self.assertIn("pass_percentage", scale)

	def test_every_registration_carries_its_components(self):
		"""'Why is my grade a B' is answered from the weighted components, so
		they travel with the row rather than in a second request per course."""
		_, _, email = make_student()
		frappe.set_user(email)

		for term in api.grades()["terms"]:
			for row in term["rows"]:
				self.assertIsInstance(row["components"], list)


class TestUpdateProfile(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_it_accepts_only_the_three_contact_fields(self):
		"""The signature is the guard. A `**values` signature here would let a
		student write any field on their own Student record -- `status`
		included, which is how somebody marks themselves Active again after
		being withdrawn."""
		parameters = list(inspect.signature(api.update_profile).parameters)
		self.assertEqual(parameters, ["mobile", "whatsapp", "address"])
		self.assertEqual(set(parameters), set(api.EDITABLE_PROFILE_FIELDS))

	def test_it_saves_contact_details(self):
		student, _, email = make_student()
		frappe.set_user(email)

		api.update_profile(mobile="+91 98765 43210", address="14 Mission Road")
		frappe.db.commit()

		row = frappe.db.get_value("Student", student.name, ["mobile", "address"], as_dict=True)
		self.assertEqual(row.mobile, "+91 98765 43210")
		self.assertEqual(row.address, "14 Mission Road")

	def test_it_leaves_unnamed_fields_alone(self):
		"""Passing only a mobile must not blank the address."""
		student, _, email = make_student(address="Original address")
		frappe.set_user(email)

		api.update_profile(mobile="9876543210")
		frappe.db.commit()

		self.assertEqual(
			frappe.db.get_value("Student", student.name, "address"), "Original address"
		)

	def test_it_refuses_something_that_is_not_a_phone_number(self):
		_, _, email = make_student()
		frappe.set_user(email)

		with self.assertRaises(frappe.ValidationError):
			api.update_profile(mobile="call me maybe")

	def test_it_accepts_the_way_people_actually_write_numbers(self):
		student, _, email = make_student()
		frappe.set_user(email)

		for number in ("+91 98400 11223", "098765-43210", "(044) 2345 6789"):
			with self.subTest(number=number):
				api.update_profile(mobile=number)
				frappe.db.commit()
				self.assertEqual(frappe.db.get_value("Student", student.name, "mobile"), number)

	def test_a_user_with_no_student_record_is_refused(self):
		email = f"nostudent{next(_seq)}@example.invalid"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "NoStudent",
				"send_welcome_email": 0,
				"roles": [{"role": "Student"}],
			}
		).insert(ignore_permissions=True)

		frappe.set_user(email)
		with self.assertRaises(frappe.PermissionError):
			api.update_profile(mobile="9876543210")


class TestUpdatePhoto(FrappeTestCase):
	# A 1x1 PNG, which is a real one -- the validator reads the bytes.
	PNG = base64.b64decode(
		"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
	)

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_a_pdf_is_not_a_photograph(self):
		_, _, email = make_student()
		frappe.set_user(email)

		with self.assertRaises(frappe.ValidationError):
			api.update_photo(
				filename="scan.pdf",
				content=base64.b64encode(b"%PDF-1.4 fake").decode(),
				content_type="application/pdf",
			)

	def test_bytes_that_are_not_an_image_are_refused_whatever_the_name(self):
		"""The name and the declared type can both lie; the bytes cannot."""
		_, _, email = make_student()
		frappe.set_user(email)

		with self.assertRaises(frappe.ValidationError):
			api.update_photo(
				filename="portrait.png",
				content=base64.b64encode(b"this is not a png").decode(),
				content_type="image/png",
			)

	def test_unreadable_base64_is_reported_not_raised_as_a_traceback(self):
		_, _, email = make_student()
		frappe.set_user(email)

		with self.assertRaises(frappe.ValidationError):
			api.update_photo(filename="portrait.png", content="!!!not base64!!!")

	def test_a_real_png_is_stored_privately_and_linked(self):
		student, _, email = make_student()
		frappe.set_user(email)

		result = api.update_photo(
			filename="portrait.png",
			content=base64.b64encode(self.PNG).decode(),
			content_type="image/png",
		)
		frappe.db.commit()

		self.assertTrue(result["photo"])
		self.assertEqual(frappe.db.get_value("Student", student.name, "photo"), result["photo"])
		# A student photograph is personal data, not a public asset.
		self.assertTrue(
			frappe.db.get_value("File", {"file_url": result["photo"]}, "is_private")
		)


class TestRegistrationOptions(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_blocked_offerings_come_back_with_a_reason(self):
		"""Returning only what a student may take turns 'why can't I take this?'
		into an email to the Registrar. Every row carries its verdict."""
		_, _, email = make_student()
		frappe.set_user(email)

		for term in api.registration_options()["terms"]:
			for row in term["rows"]:
				self.assertIn("allowed", row["eligibility"])
				if not row["eligibility"]["allowed"]:
					self.assertTrue(
						row["eligibility"]["reason"],
						f"{row['course']} is blocked with no reason given",
					)

	def test_offerings_are_grouped_by_term(self):
		"""A course runs in several terms. A flat list of near-identical rows is
		how students registered for the wrong one during acceptance testing."""
		_, _, email = make_student()
		frappe.set_user(email)

		terms = api.registration_options()["terms"]
		self.assertEqual(len(terms), len({term["term"] for term in terms}))
		for term in terms:
			for row in term["rows"]:
				self.assertEqual(row["term"], term["term"])

	def test_the_eligible_count_matches_the_rows(self):
		_, _, email = make_student()
		frappe.set_user(email)

		for term in api.registration_options()["terms"]:
			allowed = sum(1 for row in term["rows"] if row["eligibility"]["allowed"])
			self.assertEqual(term["eligible_count"], allowed)
