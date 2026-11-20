# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""Put the staff of every existing offering onto their course over there.

Until today the registrar told Campus LMS Lite which courses run and who is
registered for them, and never who taught them. `offering_payload` carries the
code, the term, the level and the programmes; the LMS reads a course's
*teachers* from its enrolments, which nothing here ever wrote. So
BISTO502-2026-T6 had Ramsemz as its instructor on this side and no teacher at
all on that one -- which is how it was noticed.

`on_offering_change` covers every offering saved from now on. This is for the
ones that may never be saved again.

Idempotent: it goes through the ordinary push, `/sync/enrollments` upserts on
`externalId`, and a site with no Campus LMS configured sends nothing. Queued
rather than sent inline, because a migration should not block on another
system being up.
"""

import frappe

from sibbcs.integrations import campus_lms


def execute():
	if not campus_lms.configured():
		return

	for offering in frappe.get_all("Course Offering", pluck="name"):
		if campus_lms.teaching_staff(offering):
			campus_lms.queue("Course Offering", offering)
