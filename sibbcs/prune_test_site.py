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
