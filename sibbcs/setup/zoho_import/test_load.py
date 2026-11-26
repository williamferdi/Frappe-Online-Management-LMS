# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""The load, end to end, on a small invented extract.

Nothing here is real Zoho data. The extract is built in a temporary folder in
the same shape the real one has (records/<name>.json, review/*.csv,
manifest.json, files/...), so the code under test is exactly what runs on the
day.
"""

import base64
import csv
import hashlib
import json
import os
import shutil
import tempfile
from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.finance import fees
from sibbcs.integrations import campus_lms
from sibbcs.setup.zoho_import import load, review

# a valid 1x1 PNG, so the photo is a real image
PNG = base64.b64decode(
	"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)

PROGRAMME = "ZTP"
PROGRAMME_NAME = "Zoho Test Programme"


def lookup(zoho_id, label="x"):
	return {"ID": zoho_id, "zc_display_value": label}


def student(zoho_id, email, level="Level 2", onboarded=True, programme=PROGRAMME_NAME):
	return {
		"ID": zoho_id,
		"full_name": {"zc_display_value": f"Zoho Test {zoho_id}"},
		"email": email,
		"phone": "",
		"gender": "Female",
		"date_of_birth": "11-Apr-1996",
		"address": {"zc_display_value": "1 Test Road"},
		"Onboarding_Status": "Onboarded" if onboarded else "Awaiting Onboarding",
		"enrollment_status": "Active",
		"program_enrolled": programme,
		"current_level": level,
		"admission_date": "",
		"application_received_date": "02-Feb-2031",
		"onboarding_term": "Term 1 2031",
	}


def grade(zoho_id, student_id, offering_id, status="Pass", marks="78"):
	return {
		"ID": zoho_id,
		"Student": lookup(student_id),
		"Course_Name": lookup(offering_id, "Term 1 - 2031 - Course"),
		"Status": status,
		"Marks": marks,
	}


class ExtractBuilder:
	"""A miniature extract on disk."""

	def __init__(self):
		self.folder = tempfile.mkdtemp(prefix="zoho-test-")
		self.records = {
			"programs": [],
			"courses": [
				{"ID": "C1", "course_code": "BIST O991", "title": "Zoho Test One", "credits": "3"},
				{"ID": "C2", "course_code": "BIST O992", "title": "Zoho Test Two", "credits": "3"},
			],
			"program_courses": [],
			"terms": [
				{"ID": "T1", "Term": "Term 1", "Academic_Year": "2031", "Status": "Past",
				 "Start_Date": "06-Jan-2031", "End_Date": "02-Mar-2031"},
				{"ID": "T2", "Term": "Term 2", "Academic_Year": "2031", "Status": "Upcoming",
				 "Start_Date": "03-Mar-2031", "End_Date": "27-Apr-2031"},
			],
			"faculty": [
				{"ID": "F1", "facilitator_name": "Zoho Test Teacher", "Role": "Faculty", "courses": [lookup("C1")]},
			],
			"offerings": [
				{"ID": "O1", "Term": lookup("T1"), "Course": [lookup("C1")], "status": "Completed",
				 "facilitator_name1": [lookup("F1")], "facilitator_name": []},
				{"ID": "O2", "Term": lookup("T2"), "Course": [lookup("C2")], "status": "Upcoming",
				 "facilitator_name1": [], "facilitator_name": []},
			],
			"students": [
				student("S1", "zoho-load1@example.com"),
				student("S2", "zoho-load2@example.com", level="Level 1"),
				student("S3", "zoho-load3@example.com", onboarded=False),
				student("S4", "zoho-load4@example.com", programme="A Programme Nobody Has"),
			],
			"grades": [
				grade("G1", "S1", "O1"),
				grade("G2", "S2", "O1", status="", marks=""),
				grade("G3", "S3", "O1"),
			],
			"documents": [],
		}
		self.courses = [
			{"zoho_id": "C1", "course_code": "BISTO991", "course_title": "Zoho Test One", "credits": "3",
			 "department": "BIST", "level": "1", "course_type": "Core", "programs": PROGRAMME},
			{"zoho_id": "C2", "course_code": "BISTO992", "course_title": "Zoho Test Two", "credits": "3",
			 "department": "BIST", "level": "2", "course_type": "Core", "programs": PROGRAMME},
		]
		self.balances = [
			{"zoho_id": "S1", "tuition_billed_before_erp": "10000", "tuition_paid_before_erp": "8000",
			 "term_6_2026_tuition_covered (Y/N)": "N", "other_amount_outstanding": "",
			 "scholarship_total_cap": "6000", "scholarship_monthly_discount": "500",
			 "scholarship_used_to_date": "2000", "notes": ""},
		]
		self.files = [("S1", "photo", "photo.png", PNG), ("S1", "Upload_Personal_Testimony", "testimony.txt", b"I was called.")]

	def write(self):
		os.makedirs(os.path.join(self.folder, "records"), exist_ok=True)
		os.makedirs(os.path.join(self.folder, "review"), exist_ok=True)
		for name, rows in self.records.items():
			with open(os.path.join(self.folder, "records", f"{name}.json"), "w") as handle:
				json.dump(rows, handle)
		self._csv("courses_reviewed.csv", self.courses)
		self._csv("opening_balances_filled.csv", self.balances)
		manifest = []
		for record, field, filename, content in self.files:
			path = os.path.join("files", "students", record, field, filename)
			os.makedirs(os.path.join(self.folder, os.path.dirname(path)), exist_ok=True)
			with open(os.path.join(self.folder, path), "wb") as handle:
				handle.write(content)
			manifest.append({"report": "students_Report", "record_id": record, "field": field, "path": path,
			                 "size": len(content), "sha256": hashlib.sha256(content).hexdigest()})
		with open(os.path.join(self.folder, "manifest.json"), "w") as handle:
			json.dump(manifest, handle)
		return self.folder

	def _csv(self, name, rows):
		with open(os.path.join(self.folder, "review", name), "w", newline="") as handle:
			writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
			writer.writeheader()
			writer.writerows(rows)


class TestTheLoad(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("Program", PROGRAMME):
			frappe.get_doc(
				{"doctype": "Program", "program_name": PROGRAMME_NAME, "abbr": PROGRAMME,
				 "monthly_tuition": 1500, "tuition_total": 30000}
			).insert(ignore_permissions=True)
		cls.patch = mock.patch.dict(review.PROGRAMMES, {PROGRAMME_NAME: PROGRAMME})
		cls.patch.start()

	@classmethod
	def tearDownClass(cls):
		cls.patch.stop()
		super().tearDownClass()

	def setUp(self):
		load.purge()
		self.extract = ExtractBuilder()
		self.addCleanup(shutil.rmtree, self.extract.folder, ignore_errors=True)

	def tearDown(self):
		frappe.flags.sibbcs_import = None
		load.purge()

	def _run(self, stages=load.STAGES):
		with mock.patch.dict(load.NEW_PROGRAMMES, {}, clear=True):
			return load.run(self.extract.write(), stages=stages, commit=False)

	def _student(self, zoho_id):
		return frappe.get_doc("Student", load.find("Student", zoho_id))

	def test_onboarded_students_arrive_with_an_enrollment_and_a_silent_account(self):
		summary = self._run()

		first = self._student("S1")
		self.assertEqual(first.email, "zoho-load1@example.com")
		self.assertEqual(str(first.dob), "1996-04-11")
		enrollment = frappe.get_doc("Program Enrollment", load.find("Program Enrollment", "S1"))
		self.assertEqual(enrollment.program, PROGRAMME)
		self.assertEqual(enrollment.current_level, "2")
		self.assertEqual(str(enrollment.start_term), "2031-T1")
		user = frappe.get_doc("User", first.user)
		self.assertIn("Student", [r.role for r in user.roles])
		self.assertEqual(user.user_type, "Website User")

		self.assertIsNone(load.find("Student", "S3"), "not onboarded: stays in Zoho")
		self.assertIsNone(load.find("Student", "S4"), "no programme here: held back")
		with open(os.path.join(self.extract.folder, "review", "load_problems.csv")) as handle:
			self.assertIn("S4", handle.read())
		self.assertEqual(summary["mail_queued_during_load"], 0)

	def test_history_carries_marks_and_awaits_the_unmarked(self):
		self._run()

		marked = frappe.get_doc("Course Registration", load.find("Course Registration", "G1"))
		self.assertEqual(marked.status, "Completed")
		self.assertEqual(marked.passed, 1)
		self.assertEqual(marked.final_marks, 78)
		self.assertEqual(marked.level_at_registration, "1", "the course's level, which is what promotion counts")
		self.assertEqual(marked.course_offering, "BISTO991-2031-T1")

		waiting = frappe.get_doc("Course Registration", load.find("Course Registration", "G2"))
		self.assertEqual(waiting.status, "Active")
		self.assertIsNone(load.find("Course Registration", "G3"))

	def test_no_registration_fee_no_lms_and_no_mail(self):
		with mock.patch.object(campus_lms, "configured", return_value=True), mock.patch("frappe.enqueue") as enqueue:
			self._run()
		self.assertFalse(
			[c for c in enqueue.call_args_list if "campus_lms" in str(c) or "offer_notice" in str(c)]
		)
		students = [load.find("Student", "S1"), load.find("Student", "S2")]
		invoices = frappe.get_all("Fee Invoice", filters={"student": ("in", students)}, pluck="fee_type")
		self.assertEqual(invoices, ["Monthly Tuition"], "only the opening balance")

	def test_the_opening_balance_counts_toward_the_ceiling(self):
		self._run()

		enrollment = load.find("Program Enrollment", "S1")
		invoice = frappe.get_doc("Fee Invoice", load.find("Fee Invoice", "opening:S1"))
		self.assertEqual(invoice.gross_amount, 10000)
		self.assertEqual(invoice.outstanding_amount, 2000)
		self.assertFalse(invoice.term)
		self.assertEqual(fees.tuition_billed_to_date(enrollment), 10000)
		scholarship = frappe.db.get_value(
			"Program Enrollment", enrollment,
			["scholarship_total_cap", "scholarship_monthly_discount", "scholarship_used_to_date"],
		)
		self.assertEqual(tuple(scholarship), (6000, 500, 2000))

	def test_documents_are_attached_privately_and_the_photo_is_set(self):
		self._run()

		student = self._student("S1")
		files = frappe.get_all(
			"File", filters={"attached_to_doctype": "Student", "attached_to_name": student.name},
			fields=["file_name", "is_private"],
		)
		self.assertEqual(len(files), 2)
		self.assertTrue(all(f.is_private for f in files))
		self.assertIn("Personal Testimony - testimony.txt", [f.file_name for f in files])
		self.assertTrue(student.photo)

	def test_running_it_again_changes_nothing(self):
		self._run()
		counts = {dt: frappe.db.count(dt, {"legacy_source": ("like", "zoho:%")}) for dt in load.PURGE_ORDER}

		again = self._run()

		self.assertEqual(counts, {dt: frappe.db.count(dt, {"legacy_source": ("like", "zoho:%")}) for dt in load.PURGE_ORDER})
		self.assertEqual(again["history"].get("created", 0), 0)
		self.assertEqual(again["students"].get("created", 0), 0)
		self.assertEqual(again["files"].get("attached", 0), 0)

	def test_marks_entered_in_zoho_later_arrive_on_the_next_run(self):
		self._run()
		self.extract.records["grades"][1].update(Status="Fail", Marks="41")

		self._run()

		late = frappe.get_doc("Course Registration", load.find("Course Registration", "G2"))
		self.assertEqual(late.status, "Completed")
		self.assertEqual(late.passed, 0)
		self.assertEqual(late.final_marks, 41)

	def test_what_was_here_already_is_matched_not_duplicated_and_survives_a_purge(self):
		frappe.get_doc(
			{"doctype": "Course", "course_code": "BISTO991", "course_title": "Here Before", "credits": 3,
			 "level": "1", "course_type": "Core", "department": "BIST"}
		).insert(ignore_permissions=True)

		self._run()

		self.assertEqual(frappe.db.get_value("Course", "BISTO991", "legacy_source"), "zoho:C1:matched")
		load.purge()
		self.assertTrue(frappe.db.exists("Course", "BISTO991"))
		self.assertFalse(frappe.db.get_value("Course", "BISTO991", "legacy_source"))
		frappe.delete_doc("Course", "BISTO991", force=True, ignore_permissions=True)

	def test_a_purge_takes_away_exactly_what_the_import_made(self):
		self._run()

		load.purge()

		for doctype in load.PURGE_ORDER:
			self.assertEqual(frappe.db.count(doctype, {"legacy_source": ("like", "zoho:%")}), 0, doctype)
		self.assertFalse(frappe.db.exists("Student", {"email": "zoho-load1@example.com"}))

	def test_a_purge_refuses_once_the_erp_has_built_on_an_imported_student(self):
		self._run()
		fees.create_invoice(load.find("Student", "S1"), "Application Fee", gross=10)

		with self.assertRaises(frappe.ValidationError):
			load.purge()
		frappe.db.delete("Fee Invoice", {"student": load.find("Student", "S1"), "fee_type": "Application Fee"})

	def test_the_lms_is_never_asked_for_marks_on_a_carried_over_course(self):
		"""G2 is still awaiting a mark on an ended term -- exactly what the
		hourly pull asks the LMS about. The LMS never taught it."""
		from sibbcs.academic import mark_pull

		self._run()

		self.assertNotIn("BISTO991-2031-T1", mark_pull.offerings_to_ask_about(limit=100000))
