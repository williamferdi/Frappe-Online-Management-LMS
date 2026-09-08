"""Clear the fixtures the test suite has left behind on test.local.

FrappeTestCase rolls a test back, but the endpoints under test call
`frappe.db.commit()` themselves -- so anything created before the commit
survives. After five phases that is 1,229 Course Offerings against
production's 12, and `available_offerings` iterating all of them is why the
student-API tests grew from 14 seconds to 33.

**test.local only.** The site name is checked, because running this anywhere
else would delete a college's records.

Deleted innermost-first, because a Course Offering with registrations pointing
at it will not go.
"""

import frappe

SAFE_SITE = "test.local"

# Everything the suite makes, in the order it has to go.
ORDER = (
	"Quiz Attempt",
	"Peer Review",
	"Assignment Override",
	"Assignment Submission",
	"Module Item Progress",
	"Course Module Item",
	"Course Module",
	"Course Discussion",
	"Course Group",
	"Course Group Set",
	"Course Assignment",
	"Course Grade Scheme",
	"Bank Question",
	"Question Bank",
	"Course Quiz",
	"Course Registration",
	"Level Promotion",
	"Program Enrollment",
	"Course Offering",
	"Course",
	"Student",
	"Academic Term",
)


# Every prefix the suite names its fixtures with. Anything else was seeded or
# made by hand, and is not ours to delete -- the seeded 2026 terms and the
# programmes are what several tests assert against.
#
# Adding to this list is not a guess. Find the helper that makes the name,
# then check what the widened filter would still spare: if that is anything
# other than the seeded terms and the programmes, the prefix is too broad.
TEST_PREFIXES = (
	"TST", "TSC", "TGB", "TCA", "TMD", "TSY", "TMK", "TCW", "TQZ", "TCO",
	"PNL", "SCOPE", "TQB", "TCQ",
	# Found by reading the helpers that make them, after the site reached 479
	# terms with the list above in place. `GRD` alone was 227 of them.
	"GRD", "GEN", "TPL", "TCN", "TIM", "TAP",
)


def _is_a_test_fixture(name):
	upper = (name or "").upper()
	return any(
		upper.startswith(prefix) or f"-{prefix}" in upper for prefix in TEST_PREFIXES
	)


def survey():
	return run(apply=False)


def run(apply=False, keep=200):
	"""Delete test fixtures, keeping the most recent `keep` of each kind.

	Keeping a tail rather than everything means a suite run that is mid-flight
	is not pulled out from under itself, and the seeded demo data that other
	tests rely on is far older than the cutoff.
	"""
	if frappe.local.site != SAFE_SITE:
		raise Exception(f"refusing to run on {frappe.local.site}; this is for {SAFE_SITE}")

	before = {doctype: frappe.db.count(doctype) for doctype in ORDER}
	print("PRUNE before:", {k: v for k, v in before.items() if v})

	if not apply:
		print("PRUNE dry run -- nothing deleted")
		return before

	frappe.flags.ignore_links = True
	removed = {}

	for doctype in ORDER:
		names = [
			name
			for name in frappe.get_all(
				doctype, pluck="name", order_by="creation desc", limit_start=keep,
				limit_page_length=100000,
			)
			if _is_a_test_fixture(name)
		]
		gone = 0
		for name in names:
			try:
				frappe.delete_doc(
					doctype, name, force=True, ignore_permissions=True,
					ignore_missing=True, delete_permanently=True,
				)
				gone += 1
			except Exception:
				# A fixture something else still points at; the next pass gets
				# it once its dependant is gone.
				continue
		if gone:
			removed[doctype] = gone
			frappe.db.commit()

	print("PRUNE removed:", removed)
	after = {doctype: frappe.db.count(doctype) for doctype in ORDER}
	print("PRUNE after:", {k: v for k, v in after.items() if v})
	return after


# A test helper's address, and a reserved TLD nobody can register.
FIXTURE_DOMAIN = "example.invalid"


def _unreferenced_people():
	"""Students and enrolments nothing points at, that no real person owns.

	Returned rather than deleted so the caller can look first. A student kept
	by `run()`'s tail is referenced by a surviving registration, so leaving
	them is also what stops this pass creating the orphans the last one
	cleared.
	"""
	live = set(
		frappe.db.sql_list(
			"select distinct pe.student from `tabProgram Enrollment` pe "
			"join `tabCourse Registration` cr on cr.program_enrollment = pe.name"
		)
	)

	students = []
	for row in frappe.db.sql(
		"select name, email, user, admission_application from `tabStudent`",
		as_dict=True,
	):
		if row.name in live:
			continue
		if row.admission_application:
			# Came through admissions, so somebody applied as this person.
			continue
		address = row.user or row.email or ""
		if address and not address.endswith(FIXTURE_DOMAIN):
			continue
		students.append(row.name)

	if not students:
		return [], []

	enrolments = frappe.get_all(
		"Program Enrollment",
		filters={"student": ("in", students)},
		pluck="name",
		limit_page_length=100000,
	)
	return students, enrolments


def people(apply=False):
	"""Clear test students and their enrolments. See `_unreferenced_people`."""
	if frappe.local.site != SAFE_SITE:
		raise Exception(f"refusing to run on {frappe.local.site}; this is for {SAFE_SITE}")

	students, enrolments = _unreferenced_people()
	print(f"PEOPLE would remove: {len(students)} student(s), {len(enrolments)} enrolment(s)")

	if not apply:
		print("PEOPLE dry run -- nothing deleted")
		return len(students), len(enrolments)

	frappe.flags.ignore_links = True
	gone = {"Program Enrollment": 0, "Student": 0}

	# Enrolments first: a student with one pointing at them will not go.
	for doctype, names in (("Program Enrollment", enrolments), ("Student", students)):
		for name in names:
			try:
				frappe.delete_doc(
					doctype, name, force=True, ignore_permissions=True,
					ignore_missing=True, delete_permanently=True,
				)
				gone[doctype] += 1
			except Exception:
				continue
		frappe.db.commit()

	# A student can go while their enrolment refuses to, which leaves the
	# enrolment pointing at nobody -- the shape of rubbish this is here to
	# clear, not to make.
	stragglers = frappe.db.sql_list(
		"select pe.name from `tabProgram Enrollment` pe "
		"left join `tabStudent` s on s.name = pe.student "
		"where s.name is null"
	)
	for name in stragglers:
		try:
			frappe.delete_doc(
				"Program Enrollment", name, force=True, ignore_permissions=True,
				ignore_missing=True, delete_permanently=True,
			)
			gone["Program Enrollment"] += 1
		except Exception as problem:
			# Said out loud. Swallowing this is how the two got left last time.
			print(f"PEOPLE could not remove {name}: {problem}")
	frappe.db.commit()

	left = frappe.db.sql(
		"select count(*) from `tabProgram Enrollment` pe "
		"left join `tabStudent` s on s.name = pe.student "
		"where s.name is null"
	)[0][0]

	print("PEOPLE removed:", gone)
	print(f"PEOPLE enrolments still pointing at nobody: {left}")
	return gone
