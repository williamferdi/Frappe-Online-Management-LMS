# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""The academic console.

Grade entry is the one place this layer writes, so most of these tests are
about that: that a blank mark is not a zero, that the letter comes from the
Grade Scale rather than from here, and that the permlevel on the grade fields
is still doing its job because nothing passes `ignore_permissions`.
"""

import ast
import inspect

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.academic.doctype.academic_term.test_academic_term import make_term
from sibbcs.academic.doctype.course.test_course import make_course
from sibbcs.academic.doctype.course_offering.test_course_offering import make_offering
from sibbcs.academic.doctype.course_registration.test_course_registration import (
	make_registration,
)
from sibbcs.admissions import checklist
from sibbcs.admissions.doctype.admission_application.test_admission_application import (
	make_application,
)
from sibbcs.api import academic_api as api
from sibbcs.api.test_api import make_user
from sibbcs.api.test_student_api import make_student


def a_registration():
	"""A live registration of our own.

	Built rather than found: grading the first Registered row on the site
	moves it to Completed, so a test that borrows one leaves the next run
	with nothing to borrow and quietly skips.
	"""
	tag = frappe.generate_hash(length=6)
	term = make_term(f"GRD-{tag}", status="Open").name
	course = make_course(f"GRD{tag}", level="1", credits=3).name
	# make_offering leaves an offering in Draft, which the rule engine
	# correctly refuses to register anyone onto.
	offering = make_offering(course, term, status="Published").name

	student, enrollment, _ = make_student()
	return make_registration(enrollment.name, offering).name


class TestAccess(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_a_student_is_refused_the_academic_console(self):
		"""Students hold read on Student and Course Registration -- they must,
		to see their own. These endpoints list everybody."""
		_, _, email = make_student()
		frappe.set_user(email)

		for endpoint, kwargs in (
			(api.students, {}),
			(api.offerings, {}),
		):
			with self.subTest(endpoint=endpoint.__name__):
				with self.assertRaises(frappe.PermissionError):
					endpoint(**kwargs)

	def test_a_guest_is_refused(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			api.students()

	def test_save_grades_never_ignores_permissions(self):
		"""The grade fields sit at permlevel 1, so an ordinary save is already
		the permission check, and `ignore_permissions` would quietly remove it.

		Read from the syntax tree, not the text: the first version of this
		test grepped the source and matched the docstring explaining the rule.
		"""
		tree = ast.parse(inspect.getsource(api.save_grades).lstrip())
		offenders = [
			node
			for node in ast.walk(tree)
			if isinstance(node, ast.Call)
			for kw in node.keywords
			if kw.arg == "ignore_permissions"
		]
		self.assertEqual(offenders, [], "save_grades bypasses the permlevel check")
		self.assertIn('check_permission("write")', inspect.getsource(api.save_grades))


class TestStudents(FrappeTestCase):
	def test_the_roll_carries_each_enrolment(self):
		result = api.students()
		self.assertIn("rows", result)
		for row in result["rows"]:
			self.assertIn("enrollment", row)

	def test_search_matches_a_fragment(self):
		"""A bare value in or_filters means `=`; the operator has to be
		spelled out or the box silently matches nothing.

		Searched on the unique part of the name, not the shared prefix: every
		student this suite makes is a Portal Student, and matching all of them
		runs into the row cap rather than testing the LIKE.
		"""
		student, _, _ = make_student()
		frappe.db.commit()

		fragment = student.full_name.split()[-1]
		names = [row.name for row in api.students(search=fragment)["rows"]]
		self.assertIn(student.name, names)

	def test_a_capped_list_says_it_was_capped(self):
		"""Two hundred results with no sign there are four hundred is a
		Registrar reading a truncated list and believing it."""
		page = api.students(limit=1)
		self.assertIn("truncated", page)
		if frappe.db.count("Student") > 1:
			self.assertTrue(page["truncated"])
			self.assertEqual(len(page["rows"]), 1)

	def test_a_missing_student_is_reported_not_returned_empty(self):
		with self.assertRaises(frappe.ValidationError):
			api.student("SIB-does-not-exist")


class TestGradeEntry(FrappeTestCase):
	def setUp(self):
		self.registration = a_registration()

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_a_blank_mark_is_not_a_zero(self):
		"""compute_grade holds the letter back until every component is marked.
		Storing a blank as 0 would award a fail on unfinished marking."""
		result = api.save_grades(
			self.registration,
			[
				{"component": "Assignment", "weight_pct": 40, "max_marks": 100, "obtained_marks": 82},
				{"component": "Final Paper", "weight_pct": 60, "max_marks": 100, "obtained_marks": None},
			],
		)

		self.assertFalse(result["marks_complete"])
		self.assertIsNone(result["grade"])
		blank = next(c for c in result["components"] if c["component"] == "Final Paper")
		self.assertIn(blank["obtained_marks"], (None, 0.0))
		self.assertIsNone(blank["obtained_marks"], "a blank mark was stored as a number")

	def test_a_complete_sheet_produces_a_letter_from_the_scale(self):
		result = api.save_grades(
			self.registration,
			[
				{"component": "Assignment", "weight_pct": 40, "max_marks": 100, "obtained_marks": 90},
				{"component": "Final Paper", "weight_pct": 60, "max_marks": 100, "obtained_marks": 90},
			],
		)

		self.assertTrue(result["marks_complete"])
		self.assertEqual(result["final_marks"], 90.0)
		self.assertTrue(result["grade"], "no grade came back from the scale")

	def test_the_weighted_score_is_computed_not_accepted(self):
		"""A caller could send any weighted_score it liked; the document
		recomputes from the raw marks."""
		result = api.save_grades(
			self.registration,
			[
				{
					"component": "Assignment",
					"weight_pct": 50,
					"max_marks": 100,
					"obtained_marks": 60,
					"weighted_score": 999,
				},
				{"component": "Final Paper", "weight_pct": 50, "max_marks": 100, "obtained_marks": 60},
			],
		)
		for component in result["components"]:
			self.assertEqual(component["weighted_score"], 30.0)

	def test_marks_out_of_something_other_than_a_hundred(self):
		result = api.save_grades(
			self.registration,
			[
				{"component": "Assignment", "weight_pct": 100, "max_marks": 50, "obtained_marks": 25},
			],
		)
		self.assertEqual(result["final_marks"], 50.0)

	def test_saving_marks_updates_the_credits_and_cgpa(self):
		enrollment = frappe.db.get_value(
			"Course Registration", self.registration, "program_enrollment"
		)
		api.save_grades(
			self.registration,
			[
				{"component": "Assignment", "weight_pct": 100, "max_marks": 100, "obtained_marks": 85},
			],
			status="Completed",
		)
		frappe.db.commit()

		row = frappe.db.get_value(
			"Program Enrollment", enrollment, ["credits_earned", "cgpa"], as_dict=True
		)
		self.assertGreater(row.credits_earned, 0)

	def test_components_may_arrive_as_a_json_string(self):
		"""Frappe hands whitelisted methods form-encoded arguments, so a list
		arrives as text."""
		import json

		result = api.save_grades(
			self.registration,
			json.dumps(
				[{"component": "Assignment", "weight_pct": 100, "max_marks": 100, "obtained_marks": 70}]
			),
		)
		self.assertEqual(result["final_marks"], 70.0)

	def test_something_that_is_not_a_list_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			api.save_grades(self.registration, {"component": "Assignment"})

	def test_a_row_with_no_component_named_is_skipped(self):
		result = api.save_grades(
			self.registration,
			[
				{"component": "Assignment", "weight_pct": 100, "max_marks": 100, "obtained_marks": 70},
				{"component": "", "weight_pct": 0, "max_marks": 100, "obtained_marks": None},
			],
		)
		self.assertEqual(len(result["components"]), 1)


class TestRoster(FrappeTestCase):
	def test_the_component_choices_come_from_the_doctype(self):
		"""Hard-coding them here is how the sheet ends up offering a component
		the Select refuses on save."""
		meta = frappe.get_meta("Grade Component")
		options = [c for c in (meta.get_field("component").options or "").split("\n") if c]
		self.assertEqual(api._component_choices(), options)

	def test_the_statuses_come_from_the_doctype(self):
		meta = frappe.get_meta("Course Registration")
		options = [c for c in (meta.get_field("status").options or "").split("\n") if c]
		self.assertEqual(api._registration_statuses(), options)

	def test_marks_complete_is_false_when_a_component_is_blank(self):
		self.assertFalse(api._marks_complete([]))
		self.assertFalse(
			api._marks_complete([{"obtained_marks": 10}, {"obtained_marks": None}])
		)
		self.assertTrue(api._marks_complete([{"obtained_marks": 10}, {"obtained_marks": 0}]))

	def test_a_missing_offering_is_reported(self):
		with self.assertRaises(frappe.ValidationError):
			api.roster("does-not-exist")


class TestPromotions(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_the_board_says_whether_the_caller_may_act(self):
		result = api.promotions()
		self.assertIn("may_approve", result)
		self.assertIn("rows", result)

	def test_every_blocked_row_gives_a_reason(self):
		"""A greyed button with no explanation is what the office rings about."""
		for row in api.promotions()["rows"]:
			if not row["eligible"]:
				self.assertTrue(row["blocked"], f"{row['student_name']} blocked with no reason")

	def test_a_student_cannot_see_the_promotion_board(self):
		_, _, email = make_student()
		frappe.set_user(email)
		with self.assertRaises(frappe.PermissionError):
			api.promotions()


class TestStudentProfile(FrappeTestCase):
	"""The admission record behind a student.

	A `Student` row holds identity and contact and nothing else. The schooling,
	the certificates, the referees and the mentor stay on the Admission
	Application and are never copied across at onboarding, so the profile page
	reads both -- and these tests are that the second half arrives, and that it
	stops arriving for a reader who may not read it.
	"""

	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def a_student_admitted_from_an_application(self):
		tag = frappe.generate_hash(length=6)
		application = make_application(
			full_name=f"Admitted {tag}",
			email=f"admitted.{tag}@example.invalid",
			ssc_status="Completed",
			ssc_year="2014",
			hslc_status="Completed",
			hslc_year="2016",
			mother_tongue="Telugu",
			nationality="Indian",
			church_denomination="Independent",
			salvation_status="I am Saved",
			baptism_status="Baptised",
			sense_of_call="Yes, clearly",
			ata_eligible=1,
			church_name="New Life Church",
			current_role="Assistant pastor",
			years_of_ministry=2,
			documents=[
				{"document_type": "SSC/10th Mark Sheet", "file": "/files/ssc.pdf", "verified": 1},
				{"document_type": "National ID", "file": "/files/id.pdf"},
			],
			references=[
				{"referee_name": "Pastor Rajesh", "referee_email": f"ref.{tag}@example.invalid",
				 "referee_type": "Pastor-Mentor"},
			],
			mentors=[
				{"mentor_name": "Benny", "mentor_email": f"mentor.{tag}@example.invalid",
				 "mentor_mobile": "+918098619631", "current_position": "Bible college professor"},
			],
		)

		student, _, _ = make_student()
		frappe.db.set_value("Student", student.name, "admission_application", application.name)
		return student.name, application.name

	def test_the_profile_carries_the_admission_record(self):
		name, application = self.a_student_admitted_from_an_application()

		block = api.student(name)["admission"]

		self.assertIsNotNone(block)
		self.assertEqual(block["application"]["name"], application)
		self.assertEqual(block["application"]["ssc_status"], "Completed")
		self.assertEqual(block["application"]["church_name"], "New Life Church")

	def test_the_profile_carries_what_the_candidate_declared(self):
		"""Mother tongue, denomination, baptism and the rest live on the
		application and nowhere else -- the profile is where anyone reads them.
		"""
		name, _ = self.a_student_admitted_from_an_application()

		record = api.student(name)["admission"]["application"]

		self.assertEqual(record["mother_tongue"], "Telugu")
		self.assertEqual(record["church_denomination"], "Independent")
		self.assertEqual(record["baptism_status"], "Baptised")
		self.assertEqual(record["sense_of_call"], "Yes, clearly")
		# And the one determination only the college may make.
		self.assertTrue(record["ata_eligible"])

	def test_the_documents_and_the_people_who_vouched_come_with_it(self):
		"""The reason for the page: a registrar looking a student up wants the
		certificates and the reference answers, not a link to go and find them."""
		name, _ = self.a_student_admitted_from_an_application()

		block = api.student(name)["admission"]

		self.assertEqual(
			[row.document_type for row in block["documents"]],
			["SSC/10th Mark Sheet", "National ID"],
		)
		self.assertEqual(block["references"][0].referee_name, "Pastor Rajesh")
		self.assertEqual(block["mentors"][0].mentor_name, "Benny")
		# The mentor's own details, which the profile shows as formation.
		self.assertEqual(block["mentors"][0].current_position, "Bible college professor")

	def test_the_checklist_is_the_admissions_board_not_a_second_copy(self):
		"""Two pages showing different answers to 'where is this person' is
		worse than one page showing none."""
		name, application = self.a_student_admitted_from_an_application()

		block = api.student(name)["admission"]

		self.assertEqual(
			[(row["step_no"], row["status"]) for row in block["checklist"]["rows"]],
			[(row["step_no"], row["status"]) for row in checklist.board(application)["rows"]],
		)

	def test_a_student_created_directly_simply_has_none(self):
		student, _, _ = make_student()
		self.assertIsNone(api.student(student.name)["admission"])

	def test_a_reader_without_admission_permission_gets_the_rest(self):
		"""Faculty may see a student and grade them but hold nothing on
		Admission Application. The page drops the block; it does not fail.

		The teacher teaches this student. Since 2026-09-11 a teacher's roll is
		their own students, and a profile outside it is refused outright.
		"""
		from sibbcs.academic.doctype.course_offering.test_course_offering import (
			make_instructor,
		)

		name, _ = self.a_student_admitted_from_an_application()
		email = f"faculty.{frappe.generate_hash(length=8)}@example.invalid"
		make_user(email, ["Faculty"])

		tag = frappe.generate_hash(length=6)
		offering = make_offering(
			make_course(f"GRD{tag}", level="1", credits=3).name,
			make_term(f"GRD-{tag}", status="Open").name,
			status="Published",
			instructor=make_instructor(f"Profile Teacher {tag}", user=email).name,
		).name
		enrollment = frappe.db.get_value("Program Enrollment", {"student": name}, "name")
		make_registration(enrollment, offering)

		frappe.set_user(email)
		profile = api.student(name)

		self.assertIsNone(profile["admission"])
		self.assertEqual(profile["student"]["name"], name)

	def test_a_student_cannot_read_another_students_profile(self):
		name, _ = self.a_student_admitted_from_an_application()
		_, _, email = make_student()

		frappe.set_user(email)
		with self.assertRaises(frappe.PermissionError):
			api.student(name)


class TestDemographics(FrappeTestCase):
	"""Six breakdowns of the roll, drawn as donuts above the student list."""

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_every_panel_adds_up_to_the_roll(self):
		"""A donut whose slices do not sum to its own centre number is worse
		than no donut."""
		make_student()
		data = api.demographics()

		self.assertEqual(data["total"], frappe.db.count("Student"))
		for panel in data["panels"]:
			with self.subTest(panel=panel["key"]):
				self.assertEqual(
					sum(slice["count"] for slice in panel["slices"]),
					data["total"],
					panel["title"],
				)

	def test_a_category_with_nobody_in_it_is_still_shown(self):
		"""'B.Th 0' is a fact worth seeing; a donut that drops empty categories
		answers a question nobody asked."""
		data = api.demographics()

		programmes = next(p for p in data["panels"] if p["key"] == "program")
		labels = [slice["label"] for slice in programmes["slices"]]
		for name in frappe.get_all("Program", pluck="name"):
			self.assertIn(name, labels)

	def test_the_categories_come_from_the_doctype(self):
		"""Not a list in the front end: a status added in Desk would otherwise
		vanish into a bucket nobody notices."""
		data = api.demographics()

		statuses = next(p for p in data["panels"] if p["key"] == "status")
		options = frappe.get_meta("Student").get_field("status").options.split("\n")
		for option in [line.strip() for line in options if line.strip()]:
			self.assertIn(option, [slice["label"] for slice in statuses["slices"]])

	def test_each_panel_says_what_kind_of_scale_it_is(self):
		"""The colour is chosen by the job it does -- identity, state, an
		ordered scale -- and the server is where that is known."""
		kinds = {panel["key"]: panel["kind"] for panel in api.demographics()["panels"]}

		self.assertEqual(kinds["program"], "categorical")
		self.assertEqual(kinds["status"], "status")
		self.assertEqual(kinds["level"], "ordinal")
		self.assertEqual(kinds["mature_candidate"], "binary")

	def test_a_student_with_no_enrolment_is_counted_somewhere(self):
		student = frappe.get_doc(
			{
				"doctype": "Student",
				"full_name": f"Unenrolled {frappe.generate_hash(length=6)}",
				"status": "Active",
			}
		).insert(ignore_permissions=True)

		data = api.demographics()
		level = next(p for p in data["panels"] if p["key"] == "level")

		self.assertIn("Not enrolled", [slice["label"] for slice in level["slices"]])
		self.assertEqual(
			sum(slice["count"] for slice in level["slices"]), data["total"]
		)
		self.assertTrue(frappe.db.exists("Student", student.name))

	def test_the_two_admission_panels_are_dropped_for_a_reader_who_may_not_read_them(self):
		"""Faculty hold nothing on Admission Application. A zero that means
		'you may not see this' is a lie, so the panels go."""
		email = f"faculty.{frappe.generate_hash(length=8)}@example.invalid"
		make_user(email, ["Faculty"])

		frappe.set_user(email)
		keys = [panel["key"] for panel in api.demographics()["panels"]]

		self.assertNotIn("mature_candidate", keys)
		self.assertNotIn("transfer_student", keys)
		self.assertIn("program", keys)

	def test_a_student_is_refused_the_whole_roll(self):
		_, _, email = make_student()
		frappe.set_user(email)

		with self.assertRaises(frappe.PermissionError):
			api.demographics()

	def test_the_roll_carries_a_photograph_to_the_list(self):
		"""The list draws a face; without this it draws initials for everybody."""
		self.assertIn("photo", api.STUDENT_LIST_FIELDS)
		rows = api.students()["rows"]
		if rows:
			self.assertIn("photo", rows[0])
