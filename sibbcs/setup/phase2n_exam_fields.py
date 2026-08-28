"""Essay score fields on Qualifying Exam Result, and a pass mark of 70.

    bench --site online.sibbc.org execute sibbcs.setup.phase2n_exam_fields.build

Idempotent.

The record was built for a four-subject paper -- Bible, Theology, Ministry,
English, averaged into a percentage. The exam the college actually sets is
three essays of 25 marks, out of 75. Rather than drop the four fields and
orphan the results already recorded against them, the essay fields are added
alongside and `compute_total` uses whichever set is filled in.
"""

import frappe

from sibbcs.admissions.doctype.qualifying_exam_result.qualifying_exam_result import (
	ESSAY_MAX,
)
from sibbcs.setup.schema import add_fields, f, section

PASS_MARK = 40


def _essay_fields():
	return add_fields(
		"Qualifying Exam Result",
		[
			section("sb_essays", "Essay Marks"),
			f(
				"essay_gospel",
				f"Understanding of the Gospel (/{ESSAY_MAX})",
				"Float",
				description="Marked against the rubric in the entrance exam course.",
			),
			f("essay_calling", f"Sense of Calling to Ministry (/{ESSAY_MAX})", "Float"),
			f(
				"essay_motivation",
				f"Motivation for Theological Education (/{ESSAY_MAX})",
				"Float",
			),
		],
		insert_after="ministry_score",
	)


def _retitle_legacy():
	"""Say what the four subject scores are, so nobody fills both sets."""
	name = frappe.db.get_value(
		"DocField",
		{"parent": "Qualifying Exam Result", "fieldname": "sb_scores"},
		"name",
	)
	if name:
		frappe.db.set_value("DocField", name, "label", "Section Marks (former paper)")
	return bool(name)


def _pass_mark():
	name = frappe.db.get_value(
		"DocField",
		{"parent": "Qualifying Exam Result", "fieldname": "pass_mark"},
		"name",
	)
	if not name:
		return False
	frappe.db.set_value("DocField", name, "default", str(PASS_MARK))
	return True


def build():
	added = _essay_fields()
	retitled = _retitle_legacy()
	pass_mark = _pass_mark()

	frappe.db.commit()
	frappe.clear_cache(doctype="Qualifying Exam Result")

	print(f"Added: {added or 'nothing new'}")
	print(f"Legacy section retitled: {retitled}")
	print(f"pass_mark default set to {PASS_MARK}: {pass_mark}")
	print(
		"Existing four-subject results keep their averaging; a result with essay "
		"marks is scored out of 75 as a percentage."
	)
