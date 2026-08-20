"""Rework the admission process into the 13-step checklist.

    bench --site online.sibbc.org execute sibbcs.setup.phase2b_checklist.build

Idempotent.

What changes and why:

* The 15-state linear workflow is replaced by 13 independently-tracked steps.
  The old model could hold one state at a time, which could not represent the
  office's actual board -- admission fee Paid while the entrance exam is still
  Awaiting, Reference 1 Awaiting while Reference 2 is Received.
* `workflow_state` shrinks to a derived summary (Draft, In Review, Admitted,
  Onboarded, Rejected, Withdrawn).
* Onboarding (step 13) becomes where the level and term are decided, so the
  application gains `onboard_level` and `onboard_term`. This deliberately
  overrides architecture doc §4, which said enrollment always starts at
  Level 1 -- the college has since confirmed any level 1-4 may be admitted.
* The manual a student must read before onboarding gets a DocType and a
  tokenised acknowledgement, reusing the Phase 2 token controller.
"""

import frappe

from sibbcs.admissions.checklist import ALL_STATUSES, STEP_LABELS
from sibbcs.setup.schema import (
	add_fields,
	check,
	column,
	ensure_doctype,
	f,
	fetched,
	full,
	link,
	read,
	section,
	select,
	table,
)

ADMISSIONS = "Admissions"
LEVELS = ["1", "2", "3", "4"]


def _checklist_item():
	ensure_doctype(
		"Admission Checklist Item",
		ADMISSIONS,
		istable=1,
		fields=[
			f("step_no", "#", "Int", reqd=1, in_list_view=1, columns=1, read_only=1),
			select("step", "Step", STEP_LABELS, reqd=1, in_list_view=1, columns=3, read_only=1),
			select(
				"status",
				"Status",
				ALL_STATUSES,
				reqd=1,
				in_list_view=1,
				columns=2,
				description=(
					"Only statuses valid for this step are accepted; the server "
					"rejects the rest."
				),
			),
			f("owner_role", "Owner", "Data", read_only=1, in_list_view=1, columns=2),
			f("remarks", "Remarks", "Small Text", in_list_view=1, columns=2),
			section("sb_audit"),
			link("updated_by", "Updated By", "User", read_only=1),
			column("cb_audit"),
			f("updated_on", "Updated On", "Datetime", read_only=1),
		],
	)


def _reading_manual():
	ensure_doctype(
		"Reading Manual Program",
		ADMISSIONS,
		istable=1,
		fields=[link("program", "Program", "Program", reqd=1, in_list_view=1)],
	)

	ensure_doctype(
		"Reading Manual",
		ADMISSIONS,
		fields=[
			section("sb_identity"),
			f("manual_title", "Title", reqd=1, unique=1, in_list_view=1),
			f("version", "Version", default="1", in_list_view=1),
			column("cb_identity"),
			check("is_active", "Is Active", default=1, in_list_view=1),
			f(
				"require_scroll",
				"Require Scroll To End",
				"Check",
				default="1",
				description="Enable the acknowledge button only after the reader reaches the end.",
			),
			section("sb_scope", "Applies To"),
			table(
				"applies_to_programs",
				"Programs",
				"Reading Manual Program",
			),
			section("sb_content", "Content"),
			f(
				"content",
				"Content",
				"Text Editor",
				description="Shown on the acknowledgement page. Leave blank to use the attachment only.",
			),
			f("attachment", "Attachment", "Attach"),
		],
		permissions=[
			full("System Manager"),
			full("Registrar"),
			read("Admissions Officer"),
			read("Academic Coordinator"),
			read("Student"),
		],
		autoname="field:manual_title",
		naming_rule="By fieldname",
	)

	ensure_doctype(
		"Manual Acknowledgement",
		ADMISSIONS,
		istable=1,
		fields=[
			link("manual", "Manual", "Reading Manual", reqd=1, in_list_view=1, columns=3),
			f("sent_on", "Sent On", "Datetime", read_only=1, in_list_view=1, columns=2),
			f("acknowledged_on", "Acknowledged On", "Datetime", read_only=1, in_list_view=1, columns=2),
			f("acknowledged_name", "Signed As", "Data", read_only=1, in_list_view=1, columns=2),
			section("sb_token"),
			f("token", "Token", read_only=1, no_copy=1),
			column("cb_token"),
			f("ip_address", "IP Address", "Data", read_only=1, no_copy=1),
		],
	)


def _application_fields():
	"""Checklist table, manual acknowledgements, and the onboarding decision."""
	add_fields(
		"Admission Application",
		[
			section("sb_checklist", "Admission Checklist"),
			table("checklist", "Checklist", "Admission Checklist Item"),
		],
		insert_after="workflow_state",
	)

	add_fields(
		"Admission Application",
		[
			section("sb_manual", "Manual Reading"),
			table("manual_acknowledgements", "Manuals", "Manual Acknowledgement"),
		],
		insert_after="mentor_consents",
	)

	add_fields(
		"Admission Application",
		[
			section("sb_onboarding", "Onboarding Decision"),
			select(
				"onboard_level",
				"Admit at Level",
				[""] + LEVELS,
				description=(
					"Decided at step 13. Overrides the old always-Level-1 rule; "
					"the enrollment is created at this level."
				),
			),
			link(
				"onboard_term",
				"Admit into Term",
				"Academic Term",
				description="Defaults to the intake term if left blank.",
			),
		],
		insert_after="student",
	)


def _simplify_workflow():
	"""Replace the 15-state chain with the derived summary states.

	The Workflow document itself is removed: the checklist is now the source of
	truth and a Frappe Workflow would fight it for control of `workflow_state`.
	The states remain as Workflow State records so the indicator colours and any
	existing values still render.
	"""
	from sibbcs.admissions.checklist import OVERALL_STATES

	styles = {
		"Draft": "Warning",
		"In Review": "Info",
		"Admitted": "Success",
		"Onboarded": "Success",
		"Rejected": "Danger",
		"Withdrawn": "Danger",
	}

	for state in OVERALL_STATES:
		if not frappe.db.exists("Workflow State", state):
			frappe.get_doc(
				{
					"doctype": "Workflow State",
					"workflow_state_name": state,
					"style": styles.get(state, "Info"),
				}
			).insert(ignore_permissions=True)

	if frappe.db.exists("Workflow", "Admission Application"):
		frappe.delete_doc("Workflow", "Admission Application", force=1, ignore_permissions=True)
		print("  removed the old 15-state Workflow -- the checklist now owns the state")


def backfill():
	"""Seed the checklist on applications that predate it, and map old states."""
	from sibbcs.admissions.checklist import seed, set_status, sync_overall_state

	# old state -> what the checklist should already show
	carry_over = {
		"Submitted": [],
		"Documents Under Review": [(2, "Awaiting Review")],
		"Awaiting References": [(2, "Verified")],
		"Qualifying Exam Scheduled": [(2, "Verified"), (8, "Scheduled")],
		"Qualifying Exam Passed": [(2, "Verified"), (8, "Passed")],
		"Qualifying Exam Failed": [(2, "Verified"), (8, "Failed")],
		"Interview Scheduled": [(2, "Verified"), (8, "Passed"), (9, "Scheduled")],
		"Interview Cleared": [(2, "Verified"), (8, "Passed"), (9, "Cleared")],
		"Offer Sent": [(2, "Verified"), (8, "Passed"), (9, "Cleared")],
		"Admission Fee Paid": [(10, "Paid")],
		"Enrolled": [(10, "Paid"), (11, "Admitted")],
		"Orientation Registered": [(10, "Paid"), (11, "Admitted")],
	}

	touched = 0
	for name in frappe.get_all("Admission Application", pluck="name"):
		doc = frappe.get_doc("Admission Application", name)
		before = len(doc.get("checklist") or [])
		seed(doc)
		if len(doc.get("checklist") or []) != before:
			doc.flags.ignore_permissions = True
			doc.save(ignore_permissions=True)
			touched += 1

		for step_no, status in carry_over.get(doc.workflow_state or "", []):
			try:
				set_status(doc, step_no, status, ignore_gates=True)
			except Exception:
				pass

		doc.reload()
		sync_overall_state(doc)

	print(f"Backfilled the checklist onto {touched} application(s).")


def build():
	_checklist_item()
	_reading_manual()
	_application_fields()
	_simplify_workflow()
	frappe.db.commit()

	backfill()
	frappe.db.commit()

	print("13-step checklist installed.")
	print(f"  statuses in the union: {len(ALL_STATUSES)}")
	print("  hard gates: 8<-7, 11<-10, 12<-11(Admitted), 13<-11(Admitted)+12")
