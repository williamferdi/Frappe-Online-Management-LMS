"""Second pass: break the child-table cycles the first pass could not.

A chapter holds Lesson Reference rows pointing at its lessons, and each lesson
has a `chapter` link pointing back. Neither can go first while the other
exists, so the child rows are removed directly and the documents then delete
in the ordinary way, with their link checks still doing real work.
"""

import sys

import frappe

APPLY = "apply" in sys.argv

KEEP_LMS_COURSES = {"entrance-exam", "m-div-preliminary-orientation"}
KEEP_USERS = {"Administrator", "Guest", "ramsemz@sibbc.org"}

frappe.init(site="online.sibbc.org")
frappe.connect()
frappe.set_user("Administrator")
frappe.flags.in_migrate = True


def names(doctype, filters=None):
	try:
		return frappe.get_all(doctype, filters=filters or {}, pluck="name", limit_page_length=0)
	except Exception:
		return []


doomed_courses = [c for c in names("LMS Course") if c not in KEEP_LMS_COURSES]
doomed_chapters = names("Course Chapter", {"course": ("in", doomed_courses)}) if doomed_courses else []
doomed_lessons = names("Course Lesson", {"course": ("in", doomed_courses)}) if doomed_courses else []

print("cutting child rows that make the cycle:")
for table, field, values in (
	("Lesson Reference", "parent", doomed_chapters),
	("Chapter Reference", "parent", doomed_courses),
):
	rows = frappe.get_all(table, filters={field: ("in", values)}, pluck="name") if values else []
	print(f"   {table}: {len(rows)}")
	if APPLY and rows:
		frappe.db.delete(table, {"name": ("in", rows)})
if APPLY:
	frappe.db.commit()

ORDER = [
	("Course Lesson", lambda: doomed_lessons),
	("Course Chapter", lambda: doomed_chapters),
	("LMS Course", lambda: doomed_courses),
	("LMS Batch", lambda: names("LMS Batch")),
	("Fee Invoice", lambda: names("Fee Invoice")),
	("Course Registration", lambda: names("Course Registration")),
	("Program Enrollment", lambda: names("Program Enrollment")),
	("Admission Application", lambda: names("Admission Application")),
	("Student", lambda: names("Student")),
	("Scholarship Request", lambda: names("Scholarship Request")),
	("Course Offering", lambda: names("Course Offering")),
	("Course", lambda: names("Course")),
	("Academic Term", lambda: names("Academic Term", {"name": ("like", "DEMO-%")})),
	("Instructor", lambda: names("Instructor")),
	("Contact", lambda: [c for c in names("Contact")
	                     if c not in set(frappe.get_all("Contact", filters={"email_id": ("in", list(KEEP_USERS))}, pluck="name"))]),
	("User", lambda: [u for u in names("User") if u not in KEEP_USERS]),
]

total = 0
for attempt in range(1, 6):
	progress = 0
	blocked = []
	for doctype, resolve in ORDER:
		for name in resolve():
			if not frappe.db.exists(doctype, name):
				continue
			if not APPLY:
				blocked.append((doctype, name, "dry run"))
				continue
			try:
				frappe.delete_doc(doctype, name, ignore_permissions=True,
				                  delete_permanently=True, ignore_missing=True)
				frappe.db.commit()
				progress += 1
				total += 1
			except Exception as e:
				frappe.db.rollback()
				blocked.append((doctype, name, str(e).split("\n")[0][:110]))
	print(f"pass {attempt}: removed {progress}, still blocked {len(blocked)}")
	if not progress:
		for dt, name, err in blocked:
			print(f"   BLOCKED {dt} {name}: {err}")
		break

print(f"\ntotal removed in this run: {total}")
