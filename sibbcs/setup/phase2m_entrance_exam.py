"""The entrance exam: three essays in the LMS, marked out of 75, pass at 40%.

    bench --site online.sibbc.org execute sibbcs.setup.phase2m_entrance_exam.build

Idempotent. Re-running leaves an existing quiz and its questions alone, so
wording edited in the LMS survives; pass `replace=True` to overwrite them.

**Open Ended, and the LMS is strict about it.** `LMS Quiz.validate_open_ended_
questions` refuses to mix Open Ended with any other type in one quiz, which
suits an all-essay paper. The consequence worth knowing: an open-ended answer
scores **0 at submission** and stays there until an instructor marks it in the
LMS. `passing_percentage` is therefore a verdict on the *marked* script, not
on the submitted one -- every candidate reads 0/75 until somebody grades them.

**The rubrics are not in the questions.** A candidate reading the mark scheme
while writing the essay is not sitting the same exam. They go in the lesson's
`instructor_content`, which the LMS shows to instructors and moderators only.

Marks: 25 an essay, 75 the paper, 40% to pass. The pass figure is the
college's and lives on the quiz, not in this file's logic.
"""

import frappe

COURSE = "entrance-exam"
CHAPTER = "Entrance Exam"
LESSON = "Essay Paper"
QUIZ_TITLE = "Entrance Exam — Essays"

PASSING_PERCENTAGE = 40
MARKS_PER_ESSAY = 25
MAX_ATTEMPTS = 1

# (title, prompt) -- the college's own wording, from
# "Essays to go into the Entrance Exam.pdf".
ESSAYS = [
	(
		"Understanding of the Gospel",
		"<p>In 200–300 words, present your understanding of the Gospel in your own "
		"words. Explain what the Gospel teaches about God, humanity, sin, salvation, "
		"and the Christian life.</p>"
		"<p><i>25 marks.</i></p>",
	),
	(
		"Sense of Calling to Ministry",
		"<p>In 200–300 words, explain your sense of calling to Christian ministry and "
		"your current ministry involvement. Describe what influenced your desire to "
		"pursue theological education, where you believe God is leading you to serve, "
		"and how theological training through SIBBCS will prepare you for that "
		"calling.</p>"
		"<p><i>25 marks.</i></p>",
	),
	(
		"Motivation for Theological Education at SIBBCS",
		"<p>In 200–300 words, share why you are applying to South India Baptist Bible "
		"College &amp; Seminary. Include the key reasons you have chosen SIBBCS for "
		"your theological and ministerial training, and what you hope to gain from "
		"studying here.</p>"
		"<p><i>25 marks.</i></p>",
	),
]

LESSON_BODY = """## Entrance Exam

Three essays, **25 marks each**, 75 marks in total. The pass mark is **40%**.

Write each answer in **200–300 words**, in your own words. Your answers are read
by the admissions panel; they are not marked automatically, so you will not see
a score when you submit.

Take your time. You have **one attempt**.
"""

# `instructor_content` is EditorJS JSON, not HTML.
#
# Lesson.vue evaluates `JSON.parse(lesson.data.instructor_content)` *in the
# template*, unguarded. Anything that is not JSON throws during render and the
# whole lesson comes out blank -- which is exactly what happened when this held
# HTML. The same template also requires `blocks.length > 1`, so a single block
# is silently invisible.
#
# (type, text) or ("header", text, level)
RUBRIC_BLOCKS = [
	("header", "Marking rubrics — for graders", 4),
	(
		"paragraph",
		"<b>These are not shown to the candidate.</b> Each essay is out of 25; "
		"the paper is out of 75 and the pass mark is 40%.",
	),
	("header", "Essay 1 — Understanding of the Gospel (25)", 5),
	(
		"paragraph",
		"<b>Clarity and accuracy of the Gospel message (0–10):</b> explains the "
		"Gospel clearly and biblically; reflects God's holiness, human sinfulness, "
		"Christ's saving work, repentance, faith, and new life in Christ.",
	),
	(
		"paragraph",
		"<b>Doctrinal soundness and balance (0–7):</b> faithful to Scripture, "
		"avoids distortions, grace-centred rather than works-based.",
	),
	(
		"paragraph",
		"<b>Personal grasp and reflection (0–5):</b> the Gospel is personally "
		"meaningful, not merely memorised.",
	),
	(
		"paragraph",
		"<b>Writing clarity and originality (0–3):</b> own words, well structured, "
		"within the word count.",
	),
	(
		"paragraph",
		"<i>22–25 excellent and compelling; 18–21 good with minor gaps; 14–17 "
		"basic with significant gaps; 13 and below major misunderstanding.</i>",
	),
	("header", "Essay 2 — Calling to Ministry and Ministry Direction (25)", 5),
	(
		"paragraph",
		"<b>Clarity of calling to ministry (0–10):</b> a clear sense of God's "
		"calling rather than personal ambition; thoughtful, prayerful, biblically "
		"grounded.",
	),
	(
		"paragraph",
		"<b>Connection to current ministry involvement (0–5):</b> genuine service "
		"in church or ministry contexts, even if informal or voluntary.",
	),
	(
		"paragraph",
		"<b>Reason for pursuing theological education and fit with SIBBCS (0–7):</b> "
		"driven by ministry need and spiritual growth rather than status, titles or "
		"academic prestige.",
	),
	(
		"paragraph",
		"<b>Direction for future ministry and realism (0–3):</b> insight into where "
		"they hope to serve, with reasonable expectations of training.",
	),
	(
		"paragraph",
		"<i>22–25 clear calling, active involvement, deeply motivated; 18–21 good "
		"clarity lacking depth; 14–17 uncertain or externally motivated; 13 and "
		"below little evidence of calling.</i>",
	),
	("header", "Essay 3 — Motivation to Study at SIBBCS (25)", 5),
	(
		"paragraph",
		"<b>Clarity of motivation to study (0–10):</b> strong, sincere reasons tied "
		"to ministry calling and spiritual growth rather than convenience, status "
		"or titles.",
	),
	(
		"paragraph",
		"<b>Alignment with the mission and values of SIBBCS (0–7):</b> appreciates "
		"biblically grounded, ministry-focused education and what makes SIBBCS "
		"suitable.",
	),
	(
		"paragraph",
		"<b>Connection between personal growth and the training offered (0–5):</b> "
		"how the program is expected to shape life, character, ministry skills and "
		"biblical understanding.",
	),
	("paragraph", "<b>Commitment and readiness for the training (0–3).</b>"),
]


def rubric_json():
	"""The rubrics as the EditorJS document the LMS expects."""
	import json
	import time

	blocks = []
	for entry in RUBRIC_BLOCKS:
		kind, text = entry[0], entry[1]
		data = {"text": text}
		if kind == "header":
			data["level"] = entry[2]
		blocks.append(
			{"id": frappe.generate_hash(length=10), "type": kind, "data": data}
		)

	return json.dumps(
		{"time": int(time.time() * 1000), "blocks": blocks, "version": "2.29.0"}
	)


def _default_instructor():
	from sibbcs.academic.lms_sync import _default_instructor

	return _default_instructor()


def ensure_chapter():
	existing = frappe.db.get_value(
		"Course Chapter", {"course": COURSE, "title": CHAPTER}, "name"
	)
	if existing:
		return existing, False

	chapter = frappe.get_doc(
		{"doctype": "Course Chapter", "course": COURSE, "title": CHAPTER}
	)
	chapter.insert(ignore_permissions=True)

	course = frappe.get_doc("LMS Course", COURSE)
	if not any(row.chapter == chapter.name for row in course.get("chapters") or []):
		course.append("chapters", {"chapter": chapter.name})
		course.save(ignore_permissions=True)

	return chapter.name, True


def ensure_questions(replace=False):
	"""One LMS Question per essay. Open Ended: nothing here is auto-marked."""
	names = []
	for title, prompt in ESSAYS:
		existing = frappe.db.get_value("LMS Question", {"question": title}, "name")
		if existing:
			if replace:
				frappe.db.set_value("LMS Question", existing, "question_detail", prompt)
			names.append(existing)
			continue

		question = frappe.get_doc(
			{
				"doctype": "LMS Question",
				"question": title,
				"question_detail": prompt,
				"type": "Open Ended",
			}
		)
		question.insert(ignore_permissions=True)
		names.append(question.name)

	return names


def ensure_quiz(lesson=None, replace=False):
	existing = frappe.db.get_value("LMS Quiz", {"title": QUIZ_TITLE}, "name")
	questions = ensure_questions(replace=replace)

	if existing:
		quiz = frappe.get_doc("LMS Quiz", existing)
		created = False
	else:
		quiz = frappe.get_doc({"doctype": "LMS Quiz", "title": QUIZ_TITLE})
		created = True

	quiz.course = COURSE
	if lesson:
		quiz.lesson = lesson
	quiz.passing_percentage = PASSING_PERCENTAGE
	quiz.max_attempts = MAX_ATTEMPTS
	quiz.shuffle_questions = 0
	quiz.show_answers = 0

	# Always reset on replace. Matching the existing rows by title is what let a
	# hand-edited question title orphan the set and silently grow duplicates.
	if created or replace or not quiz.get("questions"):
		quiz.set("questions", [])
		for name in questions:
			quiz.append("questions", {"question": name, "marks": MARKS_PER_ESSAY})

	quiz.flags.ignore_permissions = True
	quiz.save(ignore_permissions=True)
	return quiz.name, created


def ensure_lesson(chapter, quiz=None, replace=False):
	existing = frappe.db.get_value(
		"Course Lesson", {"course": COURSE, "chapter": chapter, "title": LESSON}, "name"
	)

	if existing:
		lesson = frappe.get_doc("Course Lesson", existing)
		created = False
	else:
		lesson = frappe.get_doc(
			{
				"doctype": "Course Lesson",
				"course": COURSE,
				"chapter": chapter,
				"title": LESSON,
			}
		)
		created = True

	if created or replace:
		lesson.body = LESSON_BODY

	# Shown to instructors and moderators, not to the candidate sitting the
	# paper -- the only reason the rubrics can live inside the course at all.
	lesson.instructor_content = rubric_json()
	if quiz:
		lesson.quiz_id = quiz

	lesson.flags.ignore_permissions = True
	lesson.save(ignore_permissions=True)

	if created:
		parent = frappe.get_doc("Course Chapter", chapter)
		if not any(row.lesson == lesson.name for row in parent.get("lessons") or []):
			parent.append("lessons", {"lesson": lesson.name})
			parent.save(ignore_permissions=True)

	return lesson.name, created


def attach_rubric_pdf(path):
	"""Keep the college's own document with the course, for graders."""
	import os

	if not path or not os.path.exists(path):
		return None

	file_name = os.path.basename(path)
	existing = frappe.db.get_value(
		"File",
		{"attached_to_doctype": "LMS Course", "attached_to_name": COURSE, "file_name": file_name},
		"file_url",
	)
	if existing:
		return existing

	with open(path, "rb") as handle:
		content = handle.read()

	# Private: this is the mark scheme, and the course is open to candidates.
	doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": file_name,
			"attached_to_doctype": "LMS Course",
			"attached_to_name": COURSE,
			"is_private": 1,
			"content": content,
			"decode": False,
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	return doc.file_url


def set_pass_mark(pass_mark=PASSING_PERCENTAGE):
	"""The same figure on the Desk record the office actually marks against."""
	field = frappe.db.get_value(
		"DocField",
		{"parent": "Qualifying Exam Result", "fieldname": "pass_mark"},
		"name",
	)
	if field:
		frappe.db.set_value("DocField", field, "default", str(pass_mark))
	return pass_mark


def build(rubric_pdf=None, replace=False):
	if not frappe.db.exists("LMS Course", COURSE):
		print(f"NO LMS COURSE {COURSE!r} -- nothing to build into.")
		return None

	chapter, made_chapter = ensure_chapter()
	lesson, made_lesson = ensure_lesson(chapter, replace=replace)
	quiz, made_quiz = ensure_quiz(lesson=lesson, replace=replace)
	# The lesson needs the quiz id, which needs the lesson to exist first.
	ensure_lesson(chapter, quiz=quiz, replace=False)

	attached = attach_rubric_pdf(rubric_pdf)
	set_pass_mark()

	frappe.db.commit()
	frappe.clear_cache()

	doc = frappe.get_doc("LMS Quiz", quiz)
	print(f"Chapter {CHAPTER!r}: {'created' if made_chapter else 'already present'}")
	print(f"Lesson {LESSON!r}: {'created' if made_lesson else 'already present'}")
	print(f"Quiz {quiz!r}: {'created' if made_quiz else 'updated'}")
	print(f"  questions   : {len(doc.get('questions') or [])}")
	print(f"  total marks : {doc.total_marks}")
	print(f"  pass mark   : {doc.passing_percentage}%")
	print(f"  attempts    : {doc.max_attempts}")
	print(f"Rubric PDF attached (private): {attached or 'not supplied'}")
	print(f"Qualifying Exam Result pass_mark default: {PASSING_PERCENTAGE}")
	print("Open Ended answers score 0 until an instructor marks them in the LMS.")
	return quiz


# ---------------------------------------------------------------------------
# putting it back after somebody edits it by hand
# ---------------------------------------------------------------------------
#
# Building a quiz through the LMS UI is easy to get wrong -- the rubric bands
# read like separate questions, and deleting a quiz leaves the lesson pointing
# at something that no longer exists. `tidy()` reports what it would remove and
# `tidy(apply=True)` removes it. It refuses to touch anything a candidate has
# actually answered.


def _our_quiz_names():
	return set(frappe.get_all("LMS Quiz", filters={"title": QUIZ_TITLE}, pluck="name"))


def survey():
	"""What is currently attached to the exam, and what is loose."""
	kept_questions = set()
	for quiz in frappe.get_all("LMS Quiz", pluck="name"):
		for row in frappe.get_all(
			"LMS Quiz Question", filters={"parent": quiz}, pluck="question"
		):
			kept_questions.add(row)

	stray_questions = [
		row.name
		for row in frappe.get_all(
			"LMS Question", filters={"type": "Open Ended"}, fields=["name"]
		)
		if row.name not in kept_questions
	]

	# A quiz with no course and no lesson is attached to nothing.
	loose_quizzes = [
		row.name
		for row in frappe.get_all(
			"LMS Quiz", fields=["name", "course", "lesson", "title"]
		)
		if not row.course and not row.lesson and row.title != QUIZ_TITLE
	]

	dangling_lessons = [
		row.name
		for row in frappe.get_all(
			"Course Lesson",
			filters={"course": COURSE},
			fields=["name", "quiz_id"],
		)
		if row.quiz_id and not frappe.db.exists("LMS Quiz", row.quiz_id)
	]

	empty_lessons = [
		row.name
		for row in frappe.get_all(
			"Course Lesson", filters={"course": COURSE}, fields=["name", "title", "body"]
		)
		if not (row.body or "").strip() and row.title != LESSON
	]

	return {
		"stray_questions": stray_questions,
		"loose_quizzes": loose_quizzes,
		"dangling_lessons": dangling_lessons,
		"empty_lessons": empty_lessons,
	}


def _has_submissions(quiz):
	return bool(frappe.db.count("LMS Quiz Submission", {"quiz": quiz}))


def tidy(apply=False):
	"""Report -- or clear -- what hand-editing left behind.

	Nothing with a submission against it is touched: a candidate's answers are
	the one thing here that cannot be rebuilt.
	"""
	found = survey()

	for quiz in list(found["loose_quizzes"]):
		if _has_submissions(quiz):
			found["loose_quizzes"].remove(quiz)
			print(f"  keeping {quiz}: it has submissions")

	print("Loose quizzes      :", found["loose_quizzes"] or "none")
	print("Stray questions    :", found["stray_questions"] or "none")
	print("Lessons pointing at a deleted quiz:", found["dangling_lessons"] or "none")
	print("Empty extra lessons:", found["empty_lessons"] or "none")

	if not apply:
		print("\nNothing removed. Call tidy(apply=True) to clear the above.")
		return found

	for quiz in found["loose_quizzes"]:
		frappe.delete_doc("LMS Quiz", quiz, force=True, ignore_permissions=True)

	# Re-survey: a question only counts as stray once the quiz holding it is
	# gone, so the first pass could not see the ones inside a loose quiz.
	if found["loose_quizzes"]:
		after = survey()
		newly_stray = [
			q for q in after["stray_questions"] if q not in found["stray_questions"]
		]
		if newly_stray:
			print("Freed by removing those quizzes:", newly_stray)
		found["stray_questions"] = after["stray_questions"]

	for question in found["stray_questions"]:
		frappe.delete_doc("LMS Question", question, force=True, ignore_permissions=True)
	for lesson in found["empty_lessons"]:
		frappe.delete_doc("Course Lesson", lesson, force=True, ignore_permissions=True)
	for lesson in found["dangling_lessons"]:
		frappe.db.set_value("Course Lesson", lesson, "quiz_id", None, update_modified=False)

	# The Frappe demo quiz picked up a pointer at our orientation course while
	# somebody was experimenting. It is Frappe's, so only the pointer is cleared.
	demo = "do-you-know-frappe-learning"
	if frappe.db.exists("LMS Quiz", demo):
		course = frappe.db.get_value("LMS Quiz", demo, "course")
		if course and course != "a-guide-to-frappe-learning":
			frappe.db.set_value(
				"LMS Quiz", demo, {"course": None, "lesson": None}, update_modified=False
			)
			print(f"  cleared {demo}'s pointer at {course}")

	frappe.db.commit()
	print("Cleared.")
	return found


def rebuild(rubric_pdf=None):
	"""Tidy first, then build. What to run after a hand-edit goes wrong."""
	tidy(apply=True)

	# The lesson may have been retitled; put it back so ensure_lesson finds it.
	for row in frappe.get_all(
		"Course Lesson", filters={"course": COURSE}, fields=["name", "title", "body"]
	):
		if row.title != LESSON and (row.body or "").strip():
			frappe.db.set_value(
				"Course Lesson", row.name, "title", LESSON, update_modified=False
			)
			print(f"  retitled {row.name} back to {LESSON!r}")

	return build(rubric_pdf=rubric_pdf, replace=True)
