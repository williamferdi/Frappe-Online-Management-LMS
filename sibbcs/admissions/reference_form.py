"""The Spiritual and Ministerial Reference questionnaire.

The questions are the college's own, taken from their existing reference form.

NOTE ON THE OPTION LISTS: the source form showed only the selected answer in
each dropdown, so the *questions* and the *top option* of each scale are the
college's, while the remaining rungs are inferred to make a coherent scale.
Every inferred list is marked `INFERRED` below and should be confirmed before
the form is used for real intakes. Changing one is a one-line edit here.

Answers are stored as JSON on the Reference Request row. The recommendation
question additionally maps onto the existing `recommendation` field, so the
Admissions Officer still sees Strong / Positive / Neutral / Negative in the
grid without opening anything.
"""

import json

import frappe
from frappe import _

INTRO = (
	"Greetings from the admissions office of South India Baptist Bible College "
	"&amp; Seminary (SIBBC&amp;S). We at SIBBC&amp;S seek to equip individuals who are "
	"spiritually mature, committed to ministry, and ready for theological "
	"education. As part of the application process, we require a Spiritual and "
	"Ministerial Reference from a pastor, mentor, or ministry leader who knows "
	"the applicant well. This form should be filled out by a person who knows "
	"the applicant spiritually and ministerially. Your honest evaluation will "
	"help us assess their readiness for seminary studies and their potential for "
	"ministry impact. We appreciate your time in completing this reference form."
)

UNABLE = "Unable to assess"

# fieldname, question, options (empty = free text), required
QUESTIONS = [
	(
		"relationship",
		"Your Relationship to the Applicant",
		# INFERRED apart from "Ministry Leader"
		["Pastor", "Mentor", "Ministry Leader", "Professor", "Employer", "Other"],
		True,
	),
	(
		"known_duration",
		"How long have you known the applicant?",
		# INFERRED apart from "4-6 years"
		["Less than 1 year", "1-3 years", "4-6 years", "7-10 years", "More than 10 years"],
		True,
	),
	(
		"commitment_to_christ",
		"How would you describe the applicant's commitment to Christ?",
		# INFERRED apart from the first
		[
			"Strongly devoted, actively growing in faith",
			"Committed and growing steadily",
			"Moderately committed",
			"Inconsistent in their walk",
			UNABLE,
		],
		True,
	),
	(
		"ministry_involvement",
		"How actively is the applicant involved in their church or ministry?",
		[
			"Very active (regular attendance, leadership, or service)",
			"Active and regularly involved",
			"Somewhat involved",
			"Rarely involved",
			UNABLE,
		],
		True,
	),
	(
		"leadership_potential",
		"How would you describe the applicant's leadership potential?",
		[
			"Strong leadership, leads others effectively in ministry",
			"Good leadership potential",
			"Developing leadership ability",
			"Limited leadership ability",
			UNABLE,
		],
		True,
	),
	(
		"moral_character",
		"How would you assess the applicant's moral and ethical character?",
		[
			"Excellent, a strong example of Christian integrity",
			"Good and trustworthy",
			"Satisfactory",
			"I have some concerns",
			UNABLE,
		],
		True,
	),
	(
		"teamwork",
		"How well does the applicant work with others in a ministry or church setting?",
		[
			"Excellent teamwork and relational skills",
			"Works well with others",
			"Satisfactory",
			"Finds working with others difficult",
			UNABLE,
		],
		True,
	),
	(
		"discipline",
		"How would you describe the applicant's personal discipline and responsibility?",
		[
			"Very responsible and disciplined",
			"Generally responsible",
			"Somewhat disciplined",
			"Needs improvement",
			UNABLE,
		],
		True,
	),
	(
		"calling",
		"Does the applicant demonstrate a clear calling to theological education and ministry?",
		[
			"Yes, strongly convinced of their calling",
			"Yes, appears genuinely called",
			"Uncertain at this stage",
			"No, I do not believe so",
			UNABLE,
		],
		True,
	),
	(
		"recommendation_choice",
		"Would you recommend this applicant for admission at South India Baptist "
		"Bible College & Seminary?",
		[
			"I strongly recommend",
			"I recommend",
			"I recommend with reservations",
			"I do not recommend",
		],
		True,
	),
	(
		"additional_comments",
		"If you have any additional comments, please write them below",
		[],  # free text
		False,
	),
]

BY_FIELD = {q[0]: q for q in QUESTIONS}

# The referee's wording -> the four-point value the officer sees in the grid.
RECOMMENDATION_MAP = {
	"I strongly recommend": "Strong",
	"I recommend": "Positive",
	"I recommend with reservations": "Neutral",
	"I do not recommend": "Negative",
}


def questions_for_render():
	return [
		{"fieldname": f, "question": q, "options": o, "required": r}
		for f, q, o, r in QUESTIONS
	]


def validate_answers(answers):
	"""Every required question answered, and every choice from its own list."""
	cleaned = {}

	for fieldname, question, options, required in QUESTIONS:
		value = (answers.get(fieldname) or "").strip()

		if required and not value:
			frappe.throw(_("Please answer: {0}").format(question), title=_("Incomplete"))

		if not value:
			continue

		if options and value not in options:
			frappe.throw(
				_("'{0}' is not one of the choices for: {1}").format(value, question),
				title=_("Invalid Answer"),
			)

		cleaned[fieldname] = value[:2000]

	return cleaned


def submit(token, answers):
	"""Record a completed reference against its token.

	Validation lives here, not in the browser: the token endpoint is public, so
	a crafted payload must not be able to store an answer that was never on the
	form.
	"""
	from sibbcs.admissions.tokens import mark_submitted

	if isinstance(answers, str):
		answers = json.loads(answers)

	cleaned = validate_answers(answers)

	recommendation = RECOMMENDATION_MAP.get(cleaned.get("recommendation_choice", ""))

	return mark_submitted(
		"reference",
		token,
		{
			"recommendation": recommendation,
			"response_json": json.dumps(cleaned, indent=1),
		},
	)


def format_answers(response_json):
	"""Readable HTML of a submitted reference, for the Desk viewer."""
	if not response_json:
		return ""

	try:
		answers = json.loads(response_json)
	except Exception:
		return f"<pre>{frappe.utils.escape_html(response_json)}</pre>"

	rows = []
	for fieldname, question, _options, _required in QUESTIONS:
		if fieldname not in answers:
			continue
		rows.append(
			"<tr>"
			f"<td style='padding:6px 14px 6px 0;vertical-align:top;color:var(--text-muted)'>{question}</td>"
			f"<td style='padding:6px 0;vertical-align:top'><b>{frappe.utils.escape_html(str(answers[fieldname]))}</b></td>"
			"</tr>"
		)

	# anything stored by an older version of the form
	for key, value in answers.items():
		if key not in BY_FIELD:
			rows.append(
				"<tr>"
				f"<td style='padding:6px 14px 6px 0;color:var(--text-muted)'>{frappe.unscrub(key)}</td>"
				f"<td style='padding:6px 0'><b>{frappe.utils.escape_html(str(value))}</b></td>"
				"</tr>"
			)

	return "<table style='width:100%'>" + "".join(rows) + "</table>"


@frappe.whitelist()
def view(application, row):
	"""Desk: show one submitted reference in readable form."""
	doc = frappe.get_doc("Admission Application", application)
	doc.check_permission("read")

	target = next((r for r in doc.reference_requests if r.name == row), None)
	if not target:
		frappe.throw(_("Reference not found."))

	return {
		"referee": target.referee_name,
		"email": target.referee_email,
		"type": target.referee_type,
		"recommendation": target.recommendation,
		"submitted_on": str(target.submitted_on) if target.submitted_on else None,
		"html": format_answers(target.response_json),
	}
