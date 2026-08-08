# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import date_diff, getdate, nowdate

from sibbcs.admissions.tokens import generate_token

# Documents every applicant must supply before Documents Under Review can pass.
REQUIRED_DOCUMENTS = ["10th Marksheet", "12th Marksheet", "ID Proof", "Photo"]


class AdmissionApplication(Document):
	def validate(self):
		self.normalise()
		self.set_age()
		self.validate_dob()
		self.validate_references()
		self.set_docs_verified()

	def before_insert(self):
		self.issue_tokens()

	def before_save(self):
		# New referees or mentors added later must also get links.
		self.issue_tokens()

	# -- derived fields ---------------------------------------------------

	def normalise(self):
		self.full_name = (self.full_name or "").strip()
		self.email = (self.email or "").strip().lower()

	def set_age(self):
		"""Age in whole years at today's date."""
		if not self.dob:
			self.age = 0
			return
		self.age = int(date_diff(nowdate(), getdate(self.dob)) // 365.25)

	def validate_dob(self):
		if self.dob and getdate(self.dob) >= getdate(nowdate()):
			frappe.throw(_("Date of Birth must be in the past."), title=_("Invalid Date of Birth"))

	def set_docs_verified(self):
		"""True only when every required document is present and verified."""
		supplied = {
			d.document_type: d for d in self.application_documents if d.file
		}
		self.docs_verified = int(
			all(
				doc_type in supplied and supplied[doc_type].verified
				for doc_type in REQUIRED_DOCUMENTS
			)
		)

	def validate_references(self):
		seen = set()
		for row in self.reference_requests:
			email = (row.referee_email or "").strip().lower()
			row.referee_email = email
			if email and email in seen:
				frappe.throw(
					_("Referee {0} is listed twice.").format(email),
					title=_("Duplicate Referee"),
				)
			seen.add(email)

			if email and email == self.email:
				frappe.throw(
					_("An applicant cannot be their own referee."),
					title=_("Invalid Referee"),
				)

	# -- tokens -----------------------------------------------------------

	def issue_tokens(self):
		"""Give every referee and mentor row an opaque single-use token."""
		for row in self.reference_requests:
			if not row.token:
				row.token = generate_token()
		for row in self.mentor_consents:
			if not row.token:
				row.token = generate_token()

	# -- gate helpers used by the workflow --------------------------------

	def missing_documents(self):
		supplied = {d.document_type for d in self.application_documents if d.file}
		return [d for d in REQUIRED_DOCUMENTS if d not in supplied]

	def unverified_documents(self):
		return [d.document_type for d in self.application_documents if d.file and not d.verified]

	def pending_references(self):
		return [r.referee_name for r in self.reference_requests if not r.submitted_on]

	def has_mentor_consent(self):
		return any(c.consented_on for c in self.mentor_consents)

	def reference_link(self, row):
		return token_url("reference", row.token)

	def mentor_link(self, row):
		return token_url("mentor-consent", row.token)


def token_url(form_key, token):
	base = (frappe.utils.get_url() or "").rstrip("/")
	return f"{base}/{form_key}?token={token}"


@frappe.whitelist()
def send_reference_requests(application_name):
	"""Email each referee their token link. Skips ones already submitted."""
	app = frappe.get_doc("Admission Application", application_name)
	app.check_permission("write")

	sent = []
	for row in app.reference_requests:
		if row.submitted_on or not row.referee_email:
			continue

		frappe.sendmail(
			recipients=[row.referee_email],
			subject=_("Reference request for {0}").format(app.full_name),
			template="reference_request",
			args={
				"referee_name": row.referee_name,
				"applicant_name": app.full_name,
				"program": app.program,
				"link": token_url("reference", row.token),
			},
			header=[_("Reference Request"), "blue"],
			now=False,
		)
		row.db_set("sent_on", frappe.utils.now_datetime(), update_modified=False)
		sent.append(row.referee_email)

	if not sent:
		frappe.msgprint(_("No outstanding reference requests to send."), indicator="orange")
	else:
		frappe.msgprint(
			_("Reference requests queued to: {0}").format(", ".join(sent)), indicator="green"
		)
	return sent


@frappe.whitelist()
def send_mentor_consent_requests(application_name):
	"""Email each mentor their consent link."""
	app = frappe.get_doc("Admission Application", application_name)
	app.check_permission("write")

	sent = []
	for row in app.mentor_consents:
		if row.consented_on or not row.mentor_email:
			continue

		frappe.sendmail(
			recipients=[row.mentor_email],
			subject=_("Mentor consent for {0}").format(app.full_name),
			template="mentor_consent_request",
			args={
				"mentor_name": row.mentor_name,
				"applicant_name": app.full_name,
				"program": app.program,
				"link": token_url("mentor-consent", row.token),
			},
			header=[_("Mentor Consent"), "blue"],
			now=False,
		)
		row.db_set("sent_on", frappe.utils.now_datetime(), update_modified=False)
		sent.append(row.mentor_email)

	if not sent:
		frappe.msgprint(_("No outstanding mentor consent requests."), indicator="orange")
	else:
		frappe.msgprint(
			_("Mentor consent requests queued to: {0}").format(", ".join(sent)), indicator="green"
		)
	return sent
