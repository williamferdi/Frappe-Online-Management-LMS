# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""The admissions console.

A thin arrangement over `sibbcs/admissions`, which already knows how to do all
of this. Nothing here decides anything: `checklist.py` owns the thirteen steps
and their gates, each action module owns its own rules, and every one of them
checks permissions for itself. This module fetches in bulk so a list of two
hundred applicants is a handful of queries rather than a handful per applicant.
"""

import frappe
from frappe import _
from frappe.utils import cint

from sibbcs.admissions import checklist

# The action names `checklist.ACTIONS` hands out, mapped to what actually runs.
# Kept here rather than in checklist.py so that module stays free of imports
# from every corner of admissions -- and so a UI action can never be invented
# by the browser: anything not in this table is refused.
ACTION_HANDLERS = {
	"resend_requests": "sibbcs.admissions.notifications.resend",
	"create_lms_account": "sibbcs.admissions.lms_account.create_account",
	"send_interview_invite": "sibbcs.admissions.interview.send",
	"send_scholarship_form": "sibbcs.admissions.scholarship.send",
	"send_manuals": "sibbcs.admissions.manuals.send",
	"onboard_student": "sibbcs.admissions.conversion.onboard_application",
}

# Everything the pipeline list draws. Deliberately not `*`: an application row
# carries a candidate's date of birth, address and phone number, and a list
# screen has no business shipping those to the browser.
LIST_FIELDS = (
	"name",
	"full_name",
	"email",
	"mobile",
	"program",
	"intake_term",
	"entry_level",
	"workflow_state",
	"application_fee_paid",
	"qualifying_exam_score",
	"student",
	"creation",
	"modified",
)

STATES = ["Draft", "In Review", "Admitted", "Onboarded", "Rejected", "Withdrawn"]


# Who may work in admissions. Checked alongside the DocType permission, not
# instead of it: these endpoints aggregate across every candidate, so the day
# somebody grants Student read on Admission Application -- to let an applicant
# see their own -- a permission check alone would hand them the whole intake.
OFFICE_ROLES = (
	"System Manager",
	"Registrar",
	"Admissions Officer",
	"Academic Coordinator",
	"Dean",
)


def _require_staff():
	"""Admissions work is for the office, not for every signed-in account."""
	roles = set(frappe.get_roles())
	if not roles.intersection(OFFICE_ROLES) or not frappe.has_permission(
		"Admission Application", "read"
	):
		frappe.throw(
			_("You do not have access to admissions."), frappe.PermissionError
		)


def _progress_for(applications):
	"""Steps done, per application, in one query rather than one each.

	`checklist.progress()` loads the whole document. Fine for one applicant on
	a detail screen; two hundred document loads to draw a list is not.
	"""
	if not applications:
		return {}

	done_by_step = {
		step[0]: set(step[4]) for step in checklist.STEPS
	}
	total = len(checklist.STEPS)

	counts = {name: 0 for name in applications}
	for row in frappe.get_all(
		"Admission Checklist Item",
		filters={"parent": ("in", applications), "parenttype": "Admission Application"},
		fields=["parent", "step_no", "status"],
	):
		if row.status in done_by_step.get(cint(row.step_no), ()):
			counts[row.parent] = counts.get(row.parent, 0) + 1

	return {
		name: {"done": done, "total": total, "percent": round(done * 100 / total)}
		for name, done in counts.items()
	}


@frappe.whitelist()
def pipeline(state=None, search=None, program=None, limit=200):
	"""Every application, with how far through the checklist it is."""
	_require_staff()

	filters = {}
	if state:
		filters["workflow_state"] = state
	if program:
		filters["program"] = program

	or_filters = None
	if search:
		like = f"%{search}%"
		# A bare value in or_filters means `=`. Searching for a fragment
		# needs the operator spelled out, or the box silently matches
		# nothing at all.
		or_filters = {
			field: ("like", like)
			for field in ("name", "full_name", "email", "mobile")
		}

	rows = frappe.get_all(
		"Admission Application",
		filters=filters,
		or_filters=or_filters,
		fields=list(LIST_FIELDS),
		order_by="modified desc",
		limit_page_length=cint(limit),
	)

	progress = _progress_for([row.name for row in rows])
	for row in rows:
		row["progress"] = progress.get(row.name, {"done": 0, "total": len(checklist.STEPS), "percent": 0})

	return {
		"rows": rows,
		"states": STATES,
		"programs": frappe.get_all("Program", pluck="name"),
		"can_write": bool(frappe.has_permission("Admission Application", "write")),
	}


@frappe.whitelist()
def funnel():
	"""Counts by state, and where applications are actually stuck.

	The second half is the useful half. "Twelve in review" says nothing about
	what to do next; "nine waiting on a reference" is a morning's work.
	"""
	_require_staff()

	by_state = {row.workflow_state or "Draft": row.n for row in frappe.get_all(
		"Admission Application",
		fields=["workflow_state", "count(name) as n"],
		group_by="workflow_state",
	)}

	live = frappe.get_all(
		"Admission Application",
		filters={"workflow_state": ("in", ("Draft", "In Review"))},
		pluck="name",
	)

	stuck = []
	if live:
		done_by_step = {step[0]: set(step[4]) for step in checklist.STEPS}
		outstanding = {step[0]: 0 for step in checklist.STEPS}

		seen = {name: set() for name in live}
		for row in frappe.get_all(
			"Admission Checklist Item",
			filters={"parent": ("in", live), "parenttype": "Admission Application"},
			fields=["parent", "step_no", "status"],
		):
			step_no = cint(row.step_no)
			seen[row.parent].add(step_no)
			if row.status not in done_by_step.get(step_no, ()):
				outstanding[step_no] = outstanding.get(step_no, 0) + 1

		# A step with no row yet is outstanding too -- it sits at its default,
		# which for eleven of the thirteen is not a done status.
		for step in checklist.STEPS:
			step_no, _label, _statuses, default, done, _role, _key = step
			if default in done:
				continue
			for name in live:
				if step_no not in seen[name]:
					outstanding[step_no] += 1

		stuck = [
			{
				"step_no": step[0],
				"step": step[1],
				"owner_role": step[5],
				"waiting": outstanding[step[0]],
			}
			for step in checklist.STEPS
			if outstanding[step[0]]
		]
		stuck.sort(key=lambda row: row["waiting"], reverse=True)

	return {
		"by_state": [{"state": state, "count": by_state.get(state, 0)} for state in STATES],
		"total": sum(by_state.values()),
		"live": len(live),
		"stuck": stuck,
	}


# Fields the detail screen shows. Personal data is here on purpose -- this is
# the officer's working view of one candidate -- but it is still a named list,
# so adding a field to the DocType does not silently publish it.
DETAIL_FIELDS = (
	"name", "full_name", "email", "mobile", "whatsapp", "dob", "age", "gender",
	"address", "photo", "church_name", "current_role", "years_of_ministry",
	"has_bachelors", "previous_theological_education", "program", "intake_term",
	"entry_level", "workflow_state", "application_fee_paid", "admission_fee_paid",
	"qualifying_exam_score", "interview_outcome", "offer_sent_on", "student",
	"enrolled_on", "notes", "scholarship_request", "applicant_user",
	"exam_link_sent_on", "interview_link_sent_on", "scholarship_form_sent_on",
	"onboard_term", "onboard_level",
	"mother_tongue",
	"nationality",
	"church_denomination",
	"salvation_status",
	"baptism_status",
	"sense_of_call",
	"ata_eligible",
	"mature_candidate",
	"transfer_student",
	"education_sequence_mismatch",
	"whatsapp_groups",
	"theological_writing_status",
)


@frappe.whitelist()
def application(name):
	"""One candidate: their record, the checklist, and what has been sent."""
	_require_staff()

	doc = frappe.get_doc("Admission Application", name)
	doc.check_permission("read")

	record = {field: doc.get(field) for field in DETAIL_FIELDS}

	return {
		"application": record,
		"checklist": checklist.board(name),
		"documents": frappe.get_all(
			"Application Document",
			filters={"parent": name, "parenttype": "Admission Application"},
			fields=["name", "document_type", "file", "verified", "verified_by", "idx"],
			order_by="idx",
		),
		"references": frappe.get_all(
			"Reference Request",
			filters={"parent": name, "parenttype": "Admission Application"},
			fields=[
				"name", "referee_name", "referee_email", "referee_type",
				"sent_on", "submitted_on", "recommendation", "idx",
			],
			order_by="idx",
		),
		"mentors": frappe.get_all(
			"Mentor Consent",
			filters={"parent": name, "parenttype": "Admission Application"},
			fields=["name", "mentor_name", "mentor_email", "sent_on", "consented_on", "idx"],
			order_by="idx",
		),
		"exam": _exam_result(name),
		"interview": _interview(name),
		"scholarship": _scholarship(doc.scholarship_request),
		"invoices": frappe.get_all(
			"Fee Invoice",
			filters={"admission_application": name},
			fields=["name", "fee_type", "category", "status", "net_amount",
			        "outstanding_amount", "due_date", "payment_link"],
			order_by="creation",
		),
	}


def _exam_result(name):
	result = frappe.db.get_value(
		"Qualifying Exam Result",
		{"application": name},
		["name", "total", "result", "pass_mark", "conducted_on"],
		as_dict=True,
		order_by="conducted_on desc, creation desc",
	)
	return result or None


def _interview(name):
	record = frappe.db.get_value(
		"Interview Record",
		{"application": name},
				# `panel` is a child table, not a column -- selecting it fails at the
		# database, not in Python.
		["name", "scheduled_on", "outcome", "notes"],
		as_dict=True,
		order_by="creation desc",
	)
	return record or None


def _scholarship(request):
	if not request:
		return None
	return frappe.db.get_value(
		"Scholarship Request",
		request,
		["name", "status", "approved_amount", "monthly_discount", "requested_amount"],
		as_dict=True,
	)


@frappe.whitelist(methods=["POST"])
def run_action(application, action):
	"""Run one of the checklist's own actions against an application.

	The browser names an action, never a method. `ACTION_HANDLERS` is the only
	way from one to the other, so a crafted request cannot reach an arbitrary
	whitelisted function -- and the handler still checks its own permissions.
	"""
	_require_staff()

	if action not in ACTION_HANDLERS:
		frappe.throw(_("Unknown action: {0}").format(action))

	if not frappe.db.exists("Admission Application", application):
		frappe.throw(_("Application not found."))

	handler = frappe.get_attr(ACTION_HANDLERS[action])
	result = handler(application)

	return {"action": action, "result": result}


@frappe.whitelist()
def actions_for(application):
	"""Which actions this application currently offers, and why not."""
	_require_staff()
	board = checklist.board(application)

	return [
		{
			"step_no": row["step_no"],
			"step": row["step"],
			"action": row["action"],
			"blocked": row["blocked"],
		}
		for row in board["rows"]
		if row["action"]
	]
