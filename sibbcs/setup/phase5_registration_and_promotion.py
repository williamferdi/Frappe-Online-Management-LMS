"""Pay-then-enrol, and the eight-course promotion gate.

    bench --site online.sibbc.org execute \\
        sibbcs.setup.phase5_registration_and_promotion.build

Idempotent.

Two rules the college asked for:

**A registration opens the course when the fee is settled**, not when the
student presses Register. Registering is the student saying yes; paying is
what buys the seat. Nothing here enforces that -- `Course Registration
.maybe_sync_lms` does -- but the escape hatch is worth stating plainly:

    bench --site <site> set-config require_fee_for_lms_access 0

turns the gate off. **That matters right now**: with no payment gateway
configured, the gate is the difference between a working term and nobody
reaching a course. Leave it off until Razorpay or Jodo is live, or settle each
invoice by hand from Desk.

**A level takes eight passed courses.** The figure sits on
`Program.courses_per_level`, seeded to 8, so revising it is a field edit.
Zero switches the gate off for that program.
"""

import frappe

from sibbcs.setup.schema import add_fields, check, f, read

DEAN = "Dean"
DEFAULT_COURSES_PER_LEVEL = 8


def _dean_role():
	"""The approver the college named, which did not exist as a role."""
	if frappe.db.exists("Role", DEAN):
		return False

	frappe.get_doc(
		{
			"doctype": "Role",
			"role_name": DEAN,
			"desk_access": 1,
			"is_custom": 1,
		}
	).insert(ignore_permissions=True)
	return True


def _program_fields():
	return add_fields(
		"Program",
		[
			f(
				"courses_per_level",
				"Courses per Level",
				"Int",
				default=str(DEFAULT_COURSES_PER_LEVEL),
				description=(
					"Passed courses a student must have at their current level "
					"before they can be promoted. Zero switches the check off."
				),
			)
		],
	)


def _seed_courses_per_level():
	seeded = {}
	for program in frappe.get_all("Program", pluck="name"):
		if frappe.db.get_value("Program", program, "courses_per_level"):
			continue
		frappe.db.set_value(
			"Program",
			program,
			"courses_per_level",
			DEFAULT_COURSES_PER_LEVEL,
			update_modified=False,
		)
		seeded[program] = DEFAULT_COURSES_PER_LEVEL
	return seeded


def _promotion_fields():
	return add_fields(
		"Level Promotion",
		[
			check(
				"override_shortfall",
				"Override Shortfall",
				description=(
					"Promote a student who has not passed the required number of "
					"courses. Dean, Registrar or Academic Coordinator only, and the "
					"reason belongs in Remarks."
				),
			)
		],
		insert_after="to_level",
	)


def _dean_permissions():
	"""What the Dean can see. Read everywhere they need evidence, write where
	they decide."""
	from sibbcs.setup.schema import edit

	granted = []
	for doctype, row in (
		("Level Promotion", edit(DEAN)),
		("Program Enrollment", read(DEAN)),
		("Course Registration", read(DEAN)),
		("Student", read(DEAN)),
		("Program", read(DEAN)),
		("Course", read(DEAN)),
	):
		if not frappe.db.exists("DocType", doctype):
			continue
		if frappe.db.exists("DocPerm", {"parent": doctype, "role": DEAN, "permlevel": 0}):
			continue
		doc = frappe.get_doc("DocType", doctype)
		doc.append("permissions", row)
		doc.save(ignore_permissions=True)
		granted.append(doctype)
	return granted


def build():
	made_role = _dean_role()
	added = _program_fields() + _promotion_fields()
	seeded = _seed_courses_per_level()
	granted = _dean_permissions()

	frappe.db.commit()
	for doctype in ("Program", "Level Promotion"):
		frappe.clear_cache(doctype=doctype)

	from sibbcs.academic.doctype.course_registration.course_registration import (
		require_fee_before_lms,
	)

	print(f"Role {DEAN}: {'created' if made_role else 'already present'}")
	print(f"Added: {added or 'nothing new'}")
	print(f"courses_per_level seeded: {seeded or 'none (already set)'}")
	print(f"{DEAN} granted on: {granted or 'nothing new'}")
	print(f"Fee gates LMS access: {require_fee_before_lms()}")
	if require_fee_before_lms():
		print("  No payment gateway is configured. Until one is, either settle each")
		print("  registration invoice in Desk or run:")
		print("    bench --site <site> set-config require_fee_for_lms_access 0")
