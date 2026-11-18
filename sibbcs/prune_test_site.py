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
	"Course Grade Scheme",
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
	# 2026-11-18, after the suite reached 723s. Found by extracting every
	# literal passed to `make_course`, `make_term` and `make_offering` across
	# the suite rather than by guessing, which is how the list went stale
	# twice. `TCB` alone was 262 courses. `TMP` covers `TMPX` by prefix.
	"TTS", "TTR", "TMP", "TFE", "TCL", "TCB",
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


# ---------------------------------------------------------------------------
# what no prefix can reach
# ---------------------------------------------------------------------------

# Rows named by series -- FEE-2026-00231, INS-00144 -- can never be matched by
# name, so they are found by what they point at instead. Each rule is a
# doctype and the SQL that finds rows whose owner has already gone.
ORPHAN_RULES = (
	(
		"Fee Invoice",
		"""
		select fi.name from `tabFee Invoice` fi
		left join `tabProgram Enrollment` pe on pe.name = fi.program_enrollment
		where fi.program_enrollment is not null and fi.program_enrollment != ''
		  and pe.name is null
		""",
	),
	(
		"Fee Invoice",
		"""
		select fi.name from `tabFee Invoice` fi
		left join `tabStudent` s on s.name = fi.student
		where fi.student is not null and fi.student != '' and s.name is null
		""",
	),
	(
		"Course Grade Scheme",
		"""
		select cgs.name from `tabCourse Grade Scheme` cgs
		left join `tabCourse Offering` co on co.name = cgs.course_offering
		where co.name is null
		""",
	),
	(
		"Course Registration",
		"""
		select cr.name from `tabCourse Registration` cr
		left join `tabCourse Offering` co on co.name = cr.course_offering
		where co.name is null
		""",
	),
	(
		"Instructor",
		# Fixture instructors only: the address is the test helper's, and
		# nothing still being taught points at them.
		"""
		select i.name from `tabInstructor` i
		where (i.email like '%%@example.invalid' or i.user like '%%@example.invalid')
		  and not exists (
			select 1 from `tabCourse Offering` co
			where co.instructor = i.name or co.facilitator = i.name
		  )
		""",
	),
)

# Frappe's own bookkeeping. On a site whose only purpose is to be rebuilt by
# the next test run, none of it is evidence of anything: 40,000 Comments and a
# Deleted Document graveyard are what five phases of fixtures leave behind.
HOUSEKEEPING = ("Comment", "Version", "Deleted Document", "Error Log", "Activity Log")


def leftovers(apply=False, keep=50):
	"""Clear what `run()` and `people()` cannot name.

	Run after both: every rule here finds rows by the absence of something
	those two have just deleted, so running it first finds almost nothing.
	"""
	if frappe.local.site != SAFE_SITE:
		raise Exception(f"refusing to run on {frappe.local.site}; this is for {SAFE_SITE}")

	# A set per doctype, not a list: two rules can both catch the same row --
	# a fee invoice whose enrolment AND whose student have gone -- and a
	# report that counts it twice claims more rows than the table holds.
	found = {}
	for doctype, sql in ORPHAN_RULES:
		names = frappe.db.sql_list(sql)
		if names:
			found.setdefault(doctype, set()).update(names)

	# These two exist only because a test made them; there is no seeded
	# announcement or message on this site. A tail is kept so a run in flight
	# is not pulled out from under itself.
	for doctype in ("Portal Message", "Announcement"):
		names = frappe.get_all(
			doctype, pluck="name", order_by="creation desc",
			limit_start=keep, limit_page_length=100000,
		)
		if names:
			found.setdefault(doctype, set()).update(names)

	print("LEFTOVERS would remove:", {k: len(v) for k, v in found.items()})
	if not apply:
		print("LEFTOVERS dry run -- nothing deleted")
		return found

	frappe.flags.ignore_links = True
	gone = {}
	for doctype, names in found.items():
		for name in names:
			try:
				frappe.delete_doc(
					doctype, name, force=True, ignore_permissions=True,
					ignore_missing=True, delete_permanently=True,
				)
				gone[doctype] = gone.get(doctype, 0) + 1
			except Exception:
				continue
		frappe.db.commit()
	print("LEFTOVERS removed:", gone)
	return gone


def housekeeping(apply=False):
	"""Empty Frappe's own log tables. Nothing here is a record of the college."""
	if frappe.local.site != SAFE_SITE:
		raise Exception(f"refusing to run on {frappe.local.site}; this is for {SAFE_SITE}")

	before = {}
	for doctype in HOUSEKEEPING:
		try:
			before[doctype] = frappe.db.count(doctype)
		except Exception:
			continue
	print("HOUSEKEEPING before:", {k: v for k, v in before.items() if v})

	if not apply:
		print("HOUSEKEEPING dry run -- nothing deleted")
		return before

	for doctype in before:
		frappe.db.delete(doctype)
	frappe.db.commit()

	# Contacts, defaults and notification preferences are made per User and
	# outlive the user that caused them.
	# Ordered, not a dict for its own sake: the contacts have to go before the
	# rows that hang off them, or those rows still have a parent and survive.
	orphaned = (
		(
			"Contact (unattached)",
			# Not "whose user has gone" -- that caught 277 of 6,154. The rest
			# have no user AND no Dynamic Link to anything: made in passing by
			# a fixture and never attached to a student or an application at
			# all. On this site nothing else makes a contact.
			"""
			delete c from `tabContact` c
			left join `tabDynamic Link` dl
			       on dl.parent = c.name and dl.parenttype = 'Contact'
			where ifnull(c.user, '') = '' and dl.name is null
			""",
		),
		(
			"Contact (user gone)",
			"delete c from `tabContact` c left join `tabUser` u on u.name = c.user"
			" where ifnull(c.user, '') != '' and u.name is null",
		),
		(
			"Contact Email",
			"delete ce from `tabContact Email` ce left join `tabContact` c"
			" on c.name = ce.parent where c.name is null",
		),
		(
			"Contact Phone",
			"delete cp from `tabContact Phone` cp left join `tabContact` c"
			" on c.name = cp.parent where c.name is null",
		),
		(
			"Dynamic Link",
			"delete dl from `tabDynamic Link` dl left join `tabContact` c"
			" on c.name = dl.parent where dl.parenttype = 'Contact' and c.name is null",
		),
		(
			"DefaultValue",
			"delete dv from `tabDefaultValue` dv left join `tabUser` u on u.name = dv.parent"
			" where dv.parenttype = 'User' and u.name is null",
		),
		(
			"Notification Type Preference",
			"delete n from `tabNotification Type Preference` n left join `tabUser` u"
			" on u.name = n.parent where u.name is null",
		),
	)
	for label, sql in orphaned:
		try:
			frappe.db.sql(sql)
			frappe.db.commit()
		except Exception as problem:
			print(f"HOUSEKEEPING could not clear {label}: {str(problem)[:120]}")

	after = {}
	for doctype in HOUSEKEEPING:
		try:
			after[doctype] = frappe.db.count(doctype)
		except Exception:
			continue
	print("HOUSEKEEPING after:", {k: v for k, v in after.items() if v})
	return after


def everything(apply=False):
	"""The whole sweep, in the order the passes depend on each other."""
	run(apply=apply)
	people(apply=apply)
	leftovers(apply=apply)
	housekeeping(apply=apply)
