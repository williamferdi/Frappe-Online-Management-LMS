"""The Admission Application workflow, from architecture doc §4.

    bench --site online.sibbc.org execute sibbcs.setup.phase2_workflow.build

    Draft
      -> Submitted                (applicant submits + pays the application fee)
      -> Documents Under Review   (officer verifies each Application Document)
      -> Awaiting References      (token links to 2 referees + mentor)
      -> Qualifying Exam Scheduled -> Passed / Failed
      -> Interview Scheduled       -> Cleared / Rejected
      -> Offer Sent
      -> Admission Fee Paid        <- the conversion point
      -> Enrolled
      -> Orientation Registered

Transitions carry `condition` expressions so the gates in §2.1 are enforced by
the framework rather than by hoping an officer checks. Conditions are evaluated
by Frappe against `doc`, so they must stay simple boolean expressions.

Rejection and withdrawal are reachable from most states -- an application that
cannot be refused mid-flight is not a real admissions process.
"""

import frappe

WORKFLOW = "Admission Application"
STATE_FIELD = "workflow_state"

OFFICER = "Admissions Officer"
REGISTRAR = "Registrar"

# state -> (docstatus, style, editable-by)
STATES = [
	("Draft", 0, "Warning", OFFICER),
	("Submitted", 0, "Info", OFFICER),
	("Documents Under Review", 0, "Info", OFFICER),
	("Awaiting References", 0, "Info", OFFICER),
	("Qualifying Exam Scheduled", 0, "Info", OFFICER),
	("Qualifying Exam Passed", 0, "Success", OFFICER),
	("Qualifying Exam Failed", 0, "Danger", OFFICER),
	("Interview Scheduled", 0, "Info", OFFICER),
	("Interview Cleared", 0, "Success", OFFICER),
	("Offer Sent", 0, "Success", OFFICER),
	("Admission Fee Paid", 0, "Success", REGISTRAR),
	("Enrolled", 0, "Success", REGISTRAR),
	("Orientation Registered", 0, "Success", REGISTRAR),
	("Rejected", 0, "Danger", OFFICER),
	("Withdrawn", 0, "Danger", OFFICER),
]

# (action, from, to, allowed role, condition or None)
TRANSITIONS = [
	(
		"Submit Application",
		"Draft",
		"Submitted",
		OFFICER,
		"doc.application_fee_paid",
	),
	("Start Document Review", "Submitted", "Documents Under Review", OFFICER, None),
	(
		"Documents Verified",
		"Documents Under Review",
		"Awaiting References",
		OFFICER,
		"doc.docs_verified",
	),
	(
		"References Received",
		"Awaiting References",
		"Qualifying Exam Scheduled",
		OFFICER,
		None,
	),
	(
		"Record Exam Pass",
		"Qualifying Exam Scheduled",
		"Qualifying Exam Passed",
		OFFICER,
		"doc.qualifying_exam_score >= 60",
	),
	(
		"Record Exam Fail",
		"Qualifying Exam Scheduled",
		"Qualifying Exam Failed",
		OFFICER,
		None,
	),
	("Schedule Interview", "Qualifying Exam Passed", "Interview Scheduled", OFFICER, None),
	(
		"Interview Cleared",
		"Interview Scheduled",
		"Interview Cleared",
		OFFICER,
		'doc.interview_outcome == "Recommend"',
	),
	("Send Offer", "Interview Cleared", "Offer Sent", OFFICER, None),
	(
		"Record Admission Fee",
		"Offer Sent",
		"Admission Fee Paid",
		REGISTRAR,
		"doc.admission_fee_paid",
	),
	# Enrolled is reached by the conversion function, which sets `student`.
	(
		"Enroll Student",
		"Admission Fee Paid",
		"Enrolled",
		REGISTRAR,
		"doc.student",
	),
	("Register Orientation", "Enrolled", "Orientation Registered", REGISTRAR, None),
	# retry paths
	("Re-schedule Exam", "Qualifying Exam Failed", "Qualifying Exam Scheduled", OFFICER, None),
	("Re-schedule Interview", "Interview Scheduled", "Interview Scheduled", OFFICER, None),
]

# states an application can be rejected or withdrawn from
ABANDONABLE = [
	"Submitted",
	"Documents Under Review",
	"Awaiting References",
	"Qualifying Exam Scheduled",
	"Qualifying Exam Passed",
	"Qualifying Exam Failed",
	"Interview Scheduled",
	"Interview Cleared",
	"Offer Sent",
]


def _ensure_states():
	for name, _docstatus, style, _role in STATES:
		if not frappe.db.exists("Workflow State", name):
			frappe.get_doc(
				{"doctype": "Workflow State", "workflow_state_name": name, "style": style}
			).insert(ignore_permissions=True)


def _ensure_actions():
	actions = {t[0] for t in TRANSITIONS} | {"Reject", "Withdraw"}
	for action in actions:
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc(
				{"doctype": "Workflow Action Master", "workflow_action_name": action}
			).insert(ignore_permissions=True)


def build():
	_ensure_states()
	_ensure_actions()

	if frappe.db.exists("Workflow", WORKFLOW):
		frappe.delete_doc("Workflow", WORKFLOW, force=1, ignore_permissions=True)

	workflow = frappe.get_doc(
		{
			"doctype": "Workflow",
			"workflow_name": WORKFLOW,
			"document_type": "Admission Application",
			"workflow_state_field": STATE_FIELD,
			"is_active": 1,
			"send_email_alert": 0,
			"override_status": 0,
		}
	)

	for name, docstatus, _style, role in STATES:
		workflow.append(
			"states",
			{
				"state": name,
				"doc_status": str(docstatus),
				"allow_edit": role,
			},
		)

	for action, source, target, role, condition in TRANSITIONS:
		workflow.append(
			"transitions",
			{
				"state": source,
				"action": action,
				"next_state": target,
				"allowed": role,
				"condition": condition,
				"allow_self_approval": 1,
			},
		)

	for source in ABANDONABLE:
		workflow.append(
			"transitions",
			{
				"state": source,
				"action": "Reject",
				"next_state": "Rejected",
				"allowed": OFFICER,
				"allow_self_approval": 1,
			},
		)
		workflow.append(
			"transitions",
			{
				"state": source,
				"action": "Withdraw",
				"next_state": "Withdrawn",
				"allowed": OFFICER,
				"allow_self_approval": 1,
			},
		)

	workflow.insert(ignore_permissions=True)
	frappe.db.commit()

	print(
		f"Workflow '{WORKFLOW}': {len(workflow.states)} states, "
		f"{len(workflow.transitions)} transitions."
	)
	return workflow.name
