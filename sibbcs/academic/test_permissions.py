# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""One test per rule about who may see whose marks.

The three ways into a Course Registration are tested separately on purpose,
because closing one has never closed the others: a filtered list still hands
the record over by name, and both are irrelevant to a /staff endpoint reading
through `frappe.get_all`.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.academic import permissions
from sibbcs.academic.doctype.academic_term.test_academic_term import make_term
from sibbcs.academic.doctype.course.test_course import make_course
from sibbcs.academic.doctype.course_offering.test_course_offering import (
	make_instructor,
	make_offering,
)
from sibbcs.academic.doctype.program_enrollment.test_program_enrollment import (
	make_enrollment,
	make_student,
)
from sibbcs.api import academic_api


def make_user(email, roles, name="Scope Test"):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": name,
				"user_type": "System User",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
	user = frappe.get_doc("User", email)
	user.set("roles", [])
	for role in roles:
		user.append("roles", {"role": role})
	user.save(ignore_permissions=True)
	return email


class TestAcademicScoping(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		suffix = frappe.generate_hash(length=6)
		cls.term = make_term(f"TST-SCOPE-{suffix}", status="Open").name

		# Two teachers, one course each. The point of every test below is that
		# neither can reach into the other's.
		cls.mine_user = make_user(f"mine.{suffix}@example.invalid", ["Faculty"])
		cls.theirs_user = make_user(f"theirs.{suffix}@example.invalid", ["Faculty"])

		cls.mine_instructor = make_instructor(
			f"Scope Mine {suffix}", user=cls.mine_user
		).name
		cls.theirs_instructor = make_instructor(
			f"Scope Theirs {suffix}", user=cls.theirs_user
		).name

		cls.mine_offering = make_offering(
			make_course(f"TSC M{suffix[:3]}").name, cls.term, instructor=cls.mine_instructor, status="Published"
		).name
		cls.theirs_offering = make_offering(
			make_course(f"TSC T{suffix[:3]}").name, cls.term, instructor=cls.theirs_instructor, status="Published"
		).name

		# A student on each offering.
		cls.student = make_student(f"Scope Student {suffix}").name
		cls.enrollment = make_enrollment(cls.student).name
		cls.mine_registration = cls._register(cls.enrollment, cls.mine_offering)
		cls.theirs_registration = cls._register(cls.enrollment, cls.theirs_offering)

	@staticmethod
	def _register(enrollment, offering):
		return frappe.get_doc(
			{
				"doctype": "Course Registration",
				"program_enrollment": enrollment,
				"course_offering": offering,
				"status": "Registered",
			}
		).insert(ignore_permissions=True).name

	def tearDown(self):
		frappe.set_user("Administrator")

	# --- the helpers ------------------------------------------------------

	def test_a_teacher_is_found_through_their_instructor_record(self):
		self.assertEqual(
			permissions.offerings_for(self.mine_user), [self.mine_offering]
		)

	def test_a_teacher_with_no_instructor_record_teaches_nothing(self):
		"""Fails closed. The tempting fallback -- show everything when no
		Instructor row names the user -- makes a missing record a master key."""
		stranger = make_user("stranger.scope@example.invalid", ["Faculty"])

		self.assertEqual(permissions.offerings_for(stranger), [])
		self.assertEqual(permissions.offering_scope(stranger), [])

	def test_the_registrar_is_not_scoped_at_all(self):
		"""None and [] are different answers: the whole register, versus a
		teacher who has been given no course."""
		registrar = make_user("registrar.scope@example.invalid", ["Registrar"])

		self.assertIsNone(permissions.offering_scope(registrar))

	# --- the list ---------------------------------------------------------

	def test_a_list_shows_only_the_teachers_own_registrations(self):
		frappe.set_user(self.mine_user)

		names = frappe.get_list("Course Registration", pluck="name")

		self.assertIn(self.mine_registration, names)
		self.assertNotIn(self.theirs_registration, names)

	def test_a_student_sees_only_their_own_registrations(self):
		other = make_student("Scope Other Student")
		other_enrollment = make_enrollment(other.name, program="MDIV")
		other_registration = self._register(other_enrollment.name, self.mine_offering)

		email = make_user("scope.student@example.invalid", ["Student"])
		frappe.db.set_value("Student", self.student, "user", email)

		frappe.set_user(email)
		names = frappe.get_list("Course Registration", pluck="name")

		self.assertIn(self.mine_registration, names)
		self.assertNotIn(other_registration, names)

	# --- the same record by name -----------------------------------------

	def test_a_filtered_list_does_not_make_the_url_safe(self):
		"""The query condition hides a row from a list and does nothing at all
		about `/api/resource/Course Registration/<name>`."""
		frappe.set_user(self.mine_user)

		self.assertTrue(
			frappe.has_permission(
				"Course Registration", "read", doc=self.mine_registration
			)
		)
		self.assertFalse(
			frappe.has_permission(
				"Course Registration", "read", doc=self.theirs_registration
			)
		)

	def test_a_teacher_cannot_write_marks_on_another_teachers_course(self):
		frappe.set_user(self.mine_user)

		self.assertFalse(
			frappe.has_permission(
				"Course Registration", "write", doc=self.theirs_registration
			)
		)

	def test_save_grades_refuses_another_teachers_registration(self):
		"""`save_grades` calls check_permission and saves without
		ignore_permissions, so the hook is what that check consults."""
		frappe.set_user(self.mine_user)

		with self.assertRaises(frappe.PermissionError):
			academic_api.save_grades(
				self.theirs_registration,
				[{"component": "Assignment", "weight_pct": 100, "max_marks": 100,
				  "obtained_marks": 99}],
			)

	def test_save_grades_still_works_on_the_teachers_own_course(self):
		"""A guard that also stops the legitimate case is not a guard."""
		frappe.set_user(self.mine_user)

		result = academic_api.save_grades(
			self.mine_registration,
			[{"component": "Assignment", "weight_pct": 100, "max_marks": 100,
			  "obtained_marks": 80}],
		)

		self.assertEqual(result["final_marks"], 80)

	# --- the /staff API ---------------------------------------------------

	def test_the_roster_refuses_an_offering_the_teacher_does_not_teach(self):
		"""`roster` reads with frappe.get_all, which bypasses permissions
		entirely; without its own guard the DocType hooks never see it."""
		frappe.set_user(self.mine_user)

		with self.assertRaises(frappe.PermissionError):
			academic_api.roster(self.theirs_offering)

	def test_the_roster_still_answers_for_the_teachers_own_offering(self):
		frappe.set_user(self.mine_user)

		result = academic_api.roster(self.mine_offering)

		self.assertEqual(result["offering"]["name"], self.mine_offering)

	def test_the_offering_list_is_narrowed_to_what_the_teacher_teaches(self):
		frappe.set_user(self.mine_user)

		# This class's own term. `offerings()` pages at 200 rows ordered by
		# term, and a test site carries every term every earlier run made --
		# without this the answer depends on how much rubbish is lying about.
		names = [row["name"] for row in academic_api.offerings(term=self.term)["rows"]]

		self.assertIn(self.mine_offering, names)
		self.assertNotIn(self.theirs_offering, names)

	def test_the_registrar_still_sees_every_offering(self):
		registrar = make_user("registrar2.scope@example.invalid", ["Registrar"])
		frappe.set_user(registrar)

		names = [row["name"] for row in academic_api.offerings(term=self.term)["rows"]]

		self.assertIn(self.mine_offering, names)
		self.assertIn(self.theirs_offering, names)

	# --- the student directory -------------------------------------------

	def test_a_student_cannot_read_the_whole_student_directory(self):
		email = make_user("directory.scope@example.invalid", ["Student"])
		mine = make_student("Scope Directory Mine")
		theirs = make_student("Scope Directory Theirs")
		frappe.db.set_value("Student", mine.name, "user", email)

		frappe.set_user(email)
		names = frappe.get_list("Student", pluck="name")

		self.assertIn(mine.name, names)
		self.assertNotIn(theirs.name, names)

	def test_a_teacher_may_still_look_up_their_own_students(self):
		"""This student is on the teacher's course, which since 2026-09-11 is
		exactly what a teacher's roll is: their own students."""
		frappe.set_user(self.mine_user)

		self.assertIn(self.student, frappe.get_list("Student", pluck="name"))

	def test_a_teacher_cannot_look_up_a_student_they_do_not_teach(self):
		"""Once left open -- "looking a student up is teaching work" -- until
		the college decided a teacher holds no personal details for a student
		they never teach."""
		stranger = make_student(f"Scope Stranger {frappe.generate_hash(length=5)}").name
		make_enrollment(stranger)

		frappe.set_user(self.mine_user)

		self.assertNotIn(stranger, frappe.get_list("Student", pluck="name"))
		self.assertFalse(frappe.has_permission("Student", "read", doc=stranger))

	def test_a_teacher_with_no_course_gets_an_empty_list_not_an_error(self):
		"""The live configuration today: every Instructor record has a null
		`user`, so every Faculty user scopes to []. That becomes
		`filters["name"] = ("in", [])`, and an empty IN list is a SQL syntax
		error in the hands of the wrong query builder. It must return nothing
		rather than break the offerings screen."""
		stranger = make_user("nocourse.scope@example.invalid", ["Faculty"])
		frappe.set_user(stranger)

		result = academic_api.offerings()

		self.assertEqual(result["rows"], [])

	def test_a_teacher_with_no_course_sees_no_registrations_either(self):
		"""The same empty scope, through the query condition rather than the
		endpoint."""
		stranger = make_user("nocourse2.scope@example.invalid", ["Faculty"])
		frappe.set_user(stranger)

		self.assertEqual(frappe.get_list("Course Registration", pluck="name"), [])


class TestFeeInvoiceScoping(FrappeTestCase):
	"""A student's invoices are their own.

	Until 21 Nov 2026 `Fee Invoice` had no query condition at all, so a student
	listing it -- in Desk, or through the generic records API -- was handed
	every invoice on the site, with the names and the amounts on them.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from sibbcs.finance.test_fees import make_invoice

		suffix = frappe.generate_hash(length=6)
		cls.mine_user = make_user(f"fee.mine.{suffix}@example.invalid", ["Student"], "Fee Mine")
		cls.theirs_user = make_user(
			f"fee.theirs.{suffix}@example.invalid", ["Student"], "Fee Theirs"
		)
		cls.mine = make_student(full_name=f"Fee Mine {suffix}", user=cls.mine_user).name
		cls.theirs = make_student(full_name=f"Fee Theirs {suffix}", user=cls.theirs_user).name
		cls.mine_invoice = make_invoice(cls.mine).name
		cls.theirs_invoice = make_invoice(cls.theirs).name

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_a_student_lists_only_their_own_invoices(self):
		frappe.set_user(self.mine_user)

		names = frappe.get_list("Fee Invoice", pluck="name")

		self.assertIn(self.mine_invoice, names)
		self.assertNotIn(self.theirs_invoice, names)

	def test_a_student_cannot_reach_another_invoice_by_name(self):
		"""The query condition filters a list; this is the other half of it.
		Invoices are numbered in a series, so a name is easy to guess."""
		theirs = frappe.get_doc("Fee Invoice", self.theirs_invoice)
		mine = frappe.get_doc("Fee Invoice", self.mine_invoice)

		self.assertFalse(permissions.fee_invoice_permission(theirs, "read", self.mine_user))
		self.assertTrue(permissions.fee_invoice_permission(mine, "read", self.mine_user))

	def test_a_student_with_no_student_record_sees_nothing(self):
		"""Fails closed. An empty scope has to be `1 = 0`, not an empty
		condition, or a missing record becomes a master key."""
		orphan = make_user(
			f"fee.orphan.{frappe.generate_hash(length=6)}@example.invalid", ["Student"]
		)
		frappe.set_user(orphan)

		self.assertEqual(frappe.get_list("Fee Invoice", pluck="name"), [])

	def test_the_registrar_still_sees_every_invoice(self):
		registrar = make_user(
			f"fee.registrar.{frappe.generate_hash(length=6)}@example.invalid", ["Registrar"]
		)
		frappe.set_user(registrar)

		names = frappe.get_list("Fee Invoice", pluck="name")

		self.assertIn(self.mine_invoice, names)
		self.assertIn(self.theirs_invoice, names)


class TestStudentsHaveNoDesk(FrappeTestCase):
	"""Frappe promotes anybody holding a role with `desk_access` to System
	User, whatever `user_type` the code asked for. The Student role was
	created with the `ensure_role` default of 1, which silently overrode the
	`"user_type": "Website User"` that `conversion._create_user` spells out,
	and handed every onboarded student the whole of /app.
	"""

	def setUp(self):
		# The state the patch and `phase1_academic.build` both establish.
		frappe.db.set_value("Role", "Student", "desk_access", 0, update_modified=False)
		frappe.clear_cache()

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_the_student_role_grants_no_desk_access(self):
		self.assertEqual(frappe.db.get_value("Role", "Student", "desk_access"), 0)

	def test_the_staff_roles_keep_theirs(self):
		for role in ("Registrar", "Academic Coordinator", "Admissions Officer"):
			with self.subTest(role=role):
				if frappe.db.exists("Role", role):
					self.assertEqual(frappe.db.get_value("Role", role, "desk_access"), 1)

	def test_the_student_role_no_longer_promotes_a_portal_user(self):
		"""The regression itself: give a Website User the Student role and
		they must still be a Website User afterwards."""
		email = f"desk.check.{frappe.generate_hash(length=6)}@example.invalid"
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Desk Check",
				"user_type": "Website User",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)

		user.append("roles", {"role": "Student"})
		user.save(ignore_permissions=True)

		self.assertEqual(frappe.db.get_value("User", email, "user_type"), "Website User")

	def test_the_patch_demotes_students_and_leaves_staff_alone(self):
		"""Narrow on purpose: demoting a member of staff who happens to be
		enrolled would lock them out of their own console, which is a worse
		fault than the one being fixed."""
		from sibbcs.patches import students_are_not_desk_users

		suffix = frappe.generate_hash(length=6)
		only_student = make_user(f"demote.{suffix}@example.invalid", ["Student"], "Only Student")
		also_registrar = make_user(
			f"keep.{suffix}@example.invalid", ["Student", "Registrar"], "Staff Who Studies"
		)
		for email in (only_student, also_registrar):
			frappe.db.set_value("User", email, "user_type", "System User", update_modified=False)

		students_are_not_desk_users.execute()

		self.assertEqual(frappe.db.get_value("User", only_student, "user_type"), "Website User")
		self.assertEqual(frappe.db.get_value("User", also_registrar, "user_type"), "System User")
		self.assertEqual(frappe.db.get_value("User", "Administrator", "user_type"), "System User")


class TestFeeInvoiceAndTeachingRoles(FrappeTestCase):
	"""Who may open Fee Invoice at all, and what the condition does for them.

	On 21 Nov 2026 Faculty were reported as "still seeing every invoice"
	because `fee_invoice_query` returns an empty condition for them. They see
	none: a query condition runs only **after** the DocType permission check,
	and the permission table does not name a teaching role. These tests pin
	both gates, because the first is the one that was misread.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from sibbcs.finance.test_fees import make_invoice

		suffix = frappe.generate_hash(length=6)
		cls.owner_user = make_user(f"fee.own.{suffix}@example.invalid", ["Student"], "Fee Owner")
		cls.owner = make_student(full_name=f"Fee Owner {suffix}", user=cls.owner_user).name
		cls.invoice = make_invoice(cls.owner).name
		cls.suffix = suffix

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_the_permission_table_is_the_first_gate(self):
		"""A wide condition is not by itself a hole. This is what actually
		keeps a teacher out, and it is what a future change could undo."""
		src = (
			"Custom DocPerm"
			if frappe.db.count("Custom DocPerm", {"parent": "Fee Invoice"})
			else "DocPerm"
		)
		roles = {
			row.role
			for row in frappe.get_all(
				src,
				filters={"parent": "Fee Invoice", "read": 1, "permlevel": 0},
				fields=["role"],
			)
		}

		self.assertNotIn("Faculty", roles)
		self.assertNotIn("Facilitator", roles)
		self.assertEqual(roles, {"Accounts", "Registrar", "Student", "System Manager"})

	def test_a_teacher_is_scoped_by_the_condition_as_well(self):
		"""Belt to the permission table's braces: if a teaching role is ever
		added there, the rows are already narrowed rather than wide open."""
		teacher = make_user(
			f"fee.teacher.{self.suffix}@example.invalid", ["Faculty"], "Fee Teacher"
		)

		self.assertEqual(permissions.fee_invoice_query(teacher), permissions.NOTHING)
		self.assertFalse(
			permissions.fee_invoice_permission(
				frappe.get_doc("Fee Invoice", self.invoice), "read", teacher
			)
		)

	def test_a_teacher_who_is_also_enrolled_keeps_their_own_invoices(self):
		"""Staff do study here. Scoping teachers must not cost one of them
		sight of their own fees."""
		both = make_user(
			f"fee.both.{self.suffix}@example.invalid", ["Faculty", "Student"], "Fee Both"
		)
		student = make_student(full_name=f"Fee Both {self.suffix}", user=both).name
		from sibbcs.finance.test_fees import make_invoice

		mine = make_invoice(student).name

		condition = permissions.fee_invoice_query(both)

		self.assertIn(student, condition)
		self.assertNotEqual(condition, permissions.NOTHING)
		self.assertTrue(
			permissions.fee_invoice_permission(
				frappe.get_doc("Fee Invoice", mine), "read", both
			)
		)
		self.assertFalse(
			permissions.fee_invoice_permission(
				frappe.get_doc("Fee Invoice", self.invoice), "read", both
			)
		)

	def test_the_registrar_is_still_unrestricted(self):
		registrar = make_user(
			f"fee.reg2.{self.suffix}@example.invalid", ["Registrar"], "Fee Registrar"
		)
		self.assertEqual(permissions.fee_invoice_query(registrar), "")
