"""Desk workspaces for the sibbcs modules.

    bench --site online.sibbc.org execute sibbcs.setup.workspaces.build_all

A Frappe v15 Workspace renders from its **`content`** field -- a JSON list of
layout blocks -- not from the `shortcuts` and `links` child tables directly.
Those tables only supply the targets; a workspace with a populated `shortcuts`
table but an empty `content` renders as a completely blank page, which is
exactly what happened to Academic and Admissions.

`content` blocks reference shortcuts by `shortcut_name` (matching
`Workspace Shortcut.label`) and link cards by `card_name` (matching the
`Card Break` row's label), so those strings have to line up exactly.
"""

import json
import secrets

import frappe

WORKSPACES = [
	{
		"name": "Academic",
		"icon": "education",
		"sequence": 20.0,
		"shortcuts": [
			("Course", "Blue"),
			("Course Offering", "Green"),
			("Academic Term", "Orange"),
			("Program", "Purple"),
			("Instructor", "Cyan"),
		],
		"cards": [
			("Catalog", [("Program", "DocType"), ("Course", "DocType"), ("Grade Scale", "DocType")]),
			(
				"Scheduling",
				[
					("Academic Term", "DocType"),
					("Course Offering", "DocType"),
					("Instructor", "DocType"),
				],
			),
			(
				"Students",
				[
					("Student", "DocType"),
					("Program Enrollment", "DocType"),
					("Course Registration", "DocType"),
					("Level Promotion", "DocType"),
				],
			),
		],
	},
	{
		"name": "Admissions",
		"icon": "users",
		"sequence": 10.0,
		"shortcuts": [
			("Admission Application", "Blue"),
			("Lead", "Orange"),
			("Student", "Green"),
			("Program Enrollment", "Purple"),
		],
		"cards": [
			("Pipeline", [("Lead", "DocType"), ("Admission Application", "DocType")]),
			(
				"Assessment",
				[("Qualifying Exam Result", "DocType"), ("Interview Record", "DocType")],
			),
			(
				"Outcome",
				[
					("Scholarship Request", "DocType"),
					("Student", "DocType"),
					("Program Enrollment", "DocType"),
				],
			),
		],
	},
	{
		"name": "Finance",
		"icon": "money-coins-1",
		"sequence": 30.0,
		"shortcuts": [
			("Fee Invoice", "Blue"),
			("Payment Entry", "Green"),
			("Fee Type", "Grey"),
		],
		"cards": [
			("Billing", [("Fee Type", "DocType"), ("Fee Invoice", "DocType")]),
			("Receipts", [("Payment Entry", "DocType")]),
			("Reports", [("Student Fee Ledger", "Report")]),
		],
	},
]


def _block(block_type, data):
	return {"id": secrets.token_hex(6), "type": block_type, "data": data}


def _heading(text):
	return _block("header", {"text": f'<span class="h4"><b>{text}</b></span>', "col": 12})


def build_content(spec):
	"""The layout block list that actually renders the page."""
	blocks = []

	if spec["shortcuts"]:
		blocks.append(_heading("Your Shortcuts"))
		for label, _colour in spec["shortcuts"]:
			blocks.append(_block("shortcut", {"shortcut_name": label, "col": 3}))
		blocks.append(_block("spacer", {"col": 12}))

	if spec["cards"]:
		blocks.append(_heading("Reports &amp; Masters"))
		for card_label, _items in spec["cards"]:
			blocks.append(_block("card", {"card_name": card_label, "col": 4}))

	return json.dumps(blocks)


def build(spec):
	name = spec["name"]

	if frappe.db.exists("Workspace", name):
		frappe.delete_doc("Workspace", name, force=1, ignore_permissions=True)

	doc = frappe.get_doc(
		{
			"doctype": "Workspace",
			"name": name,
			"label": name,
			"title": name,
			"module": name if frappe.db.exists("Module Def", name) else "Academic",
			"public": 1,
			"icon": spec["icon"],
			"sequence_id": spec["sequence"],
			"content": build_content(spec),
		}
	)

	for label, colour in spec["shortcuts"]:
		doc.append(
			"shortcuts",
			{"type": "DocType", "link_to": label, "label": label, "color": colour},
		)

	for card_label, items in spec["cards"]:
		doc.append(
			"links",
			{
				"type": "Card Break",
				"label": card_label,
				"hidden": 0,
				"onboard": 0,
				"link_count": len(items),
			},
		)
		for link_to, link_type in items:
			doc.append(
				"links",
				{
					"type": "Link",
					"link_type": link_type,
					"link_to": link_to,
					"label": link_to,
					"hidden": 0,
					"onboard": 0,
					"is_query_report": 1 if link_type == "Report" else 0,
				},
			)

	doc.insert(ignore_permissions=True)
	return doc


def build_all():
	built = []
	for spec in WORKSPACES:
		# Skip a workspace whose DocTypes are not installed yet, rather than
		# creating one that links to nothing.
		targets = [label for label, _c in spec["shortcuts"]]
		if not any(frappe.db.exists("DocType", t) for t in targets):
			print(f"  skipped {spec['name']} -- none of its DocTypes exist yet")
			continue

		doc = build(spec)
		blocks = json.loads(doc.content)
		built.append(doc.name)
		print(
			f"  {doc.name}: {len(doc.shortcuts)} shortcuts, "
			f"{len(spec['cards'])} cards, {len(blocks)} layout blocks"
		)

	frappe.db.commit()
	frappe.clear_cache()
	print(f"Workspaces rebuilt: {', '.join(built)}")
	return built
