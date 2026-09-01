# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import date_diff, getdate, nowdate

from sibbcs.admissions.tokens import generate_token

# Documents every applicant must supply before Documents Under Review can pass.
REQUIRED_DOCUMENTS = [
	"SSC/10th Mark Sheet",
	"HSLC/12th Mark Sheet",
	"National ID",
	"Photo",
]


# Statuses that record something a person did, which nothing inferred from
# the record may undo. Only the event they are waiting for clears them.
STICKY_STATUSES = {"Resubmit Requested"}


class AdmissionApplication(Document):
	def validate(self):
		self.normalise()
		self.set_age()
		self.validate_dob()
		self.validate_references()
		self.set_docs_verified()
		self.validate_checklist()

	def validate_checklist(self):
		"""Enforce the step gates on a plain form save.

		checklist.set_status() guards the API path, but an officer working the
		grid and pressing Save never goes through it -- so without this the
		gates are decorative exactly where they are most likely to be used.

		Only rows whose status *changed* in this save are judged, so an
		application already sitting in a valid combination stays editable, and
		a backfilled record is never made unsavable by history.
		"""
		from sibbcs.admissions.checklist import blocked_reason, is_done, statuses_for

		previous = self.get_doc_before_save()
		was = {}
		if previous:
			was = {
				int(r.step_no): r.status
				for r in (previous.get("checklist") or [])
				if r.step_no
			}

		for row in self.get("checklist") or []:
			if not row.step_no:
				continue
			step_no = int(row.step_no)

			if row.status not in statuses_for(step_no):
				frappe.throw(
					_("{0} is not a valid status for step {1} ({2}). Allowed: {3}").format(
						row.status, step_no, row.step, ", ".join(statuses_for(step_no))
					),
					title=_("Invalid Status"),
				)

			if row.status == was.get(step_no):
				continue

			if is_done(step_no, row.status):
				reason = blocked_reason(self, step_no)
				if reason:
					frappe.throw(reason, title=_("Step Blocked"))

	def before_insert(self):
		self.issue_tokens()
		self.seed_checklist()

	def before_save(self):
		# New referees or mentors added later must also get links.
		self.issue_tokens()
		self.seed_checklist()
		self.mirror_gates_to_checklist()

	def on_update(self):
		from sibbcs.admissions.checklist import sync_overall_state
		from sibbcs.admissions.notifications import dispatch_on_placement

		sync_overall_state(self)

		# Referee and mentor requests go out on their own once the application
		# is placed. Before this they were sent only when an officer pressed a
		# button, so on a self-service application nobody was ever asked.
		try:
			self.reload()
			dispatch_on_placement(self)
		except Exception:
			frappe.log_error(title=f"Request dispatch failed for {self.name}")

	def seed_checklist(self):
		"""Every application carries the 13 tracked steps."""
		from sibbcs.admissions.checklist import seed

		seed(self)

	def mirror_gates_to_checklist(self):
		"""Keep the checklist honest about facts recorded elsewhere.

		Documents, references, the mentor form and the admission fee are all
		captured on other parts of the record. Reflecting them here means an
		officer never has to tick the same fact twice, and the board cannot
		drift from the data.
		"""
		from sibbcs.admissions.checklist import NO, is_done, statuses_for

		rows = {int(r.step_no): r for r in (self.get("checklist") or []) if r.step_no}

		def move(step_no, status):
			"""Set a row in place. No save -- this runs inside before_save, and
			checklist.set_status() saves, which would recurse forever."""
			row = rows.get(step_no)
			if not row or status not in statuses_for(step_no):
				return
			# Never walk a step backwards out of a completed state; an officer's
			# explicit decision outranks anything inferred here.
			if row.status == status or is_done(step_no, row.status):
				return
			# Nor out of a request the candidate has not answered yet. The
			# documents on file have not changed since an officer asked for
			# better ones, so the mirror would put the step straight back to
			# Awaiting Review on the very next save and lose the fact that
			# anybody asked. `uploads.upload_document` clears it when a file
			# actually arrives.
			if row.status in STICKY_STATUSES:
				return
			row.status = status
			row.updated_by = frappe.session.user
			row.updated_on = frappe.utils.now_datetime()

		# documents
		supplied = [d for d in self.application_documents if d.file]
		if self.docs_verified:
			move(NO["documents"], "Verified")
		elif supplied and len(supplied) < len(REQUIRED_DOCUMENTS):
			move(NO["documents"], "Partial Submission")
		elif supplied:
			move(NO["documents"], "Awaiting Review")

		# the two referees, tracked separately
		referee_steps = [NO["reference_1"], NO["reference_2"]]
		for index, row in enumerate(self.reference_requests[:2]):
			step_no = referee_steps[index]
			if row.submitted_on:
				move(step_no, "Received")
			elif row.sent_on:
				move(step_no, "Request Sent")

		# mentor
		mentor = self.mentor_consents[0] if self.mentor_consents else None
		if mentor:
			if mentor.consented_on:
				move(NO["mentor_form"], "Received")
			elif mentor.sent_on:
				move(NO["mentor_form"], "Request Sent")

		# LMS account and exam link.
		# Not through move(): "Created" already counts as done, so move()'s
		# never-walk-backwards guard would freeze the row there and the step
		# could never reach "Link Sent". This step has a known order, so
		# advancing along it is safe where a general rule would not be.
		lms_row = rows.get(NO["lms_account"])
		if lms_row:
			order = ["Awaiting", "Created", "Link Sent"]
			target = None
			if self.exam_link_sent_on:
				target = "Link Sent"
			elif self.applicant_user:
				target = "Created"
			current = lms_row.status if lms_row.status in order else "Awaiting"
			if target and order.index(target) > order.index(current):
				lms_row.status = target
				lms_row.updated_by = frappe.session.user
				lms_row.updated_on = frappe.utils.now_datetime()

		# admission fee
		if self.admission_fee_paid:
			move(NO["admission_fee"], "Paid")

		# manuals. Acknowledged only when every one of them is in; one
		# signed manual out of three is not a candidate who has read them.
		manuals = self.get("manual_acknowledgements") or []
		if manuals:
			if all(m.acknowledged_on for m in manuals):
				move(NO["manual_reading"], "Acknowledged")
			elif any(m.sent_on for m in manuals):
				move(NO["manual_reading"], "Sent")

		# a Student exists, so onboarding happened however it was reached.
		if self.student:
			move(NO["onboarding"], "Onboarded")

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
		if not self.upload_token:
			# Every application, not only the ones that came through /apply.
			# An application typed into Desk had no token, so there was no
			# link to send when the office needed a document from it.
			from sibbcs.admissions.uploads import new_upload_token

			self.upload_token = new_upload_token()

		for row in self.reference_requests:
			if not row.token:
				row.token = generate_token()
		for row in self.mentor_consents:
			if not row.token:
				row.token = generate_token()
		# Manual rows are normally created by manuals.attach_manuals, which
		# issues its own tokens; this covers a row added by hand in the grid,
		# which would otherwise have an unopenable link.
		for row in self.get("manual_acknowledgements") or []:
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
	"""A link an outsider can actually open.

	Not frappe.utils.get_url(): outside production mode it appends the dev
	webserver port, so every referee and mentor email would have carried
	https://online.sibbc.org:8000/... which is unreachable from the internet.
	gateway.public_url() builds from host_name instead.
	"""
	from sibbcs.finance.gateway import public_url

	return public_url(f"/{form_key}?token={token}")


@frappe.whitelist()
def send_reference_requests(application_name):
	"""Send outstanding reference requests.

	Delegates to notifications.dispatch_requests so the manual button and the
	automatic dispatch-on-placement path cannot drift apart, and so a missing
	mail account produces advice rather than Frappe's raw
	"Please setup default outgoing Email Account" error.
	"""
	from sibbcs.admissions.notifications import outgoing_configured, dispatch_requests

	app = frappe.get_doc("Admission Application", application_name)
	app.check_permission("write")

	if not outgoing_configured():
		frappe.msgprint(
			_("No outgoing email account is configured, so nothing can be sent."),
			title=_("Email Not Configured"),
			indicator="orange",
		)
		return []

	sent = dispatch_requests(application_name)["referees"]
	if sent:
		frappe.msgprint(
			_("Reference requests queued to: {0}").format(", ".join(sent)), indicator="green"
		)
	else:
		frappe.msgprint(_("No outstanding reference requests to send."), indicator="orange")
	return sent


@frappe.whitelist()
def send_mentor_consent_requests(application_name):
	"""Send outstanding mentor consent requests."""
	from sibbcs.admissions.notifications import outgoing_configured, dispatch_requests

	app = frappe.get_doc("Admission Application", application_name)
	app.check_permission("write")

	if not outgoing_configured():
		frappe.msgprint(
			_("No outgoing email account is configured, so nothing can be sent."),
			title=_("Email Not Configured"),
			indicator="orange",
		)
		return []

	sent = dispatch_requests(application_name)["mentor"]
	if sent:
		frappe.msgprint(
			_("Mentor consent requests queued to: {0}").format(", ".join(sent)),
			indicator="green",
		)
	else:
		frappe.msgprint(_("No outstanding mentor consent requests."), indicator="orange")
	return sent
