# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""The last thing `lms_sync` was still needed for.

Phase 7 removed `academic/lms_sync.py`: enrolment is a push to Campus LMS Lite
now, and the hourly sweep that chased the bundled app's enrolments has nothing
to chase. This one helper outlived it, because the builders that authored
content in the bundled LMS still import it and the bundled app is still
installed -- read-only, until the college has satisfied itself that the 145
migrated pages are right.

**This module goes when the app does.** It exists so that removing 247 lines of
dead sync code did not have to wait on that decision, and so nobody has to
wonder why a single helper is sitting in an otherwise deleted module.
"""

import frappe


def _default_instructor(offering=None):
	"""LMS Course and LMS Batch both require at least one instructor.

	Prefer the offering's instructor if they have a login, else fall back to
	Administrator so a build is never blocked by missing staff data.
	"""
	if offering:
		instructor = frappe.db.get_value("Course Offering", offering, "instructor")
		if instructor:
			user = frappe.db.get_value("Instructor", instructor, "user")
			if user and frappe.db.exists("User", user):
				return user
	return "Administrator"
