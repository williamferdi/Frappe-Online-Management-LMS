# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""To Do and Calendar.

Neither is stored. An unpaid invoice is already a thing to do, and a live class
is already a calendar entry -- writing them down a second time would mean
keeping two copies of the same fact in step, and the copy is the one that goes
stale. Both endpoints assemble from records that already exist.
"""

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, today

from sibbcs.academic.portal import get_enrollment

SETTLED_FEE_STATES = ("Paid", "Waived", "Cancelled")
LIVE_REGISTRATION_STATES = ("Registered", "Active")

# Weekday.day_index is 1..7 from Monday; Python's weekday() is 0..6 from Monday.
MONDAY_OFFSET = 1


def _require_user():
	if frappe.session.user == "Guest":
		frappe.throw(_("Please sign in."), frappe.PermissionError)
	return frappe.session.user


def _registrations(enrollment):
	return frappe.get_all(
		"Course Registration",
		filters={"program_enrollment": enrollment},
		fields=[
			"name", "course", "course_title", "term", "status",
			"course_offering", "registration_fee_invoice", "lms_enrollment_created",
		],
	)


# ---------------------------------------------------------------------------
# to do
# ---------------------------------------------------------------------------


def _item(kind, title, detail, **extra):
	item = {"kind": kind, "title": title, "detail": detail, "due": None, "url": None}
	item.update(extra)
	return item


def _fee_items(student):
	items = []
	for row in frappe.get_all(
		"Fee Invoice",
		filters={"student": student, "status": ("not in", SETTLED_FEE_STATES)},
		fields=[
			"name", "fee_type", "category", "term", "outstanding_amount",
			"due_date", "payment_link",
		],
		order_by="due_date asc",
	):
		overdue = bool(row.due_date and getdate(row.due_date) < getdate(today()))
		items.append(
			_item(
				"fee",
				f"Pay {row.fee_type or row.category or 'fee'}",
				f"₹{flt(row.outstanding_amount):,.0f}"
				+ (f" · {row.term}" if row.term else ""),
				due=row.due_date,
				url=row.payment_link,
				urgent=overdue,
				reference=row.name,
			)
		)
	return items


def _blocked_course_items(registrations):
	"""A registration whose fee is unsettled is a course the student cannot open.

	Worth naming separately from the invoice: the invoice says money is owed,
	this says what the money is holding up.
	"""
	items = []
	unsettled = {
		row.name
		for row in frappe.get_all(
			"Fee Invoice",
			filters={
				"name": (
					"in",
					[r.registration_fee_invoice for r in registrations if r.registration_fee_invoice]
					or [""],
				),
				"status": ("not in", SETTLED_FEE_STATES),
			},
			fields=["name"],
		)
	}

	for row in registrations:
		if row.status not in LIVE_REGISTRATION_STATES:
			continue
		if row.lms_enrollment_created:
			continue
		if row.registration_fee_invoice in unsettled:
			items.append(
				_item(
					"blocked",
					f"{row.course} is not open yet",
					"The course opens once its registration fee is settled.",
					reference=row.name,
				)
			)
	return items



def _registration_items(registrations):
	"""An open window the student has not used yet."""
	registered_terms = {
		r.term for r in registrations if r.status in LIVE_REGISTRATION_STATES
	}

	items = []
	for term in frappe.get_all(
		"Academic Term",
		filters={"status": ("in", ("Open", "Active"))},
		fields=["name", "term_name", "registration_closes"],
		order_by="registration_closes asc",
	):
		if term.name in registered_terms:
			continue
		closes = term.registration_closes
		items.append(
			_item(
				"registration",
				f"Register for {term.term_name}",
				"Registration is open and you have not chosen a course yet.",
				due=closes,
				url="/portal/courses/register",
				urgent=bool(closes and (getdate(closes) - getdate(today())).days <= 7),
				reference=term.name,
			)
		)
	return items


@frappe.whitelist()
def todo():
	"""Everything outstanding, gathered from where it actually lives."""
	user = _require_user()
	enrollment = get_enrollment()
	if not enrollment:
		# Same shape as the loaded answer. A short empty branch is how a
		# screen ends up reading undefined for a key it always expects.
		return {"items": [], "count": 0, "urgent": 0}

	student = frappe.db.get_value("Program Enrollment", enrollment, "student")
	registrations = _registrations(enrollment)

	items = (
		_fee_items(student)
		+ _blocked_course_items(registrations)
		+ _registration_items(registrations)
	)

	# Dated first, soonest at the top; undated after it. Sorting by a
	# missing date would otherwise put an undated item above an overdue fee.
	items.sort(key=lambda item: (item["due"] is None, item["due"] or "", item["title"]))

	return {
		"items": items,
		"count": len(items),
		"urgent": sum(1 for item in items if item.get("urgent")),
	}


# ---------------------------------------------------------------------------
# calendar
# ---------------------------------------------------------------------------


def _event(kind, title, start, **extra):
	event = {"kind": kind, "title": title, "start": str(start), "end": None, "url": None}
	event.update(extra)
	return event


def _window(start, end):
	start = getdate(start) if start else getdate(add_days(today(), -31))
	end = getdate(end) if end else getdate(add_days(today(), 62))
	if end < start:
		start, end = end, start
	# A year of daily recurrences is the most anyone needs to look at, and it
	# bounds the expansion loop below.
	if (end - start).days > 400:
		end = add_days(start, 400)
	return start, end



def _weekly_sessions(registrations, start, end):
	"""Course Offering carries a weekday set and a time, not dated rows.

	The recurrence is expanded across the requested window here rather than
	stored, so a change to the timetable does not leave stale dates behind.
	"""
	offerings = [r.course_offering for r in registrations if r.status in LIVE_REGISTRATION_STATES]
	if not offerings:
		return []

	rows = frappe.get_all(
		"Course Offering",
		filters={"name": ("in", offerings)},
		fields=["name", "course", "course_title", "zoom_time", "term", "format"],
	)
	rows = [row for row in rows if row.zoom_time]
	if not rows:
		return []

	day_index = {
		row.name: cint(row.day_index)
		for row in frappe.get_all("Weekday", fields=["name", "day_index"])
	}

	days_by_offering = {}
	for row in frappe.get_all(
		"Course Offering Weekday",
		filters={"parent": ("in", [r.name for r in rows]), "parenttype": "Course Offering"},
		fields=["parent", "weekday"],
	):
		days_by_offering.setdefault(row.parent, set()).add(day_index.get(row.weekday))

	term_bounds = {
		row.name: row
		for row in frappe.get_all(
			"Academic Term",
			filters={"name": ("in", [r.term for r in rows if r.term] or [""])},
			fields=["name", "start_date", "end_date"],
		)
	}

	events = []
	for offering in rows:
		wanted = {d for d in days_by_offering.get(offering.name, set()) if d}
		if not wanted:
			continue

		bounds = term_bounds.get(offering.term)
		first = max(start, getdate(bounds.start_date)) if bounds and bounds.start_date else start
		last = min(end, getdate(bounds.end_date)) if bounds and bounds.end_date else end

		day = first
		while day <= last:
			if day.weekday() + MONDAY_OFFSET in wanted:
				events.append(
					_event(
						"session",
						offering.course_title or offering.course,
						f"{day} {offering.zoom_time}",
						detail=f"{offering.course} · {offering.format or 'Session'}",
						reference=offering.name,
					)
				)
			day += timedelta(days=1)

	return events


def _fee_due_events(student, start, end):
	return [
		_event(
			"fee",
			f"{row.fee_type or row.category or 'Fee'} due",
			row.due_date,
			detail=f"₹{flt(row.outstanding_amount):,.0f}",
			url=row.payment_link,
			reference=row.name,
			all_day=True,
		)
		for row in frappe.get_all(
			"Fee Invoice",
			filters={
				"student": student,
				"status": ("not in", SETTLED_FEE_STATES),
				"due_date": ("between", [start, end]),
			},
			fields=["name", "fee_type", "category", "outstanding_amount", "due_date", "payment_link"],
		)
	]


def _term_events(registrations, start, end):
	terms = {r.term for r in registrations if r.term}
	terms |= set(
		frappe.get_all(
			"Academic Term", filters={"status": ("in", ("Open", "Active"))}, pluck="name"
		)
	)
	if not terms:
		return []

	events = []
	for row in frappe.get_all(
		"Academic Term",
		filters={"name": ("in", list(terms))},
		fields=["name", "term_name", "start_date", "end_date", "registration_closes"],
	):
		for label, date in (
			("begins", row.start_date),
			("ends", row.end_date),
			("registration closes", row.registration_closes),
		):
			if date and start <= getdate(date) <= end:
				events.append(
					_event(
						"term",
						f"{row.term_name} {label}",
						date,
						reference=row.name,
						all_day=True,
					)
				)
	return events


@frappe.whitelist()
def calendar(start=None, end=None):
	"""Live classes, weekly sessions, fee deadlines and term milestones."""
	_require_user()
	enrollment = get_enrollment()
	if not enrollment:
		return {"events": [], "start": None, "end": None}

	start, end = _window(start, end)
	student = frappe.db.get_value("Program Enrollment", enrollment, "student")
	registrations = _registrations(enrollment)

	# The bundled LMS's live classes and batch timetable were read here. Both
	# were empty on the live site -- the college schedules its Zoom sessions on
	# the Course Offering, which is what `_weekly_sessions` expands -- so what
	# the calendar actually draws is unchanged.
	events = (
		_weekly_sessions(registrations, start, end)
		+ _fee_due_events(student, start, end)
		+ _term_events(registrations, start, end)
	)
	events.sort(key=lambda event: event["start"])

	return {"events": events, "start": str(start), "end": str(end)}
