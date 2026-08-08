"""Student registration portal.

URL: /my-courses  (login required)
"""

import frappe

from sibbcs.academic.portal import available_offerings, get_enrollment, my_registrations

no_cache = 1


def get_context(context):
	context.no_cache = 1

	if frappe.session.user == "Guest":
		frappe.throw("Please log in to see your courses.", frappe.PermissionError)

	enrollment = get_enrollment()
	context.enrollment = enrollment

	if not enrollment:
		context.no_enrollment = True
		return context

	details = frappe.db.get_value(
		"Program Enrollment",
		enrollment,
		["student_name", "program", "current_level", "credits_earned", "cgpa"],
		as_dict=True,
	)
	context.update(details or {})
	context.registrations = my_registrations(enrollment)
	context.offerings = available_offerings(enrollment)
	context.open_count = sum(1 for o in context.offerings if o["eligibility"]["allowed"])

	# Group by term. Every course runs in several terms, so a flat list shows
	# near-identical rows and students register for the wrong one -- which is
	# exactly what happened during acceptance testing.
	grouped = {}
	for offering in context.offerings:
		grouped.setdefault(offering["term"], []).append(offering)

	term_dates = {
		t.name: t
		for t in frappe.get_all(
			"Academic Term",
			filters={"name": ("in", list(grouped) or [""])},
			fields=["name", "start_date", "end_date", "registration_closes"],
		)
	}

	context.terms = [
		{
			"name": term,
			"rows": rows,
			"open_count": sum(1 for r in rows if r["eligibility"]["allowed"]),
			"dates": term_dates.get(term),
		}
		for term, rows in sorted(
			grouped.items(),
			key=lambda item: (term_dates.get(item[0], {}) or {}).get("start_date") or item[0],
		)
	]

	return context
