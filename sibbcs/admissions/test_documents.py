# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""Reviewing documents, and asking for them again.

The interesting part is not the ticking. It is that ticking the last required
box moves the checklist step without this module saying so, and that the
request an officer sends survives the next save of the application.
"""

from contextlib import contextmanager
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.admissions import checklist, documents
from sibbcs.admissions.doctype.admission_application.admission_application import (
	REQUIRED_DOCUMENTS,
)
from sibbcs.admissions.doctype.admission_application.test_admission_application import (
	make_application,
)
from sibbcs.api.test_api import make_user

DOCUMENTS_STEP = checklist.NO["documents"]


def an_application(**overrides):
	tag = frappe.generate_hash(length=6)
	values = {
		"full_name": f"Doc Review {tag}",
		"email": f"docreview.{tag}@example.invalid",
		"documents": [
			{"document_type": document_type, "file": f"/files/{tag}-{index}.pdf"}
			for index, document_type in enumerate(REQUIRED_DOCUMENTS)
		],
	}
	values.update(overrides)
	return make_application(**values)



@contextmanager
def sending():
	"""Pretend the college has an outgoing mail account, and catch the post.

	The test site has none, and giving it one would make the suite able to
	send real email to real addresses. Both guards are covered by their own
	tests; everything else asserts on what would have gone out.
	"""
	with patch(
		"sibbcs.admissions.documents.outgoing_configured", return_value=True
	), patch("frappe.sendmail") as sendmail:
		yield sendmail

def rows_of(application):
	return frappe.get_doc("Admission Application", application).application_documents


class TestReviewingOneDocument(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_a_tick_records_who_ticked_it(self):
		doc = an_application()
		row = doc.application_documents[0]

		result = documents.review(doc.name, row.name, verified=1)

		saved = next(r for r in rows_of(doc.name) if r.name == row.name)
		self.assertTrue(saved.verified)
		self.assertEqual(saved.verified_by, frappe.session.user)
		self.assertTrue(result["documents"][0]["verified"])

	def test_unticking_takes_the_name_off_it_too(self):
		"""A verified_by left behind on an unticked row says somebody stands
		behind a document nobody has accepted."""
		doc = an_application()
		row = doc.application_documents[0]
		documents.review(doc.name, row.name, verified=1)

		documents.review(doc.name, row.name, verified=0)

		saved = next(r for r in rows_of(doc.name) if r.name == row.name)
		self.assertFalse(saved.verified)
		self.assertIsNone(saved.verified_by)

	def test_remarks_are_kept_against_the_row(self):
		doc = an_application()
		row = doc.application_documents[0]

		documents.review(doc.name, row.name, remarks="  The scan is cut off  ")

		saved = next(r for r in rows_of(doc.name) if r.name == row.name)
		self.assertEqual(saved.remarks, "The scan is cut off")

	def test_a_document_with_no_file_cannot_be_verified(self):
		doc = an_application(documents=[{"document_type": "Photo"}])
		row = doc.application_documents[0]

		with self.assertRaises(frappe.ValidationError):
			documents.review(doc.name, row.name, verified=1)

	def test_a_row_from_another_application_is_refused(self):
		mine = an_application()
		theirs = an_application()

		with self.assertRaises(frappe.ValidationError):
			documents.review(mine.name, theirs.application_documents[0].name, verified=1)

	def test_a_reader_who_may_not_write_is_refused(self):
		doc = an_application()
		email = f"coord.{frappe.generate_hash(length=8)}@example.invalid"
		make_user(email, ["Academic Coordinator"])

		frappe.set_user(email)
		with self.assertRaises(frappe.PermissionError):
			documents.review(doc.name, doc.application_documents[0].name, verified=1)


class TestTheStepFollowsTheBoxes(FrappeTestCase):
	"""Requirement one: tick them all and the step verifies itself.

	Nothing in `documents.py` sets that status. `set_docs_verified` derives the
	gate and `mirror_gates_to_checklist` moves the step, so these tests are
	really asserting that the review endpoint saves through the document rather
	than around it.
	"""

	def test_ticking_the_last_required_box_verifies_the_step(self):
		doc = an_application()

		for index, row in enumerate(doc.application_documents):
			result = documents.review(doc.name, row.name, verified=1)
			status = next(
				r["status"] for r in result["checklist"]["rows"] if r["step_no"] == DOCUMENTS_STEP
			)
			last = index == len(REQUIRED_DOCUMENTS) - 1
			self.assertEqual(status == "Verified", last, f"after {index + 1} ticks")

		self.assertTrue(frappe.db.get_value("Admission Application", doc.name, "docs_verified"))

	def test_an_optional_document_does_not_move_the_step_on_its_own(self):
		"""The gate is the required list, and an officer who is not told that
		will think the screen is broken -- so the endpoint reports the list."""
		doc = an_application(
			documents=[{"document_type": "Personal Testimony", "file": "/files/t.pdf"}]
		)
		row = doc.application_documents[0]

		result = documents.review(doc.name, row.name, verified=1)

		status = next(
			r["status"] for r in result["checklist"]["rows"] if r["step_no"] == DOCUMENTS_STEP
		)
		self.assertNotEqual(status, "Verified")
		self.assertEqual(result["required"], list(REQUIRED_DOCUMENTS))

	def test_unticking_one_takes_the_step_back(self):
		doc = an_application()
		for row in doc.application_documents:
			documents.review(doc.name, row.name, verified=1)

		result = documents.review(
			doc.name, doc.application_documents[0].name, verified=0
		)

		self.assertFalse(result["docs_verified"])


class TestOutstanding(FrappeTestCase):
	def test_never_arrived_and_not_accepted_are_different_answers(self):
		"""'Send it again' is useless advice for a file nobody has ever seen."""
		doc = an_application(
			documents=[
				{"document_type": "SSC/10th Mark Sheet", "file": "/files/ssc.pdf"},
			]
		)

		items = documents.outstanding(doc.name)
		by_type = {item["document_type"]: item for item in items}

		self.assertFalse(by_type["SSC/10th Mark Sheet"]["missing"])
		self.assertTrue(by_type["Photo"]["missing"])
		self.assertNotIn("Personal Testimony", by_type, "optional and never sent")

	def test_a_verified_document_is_not_outstanding(self):
		doc = an_application()
		for row in doc.application_documents:
			documents.review(doc.name, row.name, verified=1)

		self.assertEqual(documents.outstanding(doc.name), [])


class TestRequestingAResubmit(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_nothing_outstanding_means_nothing_to_ask_for(self):
		doc = an_application()
		for row in doc.application_documents:
			documents.review(doc.name, row.name, verified=1)

		with self.assertRaises(frappe.ValidationError):
			documents.request_resubmit(doc.name)

	def test_the_step_moves_and_stays_moved(self):
		"""The bug this guards: `mirror_gates_to_checklist` runs on every save
		and would put the step straight back to Awaiting Review, losing the
		fact that anybody was ever asked."""
		doc = an_application()
		with sending():
			documents.request_resubmit(doc.name)

		self.assertEqual(checklist.status_of(doc.name, DOCUMENTS_STEP), "Resubmit Requested")

		# Any unrelated save at all.
		again = frappe.get_doc("Admission Application", doc.name)
		again.notes = "an officer typed something"
		again.save()

		self.assertEqual(checklist.status_of(doc.name, DOCUMENTS_STEP), "Resubmit Requested")

	def test_an_arriving_file_ends_the_wait(self):
		"""And the one event that is allowed to clear it does."""
		from sibbcs.admissions import uploads

		doc = an_application()
		with sending():
			documents.request_resubmit(doc.name)

		fresh = frappe.get_doc("Admission Application", doc.name)
		uploads._answer_resubmit_request(fresh)
		fresh.save(ignore_permissions=True)

		self.assertEqual(checklist.status_of(doc.name, DOCUMENTS_STEP), "Awaiting Review")

	def test_it_stamps_when_the_office_asked(self):
		doc = an_application()
		with sending():
			documents.request_resubmit(doc.name)

		self.assertTrue(
			frappe.db.get_value(
				"Admission Application", doc.name, "docs_resubmit_requested_on"
			)
		)

	def test_the_email_names_what_is_wrong_with_each_document(self):
		doc = an_application(
			documents=[{"document_type": "SSC/10th Mark Sheet", "file": "/files/ssc.pdf"}]
		)
		documents.review(
			doc.name, doc.application_documents[0].name, remarks="The scan is cut off"
		)

		with sending() as sendmail:
			result = documents.request_resubmit(
				doc.name, message="Please be quick."
			)

		self.assertEqual(result["sent_to"], doc.email)
		body = sendmail.call_args.kwargs["message"]
		self.assertEqual(sendmail.call_args.kwargs["recipients"], [doc.email])
		self.assertIn("The scan is cut off", body)
		self.assertIn("Please be quick.", body)
		# The link the candidate actually needs, carrying the credential that
		# `uploads.upload_document` already checks.
		self.assertIn("/documents?application=", body)
		self.assertIn(
			frappe.db.get_value("Admission Application", doc.name, "upload_token"), body
		)

	def test_an_application_past_uploads_is_told_so_rather_than_mailed(self):
		doc = an_application()
		frappe.db.set_value("Admission Application", doc.name, "workflow_state", "Admitted")

		with self.assertRaises(frappe.ValidationError):
			documents.request_resubmit(doc.name)

	def test_no_mail_account_is_said_plainly_and_nothing_is_stamped(self):
		"""A silent failure here looks exactly like a sent email."""
		doc = an_application(
			documents=[{"document_type": "Photo", "file": "/files/p.pdf"}]
		)

		with patch(
			"sibbcs.admissions.documents.outgoing_configured", return_value=False
		), self.assertRaises(frappe.ValidationError):
			documents.request_resubmit(doc.name)

		self.assertIsNone(
			frappe.db.get_value(
				"Admission Application", doc.name, "docs_resubmit_requested_on"
			)
		)

	def test_a_reader_who_may_not_write_cannot_send_it(self):
		doc = an_application()
		email = f"coord.{frappe.generate_hash(length=8)}@example.invalid"
		make_user(email, ["Academic Coordinator"])

		frappe.set_user(email)
		with self.assertRaises(frappe.PermissionError):
			documents.request_resubmit(doc.name)
