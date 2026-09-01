# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""The public application form.

This is the only endpoint an anonymous stranger can write to, so most of these
tests are about what it refuses.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.admissions.public_form import APPLICANT_FIELDS, submit_application


def payload(**overrides):
	values = {
		"full_name": "Public Applicant",
		"email": "public1@example.invalid",
		"mobile": "9000001111",
		"program": "MDIV",
		"dob": "1994-03-02",
		"church_name": "Grace Baptist",
		"referee1_name": "Pastor A",
		"referee1_email": "ref.a@example.invalid",
		"referee1_type": "Pastor-Mentor",
		"referee2_name": "Prof B",
		"referee2_email": "ref.b@example.invalid",
		"referee2_type": "Professor-Employer",
		"mentor_name": "Mentor M",
		"mentor_email": "mentor.m@example.invalid",
	}
	values.update(overrides)
	return values


class TestPublicApplication(FrappeTestCase):
	def test_creates_a_draft_application(self):
		result = submit_application(**payload())
		doc = frappe.get_doc("Admission Application", result["application"])
		self.assertEqual(doc.full_name, "Public Applicant")
		self.assertEqual(doc.program, "MDIV")

	def test_email_is_lower_cased(self):
		result = submit_application(**payload(email="MiXeD@Example.Invalid"))
		doc = frappe.get_doc("Admission Application", result["application"])
		self.assertEqual(doc.email, "mixed@example.invalid")

	def test_referees_and_mentor_are_attached_with_tokens(self):
		result = submit_application(**payload(email="public2@example.invalid"))
		doc = frappe.get_doc("Admission Application", result["application"])

		self.assertEqual(len(doc.reference_requests), 2)
		self.assertEqual(len(doc.mentor_consents), 1)
		for row in doc.reference_requests:
			self.assertTrue(row.token)
		self.assertTrue(doc.mentor_consents[0].token)

	# --- what it must refuse -------------------------------------------

	def test_gates_cannot_be_set_from_the_form(self):
		"""The whole point of the whitelist: no self-service admission."""
		result = submit_application(
			**payload(
				email="public3@example.invalid",
				application_fee_paid=1,
				admission_fee_paid=1,
				docs_verified=1,
				qualifying_exam_score=99,
				interview_outcome="Recommend",
				workflow_state="Enrolled",
				student="SIB-2026-0001",
			)
		)
		doc = frappe.get_doc("Admission Application", result["application"])

		self.assertFalse(doc.application_fee_paid)
		self.assertFalse(doc.admission_fee_paid)
		self.assertFalse(doc.docs_verified)
		self.assertFalse(doc.qualifying_exam_score)
		self.assertFalse(doc.interview_outcome)
		self.assertFalse(doc.student)

	def test_whitelist_excludes_every_gate(self):
		for field in (
			"application_fee_paid", "admission_fee_paid", "docs_verified",
			"qualifying_exam_score", "interview_outcome", "offer_sent_on",
			"student", "workflow_state", "scholarship_request", "notes",
		):
			self.assertNotIn(field, APPLICANT_FIELDS, field)

	def test_honeypot_blocks_submission(self):
		with self.assertRaises(frappe.ValidationError):
			submit_application(**payload(email="bot@example.invalid", website="http://spam"))

	def test_missing_required_fields_refused(self):
		with self.assertRaises(frappe.ValidationError):
			submit_application(**payload(email="public4@example.invalid", full_name=""))

	def test_unknown_program_refused(self):
		with self.assertRaises(frappe.ValidationError):
			submit_application(**payload(email="public5@example.invalid", program="NOT-A-PROGRAM"))

	def test_invalid_email_refused(self):
		with self.assertRaises(Exception):
			submit_application(**payload(email="not-an-email"))

	def test_future_dob_refused(self):
		with self.assertRaises(frappe.ValidationError):
			submit_application(
				**payload(email="public6@example.invalid", dob=frappe.utils.add_days(frappe.utils.nowdate(), 5))
			)

	def test_applicant_cannot_be_their_own_referee(self):
		with self.assertRaises(frappe.ValidationError):
			submit_application(
				**payload(email="self@example.invalid", referee1_email="self@example.invalid")
			)

	def test_duplicate_referees_refused(self):
		with self.assertRaises(frappe.ValidationError):
			submit_application(
				**payload(
					email="public7@example.invalid",
					referee1_email="same@example.invalid",
					referee2_email="same@example.invalid",
				)
			)

	def test_second_open_application_refused(self):
		submit_application(**payload(email="twice@example.invalid"))
		with self.assertRaises(frappe.ValidationError):
			submit_application(**payload(email="twice@example.invalid"))

	def test_reapplying_allowed_after_rejection(self):
		"""A rejected candidate may apply again in a later intake."""
		result = submit_application(**payload(email="again@example.invalid"))
		frappe.db.set_value(
			"Admission Application", result["application"], "workflow_state", "Rejected"
		)
		second = submit_application(**payload(email="again@example.invalid"))
		self.assertNotEqual(second["application"], result["application"])

	# --- the payment gate ----------------------------------------------

	def test_application_is_not_placed_until_the_fee_is_paid(self):
		"""The college's rule: fee first, then the application counts."""
		result = submit_application(**payload(email="gate1@example.invalid"))
		doc = frappe.get_doc("Admission Application", result["application"])

		self.assertFalse(doc.application_fee_paid)
		self.assertIn((doc.workflow_state or "Draft"), ("Draft", None, ""))
		self.assertTrue(result["payment_pending"])

	def test_application_fee_invoice_is_raised(self):
		from sibbcs.finance.fees import application_fee_invoice

		result = submit_application(**payload(email="gate2@example.invalid"))
		invoice = application_fee_invoice(result["application"])

		self.assertIsNotNone(invoice)
		self.assertEqual(invoice.net_amount, 350)
		self.assertEqual(invoice.status, "Unpaid")
		# no Student exists yet -- the invoice belongs to the application
		self.assertFalse(invoice.student)
		self.assertEqual(invoice.admission_application, result["application"])

	def test_fee_invoice_is_not_raised_twice(self):
		from sibbcs.finance.fees import raise_application_fee

		result = submit_application(**payload(email="gate3@example.invalid"))
		raise_application_fee(result["application"])
		self.assertEqual(
			frappe.db.count(
				"Fee Invoice", {"admission_application": result["application"]}
			),
			1,
		)

	def test_paying_the_fee_places_the_application(self):
		from sibbcs.finance.fees import mark_application_fee_paid

		result = submit_application(**payload(email="gate4@example.invalid"))
		state = mark_application_fee_paid(result["application"])

		doc = frappe.get_doc("Admission Application", result["application"])
		self.assertTrue(doc.application_fee_paid)
		self.assertEqual(state, "In Review")
		self.assertEqual(doc.workflow_state, "In Review")

	def test_marking_paid_twice_is_harmless(self):
		"""Razorpay retries webhooks."""
		from sibbcs.finance.fees import mark_application_fee_paid

		result = submit_application(**payload(email="gate5@example.invalid"))
		mark_application_fee_paid(result["application"])
		state = mark_application_fee_paid(result["application"])
		self.assertEqual(state, "In Review")

	def test_payment_status_reports_the_gate(self):
		from sibbcs.admissions.public_form import payment_status

		result = submit_application(**payload(email="gate6@example.invalid"))
		before = payment_status(result["application"])
		self.assertTrue(before["found"])
		self.assertFalse(before["paid"])
		self.assertEqual(before["amount"], 350)

	def test_payment_status_for_unknown_application(self):
		from sibbcs.admissions.public_form import payment_status

		self.assertFalse(payment_status("APP-DOES-NOT-EXIST")["found"])

	def test_saved_even_when_the_gateway_is_unavailable(self):
		"""A gateway problem must not lose a filled-in application."""
		result = submit_application(**payload(email="gate7@example.invalid"))
		self.assertTrue(frappe.db.exists("Admission Application", result["application"]))
		# no keys configured in tests, so no link -- but the record survives
		self.assertIsNone(result["payment_url"])
		self.assertEqual(result["payment_error"], "gateway_not_configured")

	def test_no_internal_message_leaks_to_the_applicant(self):
		"""With no outgoing mail account, frappe.sendmail pushes
		"Please setup default outgoing Email Account…" onto the message log,
		which then rides back to the anonymous applicant in the API response.
		"""
		frappe.clear_messages()
		submit_application(**payload(email="quiet@example.invalid"))

		leaked = " ".join(str(m) for m in (frappe.get_message_log() or []))
		self.assertNotIn("Email Account", leaked)
		self.assertNotIn("default outgoing", leaked.lower())

	def test_long_values_are_capped(self):
		result = submit_application(
			**payload(email="public8@example.invalid", full_name="x" * 400)
		)
		doc = frappe.get_doc("Admission Application", result["application"])
		self.assertLessEqual(len(doc.full_name), 140)


class TestRequestDispatch(FrappeTestCase):
	"""Referee and mentor requests must actually be sent, to a usable link."""

	def test_token_links_are_externally_reachable(self):
		"""frappe.utils.get_url() appends the dev port outside production mode,
		which would have made every referee link unopenable."""
		from sibbcs.admissions.doctype.admission_application.admission_application import (
			token_url,
		)

		link = token_url("reference", "SAMPLE")
		self.assertNotIn(":8000", link)
		self.assertTrue(link.startswith("http"))
		self.assertIn("/reference?token=SAMPLE", link)

	def test_dispatch_is_skipped_and_reported_without_a_mail_account(self):
		"""Never raise at whoever triggered the save -- report it instead."""
		from sibbcs.admissions.notifications import dispatch_requests

		result = submit_application(**payload(email="disp1@example.invalid"))
		report = dispatch_requests(result["application"])

		self.assertEqual(report["referees"], [])
		self.assertIn("no outgoing email account", report["skipped"])

	def test_draft_applications_are_not_dispatched(self):
		"""An abandoned, unpaid application must not email its referees."""
		from sibbcs.admissions.notifications import dispatch_on_placement

		result = submit_application(**payload(email="disp2@example.invalid"))
		doc = frappe.get_doc("Admission Application", result["application"])
		self.assertEqual(doc.workflow_state or "Draft", "Draft")
		# Draft short-circuits before any send is attempted
		self.assertIsNone(dispatch_on_placement(doc))

	def test_requests_are_dispatched_once_the_application_is_placed(self):
		"""With mail configured, placing the application sends the requests."""
		from unittest.mock import patch

		from sibbcs.admissions import notifications
		from sibbcs.finance.fees import mark_application_fee_paid

		result = submit_application(**payload(email="disp3@example.invalid"))

		sent = []
		with patch.object(notifications, "outgoing_configured", return_value=True), patch.object(
			frappe, "sendmail", side_effect=lambda **kw: sent.append(kw["recipients"][0])
		):
			mark_application_fee_paid(result["application"])

		# two referees and one mentor from the standard payload
		self.assertEqual(len(sent), 3)

		doc = frappe.get_doc("Admission Application", result["application"])
		for row in doc.reference_requests:
			self.assertTrue(row.sent_on, "referee row was never stamped as sent")
		self.assertTrue(doc.mentor_consents[0].sent_on)

	def test_dispatch_does_not_resend(self):
		from unittest.mock import patch

		from sibbcs.admissions import notifications

		result = submit_application(**payload(email="disp4@example.invalid"))
		frappe.db.set_value(
			"Admission Application", result["application"], "workflow_state", "In Review"
		)

		sent = []
		with patch.object(notifications, "outgoing_configured", return_value=True), patch.object(
			frappe, "sendmail", side_effect=lambda **kw: sent.append(kw["recipients"][0])
		):
			notifications.dispatch_requests(result["application"])
			first = len(sent)
			notifications.dispatch_requests(result["application"])

		self.assertEqual(len(sent), first, "requests were sent twice")


class TestResendRequests(FrappeTestCase):
	"""Re-sending a referee or mentor link on demand."""

	def _placed(self, email):
		from sibbcs.finance.fees import mark_application_fee_paid

		result = submit_application(**payload(email=email))
		frappe.db.set_value(
			"Admission Application", result["application"], "workflow_state", "In Review"
		)
		return result["application"]

	def test_list_requests_shows_everyone_and_their_state(self):
		from sibbcs.admissions.notifications import list_requests

		app = self._placed("rs1@example.invalid")
		data = list_requests(app)

		kinds = [r["kind"] for r in data["rows"]]
		self.assertEqual(kinds.count("reference"), 2)
		self.assertEqual(kinds.count("mentor"), 1)
		for row in data["rows"]:
			self.assertIn("sent_on", row)
			self.assertFalse(row["done"])

	def test_resend_reaches_an_already_sent_referee(self):
		"""The gap this closes: dispatch skips sent rows, so a referee who lost
		the email had no path."""
		from unittest.mock import patch

		from sibbcs.admissions import notifications

		app = self._placed("rs2@example.invalid")
		doc = frappe.get_doc("Admission Application", app)
		target = doc.reference_requests[0]

		sent = []
		with patch.object(notifications, "outgoing_configured", return_value=True), patch.object(
			frappe, "sendmail", side_effect=lambda **kw: sent.append(kw["recipients"][0])
		):
			notifications.dispatch_requests(app)          # first send
			first = len(sent)
			notifications.dispatch_requests(app)          # no-op, already sent
			self.assertEqual(len(sent), first)

			notifications.resend_selected(
				app, [{"kind": "reference", "row": target.name}]
			)

		self.assertEqual(len(sent), first + 1)
		self.assertEqual(sent[-1], target.referee_email)

	def test_resend_refuses_someone_who_already_replied(self):
		"""Their token is spent; a fresh email would only confuse them."""
		from unittest.mock import patch

		from sibbcs.admissions import notifications

		app = self._placed("rs3@example.invalid")
		doc = frappe.get_doc("Admission Application", app)
		target = doc.reference_requests[0]
		frappe.db.set_value(
			"Reference Request", target.name, "submitted_on", frappe.utils.now_datetime()
		)

		sent = []
		with patch.object(notifications, "outgoing_configured", return_value=True), patch.object(
			frappe, "sendmail", side_effect=lambda **kw: sent.append(kw["recipients"][0])
		):
			result = notifications.resend_selected(
				app, [{"kind": "reference", "row": target.name}]
			)

		self.assertEqual(sent, [])
		self.assertTrue(any("already replied" in r for r in result["refused"]))

	def test_resend_targets_only_the_chosen_person(self):
		from unittest.mock import patch

		from sibbcs.admissions import notifications

		app = self._placed("rs4@example.invalid")
		doc = frappe.get_doc("Admission Application", app)
		mentor = doc.mentor_consents[0]

		sent = []
		with patch.object(notifications, "outgoing_configured", return_value=True), patch.object(
			frappe, "sendmail", side_effect=lambda **kw: sent.append(kw["recipients"][0])
		):
			notifications.resend_selected(app, [{"kind": "mentor", "row": mentor.name}])

		self.assertEqual(sent, [mentor.mentor_email])

	def test_resend_needs_a_selection(self):
		from unittest.mock import patch

		from sibbcs.admissions import notifications

		app = self._placed("rs5@example.invalid")
		with patch.object(notifications, "outgoing_configured", return_value=True):
			with self.assertRaises(frappe.ValidationError):
				notifications.resend_selected(app, [])

	def test_resend_without_mail_configured_is_refused_clearly(self):
		from sibbcs.admissions import notifications

		app = self._placed("rs6@example.invalid")
		doc = frappe.get_doc("Admission Application", app)
		with self.assertRaises(frappe.ValidationError):
			notifications.resend_selected(
				app, [{"kind": "reference", "row": doc.reference_requests[0].name}]
			)


class TestRateLimit(FrappeTestCase):
	"""The limiter is skipped under tests, so cover it explicitly."""

	def test_rate_limit_blocks_a_flood(self):
		from sibbcs.admissions.public_form import RATE_LIMIT_PER_HOUR, _rate_limit

		cache = frappe.cache()
		redis_key = cache.make_key(f"sibbcs:apply:{getattr(frappe.local, 'request_ip', None) or 'unknown'}")
		cache.delete(redis_key)

		frappe.flags.in_test = False
		try:
			for _ in range(RATE_LIMIT_PER_HOUR):
				_rate_limit()
			with self.assertRaises(frappe.ValidationError):
				_rate_limit()
		finally:
			frappe.flags.in_test = True
			cache.delete(redis_key)
	def test_rate_limit_is_skipped_under_tests(self):
		"""Otherwise the suite fails once it grows past five applications."""
		from sibbcs.admissions.public_form import _rate_limit

		for _ in range(20):
			_rate_limit()


class TestEmailTemplates(FrappeTestCase):
	"""The templates must actually render.

	Every other mail test mocks frappe.sendmail, which meant the template was
	never resolved -- and hid a TemplateNotFound that stopped every referee and
	mentor email in production. These tests render for real.
	"""

	CONTEXT = {
		"referee_name": "Pastor A",
		"mentor_name": "Mentor M",
		"applicant_name": "Test Applicant",
		"program": "MDIV",
		"link": "https://online.sibbc.org/reference?token=ABC",
	}

	def test_reference_template_renders(self):
		from sibbcs.admissions.notifications import FALLBACK_REFERENCE, render_template

		subject, message = render_template(
			"reference_request", self.CONTEXT, *FALLBACK_REFERENCE
		)
		self.assertIn("Test Applicant", subject)
		self.assertIn("https://online.sibbc.org/reference?token=ABC", message)
		self.assertNotIn("{{", message)

	def test_mentor_template_renders(self):
		from sibbcs.admissions.notifications import FALLBACK_MENTOR, render_template

		subject, message = render_template(
			"mentor_consent_request", self.CONTEXT, *FALLBACK_MENTOR
		)
		self.assertIn("Test Applicant", subject)
		self.assertIn("token=ABC", message)
		self.assertNotIn("{{", message)

	def test_missing_template_falls_back_rather_than_failing(self):
		"""Losing the wording beats losing the request."""
		from sibbcs.admissions.notifications import FALLBACK_REFERENCE, render_template

		subject, message = render_template(
			"no_such_template", self.CONTEXT, *FALLBACK_REFERENCE
		)
		self.assertIn("Test Applicant", subject)
		self.assertIn("token=ABC", message)

	def test_sending_a_real_reference_email_does_not_raise(self):
		"""End to end through frappe.sendmail, unmocked, into the Email Queue.

		Skipped where no outgoing account exists -- Frappe refuses to queue at
		all then, which says nothing about our code. On a site with mail
		configured this is the test that would have caught the TemplateNotFound.
		"""
		from sibbcs.admissions.notifications import outgoing_configured, send_reference_row

		if not outgoing_configured():
			self.skipTest("no outgoing email account on this site")

		result = submit_application(**payload(email="tpl1@example.invalid"))
		doc = frappe.get_doc("Admission Application", result["application"])

		sent = send_reference_row(doc, doc.reference_requests[0], 0)
		self.assertEqual(sent, doc.reference_requests[0].referee_email)


class TestReferenceForm(FrappeTestCase):
	"""The college's Spiritual and Ministerial Reference questionnaire."""

	def _token(self, email):
		result = submit_application(**payload(email=email))
		doc = frappe.get_doc("Admission Application", result["application"])
		return result["application"], doc.reference_requests[0].token

	def _answers(self, **overrides):
		from sibbcs.admissions.reference_form import QUESTIONS

		answers = {}
		for fieldname, _q, options, required in QUESTIONS:
			if options:
				answers[fieldname] = options[0]
			elif required:
				answers[fieldname] = "n/a"
		answers.update(overrides)
		return answers

	def test_every_question_is_answerable(self):
		from sibbcs.admissions.reference_form import validate_answers

		cleaned = validate_answers(self._answers())
		self.assertIn("relationship", cleaned)
		self.assertIn("recommendation_choice", cleaned)

	def test_missing_required_answer_refused(self):
		from sibbcs.admissions.reference_form import validate_answers

		answers = self._answers()
		answers["calling"] = ""
		with self.assertRaises(frappe.ValidationError):
			validate_answers(answers)

	def test_answer_outside_the_option_list_refused(self):
		"""The endpoint is public; the browser's form is not trusted."""
		from sibbcs.admissions.reference_form import validate_answers

		answers = self._answers(commitment_to_christ="Whatever I like")
		with self.assertRaises(frappe.ValidationError):
			validate_answers(answers)

	def test_free_text_comment_is_optional(self):
		from sibbcs.admissions.reference_form import validate_answers

		answers = self._answers()
		answers.pop("additional_comments", None)
		validate_answers(answers)

	def test_submitting_records_answers_and_recommendation(self):
		import json

		from sibbcs.admissions.reference_form import submit as submit_reference

		app, token = self._token("ref1@example.invalid")
		submit_reference(token, self._answers(recommendation_choice="I strongly recommend"))

		doc = frappe.get_doc("Admission Application", app)
		row = doc.reference_requests[0]
		self.assertTrue(row.submitted_on)
		# maps onto the four-point value the officer sees in the grid
		self.assertEqual(row.recommendation, "Strong")

		stored = json.loads(row.response_json)
		self.assertEqual(stored["relationship"], "Pastor")

	def test_recommendation_mapping_covers_every_choice(self):
		from sibbcs.admissions.reference_form import BY_FIELD, RECOMMENDATION_MAP

		options = BY_FIELD["recommendation_choice"][2]
		for option in options:
			self.assertIn(option, RECOMMENDATION_MAP, option)
		self.assertEqual(
			set(RECOMMENDATION_MAP.values()), {"Strong", "Positive", "Neutral", "Negative"}
		)

	def test_a_reference_cannot_be_submitted_twice(self):
		from sibbcs.admissions.reference_form import submit as submit_reference
		from sibbcs.admissions.tokens import TokenError

		_app, token = self._token("ref2@example.invalid")
		submit_reference(token, self._answers())
		with self.assertRaises(TokenError):
			submit_reference(token, self._answers())

	def test_answers_render_readably_for_the_officer(self):
		from sibbcs.admissions.reference_form import format_answers, submit as submit_reference

		app, token = self._token("ref3@example.invalid")
		submit_reference(token, self._answers())

		doc = frappe.get_doc("Admission Application", app)
		html = format_answers(doc.reference_requests[0].response_json)
		self.assertIn("Your Relationship to the Applicant", html)
		self.assertIn("Pastor", html)
		self.assertNotIn("{", html)


class TestMentorForm(FrappeTestCase):
	"""The college's Mentor Consent Form."""

	def _token(self, email):
		result = submit_application(**payload(email=email))
		doc = frappe.get_doc("Admission Application", result["application"])
		return result["application"], doc.mentor_consents[0].token

	def _answers(self, **overrides):
		answers = {
			"mentor_name": "Shadrek Paul",
			"mentor_mobile": "8374220717",
			"mentor_email": "paul1999@example.invalid",
			"mentor_gender": "Male",
			"mentor_age": "27",
			"current_position": "Pastor",
			"denomination": "Holy Army Fellowship",
			"address_line_1": "Ambedkar Colony",
			"address_line_2": "Autonagar",
			"city": "Tirupati",
			"state": "Andhra Pradesh",
			"postal_code": "517501",
			"country": "India",
			"prior_theological_education": "No",
			"mentoring_experience": "No",
			"years_of_ministry": "7",
			"handbook_acknowledged": 1,
		}
		answers.update(overrides)
		return answers

	def test_every_field_is_accepted(self):
		from sibbcs.admissions.mentor_form import validate_answers

		cleaned = validate_answers(self._answers())
		self.assertEqual(cleaned["denomination"], "Holy Army Fellowship")
		self.assertEqual(cleaned["mentor_age"], 27)
		self.assertEqual(cleaned["years_of_ministry"], 7)

	def test_missing_required_field_refused(self):
		from sibbcs.admissions.mentor_form import validate_answers

		with self.assertRaises(frappe.ValidationError):
			validate_answers(self._answers(denomination=""))

	def test_optional_address_line_2_may_be_blank(self):
		from sibbcs.admissions.mentor_form import validate_answers

		validate_answers(self._answers(address_line_2=""))

	def test_age_must_be_a_number(self):
		from sibbcs.admissions.mentor_form import validate_answers

		with self.assertRaises(frappe.ValidationError):
			validate_answers(self._answers(mentor_age="twenty seven"))

	def test_absurd_age_refused(self):
		from sibbcs.admissions.mentor_form import validate_answers

		with self.assertRaises(frappe.ValidationError):
			validate_answers(self._answers(mentor_age="7"))

	def test_bad_gender_refused(self):
		from sibbcs.admissions.mentor_form import validate_answers

		with self.assertRaises(frappe.ValidationError):
			validate_answers(self._answers(mentor_gender="Sometimes"))

	def test_bad_email_refused(self):
		from sibbcs.admissions.mentor_form import validate_answers

		with self.assertRaises(Exception):
			validate_answers(self._answers(mentor_email="not-an-email"))

	def test_submitting_records_the_whole_form(self):
		from sibbcs.admissions.mentor_form import submit as submit_mentor

		app, token = self._token("men1@example.invalid")
		submit_mentor(token, self._answers())

		doc = frappe.get_doc("Admission Application", app)
		row = doc.mentor_consents[0]
		self.assertTrue(row.consented_on)
		self.assertEqual(row.current_position, "Pastor")
		self.assertEqual(row.city, "Tirupati")
		self.assertEqual(row.years_of_ministry, 7)
		self.assertTrue(row.handbook_acknowledged)

	def test_mentor_cannot_write_fields_outside_the_form(self):
		"""The endpoint is public; only the mentor's own fields are writable."""
		from sibbcs.admissions.mentor_form import submit as submit_mentor

		app, token = self._token("men2@example.invalid")
		submit_mentor(token, self._answers(token="hijack", parent="EVIL"))

		doc = frappe.get_doc("Admission Application", app)
		row = doc.mentor_consents[0]
		self.assertEqual(row.token, token)
		self.assertEqual(row.parent, app)

	def test_consent_cannot_be_submitted_twice(self):
		from sibbcs.admissions.mentor_form import submit as submit_mentor
		from sibbcs.admissions.tokens import TokenError

		_app, token = self._token("men3@example.invalid")
		submit_mentor(token, self._answers())
		with self.assertRaises(TokenError):
			submit_mentor(token, self._answers())

	def test_answers_render_readably_for_the_officer(self):
		from sibbcs.admissions.mentor_form import format_answers, submit as submit_mentor

		app, token = self._token("men4@example.invalid")
		submit_mentor(token, self._answers())

		doc = frappe.get_doc("Admission Application", app)
		html = format_answers(doc.mentor_consents[0])
		self.assertIn("Mentor Denomination", html)
		self.assertIn("Holy Army Fellowship", html)

	def test_handbook_links_are_configurable_not_hardcoded(self):
		from sibbcs.admissions.mentor_form import intro_parts

		parts = intro_parts()
		self.assertIn("role_url", parts)
		self.assertIn("handbook_url", parts)
		self.assertIn("sacred and meaningful responsibility", parts["lead"])


class TestWhatTheCandidateDeclares(FrappeTestCase):
	"""The six questions the college asks about a person, and the six it
	answers about them itself.

	The split is the point. Mother tongue and baptism are the candidate's to
	state; ATA eligibility and whether they were added to the WhatsApp groups
	are the college's to decide, and an anonymous form must not be able to
	claim either.
	"""

	DECLARED = {
		"mother_tongue": "Telugu",
		"nationality": "Indian",
		"church_denomination": "Independent",
		"salvation_status": "I am Saved",
		"baptism_status": "Baptised",
		"sense_of_call": "Yes, clearly",
	}

	def test_what_the_candidate_says_is_kept(self):
		result = submit_application(
			**payload(email="declared1@example.invalid", **self.DECLARED)
		)
		doc = frappe.get_doc("Admission Application", result["application"])

		for field, value in self.DECLARED.items():
			with self.subTest(field=field):
				self.assertEqual(doc.get(field), value)

	def test_the_colleges_own_determinations_cannot_be_claimed(self):
		result = submit_application(
			**payload(
				email="declared2@example.invalid",
				ata_eligible=1,
				mature_candidate=1,
				transfer_student=1,
				education_sequence_mismatch=1,
				whatsapp_groups="Added",
				theological_writing_status="Completed",
			)
		)
		doc = frappe.get_doc("Admission Application", result["application"])

		self.assertFalse(doc.ata_eligible)
		self.assertFalse(doc.mature_candidate)
		self.assertFalse(doc.transfer_student)
		self.assertFalse(doc.education_sequence_mismatch)
		self.assertEqual(doc.whatsapp_groups, "Awaiting")
		self.assertEqual(doc.theological_writing_status, "Not Applicable")

	def test_the_whitelist_excludes_them_by_construction(self):
		for field in (
			"ata_eligible", "mature_candidate", "transfer_student",
			"education_sequence_mismatch", "whatsapp_groups",
			"theological_writing_status",
		):
			self.assertNotIn(field, APPLICANT_FIELDS, field)

	def test_a_choice_the_doctype_does_not_offer_is_dropped_not_thrown(self):
		"""Only a crafted payload can do this. Refusing it with Frappe's own
		validation error would hand our field internals back to whoever asked;
		the application is still worth saving."""
		result = submit_application(
			**payload(email="declared3@example.invalid", salvation_status="Chosen One")
		)
		doc = frappe.get_doc("Admission Application", result["application"])

		self.assertFalse(doc.salvation_status)
		self.assertEqual(doc.full_name, "Public Applicant")

	def test_the_form_offers_every_field_it_is_allowed_to(self):
		"""A field on the whitelist that the page never asks for collects
		nothing. This is the check that the two stay in step."""
		import os

		page = open(
			os.path.join(frappe.get_app_path("sibbcs"), "www", "apply.html"),
			encoding="utf-8",
		).read()

		for field in self.DECLARED:
			with self.subTest(field=field):
				self.assertIn(f'id="{field}"', page)
				self.assertIn(f"'{field}'", page)
