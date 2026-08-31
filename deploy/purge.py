"""Remove the testing and demo data from online.sibbc.org.

Keeps the Entrance Exam and M.Div. Preliminary Orientation courses, the four
programs, the five real academic terms, the fee types, the DEMO Grade Scale
(the only one on the site, kept on the college's instruction) and the staff
account ramsemz@sibbc.org.

Run with no argument for a dry run. Run with `apply` to delete.
"""

import sys

import frappe

APPLY = "apply" in sys.argv

KEEP_LMS_COURSES = {"entrance-exam", "m-div-preliminary-orientation"}
KEEP_USERS = {"Administrator", "Guest", "ramsemz@sibbc.org"}
KEEP_QUIZZES = {"entrance-exam-essays"}

frappe.init(site="online.sibbc.org")
frappe.connect()
frappe.set_user("Administrator")
frappe.flags.in_migrate = True  # quiet the on_trash side effects that email people

removed, failed, skipped = [], [], []


def names(doctype, filters=None):
	try:
		return frappe.get_all(doctype, filters=filters or {}, pluck="name", limit_page_length=0)
	except Exception:
		return []


def drop(doctype, docnames, force=False):
	for name in docnames:
		if not frappe.db.exists(doctype, name):
			continue
		if not APPLY:
			removed.append((doctype, name))
			continue
		try:
			frappe.delete_doc(
				doctype, name, force=force, ignore_permissions=True,
				delete_permanently=True, ignore_missing=True,
			)
			removed.append((doctype, name))
		except Exception as e:
			failed.append((doctype, name, str(e).split("\n")[0][:160]))


# ---------------------------------------------------------------------------
# what goes
# ---------------------------------------------------------------------------
doomed_lms = [c for c in names("LMS Course") if c not in KEEP_LMS_COURSES]
doomed_chapters = names("Course Chapter", {"course": ("in", doomed_lms)}) if doomed_lms else []
doomed_lessons = names("Course Lesson", {"course": ("in", doomed_lms)}) if doomed_lms else []
doomed_quizzes = [q for q in names("LMS Quiz") if q not in KEEP_QUIZZES]
doomed_questions = []
for quiz in doomed_quizzes:
	doomed_questions += frappe.get_all(
		"LMS Quiz Question", filters={"parent": quiz}, pluck="question"
	)

doomed_users = [u for u in names("User") if u not in KEEP_USERS]
# Every contact except the ones belonging to the accounts we keep.
kept_contacts = set(
	frappe.get_all("Contact", filters={"email_id": ("in", list(KEEP_USERS))}, pluck="name")
)
doomed_contacts = [c for c in names("Contact") if c not in kept_contacts]
doomed_courses = names("Course")    # six DEMO + BISTO608, all going

# entrance-exam is a course we keep, and it lists a doomed user as an
# instructor. The child row has to go on its own, or it outlives the User
# and leaves the course pointing at an account that no longer exists.
stale_instructors = frappe.get_all(
	"Course Instructor",
	filters={"instructor": ("in", doomed_users), "parent": ("in", list(KEEP_LMS_COURSES))},
	fields=["name", "parent", "instructor"],
)

# Deepest first: children before parents, so link checks stay meaningful.
PLAN = [
	("Manual Acknowledgement", names("Manual Acknowledgement")),
	("LMS Course Progress", names("LMS Course Progress")),
	("LMS Enrollment", names("LMS Enrollment")),
	("LMS Quiz Submission", names("LMS Quiz Submission")),
	("LMS Certificate", names("LMS Certificate")),
	("LMS Batch", names("LMS Batch")),
	("Course Lesson", doomed_lessons),
	("Course Chapter", doomed_chapters),
	("LMS Quiz", doomed_quizzes),
	("LMS Question", doomed_questions),
	("LMS Course", doomed_lms),

	("Payment Entry", names("Payment Entry")),
	("Fee Invoice", names("Fee Invoice")),
	("Level Promotion", names("Level Promotion")),
	("Course Registration", names("Course Registration")),
	("Program Enrollment", names("Program Enrollment")),
	("Student", names("Student")),

	("Qualifying Exam Result", names("Qualifying Exam Result")),
	("Interview Record", names("Interview Record")),
	("Scholarship Request", names("Scholarship Request")),
	("Admission Application", names("Admission Application")),
	("Lead", names("Lead")),

	("Course Offering", names("Course Offering")),
	("Course", doomed_courses),
	("Academic Term", names("Academic Term", {"name": ("like", "DEMO-%")})),
	("Instructor", names("Instructor")),
	("Reading Manual", names("Reading Manual", {"is_active": 0})),

	("Contact", doomed_contacts),
	("User", doomed_users),
	("Email Queue", names("Email Queue")),
]

print("stale instructor rows on kept courses:")
for row in stale_instructors:
	print(f"   {row.parent} <- {row.instructor}  ({row.name})")
	if APPLY:
		frappe.db.delete("Course Instructor", {"name": row.name})
print()

if not APPLY:
	print("DRY RUN — nothing will be deleted\n")
	# What still points at each user, so a failed User delete is no surprise.
	for user in doomed_users:
		links = []
		for dt, field in (
			("LMS Course Progress", "member"), ("LMS Enrollment", "member"),
			("Course Instructor", "instructor"), ("LMS Batch Enrollment", "member"),
			("ToDo", "allocated_to"), ("Student", "user"),
		):
			try:
				hits = frappe.get_all(dt, filters={field: user}, limit_page_length=0)
				if hits:
					links.append(f"{dt}.{field}×{len(hits)}")
			except Exception:
				pass
		print(f"  user {user}: {', '.join(links) or 'no links found'}")
	print()

for doctype, docnames in PLAN:
	if docnames:
		print(f"{doctype:26} {len(docnames)}")
		drop(doctype, docnames)

if APPLY:
	frappe.db.commit()

print(f"\n{'deleted' if APPLY else 'would delete'}: {len(removed)}")
if failed:
	print(f"failed: {len(failed)}")
	for dt, name, err in failed:
		print(f"   {dt} {name}: {err}")

print("\n-- what remains --")
for dt in ("LMS Course", "LMS Quiz", "Course Lesson", "Course Chapter", "Admission Application",
           "Student", "Program Enrollment", "Course", "Course Offering", "Academic Term",
           "Program", "Fee Type", "Grade Scale", "User", "Contact", "Lead", "Reading Manual"):
	try:
		rows = frappe.get_all(dt, pluck="name", limit_page_length=0)
		print(f"{dt:26} {len(rows):3}  {', '.join(rows[:8])}{' …' if len(rows) > 8 else ''}")
	except Exception as e:
		print(f"{dt:26} n/a")
