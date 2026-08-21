# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""Guest document upload.

This is the only endpoint that lets an anonymous stranger put a file on the
server, so nearly all of these tests are about what it refuses.
"""

import base64

import frappe

from sibbcs.admissions.checklist import NO
from frappe.tests.utils import FrappeTestCase

from sibbcs.admissions.public_form import submit_application
from sibbcs.admissions.test_public_form import payload
from sibbcs.admissions.uploads import MAX_BYTES, upload_document

# Real images, not just the right magic bytes: Frappe strips EXIF from uploads
# with PIL, which needs a file it can actually open.
def _image(fmt):
	from io import BytesIO

	from PIL import Image

	buffer = BytesIO()
	Image.new("RGB", (8, 8), (120, 140, 160)).save(buffer, format=fmt)
	return buffer.getvalue()


PNG = _image("PNG")
JPG = _image("JPEG")
FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 40

# A structurally valid PDF, not just the right first four bytes. Frappe's
# File.check_content() parses uploaded PDFs to scan for embedded JavaScript, so
# a hand-faked header is rejected before it ever reaches our validation.
def _valid_pdf():
	from io import BytesIO

	from pypdf import PdfWriter

	writer = PdfWriter()
	writer.add_blank_page(width=200, height=200)
	buffer = BytesIO()
	writer.write(buffer)
	return buffer.getvalue()


PDF = _valid_pdf()
TRUNCATED_PDF = b"%PDF-1.4\ntruncated, never closed"


def b64(raw):
	return base64.b64encode(raw).decode()


class TestGuestUpload(FrappeTestCase):
	def _application(self, email):
		result = submit_application(**payload(email=email))
		return result["application"], result["upload_token"]

	def test_submission_returns_an_upload_token(self):
		_app, token = self._application("up1@example.invalid")
		self.assertTrue(token)
		self.assertGreaterEqual(len(token), 32)

	def test_pdf_is_accepted_and_attached(self):
		app, token = self._application("up2@example.invalid")
		result = upload_document(
			app, token, "SSC/10th Mark Sheet", "marks.pdf", b64(PDF), "application/pdf"
		)
		self.assertTrue(result["ok"])

		doc = frappe.get_doc("Admission Application", app)
		row = next(r for r in doc.application_documents if r.document_type == "SSC/10th Mark Sheet")
		self.assertTrue(row.file)
		self.assertFalse(row.verified)

	def test_uploaded_file_is_private(self):
		"""A public URL would let anyone read another applicant's ID."""
		app, token = self._application("up3@example.invalid")
		upload_document(app, token, "National ID", "id.png", b64(PNG), "image/png")

		file_name = frappe.db.get_value(
			"File", {"attached_to_name": app, "attached_to_doctype": "Admission Application"}, "name"
		)
		self.assertTrue(frappe.db.get_value("File", file_name, "is_private"))

	# --- refusals -------------------------------------------------------

	def test_upload_without_a_token_refused(self):
		app, _token = self._application("up4@example.invalid")
		with self.assertRaises(frappe.PermissionError):
			upload_document(app, "", "National ID", "id.pdf", b64(PDF))

	def test_wrong_token_refused(self):
		app, _token = self._application("up5@example.invalid")
		with self.assertRaises(frappe.PermissionError):
			upload_document(app, "x" * 40, "National ID", "id.pdf", b64(PDF))

	def test_token_from_one_application_cannot_upload_to_another(self):
		"""The token authorises one record, not the endpoint."""
		app_a, token_a = self._application("up6@example.invalid")
		app_b, _token_b = self._application("up7@example.invalid")
		with self.assertRaises(frappe.PermissionError):
			upload_document(app_b, token_a, "National ID", "id.pdf", b64(PDF))

	def test_executable_renamed_as_pdf_refused(self):
		"""Extension and magic bytes must agree."""
		app, token = self._application("up8@example.invalid")
		with self.assertRaises(frappe.ValidationError):
			upload_document(app, token, "National ID", "payload.pdf", b64(b"MZ\x90\x00evil"))

	def test_html_renamed_as_png_refused(self):
		app, token = self._application("up9@example.invalid")
		with self.assertRaises(frappe.ValidationError):
			upload_document(
				app, token, "Photo", "x.png", b64(b"<html><script>alert(1)</script>")
			)

	def test_disallowed_extension_refused(self):
		app, token = self._application("up10@example.invalid")
		with self.assertRaises(frappe.ValidationError):
			upload_document(app, token, "National ID", "notes.docx", b64(PDF))

	def test_mismatched_content_type_refused(self):
		app, token = self._application("up11@example.invalid")
		with self.assertRaises(frappe.ValidationError):
			upload_document(app, token, "National ID", "id.pdf", b64(PDF), "text/html")

	def test_oversized_file_refused(self):
		app, token = self._application("up12@example.invalid")
		big = PDF + b"0" * (MAX_BYTES + 1)
		with self.assertRaises(frappe.ValidationError):
			upload_document(app, token, "National ID", "big.pdf", b64(big), "application/pdf")

	def test_empty_file_refused(self):
		app, token = self._application("up13@example.invalid")
		with self.assertRaises(frappe.ValidationError):
			upload_document(app, token, "National ID", "empty.pdf", b64(b""))

	def test_corrupt_image_gets_a_readable_message(self):
		"""Right magic bytes, unopenable file. Frappe's EXIF stripper would
		otherwise raise an unhandled error at the applicant."""
		app, token = self._application("up18@example.invalid")
		with self.assertRaises(frappe.ValidationError) as caught:
			upload_document(app, token, "Photo", "broken.png", b64(FAKE_PNG), "image/png")
		self.assertIn("could not be read", str(caught.exception))

	def test_corrupt_pdf_gets_a_readable_message(self):
		"""Frappe parses PDFs to scan for embedded JavaScript; a truncated file
		makes that parser raise. The applicant must get advice, not a crash."""
		app, token = self._application("up17@example.invalid")
		with self.assertRaises(frappe.ValidationError) as caught:
			upload_document(
				app, token, "National ID", "broken.pdf",
				b64(TRUNCATED_PDF), "application/pdf",
			)
		self.assertIn("could not be read", str(caught.exception))

	def test_unknown_document_type_refused(self):
		app, token = self._application("up14@example.invalid")
		with self.assertRaises(frappe.ValidationError):
			upload_document(app, token, "Bank Statement", "x.pdf", b64(PDF))

	def test_reupload_replaces_rather_than_duplicates(self):
		app, token = self._application("up15@example.invalid")
		upload_document(app, token, "Photo", "a.jpg", b64(JPG), "image/jpeg")
		upload_document(app, token, "Photo", "b.jpg", b64(JPG), "image/jpeg")

		doc = frappe.get_doc("Admission Application", app)
		photos = [r for r in doc.application_documents if r.document_type == "Photo"]
		self.assertEqual(len(photos), 1)

	def test_uploads_close_once_the_application_moves_on(self):
		app, token = self._application("up16@example.invalid")
		frappe.db.set_value("Admission Application", app, "workflow_state", "Admitted")
		with self.assertRaises(frappe.ValidationError):
			upload_document(app, token, "National ID", "id.pdf", b64(PDF), "application/pdf")


class TestEducationFields(FrappeTestCase):
	def test_education_history_is_stored(self):
		result = submit_application(
			**payload(
				email="edu1@example.invalid",
				ssc_status="Completed",
				ssc_year="2010",
				hslc_status="Completed",
				hslc_year="2012",
				ug_status="Pursuing",
				ug_year="2027",
				previous_theological_education="Certificate in Theology, 2019",
			)
		)
		doc = frappe.get_doc("Admission Application", result["application"])
		self.assertEqual(doc.ssc_status, "Completed")
		self.assertEqual(doc.hslc_year, "2012")
		self.assertEqual(doc.ug_status, "Pursuing")
		self.assertIn("Certificate in Theology", doc.previous_theological_education)

	def test_photo_shows_in_the_review_form(self):
		"""Frappe renders image_field top-right on the form."""
		self.assertEqual(
			frappe.db.get_value("DocType", "Admission Application", "image_field"), "photo"
		)

	def test_uploading_a_photo_fills_the_image_field(self):
		"""Otherwise the picture sits in the documents table and never appears
		top-right, which is the whole point of showing it."""
		result = submit_application(**payload(email="photo1@example.invalid"))
		upload_document(
			result["application"],
			result["upload_token"],
			"Photo",
			"me.png",
			b64(PNG),
			"image/png",
		)
		doc = frappe.get_doc("Admission Application", result["application"])
		self.assertTrue(doc.photo, "photo field is empty, so nothing renders top-right")


class TestChecklistGateOnSave(FrappeTestCase):
	"""The gates must hold on a plain form save, not just through the API.

	An officer works the grid and presses Save; that path never calls
	checklist.set_status(), so without validation the gates are decorative
	exactly where they matter most.
	"""

	def _application(self, email):
		return submit_application(**payload(email=email))["application"]

	def _row(self, doc, step_no):
		return next(r for r in doc.checklist if int(r.step_no) == step_no)

	def test_grid_edit_cannot_bypass_a_gate(self):
		doc = frappe.get_doc("Admission Application", self._application("gg1@example.invalid"))
		self._row(doc, NO["entrance_exam"]).status = "Passed"  # the LMS account step is still Awaiting
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_grid_edit_allows_progress_short_of_completion(self):
		"""Gates guard completion, not progress: Scheduled is fine any time."""
		doc = frappe.get_doc("Admission Application", self._application("gg2@example.invalid"))
		self._row(doc, NO["entrance_exam"]).status = "Scheduled"
		doc.save(ignore_permissions=True)
		doc.reload()
		self.assertEqual(self._row(doc, NO["entrance_exam"]).status, "Scheduled")

	def test_grid_edit_works_once_the_gate_opens(self):
		doc = frappe.get_doc("Admission Application", self._application("gg3@example.invalid"))
		self._row(doc, NO["lms_account"]).status = "Created"
		doc.save(ignore_permissions=True)
		doc.reload()
		self._row(doc, NO["entrance_exam"]).status = "Passed"
		doc.save(ignore_permissions=True)
		doc.reload()
		self.assertEqual(self._row(doc, NO["entrance_exam"]).status, "Passed")

	def test_grid_edit_rejects_a_status_from_another_step(self):
		doc = frappe.get_doc("Admission Application", self._application("gg4@example.invalid"))
		self._row(doc, NO["admission_fee"]).status = "Onboarded"
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_unrelated_edit_does_not_re_judge_settled_rows(self):
		"""A record already in a valid combination must stay editable."""
		doc = frappe.get_doc("Admission Application", self._application("gg5@example.invalid"))
		self._row(doc, NO["admission_fee"]).status = "Paid"
		doc.save(ignore_permissions=True)
		doc.reload()
		self._row(doc, NO["decision"]).status = "Admitted"
		doc.save(ignore_permissions=True)
		doc.reload()

		doc.church_name = "Somewhere Else"
		doc.save(ignore_permissions=True)
		doc.reload()
		self.assertEqual(self._row(doc, NO["decision"]).status, "Admitted")
