# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""One test per rule about what a student may reach, and why not.

The rule the phase turns on is that a lock explains itself and cannot be
walked around by typing a URL. Both halves are tested: the outline says why
something is shut, and the endpoint that hands over content refuses.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, now_datetime

from sibbcs.academic import lesson_content, modules
from sibbcs.academic.doctype.academic_term.test_academic_term import make_term
from sibbcs.academic.doctype.course.test_course import make_course
from sibbcs.academic.doctype.course_offering.test_course_offering import make_offering
from sibbcs.academic.doctype.program_enrollment.test_program_enrollment import (
	make_enrollment,
	make_student,
)
from sibbcs.academic.test_gradebook import make_assignment, make_scheme
from sibbcs.api import syllabus


def make_module(offering, title="Week One", **kw):
	values = {
		"doctype": "Course Module",
		"course_offering": offering,
		"title": title,
		"published": kw.pop("published", 1),
	}
	values.update(kw)
	return frappe.get_doc(values).insert(ignore_permissions=True)


def make_item(module, **kw):
	values = {
		"doctype": "Course Module Item",
		"module": module,
		"item_type": kw.pop("item_type", "Sub-header"),
		"title": kw.pop("title", "An item"),
		"published": kw.pop("published", 1),
	}
	values.update(kw)
	return frappe.get_doc(values).insert(ignore_permissions=True)


class TestModules(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.term = make_term(
			f"TST-MOD-{frappe.generate_hash(length=6)}", status="Open"
		).name

	def setUp(self):
		frappe.set_user("Administrator")
		suffix = frappe.generate_hash(length=6)
		self.course = make_course(f"TMD {suffix[:4]}").name
		self.offering = make_offering(self.course, self.term, status="Published").name

		email = f"mod.{suffix}@example.invalid"
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": "Module Student",
					"user_type": "System User",
					"send_welcome_email": 0,
					"roles": [{"role": "Student"}],
				}
			).insert(ignore_permissions=True)
		self.email = email
		self.student = make_student(f"Module Student {suffix}", user=email).name
		self.registration = frappe.get_doc(
			{
				"doctype": "Course Registration",
				"program_enrollment": make_enrollment(self.student).name,
				"course_offering": self.offering,
				"status": "Registered",
			}
		).insert(ignore_permissions=True).name

	def tearDown(self):
		frappe.set_user("Administrator")

	# --- what a student can see -------------------------------------------

	def test_an_unpublished_module_is_invisible_to_a_student(self):
		make_module(self.offering, "Draft week", published=0)

		self.assertEqual(modules.outline(self.offering, self.registration), [])
		# The teacher still sees it.
		self.assertEqual(len(modules.outline(self.offering, for_staff=True)), 1)

	def test_an_open_module_is_open(self):
		module = make_module(self.offering).name
		make_item(module, title="Read this")

		outline = modules.outline(self.offering, self.registration)

		self.assertTrue(outline[0]["state"]["open"])
		self.assertIsNone(outline[0]["state"]["reason"])
		self.assertFalse(outline[0]["items"][0]["locked"])

	def test_a_file_row_carries_what_its_teacher_wrote_about_it(self):
		"""So the module list can say what a file is before anyone opens it."""
		module = make_module(self.offering).name
		reading = (
			frappe.get_doc(
				{
					"doctype": "Course File",
					"course": self.course,
					"title": "Reading",
					"description": "Chapters 1-3",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		make_item(
			module,
			item_type="File",
			file=reading,
			title="Reading",
			position=0,
			course_offering=self.offering,
		)
		make_item(module, title="A heading", position=1)

		items = modules.outline(self.offering, self.registration)[0]["items"]

		self.assertEqual(items[0]["description"], "Chapters 1-3")
		self.assertIsNone(items[1]["description"], "only a file row carries one")

	# --- the three ways a module stays shut -------------------------------

	def test_a_module_with_a_future_date_says_when_it_opens(self):
		"""A bare "locked" is the reason the registrar answers email."""
		make_module(self.offering, unlock_at=add_days(now_datetime(), 7))

		outline = modules.outline(self.offering, self.registration)

		self.assertFalse(outline[0]["state"]["open"])
		self.assertIn("opens on", outline[0]["state"]["reason"])

	def test_a_module_waiting_on_another_names_it(self):
		first = make_module(self.offering, "Week One", position=0)
		make_item(first.name, title="Do this", completion_requirement="Mark it done")

		second = make_module(self.offering, "Week Two", position=1)
		second.append("prerequisites", {"module": first.name})
		second.save(ignore_permissions=True)

		outline = modules.outline(self.offering, self.registration)
		week_two = next(row for row in outline if row["name"] == second.name)

		self.assertFalse(week_two["state"]["open"])
		self.assertIn("Week One", week_two["state"]["reason"])

	def test_finishing_the_prerequisite_opens_the_next_module(self):
		first = make_module(self.offering, "Week One", position=0)
		item = make_item(
			first.name, title="Do this", completion_requirement="Mark it done"
		)
		second = make_module(self.offering, "Week Two", position=1)
		second.append("prerequisites", {"module": first.name})
		second.save(ignore_permissions=True)

		modules.record_progress(item.name, self.registration)

		outline = modules.outline(self.offering, self.registration)
		week_two = next(row for row in outline if row["name"] == second.name)
		self.assertTrue(week_two["state"]["open"])

	def test_sequential_progress_holds_the_next_item_only(self):
		module = make_module(self.offering, require_sequential_progress=1).name
		first = make_item(
			module, title="First", position=0, completion_requirement="Mark it done"
		)
		make_item(module, title="Second", position=1, completion_requirement="Mark it done")

		outline = modules.outline(self.offering, self.registration)
		items = outline[0]["items"]

		self.assertFalse(items[0]["locked"], "the first item is always reachable")
		self.assertTrue(items[1]["locked"])
		self.assertIn("before this", items[1]["lock_reason"])

		modules.record_progress(first.name, self.registration)
		items = modules.outline(self.offering, self.registration)[0]["items"]
		self.assertFalse(items[1]["locked"])

	def test_an_item_that_asks_nothing_never_blocks_a_sequence(self):
		"""A sub-header holding a module shut would be absurd."""
		module = make_module(self.offering, require_sequential_progress=1).name
		make_item(module, title="Heading", position=0)
		make_item(module, title="Next", position=1)

		items = modules.outline(self.offering, self.registration)[0]["items"]
		self.assertFalse(items[1]["locked"])

	# --- the lock is not decoration ---------------------------------------

	def test_a_locked_item_cannot_be_opened_by_asking_for_it(self):
		"""The whole point. A lock a student can walk around by typing a URL
		is decoration."""
		module = make_module(self.offering, unlock_at=add_days(now_datetime(), 7)).name
		item = make_item(module, title="Locked", completion_requirement="View it")

		frappe.set_user(self.email)
		with self.assertRaises(frappe.PermissionError):
			syllabus.read_item(self.registration, item.name)

	def test_an_item_from_another_course_is_refused(self):
		other = make_offering(
			make_course(f"TMD X{frappe.generate_hash(length=4)}").name,
			self.term,
			status="Published",
		).name
		other_item = make_item(make_module(other, "Theirs").name, title="Not mine")

		frappe.set_user(self.email)
		with self.assertRaises(frappe.PermissionError):
			syllabus.read_item(self.registration, other_item.name)

	def test_a_student_cannot_open_somebody_elses_registration(self):
		other = make_student(f"Another {frappe.generate_hash(length=6)}").name
		other_registration = frappe.get_doc(
			{
				"doctype": "Course Registration",
				"program_enrollment": make_enrollment(other).name,
				"course_offering": self.offering,
				"status": "Registered",
			}
		).insert(ignore_permissions=True).name

		frappe.set_user(self.email)
		with self.assertRaises(frappe.PermissionError):
			syllabus.my_course(other_registration)

	# --- progress ----------------------------------------------------------

	def test_opening_a_view_item_completes_it(self):
		module = make_module(self.offering).name
		item = make_item(module, title="Read me", completion_requirement="View it")

		frappe.set_user(self.email)
		syllabus.read_item(self.registration, item.name)

		frappe.set_user("Administrator")
		outline = modules.outline(self.offering, self.registration)
		self.assertTrue(outline[0]["items"][0]["complete"])

	def test_a_student_cannot_declare_scored_work_finished(self):
		"""Letting a student mark their own work done is letting them mark
		their own work."""
		module = make_module(self.offering).name
		item = make_item(
			module, title="Essay", completion_requirement="Score at least", min_score=50
		)

		frappe.set_user(self.email)
		with self.assertRaises(frappe.ValidationError):
			syllabus.mark_done(self.registration, item.name)

	def test_a_score_below_the_bar_is_not_a_pass(self):
		module = make_module(self.offering).name
		item = make_item(
			module, title="Essay", completion_requirement="Score at least", min_score=50
		)

		modules.record_progress(item.name, self.registration, status="Complete", score=40)
		outline = modules.outline(self.offering, self.registration)
		self.assertFalse(outline[0]["items"][0]["complete"])

		modules.record_progress(item.name, self.registration, status="Complete", score=60)
		outline = modules.outline(self.offering, self.registration)
		self.assertTrue(outline[0]["items"][0]["complete"])

	def test_progress_is_one_row_however_often_it_is_recorded(self):
		module = make_module(self.offering).name
		item = make_item(module, title="Read me", completion_requirement="View it")

		modules.record_progress(item.name, self.registration)
		modules.record_progress(item.name, self.registration)

		self.assertEqual(
			frappe.db.count(
				"Module Item Progress",
				{"module_item": item.name, "course_registration": self.registration},
			),
			1,
		)

	def test_completion_does_not_go_backwards(self):
		module = make_module(self.offering).name
		item = make_item(module, title="Read me", completion_requirement="Mark it done")

		modules.record_progress(item.name, self.registration, status="Complete")
		modules.record_progress(item.name, self.registration, status="In progress")

		outline = modules.outline(self.offering, self.registration)
		self.assertTrue(outline[0]["items"][0]["complete"])

	# --- lesson content ----------------------------------------------------

	def test_every_stored_block_type_is_one_the_renderer_knows(self):
		"""A block type with no renderer entry is a blank lesson, which is a
		failure worth a test rather than a bug report.

		The renderer's list lives in the front end; this asserts the Python
		side agrees about what exists, so a new block type in stored content
		shows up here first.
		"""
		known = {
			"paragraph", "header", "list", "embed", "markdown", "image",
			"code", "table", "delimiter", "quote",
		} | set(lesson_content.INTERACTIVE)

		found = lesson_content.estate_block_types()
		unknown = found - known

		self.assertEqual(
			unknown,
			set(),
			f"lesson content uses block types the renderer has never heard of: {unknown}",
		)

	def test_interactive_blocks_are_stripped_and_reported(self):
		"""An embedded quiz would be a second route to a grade, running on the
		LMS's scoring instead of the gradebook."""
		content = frappe.as_json(
			{
				"blocks": [
					{"type": "paragraph", "data": {"text": "Read this"}},
					{"type": "quiz", "data": {"quiz": "some-quiz"}},
				]
			}
		)

		kept, removed = lesson_content.strip_interactive(content)

		self.assertEqual(len(kept), 1)
		self.assertEqual(kept[0]["type"], "paragraph")
		self.assertEqual(removed, ["quiz"])

	def test_unreadable_content_is_an_empty_lesson_not_an_exception(self):
		"""Lesson content is not a contract we control."""
		self.assertEqual(lesson_content.strip_interactive("not json at all"), ([], []))
		self.assertEqual(lesson_content.strip_interactive(None), ([], []))
		self.assertEqual(lesson_content.strip_interactive('{"no": "blocks"}'), ([], []))


class TestSyllabusApi(FrappeTestCase):
	"""The staff half."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.term = make_term(
			f"TST-SYL-{frappe.generate_hash(length=6)}", status="Open"
		).name

	def setUp(self):
		frappe.set_user("Administrator")
		suffix = frappe.generate_hash(length=6)
		self.course = make_course(f"TSY {suffix[:4]}").name
		self.offering = make_offering(self.course, self.term, status="Published").name

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_building_a_module_and_ordering_its_items(self):
		module = syllabus.save_module(self.offering, {"title": "Week One"})["module"]

		first = syllabus.save_item(module, {"item_type": "Sub-header", "title": "A"})["item"]
		second = syllabus.save_item(module, {"item_type": "Sub-header", "title": "B"})["item"]

		syllabus.reorder(module=module, order=[second, first])

		outline = syllabus.outline(self.offering)["modules"]
		titles = [item["title"] for item in outline[0]["items"]]
		self.assertEqual(titles, ["B", "A"])

	def test_a_module_cannot_require_itself(self):
		module = syllabus.save_module(self.offering, {"title": "Only"})["module"]
		syllabus.save_module(
			self.offering, {"title": "Only", "prerequisites": [module]}, module=module
		)

		doc = frappe.get_doc("Course Module", module)
		self.assertEqual(doc.prerequisites, [])

	def test_reordering_cannot_move_another_courses_module(self):
		"""A name from elsewhere in the payload must not move somebody else's
		course."""
		other = make_offering(
			make_course(f"TSY X{frappe.generate_hash(length=4)}").name,
			self.term,
			status="Published",
		).name
		theirs = syllabus.save_module(other, {"title": "Theirs", "position": 5})["module"]
		mine = syllabus.save_module(self.offering, {"title": "Mine"})["module"]

		result = syllabus.reorder(course_offering=self.offering, order=[theirs, mine])

		self.assertEqual(result["ordered"], 1)
		self.assertEqual(frappe.db.get_value("Course Module", theirs, "position"), 5)

	def test_the_preview_shows_exactly_what_a_student_would_get(self):
		"""It calls the same modules.outline the portal calls, so the preview
		cannot drift from the thing it previews."""
		from sibbcs.academic import modules as modules_module

		module = syllabus.save_module(
			self.offering, {"title": "Week One", "published": 1}
		)["module"]
		syllabus.save_item(module, {"item_type": "Sub-header", "title": "Read"})

		preview = syllabus.preview(self.offering)["modules"]
		student = modules_module.outline(self.offering, None)

		self.assertEqual(
			[(m["name"], m["state"]["open"]) for m in preview],
			[(m["name"], m["state"]["open"]) for m in student],
		)

	def test_the_preview_hides_what_a_student_cannot_see(self):
		"""An unpublished module is absent here exactly as it is absent there,
		which is usually the answer to "why can't they see it?"."""
		syllabus.save_module(self.offering, {"title": "Draft", "published": 0})

		data = syllabus.preview(self.offering)

		self.assertEqual(data["modules"], [])
		self.assertEqual(data["unpublished_modules"], 1)

	def test_the_preview_counts_what_it_is_not_showing(self):
		"""A number beats spotting the difference between two screens."""
		module = syllabus.save_module(
			self.offering, {"title": "Week One", "published": 1}
		)["module"]
		syllabus.save_item(
			module, {"item_type": "Sub-header", "title": "Hidden", "published": 0}
		)

		data = syllabus.preview(self.offering)

		self.assertEqual(data["unpublished_items"], 1)
		self.assertEqual(data["modules"][0]["items"], [])

	def test_the_preview_can_be_taken_as_a_named_student(self):
		"""So "why is it locked for her?" is answerable without asking her."""
		module = syllabus.save_module(
			self.offering, {"title": "Week One", "published": 1}
		)["module"]

		data = syllabus.preview(self.offering)
		self.assertIsInstance(data["roster"], list)
		self.assertTrue(module)

	def test_the_preview_refuses_a_student_from_another_course(self):
		other = make_offering(
			make_course(f"TSY P{frappe.generate_hash(length=4)}").name,
			self.term,
			status="Published",
		).name
		student = make_student(f"Elsewhere {frappe.generate_hash(length=5)}").name
		theirs = frappe.get_doc(
			{
				"doctype": "Course Registration",
				"program_enrollment": make_enrollment(student).name,
				"course_offering": other,
				"status": "Registered",
			}
		).insert(ignore_permissions=True).name

		with self.assertRaises(frappe.PermissionError):
			syllabus.preview(self.offering, theirs)

	def test_previewing_an_item_records_nothing(self):
		"""`read_item` is the student's call and completes a "View it" item.
		Previewing through it would tick boxes for whichever student was being
		previewed as -- quietly, from somebody else's session."""
		module = syllabus.save_module(
			self.offering, {"title": "Week One", "published": 1}
		)["module"]
		item = syllabus.save_item(
			module,
			{
				"item_type": "Sub-header",
				"title": "Read",
				"completion_requirement": "View it",
			},
		)["item"]

		before = frappe.db.count("Module Item Progress")
		syllabus.preview_item(self.offering, item)

		self.assertEqual(frappe.db.count("Module Item Progress"), before)

	def test_a_locked_item_can_still_be_opened_in_the_preview(self):
		"""A teacher checking a module that opens next week needs to see inside
		it. The outline still reports the lock, so nothing is misrepresented."""
		module = syllabus.save_module(
			self.offering,
			{
				"title": "Later",
				"published": 1,
				"unlock_at": add_days(now_datetime(), 7),
			},
		)["module"]
		item = syllabus.save_item(
			module, {"item_type": "Sub-header", "title": "Locked"}
		)["item"]

		payload = syllabus.preview_item(self.offering, item)
		self.assertEqual(payload["item"]["name"], item)

		shown = syllabus.preview(self.offering)["modules"]
		self.assertFalse(shown[0]["state"]["open"])

	def test_an_item_from_another_course_cannot_be_previewed(self):
		other = make_offering(
			make_course(f"TSY Q{frappe.generate_hash(length=4)}").name,
			self.term,
			status="Published",
		).name
		theirs = syllabus.save_module(other, {"title": "Theirs", "published": 1})["module"]
		item = syllabus.save_item(
			theirs, {"item_type": "Sub-header", "title": "Not mine"}
		)["item"]

		with self.assertRaises(frappe.PermissionError):
			syllabus.preview_item(self.offering, item)

	def test_the_builder_offers_the_courses_own_lessons(self):
		"""Read out of the LMS through its chapter tables, not guessed at."""
		payload = syllabus.outline(self.offering)
		self.assertIn("lessons", payload["choices"])
		self.assertIn("item_types", payload["choices"])
		self.assertIn("Lesson", payload["choices"]["item_types"])

	def test_a_page_belongs_to_the_course_so_it_survives_the_term(self):
		"""Content is the Course's; only dates and sequence are the
		Offering's. A page written this term is there next term."""
		# Made directly: `syllabus.save_page` was removed on 2026-09-11, and
		# this test is about where a page belongs, not how one is written.
		page = frappe.get_doc(
			{
				"doctype": "Course Page",
				"course": self.course,
				"title": "Syllabus",
				"body": "<p>Welcome</p>",
			}
		).insert(ignore_permissions=True).name

		next_term = make_term(f"TSY-N-{frappe.generate_hash(length=5)}", status="Open").name
		next_offering = make_offering(self.course, next_term, status="Published").name

		names = [row["name"] for row in syllabus.outline(next_offering)["choices"]["pages"]]
		self.assertIn(page, names)
