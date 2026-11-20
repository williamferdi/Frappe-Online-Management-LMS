# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""Learn the learning site's own id for every course already running there.

`lms_course_id` is what a link straight to a course is built from: the LMS
validates `/courses/:courseId` as a UUID, so the registrar's own
`BISTO502-2026-T6` is not an address anybody can open. The id comes back in
what `/sync/courses` answers, and from today `push` keeps it -- but only for
offerings pushed from today onward. Everything already over there was synced
before the field existed, so without this the student portal would go on
offering the LMS front door for the rest of the term.

A plain re-push, through the ordinary queue. `/sync/courses` upserts on
`externalId`, so this is the same call the offering would make the next time
somebody saved it; it simply does not wait for that. Silent on a site with no
Campus LMS configured, and queued rather than inline, because a migration
should not block on another system being up.
"""

import frappe

from sibbcs.integrations import campus_lms


def execute():
	if not campus_lms.configured():
		return

	for offering in frappe.get_all("Course Offering", pluck="name"):
		campus_lms.queue("Course Offering", offering)
