"""A second outline that uses the parts of the model the live course does not.

TEST COURSE has two modules, five items, everything published and nothing
indented -- which is a fair picture of the course and a poor picture of the
screen. This builds a second payload out of the same real items so the
sub-headers, the indents and a draft row can be seen, without touching
anything on the live site.

Cloned from the real rows rather than written by hand, so every key the type
expects is present and correctly shaped.
"""

import copy
import json

live = json.load(open("/tmp/payloads.json"))
outline = copy.deepcopy(live["outline"])

modules = outline["modules"]
assert len(modules) >= 2, f"expected two modules, found {len(modules)}"

first, second = modules[0], modules[1]
template = copy.deepcopy(first["items"][0])


def row(kind, title, indent=0, published=1, requirement="Nothing", position=0):
	item = copy.deepcopy(template)
	item.update(
		name=f"CMI-PREVIEW-{position}",
		item_type=kind,
		title=title,
		indent=indent,
		published=published,
		completion_requirement=requirement,
		position=position,
	)
	return item


first["title"] = "Week 1 — Introduction"
first["published"] = 1
first["items"] = [
	row("Sub-header", "Course Materials", position=0),
	row("Lesson", "Lesson1", indent=1, requirement="View it", position=1),
	row("Page", "Page1", indent=1, position=2),
	row("Page", "P2", indent=1, published=0, position=3),
	row("Sub-header", "Assignments", position=4),
	row("Assignment", "ASS1", indent=1, requirement="Hand it in", position=5),
	row("File", "File", indent=1, position=6),
]

second["title"] = "Week 2 — Descriptive Statistics"
second["published"] = 0
second["prerequisites"] = [first["name"]]
second["require_sequential_progress"] = 1
second["unlock_at"] = "2026-10-01 09:00:00"
second["items"] = [
	row("Sub-header", "Course Materials", position=0),
	row("Lesson", "Lesson1", indent=1, published=0, position=1),
]

json.dump(outline, open("/tmp/shaped.json", "w"), indent=1)
print("shaped outline written")
