"""The 13-step admission checklist.

Replaces the old 15-state linear workflow. That model could hold only one state
at a time, so it could not represent how the office actually works -- the
tracking board routinely shows the admission fee Paid while the entrance exam
and interview are still Awaiting, and Reference 1 Awaiting while Reference 2 is
Received.

Each of the 13 steps therefore carries its own status. Steps are worked in any
order except for four genuine dependencies (see REQUIRES), each a real causal
constraint rather than a preference.

The overall `workflow_state` is now a small summary -- Draft, In Review,
Admitted, Onboarded, Rejected, Withdrawn -- derived from the checklist rather
than driving it.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime

OFFICER = "Admissions Officer"
REGISTRAR = "Registrar"

# step_no, label, allowed statuses, default, statuses counting as done, owner role
STEPS = [
	(1, "Full Application Review",
	 ["Needs Admin Inspection", "Under Review", "Approved", "Rejected"],
	 "Needs Admin Inspection", ["Approved"], OFFICER),

	(2, "Applicant Documents Review",
	 ["Awaiting", "Partial Submission", "Awaiting Review", "Resubmit Requested", "Verified"],
	 "Awaiting", ["Verified"], OFFICER),

	(3, "Reference 1 Review",
	 ["Awaiting", "Request Sent", "Received", "Awaiting Review", "Reviewed", "Not Applicable"],
	 "Awaiting", ["Reviewed", "Not Applicable"], OFFICER),

	(4, "Reference 2 Review",
	 ["Awaiting", "Request Sent", "Received", "Awaiting Review", "Reviewed", "Not Applicable"],
	 "Awaiting", ["Reviewed", "Not Applicable"], OFFICER),

	(5, "Scholarship Form Review",
	 ["Not Applicable", "Awaiting Review", "Received", "Approved", "Rejected"],
	 "Not Applicable", ["Approved", "Rejected", "Not Applicable"], REGISTRAR),

	(6, "Mentor Form Review",
	 ["Awaiting", "Request Sent", "Received", "Verified", "Not Applicable"],
	 "Awaiting", ["Verified", "Not Applicable"], OFFICER),

	(7, "LMS Account Creation",
	 ["Awaiting", "Created", "Link Sent"],
	 "Awaiting", ["Created", "Link Sent"], OFFICER),

	(8, "Entrance Exam Review",
	 ["Awaiting", "Scheduled", "Passed", "Failed"],
	 "Awaiting", ["Passed"], OFFICER),

	(9, "Zoom Interview Review",
	 ["Awaiting", "Scheduled", "Cleared", "Rejected", "Deferred"],
	 "Awaiting", ["Cleared"], OFFICER),

	(10, "Admission Fee Status",
	 ["Awaiting", "Paid", "Waived"],
	 "Awaiting", ["Paid", "Waived"], REGISTRAR),

	(11, "Admission Decision",
	 ["Awaiting Review", "Admitted", "Rejected", "Deferred"],
	 "Awaiting Review", ["Admitted"], REGISTRAR),

	(12, "Manual Reading Review",
	 ["Awaiting", "Sent", "Acknowledged"],
	 "Awaiting", ["Acknowledged"], OFFICER),

	(13, "Onboarding Status",
	 ["Awaiting Onboarding", "Onboarded"],
	 "Awaiting Onboarding", ["Onboarded"], REGISTRAR),
]

BY_NO = {s[0]: s for s in STEPS}
LABELS = {s[0]: s[1] for s in STEPS}
ALL_STATUSES = sorted({status for s in STEPS for status in s[2]})
STEP_LABELS = [s[1] for s in STEPS]

# The only four hard gates. Everything else is freely parallel.
# step_no -> [(required_step_no, required_status or None meaning "done")]
REQUIRES = {
	8: [(7, None)],
	11: [(10, None)],
	12: [(11, "Admitted")],
	13: [(11, "Admitted"), (12, None)],
}


def statuses_for(step_no):
	return BY_NO[int(step_no)][2]


def is_done(step_no, status):
	return status in BY_NO[int(step_no)][4]


def owner_role(step_no):
	return BY_NO[int(step_no)][5]


def _as_doc(application):
	if hasattr(application, "doctype"):
		return application
	return frappe.get_doc("Admission Application", application)


# ---------------------------------------------------------------------------
# reading and writing
# ---------------------------------------------------------------------------


def seed(doc):
	"""Give an application its 13 rows. Idempotent -- adds only what is absent."""
	rows = doc.get("checklist") or []
	existing = {int(r.step_no) for r in rows if r.step_no}

	for step_no, label, _statuses, default, _done, role in STEPS:
		if step_no in existing:
			continue
		doc.append(
			"checklist",
			{"step_no": step_no, "step": label, "status": default, "owner_role": role},
		)

	ordered = sorted(doc.get("checklist"), key=lambda r: int(r.step_no or 0))
	for index, row in enumerate(ordered, start=1):
		row.idx = index


def get_row(application, step_no):
	doc = _as_doc(application)
	for row in doc.get("checklist") or []:
		if int(row.step_no or 0) == int(step_no):
			return doc, row
	return doc, None


def status_of(application, step_no):
	_doc, row = get_row(application, step_no)
	return row.status if row else None


def step_complete(application, step_no):
	status = status_of(application, step_no)
	return bool(status and is_done(step_no, status))


def blocked_reason(application, step_no):
	"""Why this step cannot be completed yet, or None."""
	doc = _as_doc(application)
	for required_no, required_status in REQUIRES.get(int(step_no), []):
		current = status_of(doc, required_no)
		if required_status:
			if current != required_status:
				return _("Step {0} ({1}) must be {2} first -- it is {3}.").format(
					required_no, LABELS[required_no], required_status, current or "-"
				)
		elif not step_complete(doc, required_no):
			return _("Step {0} ({1}) must be completed first -- it is {2}.").format(
				required_no, LABELS[required_no], current or "-"
			)
	return None


def set_status(application, step_no, status, remarks=None, ignore_gates=False):
	"""Move one step. Validates the status and the four hard gates."""
	step_no = int(step_no)
	if step_no not in BY_NO:
		frappe.throw(_("Unknown checklist step {0}.").format(step_no))

	if status not in statuses_for(step_no):
		frappe.throw(
			_("{0} is not a valid status for {1}. Allowed: {2}").format(
				status, LABELS[step_no], ", ".join(statuses_for(step_no))
			),
			title=_("Invalid Status"),
		)

	doc, row = get_row(application, step_no)
	if not row:
		seed(doc)
		doc.flags.ignore_permissions = True
		doc.save(ignore_permissions=True)
		doc, row = get_row(doc.name, step_no)

	# Gates guard *completion*, not intermediate progress: an officer may mark
	# an exam Scheduled before anything else, but not Passed.
	if not ignore_gates and is_done(step_no, status):
		reason = blocked_reason(doc, step_no)
		if reason:
			frappe.throw(reason, title=_("Step Blocked"))

	row.status = status
	row.updated_by = frappe.session.user
	row.updated_on = now_datetime()
	if remarks is not None:
		row.remarks = remarks

	doc.flags.ignore_permissions = True
	doc.save(ignore_permissions=True)
	sync_overall_state(doc)
	return row.status


def progress(application):
	doc = _as_doc(application)
	rows = doc.get("checklist") or []
	done = sum(1 for r in rows if r.step_no and is_done(r.step_no, r.status))
	return {"done": done, "total": len(rows) or len(STEPS)}


# ---------------------------------------------------------------------------
# overall state, derived from the checklist
# ---------------------------------------------------------------------------

DRAFT = "Draft"
IN_REVIEW = "In Review"
ADMITTED = "Admitted"
ONBOARDED = "Onboarded"
REJECTED = "Rejected"
WITHDRAWN = "Withdrawn"

OVERALL_STATES = [DRAFT, IN_REVIEW, ADMITTED, ONBOARDED, REJECTED, WITHDRAWN]


def derive_state(doc):
	"""The summary state. The checklist is the truth; this reflects it."""
	if doc.workflow_state == WITHDRAWN:
		return WITHDRAWN

	if status_of(doc, 11) == "Rejected" or status_of(doc, 1) == "Rejected":
		return REJECTED

	if step_complete(doc, 13):
		return ONBOARDED
	if status_of(doc, 11) == "Admitted":
		return ADMITTED
	if not doc.application_fee_paid:
		return DRAFT
	return IN_REVIEW


def sync_overall_state(doc):
	state = derive_state(doc)
	if doc.workflow_state != state:
		doc.db_set("workflow_state", state, update_modified=False)
	return state


# ---------------------------------------------------------------------------
# whitelisted actions for the Desk board
# ---------------------------------------------------------------------------


@frappe.whitelist()
def update_step(application, step_no, status, remarks=None):
	doc = frappe.get_doc("Admission Application", application)
	doc.check_permission("write")
	new_status = set_status(doc, step_no, status, remarks=remarks)
	return {
		"step_no": int(step_no),
		"status": new_status,
		"state": frappe.db.get_value("Admission Application", application, "workflow_state"),
	}


@frappe.whitelist()
def board(application):
	"""Everything the Desk board needs to draw itself."""
	doc = frappe.get_doc("Admission Application", application)
	doc.check_permission("read")

	rows = []
	for step_no, label, statuses, _default, _done, role in STEPS:
		current = status_of(doc, step_no)
		rows.append(
			{
				"step_no": step_no,
				"step": label,
				"status": current,
				"statuses": statuses,
				"owner_role": role,
				"done": bool(current and is_done(step_no, current)),
				"blocked": blocked_reason(doc, step_no),
			}
		)

	return {
		"application": doc.name,
		"state": doc.workflow_state,
		"progress": progress(doc),
		"rows": rows,
	}
