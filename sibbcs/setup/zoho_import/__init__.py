# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""Carrying the college's records over from Zoho Creator.

The college ran admissions and student records in a Zoho Creator app
("Administration - SIBBCS Online Education") before this ERP. This package moves
the onboarded students across: who they are, their programme and level, the
courses they have taken and their marks, and their documents.

It runs in three steps, each a separate command so each can be checked before
the next:

  credentials  the person at the server creates the API token (never seen by
               anybody else, never committed)
  extract      read-only on Zoho: every record and file, to a private folder
               on the server
  load         write into the ERP, quietly

**Quietly** is the important word. Inserted the ordinary way, a hundred students
would each get an LMS account and a welcome mail, and a thousand historical
course registrations would each raise a Rs350 fee -- that night, and again from
the nightly sweep. `quiet()` switches those off for the length of the load, and
the records it writes carry `legacy_source` (the Zoho record id), which the fee
code also honours permanently: a registration carried over from Zoho is history,
never a new sign-up to bill.

What the extract holds is personal data. It lives under the bench user's home
in a folder only that user can read, and is never committed or copied off the
server.
"""

from contextlib import contextmanager

import frappe


@contextmanager
def quiet():
	"""Load records without the side effects meant for new ones.

	Inside this block nothing is pushed to Campus LMS, no "registration open"
	mail is queued, no registration fee is raised, and Frappe's own mail is
	muted. The previous state is restored afterwards, even on an error.
	"""
	previous = (frappe.flags.sibbcs_import, frappe.flags.mute_emails)
	frappe.flags.sibbcs_import = True
	frappe.flags.mute_emails = True
	try:
		yield
	finally:
		frappe.flags.sibbcs_import, frappe.flags.mute_emails = previous
