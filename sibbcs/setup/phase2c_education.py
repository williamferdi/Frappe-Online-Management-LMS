"""Educational history, document uploads, and the applicant photo.

    bench --site online.sibbc.org execute sibbcs.setup.phase2c_education.build

Idempotent.

* Adds the Educational History block from the college's reference form: SSC/10th,
  HSLC/12th and Undergraduate completion status and year, plus previous
  theological education.
* Renames the document types to the college's own vocabulary, so the labels an
  officer sees match the labels on the form the applicant filled in. Existing
  rows are migrated.
* Sets `image_field` on Admission Application so the applicant's photo appears
  in the top-right of the review form, which is what Frappe does natively with
  an Attach Image field.
* Adds `upload_token`, which ties a guest document upload to one real
  application (see admissions/uploads.py).
"""

import frappe

from sibbcs.setup.schema import add_fields, column, f, link, section, select

COMPLETION_STATUSES = ["", "Completed", "Pursuing", "Not Completed"]

# old label -> the college's wording
DOCUMENT_RENAMES = {
	"10th Marksheet": "SSC/10th Mark Sheet",
	"12th Marksheet": "HSLC/12th Mark Sheet",
	"Degree Certificate": "Undergraduate Degree Certificate",
	"Degree Marksheet": "Undergraduate Degree Mark Sheet",
	"Testimony": "Personal Testimony",
	"ID Proof": "National ID",
}

DOCUMENT_TYPES = [
	"SSC/10th Mark Sheet",
	"HSLC/12th Mark Sheet",
	"Undergraduate Degree Certificate",
	"Undergraduate Degree Mark Sheet",
	"Personal Testimony",
	"National ID",
	"Ministry Proof",
	"Photo",
]


def _education_fields():
	add_fields(
		"Admission Application",
		[
			section("sb_education", "Educational History"),
			select("ssc_status", "SSC / 10th Completion Status", COMPLETION_STATUSES),
			f("ssc_year", "SSC / 10th Completion Year", "Data", length=4),
			select("hslc_status", "HSLC / 12th Completion Status", COMPLETION_STATUSES),
			f("hslc_year", "HSLC / 12th Completion Year", "Data", length=4),
			column("cb_education"),
			select("ug_status", "Undergraduate Completion Status", COMPLETION_STATUSES),
			f("ug_year", "Undergraduate Completion Year", "Data", length=4),
			f(
				"previous_theological_education",
				"Any Previous Theological Education?",
				"Small Text",
				description="Institution, qualification and year, or 'None'.",
			),
		],
		insert_after="ministry_experience_doc",
	)

	add_fields(
		"Admission Application",
		[
			f(
				"upload_token",
				"Upload Token",
				"Data",
				read_only=1,
				hidden=1,
				no_copy=1,
				description="Authorises document upload from the public form for this application only.",
			)
		],
		insert_after="workflow_state",
	)


def _rename_document_types():
	"""Adopt the college's wording, and migrate the rows already using the old."""
	doc = frappe.get_doc("DocType", "Application Document")
	changed = False
	for row in doc.fields:
		if row.fieldname == "document_type":
			wanted = "\n".join(DOCUMENT_TYPES)
			if row.options != wanted:
				row.options = wanted
				changed = True
	if changed:
		doc.save(ignore_permissions=True)
		print("  document_type options updated to the college's wording")

	migrated = 0
	for old, new in DOCUMENT_RENAMES.items():
		count = frappe.db.count("Application Document", {"document_type": old})
		if not count:
			continue
		frappe.db.set_value(
			"Application Document",
			{"document_type": old},
			"document_type",
			new,
			update_modified=False,
		)
		migrated += count
	if migrated:
		print(f"  migrated {migrated} existing document row(s) to the new names")


def _show_photo_in_review():
	"""Frappe renders image_field at the top-right of the form."""
	doc = frappe.get_doc("DocType", "Admission Application")
	if doc.image_field != "photo":
		doc.image_field = "photo"
		doc.save(ignore_permissions=True)
		print("  applicant photo now shows top-right on Admission Application")


def build():
	_education_fields()
	_rename_document_types()
	_show_photo_in_review()
	frappe.db.commit()
	frappe.clear_cache()
	print("Education block, document naming and applicant photo installed.")
