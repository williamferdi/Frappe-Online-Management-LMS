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

# step_no, label, allowed statuses, default, statuses counting as done,
# owner role, stable key
#
# **The step number is a position, the key is the identity.** The college has
# reordered these once already -- the scholarship form moved from second in the
# list to after the interview, because until the interview nobody knows whether
# a candidate needs one. Renumbering is therefore a thing that happens, and
# nothing outside this file should hardcode a number. Use `NO["scholarship"]`.
# Existing rows are remapped by their stored label; see
# `patches/renumber_checklist_steps.py`.
STEPS = [
	(1, "Full Application Review",
	 ["Needs Admin Inspection", "Under Review", "Approved", "Rejected"],
	 "Needs Admin Inspection", ["Approved"], OFFICER, "application_review"),

	(2, "Applicant Documents Review",
	 ["Awaiting", "Partial Submission", "Awaiting Review", "Resubmit Requested", "Verified"],
	 "Awaiting", ["Verified"], OFFICER, "documents"),

	(3, "Spiritual & Ministerial Reference Review",
	 ["Awaiting", "Request Sent", "Received", "Awaiting Review", "Reviewed", "Not Applicable"],
	 "Awaiting", ["Reviewed", "Not Applicable"], OFFICER, "reference_1"),

	(4, "Academic & Professional Reference Review",
	 ["Awaiting", "Request Sent", "Received", "Awaiting Review", "Reviewed", "Not Applicable"],
	 "Awaiting", ["Reviewed", "Not Applicable"], OFFICER, "reference_2"),

	(5, "Mentor Form Review",
	 ["Awaiting", "Request Sent", "Received", "Verified", "Not Applicable"],
	 "Awaiting", ["Verified", "Not Applicable"], OFFICER, "mentor_form"),

	(6, "LMS Account Creation",
	 ["Awaiting", "Created", "Link Sent"],
	 "Awaiting", ["Created", "Link Sent"], OFFICER, "lms_account"),

	(7, "Entrance Exam Review",
	 ["Awaiting", "Scheduled", "Passed", "Failed"],
	 "Awaiting", ["Passed"], OFFICER, "entrance_exam"),

	(8, "Zoom Interview Review",
	 # Invite Sent sits between Awaiting and Scheduled because on Calendly's
	 # free plan nobody here learns that a slot was taken until an officer
	 # looks. Leaving the step at Awaiting after emailing the link would say
	 # something untrue about work already done.
	 ["Awaiting", "Invite Sent", "Scheduled", "Cleared", "Rejected", "Deferred"],
	 "Awaiting", ["Cleared"], OFFICER, "interview"),

	(9, "Scholarship Form Review",
	 # After the interview, because that conversation is where the college
	 # learns whether a candidate needs a scholarship at all.
	 #
	 # Form Sent, like the interview's Invite Sent: the default here is Not
	 # Applicable, which counts as done because most candidates never ask. Once
	 # the form has gone out the step is genuinely outstanding again, and saying
	 # so is the whole point of tracking it.
	 ["Not Applicable", "Form Sent", "Received", "Awaiting Review", "Approved", "Rejected"],
	 "Not Applicable", ["Approved", "Rejected", "Not Applicable"], REGISTRAR, "scholarship"),

	(10, "Admission Fee Status",
	 ["Awaiting", "Paid", "Waived"],
	 "Awaiting", ["Paid", "Waived"], REGISTRAR, "admission_fee"),

	(11, "Admission Decision",
	 ["Awaiting Review", "Admitted", "Rejected", "Deferred"],
	 "Awaiting Review", ["Admitted"], REGISTRAR, "decision"),

	(12, "Manual Reading Review",
	 ["Awaiting", "Sent", "Acknowledged"],
	 "Awaiting", ["Acknowledged"], OFFICER, "manual_reading"),

	(13, "Onboarding Status",
	 ["Awaiting Onboarding", "Onboarded"],
	 "Awaiting Onboarding", ["Onboarded"], REGISTRAR, "onboarding"),
]

BY_NO = {s[0]: s for s in STEPS}
LABELS = {s[0]: s[1] for s in STEPS}
ALL_STATUSES = sorted({status for s in STEPS for status in s[2]})
STEP_LABELS = [s[1] for s in STEPS]

# The stable name of each step -> the position it currently sits at. Every
# other module addresses steps through this, so a reorder is an edit to STEPS
# and nothing else.
NO = {s[6]: s[0] for s in STEPS}

# What each step used to be called. The two references were "Reference 1" and
# "Reference 2" until the college named them for what they are; a stored row
# still carrying an old label has to be recognisable, or the renumbering patch
# would skip it as unknown when an old backup is restored.
RENAMED_LABELS = {
	"Reference 1 Review": "Spiritual & Ministerial Reference Review",
	"Reference 2 Review": "Academic & Professional Reference Review",
}

# A row's stored label is what survives a renumbering, so it is what the
# migration matches on -- under either name.
NO_BY_LABEL = {s[1]: s[0] for s in STEPS}
NO_BY_LABEL.update(
	{old: NO_BY_LABEL[new] for old, new in RENAMED_LABELS.items() if new in NO_BY_LABEL}
)

# The only four hard gates. Everything else is freely parallel.
# step_no -> [(required_step_no, required_status or None meaning "done")]
REQUIRES = {
	NO["entrance_exam"]: [(NO["lms_account"], None)],
	NO["decision"]: [(NO["admission_fee"], None)],
	# Manuals go out after the admission decision, not after the exam: they are
	# sent to people the college has actually admitted, so nobody is asked to
	# read a handbook for a place they may not be offered.
	NO["manual_reading"]: [(NO["decision"], "Admitted")],
	NO["onboarding"]: [(NO["decision"], "Admitted"), (NO["manual_reading"], None)],
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

	for step_no, label, _statuses, default, _done, role, _key in STEPS:
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

# Statuses that mean somebody has decided something, which nothing derived from
# a record may overwrite.
DECIDED = ("Reviewed", "Verified", "Approved", "Rejected", "Not Applicable")


def record_fact(application, step_no, status, remarks=None):
	"""Move a step because something happened, not because somebody chose to.

	`set_status` is the officer's path: it validates the status and refuses to
	complete a step whose gates are unmet. This is for the other direction --
	an exam was marked, an interview was held -- where the event is simply
	true and the step should say so. It writes the row directly, so it neither
	saves the application nor recurses through `mirror_gates_to_checklist`.

	Never walks a step out of a status an officer already recorded.
	"""
	step_no = int(step_no)
	if status not in statuses_for(step_no):
		frappe.throw(
			_("{0} is not a valid status for {1}.").format(status, LABELS[step_no])
		)

	name = frappe.db.get_value(
		"Admission Checklist Item",
		{
			"parent": application,
			"parenttype": "Admission Application",
			"step_no": step_no,
		},
		"name",
	)
	if not name:
		return None

	current = frappe.db.get_value("Admission Checklist Item", name, "status")
	if current == status or current in DECIDED:
		return current

	values = {
		"status": status,
		"updated_by": frappe.session.user,
		"updated_on": now_datetime(),
	}
	if remarks:
		values["remarks"] = remarks

	frappe.db.set_value(
		"Admission Checklist Item", name, values, update_modified=False
	)
	return status

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

	if (
		status_of(doc, NO["decision"]) == "Rejected"
		or status_of(doc, NO["application_review"]) == "Rejected"
	):
		return REJECTED

	if step_complete(doc, NO["onboarding"]):
		return ONBOARDED
	if status_of(doc, NO["decision"]) == "Admitted":
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


# Steps that have something to *do*, not just a status to record. The board
# puts the action next to the step rather than in a toolbar menu, because the
# officer working the board is looking at the step, not at the toolbar.
ACTIONS = {
	NO["reference_1"]: "resend_requests",
	NO["reference_2"]: "resend_requests",
	NO["mentor_form"]: "resend_requests",
	NO["lms_account"]: "create_lms_account",
	NO["interview"]: "send_interview_invite",
	NO["scholarship"]: "send_scholarship_form",
	NO["manual_reading"]: "send_manuals",
	NO["onboarding"]: "onboard_student",
}


@frappe.whitelist()
def board(application):
	"""Everything the Desk board needs to draw itself."""
	doc = frappe.get_doc("Admission Application", application)
	doc.check_permission("read")

	# Remarks and the audit stamps live on the child rows, not in STEPS.
	stored = {
		int(r.step_no): r
		for r in (doc.get("checklist") or [])
		if r.step_no
	}

	rows = []
	for step_no, label, statuses, _default, _done, role, _key in STEPS:
		current = status_of(doc, step_no)
		row = stored.get(step_no)
		rows.append(
			{
				"step_no": step_no,
				"step": label,
				"status": current,
				"statuses": statuses,
				"owner_role": role,
				"done": bool(current and is_done(step_no, current)),
				"done_statuses": BY_NO[step_no][4],
				"blocked": blocked_reason(doc, step_no),
				"remarks": row.remarks if row else None,
				"updated_by": row.updated_by if row else None,
				"updated_on": str(row.updated_on) if row and row.updated_on else None,
				"action": ACTIONS.get(step_no),
			}
		)

	return {
		"application": doc.name,
		"state": doc.workflow_state,
		"progress": progress(doc),
		"rows": rows,
		# The board greys itself out rather than offering controls that will be
		# refused; the server still checks on every update_step.
		"can_write": bool(doc.has_permission("write")),
	}
