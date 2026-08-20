"""Document upload from the public application form.

This is the one place an anonymous stranger can put a *file* on the server, so
it is deliberately narrow.

How it is kept safe:

* **Never free-floating.** A guest cannot upload without an `upload_token`,
  which is minted only when an application is created and stored on that
  application. Every file therefore belongs to exactly one real record.
* **The token is not a session.** It authorises attaching documents to one
  application and nothing else -- no reads, no edits, no other document types.
* **Extension, MIME and magic bytes must agree.** A `.pdf` whose first bytes
  are not `%PDF` is refused, which stops the oldest trick of renaming an
  executable or an HTML file with script in it.
* **Private files only.** `is_private=1`, so nothing lands on a guessable
  public URL.
* **Capped**: size per file, count per application.
* Applications already past review stop accepting uploads.
"""

import base64
import secrets

import frappe
from frappe import _

MAX_BYTES = 5 * 1024 * 1024
MAX_FILES_PER_APPLICATION = 15

# extension -> (allowed content types, magic byte prefixes)
ALLOWED = {
	"pdf": (("application/pdf",), (b"%PDF",)),
	"jpg": (("image/jpeg",), (b"\xff\xd8\xff",)),
	"jpeg": (("image/jpeg",), (b"\xff\xd8\xff",)),
	"png": (("image/png",), (b"\x89PNG\r\n\x1a\n",)),
}

ACCEPTED_DOCUMENT_TYPES = [
	"SSC/10th Mark Sheet",
	"HSLC/12th Mark Sheet",
	"Undergraduate Degree Certificate",
	"Undergraduate Degree Mark Sheet",
	"Personal Testimony",
	"National ID",
	"Ministry Proof",
	"Photo",
]

# Uploads are accepted while the application is still being assembled.
OPEN_STATES = ("", "Draft", "In Review")


def new_upload_token():
	return secrets.token_urlsafe(32)


def _resolve(application, upload_token):
	if not (application and upload_token):
		raise frappe.PermissionError("Upload not authorised.")

	stored = frappe.db.get_value(
		"Admission Application", application, ["upload_token", "workflow_state"], as_dict=True
	)
	if not stored or not stored.upload_token:
		raise frappe.PermissionError("Upload not authorised.")

	# constant-time compare: the token is the only credential
	import hmac

	if not hmac.compare_digest(str(stored.upload_token), str(upload_token)):
		raise frappe.PermissionError("Upload not authorised.")

	if (stored.workflow_state or "") not in OPEN_STATES:
		frappe.throw(
			_("This application is no longer accepting documents. Contact the Admissions Office."),
			title=_("Uploads Closed"),
		)

	return application


def _validate_file(filename, content, content_type=None):
	extension = (filename or "").rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""
	if extension not in ALLOWED:
		frappe.throw(
			_("Only PDF, JPG and PNG files are accepted. Received: {0}").format(extension or "?"),
			title=_("Unsupported File"),
		)

	if not content:
		frappe.throw(_("The file is empty."), title=_("Empty File"))

	if len(content) > MAX_BYTES:
		frappe.throw(
			_("Files must be under {0} MB.").format(MAX_BYTES // (1024 * 1024)),
			title=_("File Too Large"),
		)

	allowed_types, magic_prefixes = ALLOWED[extension]

	if content_type and content_type.split(";")[0].strip().lower() not in allowed_types:
		frappe.throw(_("The file type does not match its name."), title=_("Unsupported File"))

	# The name and the declared type can both lie; the bytes cannot.
	if not any(content.startswith(prefix) for prefix in magic_prefixes):
		frappe.throw(
			_("That file does not look like a real {0}.").format(extension.upper()),
			title=_("Unsupported File"),
		)

	if extension == "pdf":
		_check_pdf_readable(content)
	else:
		_check_image_readable(content, extension)

	return extension


def _check_image_readable(content, extension):
	"""Reject an image PIL cannot open, with advice rather than a stack trace.

	Frappe's File.save_file() runs strip_exif_data() on images -- which is worth
	having, since it removes the GPS coordinates a phone camera bakes into an
	applicant's photo. It opens the image with PIL, and a corrupt or truncated
	file makes that raise as an unhandled error.
	"""
	from io import BytesIO

	try:
		from PIL import Image

		image = Image.open(BytesIO(content))
		image.verify()
	except ImportError:
		return
	except Exception:
		frappe.throw(
			_(
				"That {0} could not be read -- it may be damaged or incomplete. "
				"Try opening it, re-saving it, and uploading again."
			).format(extension.upper()),
			title=_("Unreadable Image"),
		)


def _check_pdf_readable(content):
	"""Reject a PDF that cannot be parsed, with a message a person can act on.

	Frappe's File.check_content() runs pdf_contains_js(), which builds a
	PdfReader and scans for embedded JavaScript -- a control worth keeping. But
	on a truncated or corrupt PDF the reader raises, and that escapes as an
	unhandled server error rather than advice. Catch it here first.
	"""
	from io import BytesIO

	try:
		from pypdf import PdfReader

		PdfReader(BytesIO(content))
	except ImportError:
		return
	except Exception:
		frappe.throw(
			_(
				"That PDF could not be read -- it may be damaged or incomplete. "
				"Try opening it, re-saving it, and uploading again."
			),
			title=_("Unreadable PDF"),
		)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def upload_document(application, upload_token, document_type, filename, content, content_type=None):
	"""Attach one document to an application. The token is the only credential."""
	_resolve(application, upload_token)

	if document_type not in ACCEPTED_DOCUMENT_TYPES:
		frappe.throw(_("Unknown document type."), title=_("Invalid Document"))

	try:
		raw = base64.b64decode(content, validate=True)
	except Exception:
		frappe.throw(_("The file could not be read."), title=_("Upload Failed"))

	extension = _validate_file(filename, raw, content_type)

	doc = frappe.get_doc("Admission Application", application)

	if len(doc.application_documents or []) >= MAX_FILES_PER_APPLICATION:
		frappe.throw(
			_("You have already uploaded the maximum number of documents."),
			title=_("Too Many Files"),
		)

	safe_name = f"{application}-{frappe.scrub(document_type)}.{extension}"

	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": safe_name,
			"attached_to_doctype": "Admission Application",
			"attached_to_name": application,
			"content": raw,
			"decode": False,
			"is_private": 1,
		}
	)
	file_doc.flags.ignore_permissions = True
	file_doc.insert(ignore_permissions=True)

	# One row per document type: re-uploading replaces rather than duplicates.
	existing = next(
		(r for r in doc.application_documents if r.document_type == document_type), None
	)
	if existing:
		existing.file = file_doc.file_url
		existing.verified = 0
		existing.verified_by = None
	else:
		doc.append(
			"application_documents",
			{"document_type": document_type, "file": file_doc.file_url, "verified": 0},
		)

	# The photo also fills the application's own image field, which is what
	# Frappe renders at the top-right of the review form. Without this the
	# picture would sit in the documents table where a reviewer has to go
	# looking for it.
	if document_type == "Photo":
		doc.photo = file_doc.file_url

	doc.flags.ignore_permissions = True
	doc.save(ignore_permissions=True)

	return {
		"ok": True,
		"document_type": document_type,
		"uploaded": len(doc.application_documents),
	}


@frappe.whitelist(allow_guest=True)
def uploaded_documents(application, upload_token):
	"""What has been received so far, for the applicant's own progress display."""
	_resolve(application, upload_token)
	rows = frappe.get_all(
		"Application Document",
		filters={"parent": application, "parenttype": "Admission Application"},
		fields=["document_type", "file"],
	)
	return [r.document_type for r in rows if r.file]
