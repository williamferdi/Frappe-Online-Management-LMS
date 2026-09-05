"""Question banks and quizzes whose timer cannot be beaten from devtools.

    bench --site online.sibbc.org execute \\
        sibbcs.setup.phase10_quizzes.build

Idempotent.

The vendored LMS quiz runs its timer, its shuffling and its attempt limit in
the browser. That is fine for practice and useless for anything that counts,
and the entrance exam has been sitting on it. Everything here is decided by
the server:

    expires_at        computed when the attempt starts, from the quiz's own
                      time limit -- never accepted from the client
    question_order    fixed and stored at the start, so a shuffle cannot be
                      re-rolled by reloading until an easier paper appears
    attempts          counted in the database, not in the page
    correctness       never sent to the browser while an attempt is open

**A quiz never grades independently.** A Course Quiz is reached through a
Course Assignment whose submission type is Quiz, and scoring an attempt writes
an Assignment Submission -- the same record a hand-marked essay produces. One
route to a grade, so the gradebook, the Grade Scale and the transcript need to
know nothing about quizzes at all.

**A bank belongs to the Course, an attempt to the Offering.** Questions are
content and survive the term; when and how long a student gets is this run's
business.
"""

import frappe

from sibbcs.setup.schema import (
	add_fields,
	check,
	column,
	ensure_doctype,
	f,
	fetched,
	full,
	level,
	link,
	read,
	section,
	select,
	table,
)

MODULE = "Academic"

SM = "System Manager"
REGISTRAR = "Registrar"
COORDINATOR = "Academic Coordinator"
FACULTY = "Faculty"
FACILITATOR = "Facilitator"
STUDENT = "Student"

QUESTION_TYPES = [
	"Choice",
	"Multiple answers",
	"True or False",
	"Short answer",
]

REVEAL_POLICIES = [
	"Never",
	"After the attempt",
	"After the due date",
]

ATTEMPT_STATES = ["In progress", "Submitted", "Expired"]


def _authoring_perms():
	"""Banks and quizzes are written by staff and never read by students.

	A student reaches questions only through `api.quiz`, which strips the
	answers. There is no Student row here at all, so a bank cannot be read
	through /api/resource however the URL is spelled.
	"""
	return [
		full(SM), full(COORDINATOR), full(FACULTY),
		read(REGISTRAR), read(FACILITATOR),
	]


# ---------------------------------------------------------------------------
# the bank
# ---------------------------------------------------------------------------


def _bank_question_option():
	return ensure_doctype(
		"Bank Question Option",
		MODULE,
		istable=1,
		fields=[
			f("option_text", "Option", "Small Text", reqd=1, in_list_view=1),
			check("is_correct", "Correct", 0, in_list_view=1),
		],
	)


def _question_bank():
	return ensure_doctype(
		"Question Bank",
		MODULE,
		autoname="naming_series:",
		naming_rule='By "Naming Series" field',
		title_field="title",
		fields=[
			select("naming_series", "Series", ["QBK-.#####"], default="QBK-.#####",
				   hidden=1, print_hide=1),
			f("title", "Title", "Data", reqd=1),
			link("course", "Course", "Course",
				 description="Leave blank for a bank any course may draw from."),
			column("cb_head"),
			f("question_count", "Questions", "Int", read_only=1),
			section("sb_about"),
			f("description", "Description", "Small Text"),
		],
		permissions=_authoring_perms(),
	)


def _bank_question():
	return ensure_doctype(
		"Bank Question",
		MODULE,
		autoname="naming_series:",
		naming_rule='By "Naming Series" field',
		title_field="question_text",
		fields=[
			section("sb_what"),
			select("naming_series", "Series", ["BQN-.#####"], default="BQN-.#####",
				   hidden=1, print_hide=1),
			link("bank", "Bank", "Question Bank", reqd=1),
			select("question_type", "Type", QUESTION_TYPES, default="Choice", reqd=1),
			column("cb_what"),
			f("points", "Points", "Float", default="1", reqd=1),
			f("position", "Position", "Int", default="0"),

			section("sb_question"),
			f("question", "Question", "Text Editor", reqd=1),
			# A plain-text shadow, so a list of questions does not render HTML
			# and the title field has something to show.
			f("question_text", "Question (plain)", "Data", read_only=1),

			section("sb_options", "Answers"),
			table("options", "Options", "Bank Question Option"),
			section("sb_explain"),
			f("explanation", "Explanation", "Text Editor",
			  description="Shown after the attempt, when the quiz reveals answers."),
		],
		permissions=_authoring_perms(),
	)


# ---------------------------------------------------------------------------
# the quiz
# ---------------------------------------------------------------------------


def _quiz_question_source():
	return ensure_doctype(
		"Quiz Question Source",
		MODULE,
		istable=1,
		fields=[
			link("bank", "Bank", "Question Bank", reqd=1, in_list_view=1),
			f("pick", "Draw", "Int", default="1", reqd=1, in_list_view=1,
			  description="How many questions to draw at random from this bank."),
		],
	)


def _course_quiz():
	return ensure_doctype(
		"Course Quiz",
		MODULE,
		autoname="naming_series:",
		naming_rule='By "Naming Series" field',
		title_field="title",
		fields=[
			section("sb_what"),
			select("naming_series", "Series", ["CQZ-.#####"], default="CQZ-.#####",
				   hidden=1, print_hide=1),
			link("course", "Course", "Course", reqd=1,
				 description="Questions are content, so a quiz survives into next term."),
			f("title", "Title", "Data", reqd=1),
			column("cb_what"),
			f("total_points", "Total Points", "Float", read_only=1),

			section("sb_timing", "Timing"),
			# The whole point of the phase. Minutes, held here and applied by
			# the server when an attempt starts.
			f("time_limit_minutes", "Time Limit (minutes)", "Int", default="0",
			  description="0 means no limit."),
			column("cb_timing"),
			f("allowed_attempts", "Allowed Attempts", "Int", default="1",
			  description="0 means no limit."),

			section("sb_behaviour", "Behaviour"),
			check("shuffle_questions", "Shuffle questions", 0),
			check("shuffle_options", "Shuffle options", 0),
			column("cb_behaviour"),
			select("reveal_answers", "Show correct answers", REVEAL_POLICIES,
				   default="Never"),
			check("one_question_at_a_time", "One question at a time", 0),

			section("sb_questions", "Where the questions come from"),
			table("sources", "Draw from banks", "Quiz Question Source"),
			f("description", "Instructions", "Text Editor"),
		],
		permissions=_authoring_perms(),
	)


# ---------------------------------------------------------------------------
# an attempt
# ---------------------------------------------------------------------------


def _quiz_attempt_answer():
	return ensure_doctype(
		"Quiz Attempt Answer",
		MODULE,
		istable=1,
		fields=[
			link("question", "Question", "Bank Question", reqd=1, in_list_view=1),
			f("answer", "Answer", "Long Text",
			  description="JSON: chosen option indexes, or typed text."),
			column("cb_marking"),
			# permlevel 1: whether an answer was right is a mark, and a student
			# must not read it out of their own attempt while it is open.
			check("is_correct", "Correct", 0, permlevel=1, in_list_view=1),
			f("points_awarded", "Points", "Float", permlevel=1, in_list_view=1),
		],
	)


def _quiz_attempt():
	return ensure_doctype(
		"Quiz Attempt",
		MODULE,
		autoname="naming_series:",
		naming_rule='By "Naming Series" field',
		title_field="student_name",
		fields=[
			section("sb_what"),
			select("naming_series", "Series", ["QAT-.#####"], default="QAT-.#####",
				   hidden=1, print_hide=1),
			link("assignment", "Assignment", "Course Assignment", reqd=1),
			fetched("course_offering", "Course Offering", "assignment.course_offering"),
			link("quiz", "Quiz", "Course Quiz", reqd=1),
			column("cb_what"),
			link("course_registration", "Registration", "Course Registration", reqd=1),
			fetched("student_name", "Student", "course_registration.student_name"),
			f("attempt", "Attempt", "Int", default="1"),

			section("sb_timing", "Timing"),
			f("started_at", "Started", "Datetime", read_only=1),
			# Computed by the server when the attempt starts. Never accepted
			# from the client, and never recomputed afterwards -- a second
			# clock is a second answer.
			f("expires_at", "Expires", "Datetime", read_only=1),
			column("cb_timing"),
			f("submitted_at", "Submitted", "Datetime", read_only=1),
			select("status", "Status", ATTEMPT_STATES, default="In progress", reqd=1),
			check("auto_submitted", "Closed by the clock", 0, read_only=1),

			section("sb_paper", "The paper"),
			# Fixed at the start and stored, so reloading cannot re-roll a
			# shuffle until an easier paper turns up.
			f("question_order", "Question Order", "Long Text", read_only=1),
			table("answers", "Answers", "Quiz Attempt Answer"),

			section("sb_result"),
			f("score", "Score", "Float", permlevel=1, read_only=1),
			column("cb_result"),
			f("points_possible", "Out of", "Float", permlevel=1, read_only=1),
		],
		permissions=[
			full(SM), full(COORDINATOR), full(FACULTY),
			read(REGISTRAR), read(FACILITATOR),
			level(SM, 1), level(COORDINATOR, 1), level(FACULTY, 1),
			level(REGISTRAR, 1, write=0), level(FACILITATOR, 1, write=0),
		],
	)


# ---------------------------------------------------------------------------
# the join to the one grade path
# ---------------------------------------------------------------------------


def _assignment_quiz_field():
	"""Course Assignment could not carry this before Course Quiz existed.

	A quiz is set like any other piece of work: the assignment holds the due
	date, the points and the grade component, and the quiz holds the questions
	and the clock.
	"""
	added = add_fields(
		"Course Assignment",
		[
			link("course_quiz", "Quiz", "Course Quiz",
				 depends_on="eval:doc.submission_type=='Quiz'",
				 description="Which quiz a student sits for this assignment."),
		],
	)

	# "Quiz" has to be a submission type before an assignment can name one.
	meta = frappe.get_meta("Course Assignment")
	field = meta.get_field("submission_type")
	options = [line.strip() for line in (field.options or "").split("\n") if line.strip()]
	if "Quiz" not in options:
		doc = frappe.get_doc("DocType", "Course Assignment")
		for row in doc.fields:
			if row.fieldname == "submission_type":
				row.options = "\n".join(options + ["Quiz"])
		doc.save(ignore_permissions=True)

	return added


# ---------------------------------------------------------------------------


def build():
	_bank_question_option()
	_question_bank()
	_bank_question()
	_quiz_question_source()
	_course_quiz()
	_quiz_attempt_answer()
	_quiz_attempt()
	_assignment_quiz_field()

	frappe.db.commit()
	frappe.clear_cache()

	for name in (
		"Bank Question Option", "Question Bank", "Bank Question",
		"Quiz Question Source", "Course Quiz", "Quiz Attempt Answer", "Quiz Attempt",
	):
		print(f"  {name}: {'ok' if frappe.db.exists('DocType', name) else 'MISSING'}")

	options = frappe.get_meta("Course Assignment").get_field("submission_type").options
	print("  submission types:", ", ".join(options.split("\n")))
