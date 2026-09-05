# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""Announcements, the Inbox and course discussions.

Scoped, like everything in `sibbcs/api`, to the signed-in user. An announcement
aimed at Level 3 is not merely hidden from a Level 1 student -- it is never
fetched for them, so there is no endpoint here through which one cohort can
read another's notices.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime, cint

from sibbcs.academic.portal import get_enrollment

# How far back the portal looks. A notice from two years ago is history, not
# news, and fetching every announcement ever written to filter five of them in
# Python gets slower every term.
ANNOUNCEMENT_WINDOW_DAYS = 400
ANNOUNCEMENT_LIMIT = 200


def _require_user():
	if frappe.session.user == "Guest":
		frappe.throw(_("Please sign in."), frappe.PermissionError)
	return frappe.session.user


def _audience_context():
	"""Everything an announcement might be addressed to, for this student."""
	enrollment = get_enrollment()
	if not enrollment:
		return {"enrollment": None, "program": None, "level": None, "terms": set(), "offerings": set()}

	row = frappe.db.get_value(
		"Program Enrollment", enrollment, ["program", "current_level"], as_dict=True
	) or {}

	registrations = frappe.get_all(
		"Course Registration",
		filters={"program_enrollment": enrollment},
		fields=["term", "course_offering"],
	)

	return {
		"enrollment": enrollment,
		"program": row.get("program"),
		"level": str(row.get("current_level") or ""),
		"terms": {r.term for r in registrations if r.term},
		"offerings": {r.course_offering for r in registrations if r.course_offering},
	}


def _addressed_to_me(announcement, context):
	audience = announcement.get("audience")
	if audience == "All Students":
		return True
	if audience == "Programme":
		return bool(context["program"]) and announcement.get("program") == context["program"]
	if audience == "Level":
		return bool(context["level"]) and str(announcement.get("level") or "") == context["level"]
	if audience == "Term":
		return announcement.get("term") in context["terms"]
	if audience == "Course Offering":
		return announcement.get("course_offering") in context["offerings"]
	# An audience the builder does not know about is shown to nobody rather
	# than to everybody.
	return False


def _live_announcements():
	"""Published, in window, newest first. Not yet filtered by audience."""
	now = now_datetime()
	rows = frappe.get_all(
		"Announcement",
		filters=[
			["published", "=", 1],
			["publish_on", "<=", now],
			["publish_on", ">=", frappe.utils.add_days(now, -ANNOUNCEMENT_WINDOW_DAYS)],
		],
		fields=[
			"name", "title", "body", "category", "pinned", "publish_on", "expires_on",
			"audience", "program", "level", "term", "course_offering",
		],
		order_by="pinned desc, publish_on desc",
		limit_page_length=ANNOUNCEMENT_LIMIT,
		ignore_permissions=True,
	)
	return [r for r in rows if not r.expires_on or r.expires_on > now]


@frappe.whitelist()
def announcements():
	"""Notices addressed to this student, with read state."""
	user = _require_user()
	context = _audience_context()

	mine = [row for row in _live_announcements() if _addressed_to_me(row, context)]
	if not mine:
		return {"rows": [], "unread": 0}

	seen = set(
		frappe.get_all(
			"Announcement Read",
			filters={"user": user, "announcement": ("in", [r.name for r in mine])},
			pluck="announcement",
		)
	)

	for row in mine:
		row["read"] = row.name in seen

	return {"rows": mine, "unread": sum(1 for row in mine if not row["read"])}


@frappe.whitelist(methods=["POST"])
def mark_announcement_read(announcement):
	"""Record that this user has read a notice.

	Its own DocType, not a child row: a thousand students marking one notice
	would otherwise rewrite that notice a thousand times, each write colliding
	with the next.
	"""
	user = _require_user()

	context = _audience_context()
	match = next(
		(row for row in _live_announcements() if row.name == announcement), None
	)
	if not match or not _addressed_to_me(match, context):
		frappe.throw(_("Announcement not found."), frappe.PermissionError)

	if frappe.db.exists("Announcement Read", {"announcement": announcement, "user": user}):
		return {"announcement": announcement, "read": True}

	frappe.get_doc(
		{
			"doctype": "Announcement Read",
			"announcement": announcement,
			"user": user,
			"read_on": now_datetime(),
		}
	).insert(ignore_permissions=True)
	frappe.db.commit()

	return {"announcement": announcement, "read": True}


# ---------------------------------------------------------------------------
# inbox
# ---------------------------------------------------------------------------

# Who a student may write to unprompted. Replying inside a thread reaches
# whoever is already on it; starting a new one goes to the office, so that a
# student cannot use the portal to message the whole college.
OFFICE_ROLES = ("Registrar", "Admissions Officer", "Academic Coordinator")


def _my_message_names(user):
	return set(
		frappe.get_all(
			"Portal Message Recipient",
			filters={"recipient": user, "parenttype": "Portal Message"},
			pluck="parent",
		)
	) | set(frappe.get_all("Portal Message", filters={"sender": user}, pluck="name"))


def _thread_of(message):
	return frappe.db.get_value("Portal Message", message, "thread") or message


@frappe.whitelist()
def inbox():
	"""Conversations this user is part of, newest first.

	One row per thread, carrying the latest message and an unread count, so the
	list screen does not fetch every message in every conversation.
	"""
	user = _require_user()

	names = _my_message_names(user)
	if not names:
		return {"threads": [], "unread": 0}

	messages = frappe.get_all(
		"Portal Message",
		filters={"name": ("in", list(names))},
		fields=["name", "subject", "sender", "sent_on", "thread", "body"],
		order_by="sent_on asc",
		ignore_permissions=True,
	)

	unread_rows = set(
		frappe.get_all(
			"Portal Message Recipient",
			filters={
				"recipient": user,
				"parenttype": "Portal Message",
				"parent": ("in", list(names)),
				"read_on": ("is", "not set"),
			},
			pluck="parent",
		)
	)

	senders = _sender_names({m.sender for m in messages})

	threads = {}
	for message in messages:
		root = message.thread or message.name
		thread = threads.setdefault(
			root,
			{"thread": root, "subject": message.subject, "count": 0, "unread": 0, "last": None},
		)
		thread["count"] += 1
		if message.name in unread_rows:
			thread["unread"] += 1
		thread["last"] = {
			"name": message.name,
			"sender": message.sender,
			"sender_name": senders.get(message.sender, message.sender),
			"sent_on": message.sent_on,
			"preview": _preview(message.body),
		}

	rows = sorted(
		threads.values(),
		key=lambda t: (t["last"] or {}).get("sent_on") or "",
		reverse=True,
	)
	return {"threads": rows, "unread": sum(t["unread"] for t in rows)}


@frappe.whitelist()
def thread(name):
	"""Every message in one conversation, oldest first."""
	user = _require_user()

	root = _thread_of(name)
	names = _my_message_names(user)
	if root not in names:
		frappe.throw(_("Conversation not found."), frappe.PermissionError)

	messages = frappe.get_all(
		"Portal Message",
		filters=[["name", "in", list(names)], ["ifnull(thread, name)", "=", root]],
		fields=["name", "subject", "sender", "sent_on", "body", "thread"],
		order_by="sent_on asc",
		ignore_permissions=True,
	)

	senders = _sender_names({m.sender for m in messages})
	for message in messages:
		message["sender_name"] = senders.get(message.sender, message.sender)
		message["mine"] = message.sender == user

	_mark_thread_read(user, [m.name for m in messages])

	return {"thread": root, "subject": messages[0].subject if messages else "", "messages": messages}


def _mark_thread_read(user, message_names):
	if not message_names:
		return
	rows = frappe.get_all(
		"Portal Message Recipient",
		filters={
			"recipient": user,
			"parenttype": "Portal Message",
			"parent": ("in", message_names),
			"read_on": ("is", "not set"),
		},
		pluck="name",
	)
	if not rows:
		return
	# db.set_value on the child rows: loading each parent to touch one column
	# would rewrite the message and bump its modified timestamp.
	for row in rows:
		frappe.db.set_value("Portal Message Recipient", row, "read_on", now_datetime())
	frappe.db.commit()


def _sender_names(users):
	if not users:
		return {}
	return {
		row.name: row.full_name
		for row in frappe.get_all(
			"User", filters={"name": ("in", list(users))}, fields=["name", "full_name"]
		)
	}


def _preview(body, length=140):
	text = frappe.utils.strip_html(body or "").strip()
	return text[:length] + ("…" if len(text) > length else "")


def _office_recipients():
	"""The staff a student reaches when they start a new conversation."""
	users = set()
	for role in OFFICE_ROLES:
		users |= set(
			frappe.get_all(
				"Has Role",
				filters={"role": role, "parenttype": "User"},
				pluck="parent",
			)
		)
	enabled = frappe.get_all(
		"User",
		filters={"name": ("in", list(users) or [""]), "enabled": 1},
		fields=["name", "full_name"],
	)
	return enabled


@frappe.whitelist()
def office_contacts():
	"""Who a new message would go to, so the compose form can say so."""
	_require_user()
	return _office_recipients()


@frappe.whitelist(methods=["POST"])
def send_message(subject=None, body=None, reply_to=None):
	"""Start a conversation with the office, or reply inside one.

	A student cannot name recipients. Replying reaches whoever is already on
	the thread; a new message goes to the office. Without that, the portal
	becomes a way to message every account on the site.
	"""
	user = _require_user()

	if not (body or "").strip():
		frappe.throw(_("The message is empty."), title=_("Nothing to send"))

	if reply_to:
		root = _thread_of(reply_to)
		if root not in _my_message_names(user):
			frappe.throw(_("Conversation not found."), frappe.PermissionError)

		recipients = _thread_participants(root) - {user}
		subject = frappe.db.get_value("Portal Message", root, "subject")
	else:
		root = None
		if not (subject or "").strip():
			frappe.throw(_("Please give the message a subject."), title=_("No subject"))
		recipients = {row.name for row in _office_recipients()}

	if not recipients:
		frappe.throw(
			_("There is nobody to send this to. Please contact the college directly."),
			title=_("No recipient"),
		)

	message = frappe.get_doc(
		{
			"doctype": "Portal Message",
			"subject": subject,
			"body": body,
			"sender": user,
			"sent_on": now_datetime(),
			"thread": root,
			"recipients": [{"recipient": name} for name in sorted(recipients)],
		}
	)
	message.insert(ignore_permissions=True)
	frappe.db.commit()

	return {"message": message.name, "thread": root or message.name}


def _thread_participants(root):
	names = [root] + frappe.get_all("Portal Message", filters={"thread": root}, pluck="name")
	people = set(frappe.get_all("Portal Message", filters={"name": ("in", names)}, pluck="sender"))
	people |= set(
		frappe.get_all(
			"Portal Message Recipient",
			filters={"parent": ("in", names), "parenttype": "Portal Message"},
			pluck="recipient",
		)
	)
	return people


# ---------------------------------------------------------------------------
# discussions
# ---------------------------------------------------------------------------


def _my_offerings():
	"""The offerings a student is registered on -- their discussion rooms."""
	enrollment = get_enrollment()
	if not enrollment:
		return []

	return frappe.get_all(
		"Course Registration",
		filters={
			"program_enrollment": enrollment,
			"status": ("in", ("Registered", "Active", "Completed")),
		},
		fields=["course_offering", "course", "course_title", "term"],
		order_by="registration_date desc",
	)


@frappe.whitelist()
def discussion_rooms():
	"""One room per course the student is on, with its topic count."""
	_require_user()
	offerings = _my_offerings()
	if not offerings:
		return []

	counts = {}
	for row in frappe.get_all(
		"Discussion Topic",
		filters={
			"reference_doctype": "Course Offering",
			"reference_docname": ("in", [o.course_offering for o in offerings]),
		},
		fields=["reference_docname", "count(name) as n"],
		group_by="reference_docname",
	):
		counts[row.reference_docname] = cint(row.n)

	return [
		{
			"course_offering": row.course_offering,
			"course": row.course,
			"course_title": row.course_title,
			"term": row.term,
			"topics": counts.get(row.course_offering, 0),
		}
		for row in offerings
	]


def _may_use_room(course_offering):
	if not any(row.course_offering == course_offering for row in _my_offerings()):
		frappe.throw(
			_("You are not registered on that course."), frappe.PermissionError
		)


# ---------------------------------------------------------------------------
# a thread on one lesson
# ---------------------------------------------------------------------------

LESSON_REFERENCE = "Course Module Item"


def _may_discuss_item(module_item):
	"""Who may read and post on one lesson's thread.

	A teacher of the course, or a student registered on it for whom the item
	is actually reachable -- a locked lesson's discussion is locked too, or the
	thread becomes a way to read about a lesson you cannot open.

	Returns the student's registration when there is one, so the caller can
	check reachability without asking twice.
	"""
	from sibbcs.academic import modules
	from sibbcs.academic import permissions as academic_permissions

	offering = frappe.db.get_value("Course Module Item", module_item, "course_offering")
	if not offering:
		frappe.throw(_("Discussion not found."), frappe.PermissionError)

	if academic_permissions.is_teaching_staff():
		# Staff, narrowed to their own courses. `offering_scope() is None`
		# would not do here: it is also true of every student, which let
		# anybody read any lesson's thread on any course.
		academic_permissions.assert_may_teach(offering)
		return None

	mine = [row for row in _my_offerings() if row.course_offering == offering]
	if not mine:
		frappe.throw(_("You are not registered on that course."), frappe.PermissionError)

	registration = frappe.db.get_value(
		"Course Registration",
		{"program_enrollment": get_enrollment(), "course_offering": offering},
		"name",
	)
	state = modules.item_is_reachable(module_item, registration)
	if not state["open"]:
		frappe.throw(state["reason"] or _("This is locked."), frappe.PermissionError)

	return registration


def _lesson_topic(module_item, create=False):
	"""The thread for one item, made on the first thing anybody says.

	Not made up front: a topic per item on every course would be thousands of
	empty threads, and an empty thread reads as a room nobody came to rather
	than a room nobody has opened.
	"""
	existing = frappe.get_all(
		"Discussion Topic",
		filters={
			"reference_doctype": LESSON_REFERENCE,
			"reference_docname": module_item,
		},
		pluck="name",
		limit=1,
	)
	if existing:
		return existing[0]
	if not create:
		return None

	title = frappe.db.get_value("Course Module Item", module_item, "title") or module_item
	topic = frappe.get_doc(
		{
			"doctype": "Discussion Topic",
			"title": title,
			"reference_doctype": LESSON_REFERENCE,
			"reference_docname": module_item,
		}
	).insert(ignore_permissions=True)
	return topic.name


@frappe.whitelist()
def lesson_discussion(module_item):
	"""Everything said about one lesson."""
	_require_user()
	_may_discuss_item(module_item)

	topic = _lesson_topic(module_item)
	if not topic:
		return {"topic": None, "replies": []}

	replies = frappe.get_all(
		"Discussion Reply",
		filters={"topic": topic},
		fields=["name", "reply", "owner", "creation"],
		order_by="creation asc",
	)
	authors = _sender_names({row.owner for row in replies})
	staff = _staff_users()

	for reply in replies:
		reply["author_name"] = authors.get(reply.owner, reply.owner)
		reply["mine"] = reply.owner == frappe.session.user
		# Worth marking: an answer from the person teaching the course is not
		# the same as an answer from the room.
		reply["from_staff"] = reply.owner in staff

	return {"topic": topic, "replies": replies}


def _staff_users():
	"""Who counts as teaching staff, for marking their replies."""
	return {
		row.parent
		for row in frappe.get_all(
			"Has Role",
			filters={
				"role": ("in", ("Faculty", "Facilitator", "Academic Coordinator", "Registrar")),
				"parenttype": "User",
			},
			fields=["parent"],
		)
	}


@frappe.whitelist(methods=["POST"])
def post_lesson_reply(module_item, reply):
	"""Say something about one lesson."""
	_require_user()
	_may_discuss_item(module_item)

	if not (reply or "").strip():
		frappe.throw(_("The reply is empty."))

	topic = _lesson_topic(module_item, create=True)
	doc = frappe.get_doc(
		{"doctype": "Discussion Reply", "topic": topic, "reply": reply}
	).insert(ignore_permissions=True)
	frappe.db.commit()

	return {"reply": doc.name, "topic": topic}


@frappe.whitelist()
def discussion_topics(course_offering):
	"""Topics in one course room, with reply counts."""
	_require_user()
	_may_use_room(course_offering)

	topics = frappe.get_all(
		"Discussion Topic",
		filters={"reference_doctype": "Course Offering", "reference_docname": course_offering},
		fields=["name", "title", "owner", "creation", "modified"],
		order_by="modified desc",
		ignore_permissions=True,
	)
	if not topics:
		return []

	counts = {}
	for row in frappe.get_all(
		"Discussion Reply",
		filters={"topic": ("in", [t.name for t in topics])},
		fields=["topic", "count(name) as n"],
		group_by="topic",
	):
		counts[row.topic] = cint(row.n)

	authors = _sender_names({t.owner for t in topics})
	for topic in topics:
		topic["replies"] = counts.get(topic.name, 0)
		topic["author_name"] = authors.get(topic.owner, topic.owner)

	return topics


@frappe.whitelist()
def discussion_replies(topic):
	"""One thread. The room is checked, not the topic name."""
	_require_user()

	reference = frappe.db.get_value(
		"Discussion Topic", topic, ["reference_doctype", "reference_docname", "title"], as_dict=True
	)
	if not reference or reference.reference_doctype != "Course Offering":
		frappe.throw(_("Discussion not found."), frappe.PermissionError)
	_may_use_room(reference.reference_docname)

	replies = frappe.get_all(
		"Discussion Reply",
		filters={"topic": topic},
		fields=["name", "reply", "owner", "creation"],
		order_by="creation asc",
		ignore_permissions=True,
	)
	authors = _sender_names({r.owner for r in replies})
	for reply in replies:
		reply["author_name"] = authors.get(reply.owner, reply.owner)
		reply["mine"] = reply.owner == frappe.session.user

	return {"topic": topic, "title": reference.title, "replies": replies}


@frappe.whitelist(methods=["POST"])
def post_topic(course_offering, title, reply):
	"""Open a discussion in a course the student is actually on."""
	_require_user()
	_may_use_room(course_offering)

	if not (title or "").strip() or not (reply or "").strip():
		frappe.throw(_("A discussion needs a title and a first message."))

	topic = frappe.get_doc(
		{
			"doctype": "Discussion Topic",
			"title": title.strip(),
			"reference_doctype": "Course Offering",
			"reference_docname": course_offering,
		}
	).insert(ignore_permissions=True)

	frappe.get_doc(
		{"doctype": "Discussion Reply", "topic": topic.name, "reply": reply}
	).insert(ignore_permissions=True)
	frappe.db.commit()

	return {"topic": topic.name}


@frappe.whitelist(methods=["POST"])
def post_reply(topic, reply):
	_require_user()

	reference = frappe.db.get_value(
		"Discussion Topic", topic, ["reference_doctype", "reference_docname"], as_dict=True
	)
	if not reference or reference.reference_doctype != "Course Offering":
		frappe.throw(_("Discussion not found."), frappe.PermissionError)
	_may_use_room(reference.reference_docname)

	if not (reply or "").strip():
		frappe.throw(_("The reply is empty."))

	doc = frappe.get_doc(
		{"doctype": "Discussion Reply", "topic": topic, "reply": reply}
	).insert(ignore_permissions=True)
	frappe.db.commit()

	return {"reply": doc.name}


# ---------------------------------------------------------------------------
# badges
# ---------------------------------------------------------------------------


@frappe.whitelist()
def unread_counts():
	"""What the sidebar badges show. Deliberately cheap: two counts."""
	_require_user()
	return {
		"announcements": announcements()["unread"],
		"inbox": inbox()["unread"],
	}
