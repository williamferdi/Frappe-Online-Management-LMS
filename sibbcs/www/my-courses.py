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

	return context
