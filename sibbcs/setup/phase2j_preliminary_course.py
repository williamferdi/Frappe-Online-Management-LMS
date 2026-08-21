"""Build the preliminary orientation course in the LMS from the college's
two handbooks.

    bench --site online.sibbc.org execute \\
        sibbcs.setup.phase2j_preliminary_course.build \\
        --kwargs '{"manual": "/tmp/program_manual.pdf", "handbook": "/tmp/formation_handbook.pdf"}'

Idempotent: a chapter or lesson that already exists is left alone, so wording
edited in the LMS survives a re-run. Pass `replace=True` to overwrite lesson
bodies from the PDFs again -- which will discard those edits.

**Why import the text rather than attach the PDFs.** A course whose only
content is "here is a 61-page PDF" has one lesson, so "completed" means the
student clicked once. Onboarding is gated on completing this course, so that
gate would be worth nothing. One lesson per section of the college's own
documents makes progress mean something. Both PDFs are attached as well, so
the authoritative document is always a click away.

**What is left out, on purpose.** The Holistic Formation Handbook is a
four-year workbook -- its Level 1 to 4 sections are reflection and
goal-setting forms filled *at the start of each level, with a mentor*. Putting
them here would have a new admit writing Level 4 goals before they have begun
Level 1, guided by a mentor who is not assigned until Phase 6. Only the front
matter and the Formation Covenant are imported. Sections 9 to 12 (FAQs, Your
Mentor & You, Choosing a Mentor, Suggested Practices) are not level-bound
either and can be added by extending HANDBOOK_PARTS.
"""

import re

import frappe

COURSE_TITLE = "M.Div. Preliminary Orientation"

COURSE_DESCRIPTION = """
<p>
	Every admitted student completes this orientation before enrolment is
	finalised. It carries <b>no credit</b> and is <b>mandatory</b>: it is the
	Master of Divinity Program Handbook and the opening of the Holistic
	Formation Handbook, section by section.
</p>
<p>
	Work through every lesson. When the course is complete you will be asked to
	sign an acknowledgement, and your onboarding follows from there.
</p>
"""

# The Program Handbook's own four parts, and where each begins.
MANUAL_PARTS = [
	(1, "Welcome"),
	(2, "Navigating Your Academic Journey"),
	(3, "Holistic Formation Framework"),
	(4, "Guidelines, Expectations & Support"),
]

# Formation Handbook: (chapter-relative title, first page, last page).
# Page 5-6 is its table of contents and page 9 onward is the level workbook.
HANDBOOK_PARTS = [
	("Welcome to Holistic Formation", 2, 3),
	("Before You Begin: How This Handbook Works", 4, 4),
	("Formation Covenant — My Commitment to the Journey", 7, 8),
]
HANDBOOK_CHAPTER = "Holistic Formation"

PART_HEADING = re.compile(r"^Section\s+(\d+)\s*:\s*(.*)$")
SECTION_HEADING = re.compile(r"^(\d+)\.(\d+)\.?\s+(\S.*)$")

# pypdf hands back the ligatures the PDF actually contains.
LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl"}


# ---------------------------------------------------------------------------
# reading the documents
# ---------------------------------------------------------------------------


def _pages(path):
	from pypdf import PdfReader

	reader = PdfReader(path)
	return [_normalise(page.extract_text() or "") for page in reader.pages]


def _normalise(text):
	for bad, good in LIGATURES.items():
		text = text.replace(bad, good)
	return text.replace(" ", " ")


def _lines(text):
	"""Drop the running page number and blank lines."""
	out = []
	for line in text.splitlines():
		line = line.rstrip()
		if not line.strip():
			continue
		if line.strip().isdigit():
			continue  # the page number sits on its own line
		out.append(line)
	return out


def _paragraphs(lines):
	"""Rebuild paragraphs from a PDF's hard line breaks.

	Extracted text has one line per *visual* line, so paragraph boundaries are
	gone. In justified body text every line runs nearly full width except the
	last one, so a noticeably short line ends a paragraph. Bullets and numbered
	items start their own.
	"""
	if not lines:
		return []

	widths = sorted(len(line) for line in lines)
	median = widths[len(widths) // 2] or 1

	paragraphs = []
	current = []

	def flush():
		if current:
			paragraphs.append(" ".join(part.strip() for part in current).strip())
			current.clear()

	for line in lines:
		stripped = line.strip()
		if re.match(r"^[•●*\-–]\s+", stripped) or re.match(r"^\d+[.)]\s+\S", stripped):
			flush()
			current.append(stripped)
			flush()
			continue

		current.append(stripped)
		if len(stripped) < median * 0.72 or stripped.endswith((":", "?")):
			flush()

	flush()
	return [p for p in paragraphs if p]


def _markdown(lines):
	body = []
	for paragraph in _paragraphs(lines):
		if re.match(r"^[•●*–]\s+", paragraph):
			body.append("- " + paragraph[1:].strip())
		else:
			body.append(paragraph)
	return "\n\n".join(body)


def read_manual(path):
	"""The Program Handbook as [(part_no, part_title, title, markdown)]."""
	pages = _pages(path)

	# Where each part begins, so a section is filed under the right chapter.
	part_start = {}
	for index, text in enumerate(pages, start=1):
		if index <= 3:
			continue  # cover and contents
		for line in text.splitlines():
			match = PART_HEADING.match(line.strip())
			if match:
				part_start.setdefault(int(match.group(1)), index)

	# Collect (page, part_no, section_label, title) for every heading.
	heads = []
	for index, text in enumerate(pages, start=1):
		if index <= 3:
			continue
		for line in text.splitlines():
			match = SECTION_HEADING.match(line.strip())
			if match:
				part_no, sub, title = int(match.group(1)), match.group(2), match.group(3)
				heads.append((index, part_no, f"{part_no}.{sub}", title.strip()))

	sections = []
	for position, (page, part_no, label, title) in enumerate(heads):
		end = heads[position + 1][0] - 1 if position + 1 < len(heads) else len(pages)
		lines = []
		for page_no in range(page, end + 1):
			for line in _lines(pages[page_no - 1]):
				# Drop the heading line itself and any later part heading.
				if SECTION_HEADING.match(line.strip()) or PART_HEADING.match(line.strip()):
					continue
				lines.append(line)
		part_title = next((t for n, t in MANUAL_PARTS if n == part_no), f"Section {part_no}")
		sections.append((part_no, part_title, f"{label} {title}", _markdown(lines)))

	# Part 3 has no numbered subsections; take its pages whole.
	if 3 in part_start:
		start = part_start[3]
		end = (part_start.get(4) or len(pages) + 1) - 1
		lines = []
		for page_no in range(start, end + 1):
			for line in _lines(pages[page_no - 1]):
				if PART_HEADING.match(line.strip()):
					continue
				lines.append(line)
		sections.append((3, "Holistic Formation Framework", "Holistic Formation Framework", _markdown(lines)))

	sections.sort(key=lambda s: (s[0], _sort_key(s[2])))
	return sections


def _sort_key(title):
	match = re.match(r"^(\d+)\.(\d+)", title)
	return (int(match.group(1)), int(match.group(2))) if match else (0, 0)


def read_handbook(path):
	"""The Formation Handbook's front matter as [(title, markdown)]."""
	pages = _pages(path)
	sections = []
	for title, first, last in HANDBOOK_PARTS:
		lines = []
		for page_no in range(first, min(last, len(pages)) + 1):
			lines.extend(_lines(pages[page_no - 1]))
		sections.append((title, _markdown(lines)))
	return sections


# ---------------------------------------------------------------------------
# building the course
# ---------------------------------------------------------------------------


def _default_instructor():
	from sibbcs.academic.lms_sync import _default_instructor

	return _default_instructor()


def ensure_course():
	existing = frappe.db.get_value("LMS Course", {"title": COURSE_TITLE}, "name")
	if existing:
		return existing, False

	course = frappe.get_doc(
		{
			"doctype": "LMS Course",
			"title": COURSE_TITLE,
			"short_introduction": "Mandatory orientation for admitted M.Div. students. No credit.",
			"description": COURSE_DESCRIPTION,
			"published": 1,
			# Batch entry only. This course gates onboarding, so a stranger
			# enrolling themselves into it would be enrolling into the
			# admission process.
			"disable_self_learning": 1,
			"instructors": [{"instructor": _default_instructor()}],
		}
	)
	course.insert(ignore_permissions=True)
	return course.name, True


def ensure_chapter(course, title, position):
	existing = frappe.db.get_value(
		"Course Chapter", {"course": course, "title": title}, "name"
	)
	if existing:
		return existing, False

	chapter = frappe.get_doc(
		{"doctype": "Course Chapter", "course": course, "title": title}
	)
	chapter.insert(ignore_permissions=True)

	parent = frappe.get_doc("LMS Course", course)
	if not any(row.chapter == chapter.name for row in parent.get("chapters") or []):
		parent.append("chapters", {"chapter": chapter.name})
		parent.save(ignore_permissions=True)

	return chapter.name, True


def ensure_lesson(course, chapter, title, body, replace=False):
	existing = frappe.db.get_value(
		"Course Lesson", {"course": course, "chapter": chapter, "title": title}, "name"
	)
	if existing:
		if replace:
			frappe.db.set_value("Course Lesson", existing, "body", body)
			return existing, "replaced"
		return existing, "kept"

	lesson = frappe.get_doc(
		{
			"doctype": "Course Lesson",
			"course": course,
			"chapter": chapter,
			"title": title,
			"body": body,
			"content": "",
		}
	)
	lesson.insert(ignore_permissions=True)

	parent = frappe.get_doc("Course Chapter", chapter)
	if not any(row.lesson == lesson.name for row in parent.get("lessons") or []):
		parent.append("lessons", {"lesson": lesson.name})
		parent.save(ignore_permissions=True)

	return lesson.name, "created"


def attach_pdf(course, path, label):
	"""Keep the authoritative document one click away. Public: every student
	is given these handbooks anyway, and a private file would 403 in the
	lesson body."""
	import os

	file_name = os.path.basename(path)
	existing = frappe.db.get_value(
		"File",
		{"attached_to_doctype": "LMS Course", "attached_to_name": course, "file_name": file_name},
		"file_url",
	)
	if existing:
		return existing

	with open(path, "rb") as handle:
		content = handle.read()

	doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": file_name,
			"attached_to_doctype": "LMS Course",
			"attached_to_name": course,
			"is_private": 0,
			"content": content,
			"decode": False,
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	frappe.logger("sibbcs").info(f"attached {label}: {doc.file_url}")
	return doc.file_url


def build(manual=None, handbook=None, replace=False):
	manual = manual or "/tmp/program_manual.pdf"
	handbook = handbook or "/tmp/formation_handbook.pdf"

	course, made = ensure_course()
	print(f"Course {course}: {'created' if made else 'already present'}")

	manual_url = attach_pdf(course, manual, "program manual")
	handbook_url = attach_pdf(course, handbook, "formation handbook")

	counts = {"created": 0, "kept": 0, "replaced": 0}
	position = 0

	sections = read_manual(manual)
	seen_chapters = {}
	for part_no, part_title, title, body in sections:
		if part_title not in seen_chapters:
			position += 1
			seen_chapters[part_title], _ = ensure_chapter(course, part_title, position)
			print(f"  chapter: {part_title}")
		chapter = seen_chapters[part_title]

		if not body.strip():
			print(f"    SKIPPED (no text extracted): {title}")
			continue

		footer = (
			f"\n\n---\n\n*From the M.Div. Program Handbook, January 2026. "
			f"[Open the full handbook]({manual_url}).*"
		)
		_name, outcome = ensure_lesson(course, chapter, title, body + footer, replace)
		counts[outcome] += 1

	position += 1
	chapter, _ = ensure_chapter(course, HANDBOOK_CHAPTER, position)
	print(f"  chapter: {HANDBOOK_CHAPTER}")
	for title, body in read_handbook(handbook):
		if not body.strip():
			print(f"    SKIPPED (no text extracted): {title}")
			continue
		footer = (
			f"\n\n---\n\n*From the Holistic Formation Handbook, January 2026. "
			f"[Open the full handbook]({handbook_url}).*"
		)
		_name, outcome = ensure_lesson(course, chapter, title, body + footer, replace)
		counts[outcome] += 1

	frappe.db.commit()

	total = frappe.db.count("Course Lesson", {"course": course})
	print(
		f"Lessons: {counts['created']} created, {counts['kept']} left alone, "
		f"{counts['replaced']} replaced. {total} in the course."
	)
	print(f"Course URL: /lms/courses/{course}")
	return course
