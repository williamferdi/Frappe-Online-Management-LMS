# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""The admissions console.

This module arranges what `sibbcs/admissions` already does, so the tests are
about the arranging: that the bulk queries agree with the per-document truth,
that a student cannot read the pipeline, and that naming an action can never
reach a method the table does not list.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.admissions import checklist
from sibbcs.api import admissions_api, console
from sibbcs.api.test_student_api import make_student


def make_application(**overrides):
	values = {
		"doctype": "Admission Application",
		"full_name": "Console Candidate",
		"email": f"console.{frappe.generate_hash(length=8)}@example.invalid",
		"mobile": "+91 90000 00001",
		"program": "MDIV",
	}
	values.update(overrides)
	return frappe.get_doc(values).insert(ignore_permissions=True)


class TestActionDispatch(FrappeTestCase):
	"""The browser names an action; it must never name a method."""

	def test_every_action_the_checklist_offers_has_a_handler(self):
		"""A step offering a button with nothing behind it fails only when an
		officer presses it."""
		for action in set(checklist.ACTIONS.values()):
			with self.subTest(action=action):
				self.assertIn(action, admissions_api.ACTION_HANDLERS)

	def test_every_handler_resolves_to_something_callable(self):
		for action, path in admissions_api.ACTION_HANDLERS.items():
			with self.subTest(action=action):
				self.assertTrue(callable(frappe.get_attr(path)))

	def test_every_handler_is_whitelisted_in_its_own_right(self):
		"""run_action is a front door, not a way in through the back: each
		handler is an endpoint the office could already call."""
		for action, path in admissions_api.ACTION_HANDLERS.items():
			with self.subTest(action=action):
				self.assertIn(frappe.get_attr(path), frappe.whitelisted)

	def test_an_unlisted_action_is_refused(self):
		application = make_application()
		with self.assertRaises(frappe.ValidationError):
			admissions_api.run_action(application.name, "frappe.db.sql")

	def test_a_missing_application_is_refused_before_any_handler_runs(self):
		with self.assertRaises(frappe.ValidationError):
			admissions_api.run_action("APP-does-not-exist", "create_lms_account")


class TestPipeline(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_a_student_cannot_read_the_pipeline(self):
		_, _, email = make_student()
		frappe.set_user(email)

		for endpoint in (admissions_api.pipeline, admissions_api.funnel):
			with self.subTest(endpoint=endpoint.__name__):
				with self.assertRaises(frappe.PermissionError):
					endpoint()

	def test_the_list_does_not_ship_personal_data_it_does_not_need(self):
		"""A pipeline row is a person and a state.

		The photograph is deliberately in: the college asked for faces in the
		list, and a row is easier to find by the person than by the reference.
		What stays behind a click is the rest -- date of birth, address, the ID
		document and the officer.s notes -- none of which a list needs to draw
		itself.
		"""
		for field in ("dob", "address", "id_document", "notes"):
			self.assertNotIn(field, admissions_api.LIST_FIELDS)

		self.assertIn("photo", admissions_api.LIST_FIELDS)

	def test_progress_matches_what_the_checklist_itself_reports(self):
		"""The list counts done steps with one grouped query instead of loading
		each document. If the two ever disagree, the fast one is wrong."""
		application = make_application()
		checklist.update_step(application.name, checklist.NO["application_review"], "Approved")
		checklist.update_step(application.name, checklist.NO["documents"], "Verified")
		frappe.db.commit()

		bulk = admissions_api._progress_for([application.name])[application.name]
		board = checklist.board(application.name)
		per_document = sum(1 for row in board["rows"] if row["done"])

		self.assertEqual(bulk["done"], per_document)
		self.assertEqual(bulk["total"], len(checklist.STEPS))

	def test_search_matches_a_candidate_by_name(self):
		application = make_application(full_name="Findable Person")
		frappe.db.commit()

		names = [row.name for row in admissions_api.pipeline(search="Findable")["rows"]]
		self.assertIn(application.name, names)

	def test_filtering_by_state_returns_only_that_state(self):
		make_application()
		frappe.db.commit()

		for row in admissions_api.pipeline(state="Draft")["rows"]:
			self.assertEqual(row.workflow_state, "Draft")


class TestFunnel(FrappeTestCase):
	def test_a_step_with_no_row_yet_still_counts_as_outstanding(self):
		"""Eleven of the thirteen steps default to a status that is not done. A
		fresh application has no checklist rows for them, and counting only the
		rows that exist would report it as finished."""
		application = make_application()
		frappe.db.commit()

		result = admissions_api.funnel()
		waiting = {row["step"]: row["waiting"] for row in result["stuck"]}

		self.assertGreater(len(waiting), 0)
		# The application is live, so the first step is outstanding for it.
		self.assertGreaterEqual(
			waiting.get("Full Application Review", 0), 1, f"{application.name} not counted"
		)

	def test_the_state_counts_cover_every_state_even_at_zero(self):
		"""A funnel that omits empty states redraws itself differently as the
		intake moves, which makes it unreadable week to week."""
		result = admissions_api.funnel()
		self.assertEqual(
			[row["state"] for row in result["by_state"]], admissions_api.STATES
		)


class TestConsoleDashboard(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_a_guest_is_refused(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			console.dashboard()

	def test_a_student_is_refused_the_console_entirely(self):
		"""Students hold read on Fee Invoice and Program Enrollment -- they
		have to, to see their own. These panels are SQL aggregates over every
		row, so gating them on that permission handed a student the whole
		college's billing totals. They are gated on role instead."""
		_, _, email = make_student()
		frappe.set_user(email)

		with self.assertRaises(frappe.PermissionError):
			console.dashboard()

	def test_each_panel_answers_to_its_own_roles(self):
		"""Faculty see the academic figures and no fee collection; Accounts
		see the money and no candidate names."""
		cases = {
			"Faculty": {"academic"},
			"Accounts": {"finance"},
			"Admissions Officer": {"admissions"},
		}

		for role, expected in cases.items():
			with self.subTest(role=role):
				email = f"console.{frappe.generate_hash(length=8)}@example.invalid"
				frappe.set_user("Administrator")
				frappe.get_doc({
					"doctype": "User",
					"email": email,
					"first_name": role.replace(" ", ""),
					"send_welcome_email": 0,
					"roles": [{"role": role}],
				}).insert(ignore_permissions=True)

				frappe.set_user(email)
				self.assertEqual(set(console.dashboard()["panels"]), expected)
	def test_an_administrator_sees_all_three(self):
		panels = console.dashboard()["panels"]
		self.assertEqual(set(panels), {"admissions", "academic", "finance"})

	def test_finance_separates_outstanding_from_overdue(self):
		"""Outstanding reads as a problem when most of it is not due yet."""
		finance = console.dashboard()["panels"]["finance"]
		for key in ("billed", "collected", "outstanding", "overdue", "overdue_count"):
			self.assertIn(key, finance)
		self.assertLessEqual(finance["overdue"], finance["outstanding"])


class TestApplicationDetail(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_a_student_cannot_open_an_application(self):
		application = make_application()
		_, _, email = make_student()
		frappe.set_user(email)

		with self.assertRaises(frappe.PermissionError):
			admissions_api.application(application.name)

	def test_the_detail_carries_the_checklist_and_the_evidence(self):
		application = make_application()
		detail = admissions_api.application(application.name)

		for key in (
			"application",
			"checklist",
			"documents",
			"references",
			"mentors",
			"exam",
			"interview",
			"scholarship",
			"invoices",
		):
			self.assertIn(key, detail)

		self.assertEqual(len(detail["checklist"]["rows"]), len(checklist.STEPS))

	def test_the_detail_fields_all_exist_on_the_doctype(self):
		"""A field named here but absent from the DocType comes back as None
		and shows as an empty row rather than an error."""
		meta = frappe.get_meta("Admission Application")
		fieldnames = {df.fieldname for df in meta.fields} | {"name"}

		for field in admissions_api.DETAIL_FIELDS:
			self.assertIn(field, fieldnames, f"{field} is not on Admission Application")

	def test_the_list_fields_all_exist_too(self):
		meta = frappe.get_meta("Admission Application")
		fieldnames = {df.fieldname for df in meta.fields} | {"name", "creation", "modified"}

		for field in admissions_api.LIST_FIELDS:
			self.assertIn(field, fieldnames, f"{field} is not on Admission Application")
