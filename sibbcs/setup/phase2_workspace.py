"""An Admissions workspace.

    bench --site online.sibbc.org execute sibbcs.setup.phase2_workspace.build
"""

import frappe

WORKSPACE = "Admissions"

SHORTCUTS = [
	("Admission Application", "Blue"),
	("Lead", "Orange"),
	("Student", "Green"),
	("Program Enrollment", "Purple"),
]

LINK_CARDS = [
	("Pipeline", ["Lead", "Admission Application"]),
	("Assessment", ["Qualifying Exam Result", "Interview Record"]),
	("Outcome", ["Scholarship Request", "Student", "Program Enrollment"]),
]


def build():
	if frappe.db.exists("Workspace", WORKSPACE):
		frappe.delete_doc("Workspace", WORKSPACE, force=1, ignore_permissions=True)

	doc = frappe.get_doc(
		{
			"doctype": "Workspace",
			"name": WORKSPACE,
			"label": WORKSPACE,
			"title": WORKSPACE,
			"module": "Admissions",
			"public": 1,
			"icon": "users",
			"sequence_id": 10.0,
		}
	)

	for label, color in SHORTCUTS:
		doc.append(
			"shortcuts",
			{"type": "DocType", "link_to": label, "label": label, "color": color},
		)

	for card_label, doctypes in LINK_CARDS:
		doc.append(
			"links",
			{
				"type": "Card Break",
				"label": card_label,
				"hidden": 0,
				"onboard": 0,
				"link_count": len(doctypes),
			},
		)
		for doctype in doctypes:
			doc.append(
				"links",
				{
					"type": "Link",
					"link_type": "DocType",
					"link_to": doctype,
					"label": doctype,
					"hidden": 0,
					"onboard": 0,
					"is_query_report": 0,
				},
			)

	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	print(f"Workspace '{WORKSPACE}' created with {len(SHORTCUTS)} shortcuts.")
