"""Correct the orientation course's references to Canvas.

    bench --site online.sibbc.org execute sibbcs.setup.phase2l_lms_naming.build
    bench --site online.sibbc.org execute sibbcs.setup.phase2l_lms_naming.preview

The college's handbooks were written for Canvas. The courses now run on this
site's own LMS, so a student reading the orientation would be told to use a
platform they have no account on.

**Most of this is a rename, but not all of it.** Some sentences describe
things Canvas does and this LMS does not, and renaming those would leave the
handbook confidently wrong rather than merely out of date. Those are rewritten
and listed separately in REWRITES, so the college can review the new wording
against what they meant.

The attached PDFs are untouched -- they are the college's documents, and
editing them is theirs to do. Until they are revised, the lessons and the
attachments disagree about the platform's name.

Idempotent: a lesson already free of "Canvas" is skipped.
"""

import re

import frappe

COURSE = "m-div-preliminary-orientation"
LMS_NAME = "SIBBCS Online LMS"

# Sentences that assert something Canvas-specific. Each is a claim about how
# the platform behaves, not a name, so each is rewritten rather than renamed.
# (pattern, replacement, why)
REWRITES = [
	(
		r"During\s+your\s+application\s+stage,\s*you\s+would\s+have\s+received\s+your\s+Canvas\s+login\s+"
		r"credentials\s+from\s+our\s+admissions\s+office\.\s*Those\s+credentials\s+help\s+you\s+to\s+log\s+"
		r"into\s+canvas\s+platform\.",
		"When you are admitted, the Admissions Office creates your account and emails "
		"you a link to set your own password. We never send passwords by email. Your "
		"username is the email address you gave on your application.",
		"we deliberately never email a password; the account is created at admission",
	),
	(
		r"[•·]?\s*📱?\s*Canvas\s+Student\s+App:\s*You\s+can\s+download\s+the\s+Canvas\s+Student\s+app\s+on\s+"
		r"your\s+mobile\s+device\s+\(Android\s+or\s+iOS\)\s+to\s+access\s+your\s+courses\s+anytime,\s+anywhere\.",
		"📱 On your phone: the " + LMS_NAME + " works in your phone's web browser, so "
		"you can study anywhere. There is no separate app to install.",
		"there is no mobile app for this LMS",
	),
	(
		r"Just\s+go\s+to\s+your\s+Canvas\s+Account\s*→\s*Settings\s+and\s+make\s+the\s+necessary\s+changes\.",
		"Just open your profile page in the " + LMS_NAME + " and make the necessary "
		"changes, or write to the Student Services Office.",
		"the Account -> Settings path does not exist here",
	),
	(
		r"For\s+your\s+privacy\s+and\s+safety,\s*the\s+seminary\s+doesn['’]t\s+have\s+access\s+to\s+reset\s+"
		r"your\s+password,\s*you['’]ll\s+need\s+to\s+do\s+it\s+directly\s+through\s+Canvas\.",
		"If you forget your password, use the \"Forgot Password\" link on the sign-in "
		"page to set a new one yourself.",
		"the old sentence told students something untrue about who can reset a password",
	),
	(
		r"look\s+for\s+the\s+WhatsApp\s+group\s+link\s+posted\s+in\s+the\s+[“\"]Announcements[”\"] section "
		r"on\s+your\s+Canvas\s+course\s+page\.",
		"look for the WhatsApp group link shared by your facilitator on the course page "
		"or by email.",
		"this LMS has no Announcements section on a course page",
	),
	(
		r"Once\s+enrollment\s+is\s+completed,\s*you\s+will\s+receive\s+an\s+email\s+invitation\s+to\s+join\s+"
		r"the\s+course\s+on\s+Canvas\.",
		"Once enrollment is completed, the course appears on your dashboard in the "
		+ LMS_NAME + ".",
		"enrolment here is done by the Student Services Office, with no invitation email",
	),
]

# Plain renames, longest first so the specific ones win. Every one produces
# "the SIBBCS Online LMS"; _tidy afterwards clears the doubled articles that
# leaves behind ("your the ...", "a the ...").
RENAMES = [
	(r"\bCanvas announcements\b", "course announcements"),
	(r"\bCanvas course page\b", "course page"),
	(r"\bCanvas course\b", "course"),
	(r"\bCanvas Student App\b", LMS_NAME),
	(r"\bCanvas Issues\b", "LMS issues"),
	(r"\bCanvas LMS\b", "the " + LMS_NAME),
	(r"\bon Canvas\b", "in the " + LMS_NAME),
	(r"\bCanvas\b", "the " + LMS_NAME),
	(r"\bcanvas\b", "the " + LMS_NAME),
]

# A rename inside running prose leaves articles stacked up. Each of these is
# something the dry run actually produced, not a precaution.
TIDY = [
	(r"\bthe the\b", "the"),
	(r"\b(your|Your|our|Our|their|its|his|her|a|A)\s+the\s+" + re.escape(LMS_NAME),
	 r"\1 " + LMS_NAME),
	(r"\bthe\s+" + re.escape(LMS_NAME) + r"\s+platform\b", "the " + LMS_NAME),
	(r"\bthe\s+" + re.escape(LMS_NAME) + r"\s+LMS\b", "the " + LMS_NAME),
	(r"[ \t]{2,}", " "),
]

TITLES = {
	"2.4 Understanding Canvas LMS in Your Learning Journey":
		f"2.4 Understanding the {LMS_NAME} in Your Learning Journey",
	"4.11 Maintaining Your Canvas LMS Account":
		f"4.11 Maintaining Your {LMS_NAME} Account",
}


def _tidy(text):
	"""Clear up what a mid-sentence rename leaves behind."""
	for pattern, replacement in TIDY:
		text = re.sub(pattern, replacement, text)

	# "Canvas serves as..." became "the SIBBCS..." at the start of a sentence.
	text = re.sub(
		r"(\A|[.!?:]\s+|\n\s*|[•·-]\s*)the (" + re.escape(LMS_NAME) + ")",
		lambda m: m.group(1) + "The " + m.group(2),
		text,
	)
	return text


def correct(body):
	"""Return (new_body, [notes]) for one lesson."""
	notes = []
	for pattern, replacement, why in REWRITES:
		body, count = re.subn(pattern, replacement, body, flags=re.I | re.S)
		if count:
			notes.append(f"rewritten ({why})")

	for pattern, replacement in RENAMES:
		body = re.sub(pattern, replacement, body)

	return _tidy(body), notes


def _lessons():
	return frappe.get_all(
		"Course Lesson",
		filters={"course": COURSE},
		fields=["name", "title", "body"],
		order_by="title",
	)


def preview():
	"""Show what would change, without changing anything."""
	for row in _lessons():
		if "canvas" not in (row.body or "").lower():
			continue
		new, notes = correct(row.body)
		print(f"########## {row.title}")
		for note in notes:
			print(f"   ! {note}")
		remaining = len(re.findall(r"canvas", new, re.I))
		print(f"   canvas mentions: {len(re.findall(r'canvas', row.body, re.I))} -> {remaining}")
		for match in re.finditer(r"[^.]*?" + re.escape(LMS_NAME) + r"[^.]*\.", new):
			print("    ", " ".join(match.group(0).split())[:200])
		print()


def build():
	changed = 0
	leftovers = {}

	for row in _lessons():
		if "canvas" not in (row.body or "").lower():
			continue
		new, notes = correct(row.body)
		frappe.db.set_value("Course Lesson", row.name, "body", new)
		changed += 1
		for note in notes:
			print(f"  {row.title}: {note}")
		remaining = len(re.findall(r"canvas", new, re.I))
		if remaining:
			leftovers[row.title] = remaining

	for old, new in TITLES.items():
		name = frappe.db.get_value(
			"Course Lesson", {"course": COURSE, "title": old}, "name"
		)
		if name:
			frappe.db.set_value("Course Lesson", name, "title", new)
			print(f"  retitled: {old!r} -> {new!r}")

	frappe.db.commit()
	frappe.clear_cache()

	print(f"Lessons corrected: {changed}")
	if leftovers:
		print("STILL MENTION CANVAS -- look at these by hand:")
		for title, count in leftovers.items():
			print(f"  {title}: {count}")
	else:
		print("No lesson mentions Canvas any more.")
	print("The attached PDFs are unchanged and still say Canvas.")
