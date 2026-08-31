# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""Announcements and the portal Inbox.

    bench --site online.sibbc.org execute sibbcs.setup.phase6_portal_comms.build

Idempotent, like every other builder here.

Two DocTypes, and deliberately only two. To Do and Calendar are assembled from
records that already exist -- an unpaid invoice is already a To Do item, a live
class is already a calendar entry -- and storing them again would mean keeping
two copies of the same fact in step. Discussions reuse Frappe's own
`Discussion Topic` / `Discussion Reply`, scoped to a Course Offering.

Read state lives in its own DocType rather than a child table on the
announcement. A thousand students marking one notice as read would otherwise
rewrite that notice a thousand times, and every write would collide with the
next.
"""

import frappe

from sibbcs.setup.schema import (
	check,
	column,
	edit,
	ensure_doctype,
	f,
	full,
	link,
	read,
	section,
	select,
	table,
)

MODULE = "SIBBCS ERP"

SM = "System Manager"
REGISTRAR = "Registrar"
COORDINATOR = "Academic Coordinator"
OFFICER = "Admissions Officer"
FACULTY = "Faculty"
FACILITATOR = "Facilitator"
ACCOUNTS = "Accounts"
STUDENT = "Student"

# How an announcement chooses who sees it. "All Students" is the common case;
# the rest narrow it, and each one names the field it reads.
AUDIENCES = ["All Students", "Programme", "Level", "Term", "Course Offering"]

CATEGORIES = ["General", "Academic", "Finance", "Events", "Urgent"]


def build():
	announcement()
	announcement_read()
	portal_message()
	frappe.db.commit()
	print("Portal communications ready.")
	print("  Announcement, Announcement Read, Portal Message, Portal Message Recipient")


def announcement():
	ensure_doctype(
		"Announcement",
		MODULE,
		fields=[
			f("title", "Title", reqd=1, in_list_view=1),
			select("category", "Category", CATEGORIES, default="General", in_list_view=1),
			column("c1"),
			check("published", "Published", in_list_view=1),
			check("pinned", "Pinned"),
			section("audience_section", "Audience"),
			select("audience", "Audience", AUDIENCES, default="All Students", reqd=1),
			link("program", "Programme", "Program", depends_on="eval:doc.audience=='Programme'"),
			select(
				"level",
				"Level",
				["1", "2", "3", "4"],
				depends_on="eval:doc.audience=='Level'",
			),
			link("term", "Term", "Academic Term", depends_on="eval:doc.audience=='Term'"),
			link(
				"course_offering",
				"Course Offering",
				"Course Offering",
				depends_on="eval:doc.audience=='Course Offering'",
			),
			section("timing_section", "Timing"),
			f("publish_on", "Publish On", "Datetime", reqd=1),
			column("c2"),
			f("expires_on", "Expires On", "Datetime"),
			section("body_section", "Notice"),
			f("body", "Body", "Text Editor", reqd=1),
		],
		permissions=[
			full(SM),
			full(REGISTRAR),
			full(COORDINATOR),
			edit(OFFICER),
			read(FACULTY),
			read(FACILITATOR),
			read(ACCOUNTS),
			# Students read announcements through the portal endpoint, which
			# filters by audience. A blanket read here would let one student
			# fetch a notice aimed at a different cohort straight from the API.
		],
		autoname="format:ANN-{YYYY}-{#####}",
		title_field="title",
		sort_field="publish_on",
		sort_order="DESC",
	)


def announcement_read():
	ensure_doctype(
		"Announcement Read",
		MODULE,
		fields=[
			link("announcement", "Announcement", "Announcement", reqd=1, in_list_view=1),
			link("user", "User", "User", reqd=1, in_list_view=1),
			f("read_on", "Read On", "Datetime"),
		],
		permissions=[full(SM), read(REGISTRAR)],
		autoname="hash",
	)


def portal_message():
	ensure_doctype(
		"Portal Message Recipient",
		MODULE,
		fields=[
			link("recipient", "Recipient", "User", reqd=1, in_list_view=1),
			f("recipient_name", "Name", "Data", in_list_view=1, read_only=1),
			column("c1"),
			f("read_on", "Read On", "Datetime", read_only=1),
		],
		istable=1,
	)

	ensure_doctype(
		"Portal Message",
		MODULE,
		fields=[
			f("subject", "Subject", reqd=1, in_list_view=1),
			link("sender", "From", "User", reqd=1, read_only=1, in_list_view=1),
			column("c1"),
			f("sent_on", "Sent On", "Datetime", read_only=1),
			# The root message of the conversation. A reply points at the root,
			# not at the message before it, so a thread is one query rather
			# than a walk back up a chain.
			link("thread", "Thread", "Portal Message", read_only=1),
			section("to_section", "To"),
			table("recipients", "Recipients", "Portal Message Recipient", reqd=1),
			section("body_section", "Message"),
			f("body", "Message", "Text Editor", reqd=1),
		],
		permissions=[
			full(SM),
			full(REGISTRAR),
			full(COORDINATOR),
			full(OFFICER),
			edit(FACULTY),
			edit(FACILITATOR),
			edit(ACCOUNTS),
			# Students read and reply through the portal endpoints, which scope
			# every query to their own recipient rows.
		],
		autoname="format:MSG-{YYYY}-{#####}",
		title_field="subject",
		sort_field="sent_on",
		sort_order="DESC",
	)
