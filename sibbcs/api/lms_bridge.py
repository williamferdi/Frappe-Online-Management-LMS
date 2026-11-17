# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""The one door marks come back through, from Campus LMS Lite.

Teaching and marking happen in the LMS; the transcript is made here. When staff
release a course result over there, it arrives as a percentage against one
registration and lands on a grade component, exactly as a hand-typed mark does.
Everything after that -- the weighted total, the Grade Scale, the letter, the
points, the pass flag, the enrolment progress -- is the pipeline that already
exists, untouched.

Written through `academic_api.save_grades` rather than around it. The grade
fields are permlevel 1, so saving the document *is* the permission check: a
caller without the authority to grade is refused here as they would be in Desk.

The other direction -- students, courses and registrations going out -- is
`sibbcs.integrations.campus_lms`.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from sibbcs.academic import gradebook
from sibbcs.api import academic_api


def _component_for(doc, requested):
	"""Which bucket the LMS result fills.

	Named by the caller, else by site config, else the only bucket there is.
	With several buckets and no name there is no safe guess -- putting a course
	result into "Attendance" would be worse than refusing.
	"""
	if requested:
		return requested
	configured = (frappe.conf.get("campus_lms_grade_component") or "").strip()
	if configured:
		return configured
	if len(doc.grade_components) == 1:
		return doc.grade_components[0].component
	frappe.throw(
		_("Say which grade component this mark is for: {0} has {1}.").format(
			doc.name,
			", ".join(c.component for c in doc.grade_components) or _("no components yet"),
		)
	)


@frappe.whitelist(methods=["POST"])
def post_final_mark(course_registration, percentage, component=None, status=None):
	"""Record a course result released in the LMS.

	Idempotent: sending the same mark again leaves the registration as it is,
	so a repeated or re-run release is harmless.
	"""
	mark = flt(percentage)
	if mark < 0 or mark > 100:
		frappe.throw(_("A course result must be between 0 and 100, not {0}.").format(percentage))

	doc = frappe.get_doc("Course Registration", course_registration)

	# Mirror the offering's scheme onto this registration first. A registration
	# created before its scheme existed carries no components at all, and
	# sending one bucket on its own would make `save_grades` the whole set --
	# a course weighted 60/40 would then award a final mark out of 60, silently.
	# `sync_components` keeps marks already entered and does not save.
	gradebook.sync_components(doc)

	bucket = _component_for(doc, component)

	rows = []
	found = False
	for existing in doc.grade_components:
		row = {
			"component": existing.component,
			"weight_pct": flt(existing.weight_pct),
			"max_marks": flt(existing.max_marks) or 100,
			# A bucket nobody has marked stays blank: a blank is not a zero, and
			# compute_grade holds the letter back until every bucket is in.
			"obtained_marks": flt(existing.obtained_marks) if cint(existing.marked) else None,
		}
		if existing.component == bucket:
			row["obtained_marks"] = mark
			found = True
		rows.append(row)

	if not found:
		if rows:
			# The LMS knows what the student scored; which buckets a course has,
			# and what each is worth, is the college's decision, made here.
			frappe.throw(
				_("{0} is not a grade component on {1}.").format(bucket, doc.course_offering)
			)
		rows.append({"component": bucket, "weight_pct": 100, "max_marks": 100, "obtained_marks": mark})

	result = academic_api.save_grades(doc.name, rows, status=status)
	result["component"] = bucket
	return result
