"""Third pass: the last knot.

Every remaining document is one the college asked to remove, and each is held
only by another member of the same set. Two of those holds are genuine
two-document cycles -- a Course Registration and its fee invoice each carry a
link to the other, and so do a Student and the application it came from.
Clearing one side of each cycle lets the ordinary link checks do their job on
everything else, which is safer than deleting with force and hoping nothing we
keep was pointing in.
"""

import sys

import frappe

APPLY = "apply" in sys.argv
frappe.init(site="online.sibbc.org"); frappe.connect(); frappe.set_user("Administrator")
frappe.flags.in_migrate = True

print("orphan rows on the way out:")
for dt in ("LMS Course Review", "LMS Batch Enrollment"):
	for name in frappe.get_all(dt, pluck="name"):
		print(f"   {dt} {name}")
		if APPLY:
			frappe.delete_doc(dt, name, ignore_permissions=True, delete_permanently=True,
			                  ignore_missing=True, force=True)

print("\ncutting one side of each cycle:")
for dt, field in (("Course Registration", "registration_fee_invoice"),
                  ("Student", "admission_application")):
	for row in frappe.get_all(dt, filters={field: ("is", "set")}, fields=["name", field]):
		print(f"   {dt} {row.name}.{field} = {row.get(field)} -> null")
		if APPLY:
			frappe.db.set_value(dt, row.name, field, None, update_modified=False)
if APPLY:
	frappe.db.commit()

ORDER = [
	"Fee Invoice", "Course Registration", "Program Enrollment", "Admission Application",
	"Student", "Scholarship Request", "LMS Batch", "LMS Course Review",
	"Course Offering", "Course", "Instructor",
]

KEEP_LMS_COURSES = {"entrance-exam", "m-div-preliminary-orientation"}
KEEP_USERS = {"Administrator", "Guest", "ramsemz@sibbc.org"}

print()
total = 0
for attempt in range(1, 6):
	progress, blocked = 0, []
	targets = [(dt, n) for dt in ORDER for n in frappe.get_all(dt, pluck="name")]
	targets += [("LMS Course", n) for n in frappe.get_all("LMS Course", pluck="name")
	            if n not in KEEP_LMS_COURSES]
	targets += [("Academic Term", n) for n in
	            frappe.get_all("Academic Term", filters={"name": ("like", "DEMO-%")}, pluck="name")]
	targets += [("User", n) for n in frappe.get_all("User", pluck="name") if n not in KEEP_USERS]

	for dt, name in targets:
		if not frappe.db.exists(dt, name):
			continue
		if not APPLY:
			blocked.append((dt, name, "dry run")); continue
		try:
			frappe.delete_doc(dt, name, ignore_permissions=True, delete_permanently=True,
			                  ignore_missing=True)
			frappe.db.commit()
			progress += 1; total += 1
		except Exception as e:
			frappe.db.rollback()
			blocked.append((dt, name, frappe.utils.strip_html(str(e)).replace("\n", " ")[:150]))
	print(f"pass {attempt}: removed {progress}, blocked {len(blocked)}")
	if not progress:
		for dt, name, err in blocked:
			print(f"   BLOCKED {dt} {name}: {err}")
		break

print(f"\ntotal removed: {total}")
