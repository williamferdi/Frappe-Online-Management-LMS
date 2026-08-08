"""An Academic workspace so the Phase 1 masters are reachable in Desk.

    bench --site online.sibbc.org execute sibbcs.setup.phase1_workspace.build

Without this the DocTypes exist but a coordinator has to find them through the
awesome-bar, which is not a demonstrable Phase 1.
"""

import frappe

WORKSPACE = "Academic"

SHORTCUTS = [
	("Course", "Blue"),
	("Course Offering", "Green"),
	("Academic Term", "Orange"),
	("Program", "Purple"),
	("Instructor", "Cyan"),
]

LINK_CARDS = [
	(
		"Catalog",
		["Program", "Course", "Grade Scale"],
	),
	(
		"Scheduling",
		["Academic Term", "Course Offering", "Instructor"],
	),
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
			"module": "Academic",
			"public": 1,
			"icon": "education",
			"sequence_id": 20.0,
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
