# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""Bringing released course marks back from Campus LMS Lite onto the transcript.

Teaching and marking happen over there; the transcript is made here. Until this
module existed there was no path between the two: `api/lms_bridge.post_final_mark`
was the right door and nothing ever knocked on it, so a result a teacher released
in the LMS stayed in the LMS.

**Pulled, not pushed**, for the same three reasons the entrance exam is pulled:
no credential of this system has to live over there, a run that fails simply runs
again, and the LMS never has to know our address. The price is that a mark takes
up to an hour to appear, which costs a transcript nothing.

The whole difficulty is knowing *when* a figure is final, and the LMS cannot
answer that -- it does not know when a term ended. So:

- **the registrar decides a course is over**, by the term's end date passing or
  by somebody marking the offering Completed. Only then is a mark taken at all;
- **the LMS decides whether marking is finished**, and says so plainly. Anything
  still awaiting a marker, or marked and not yet released, stops the pull for
  that student.

Both halves are needed. Without the first, a mark would be recorded in week two
of a twelve-week course from the `final` figure, which counts work nobody has
handed in yet as zero. Without the second, a half-marked course would be recorded
as a fail. That second mistake is the one this codebase has already made three
times with Float columns that cannot hold "no value", and once with the entrance
exam, where recording an unmarked essay would have told a candidate they scored
nothing. It is the same error wearing different clothes.
"""

import frappe
from frappe.utils import add_days, cint, flt, nowdate

from sibbcs.integrations import campus_lms

# What a registration becomes when its course result arrives. Always Completed,
# never Failed: `passed` already records the outcome, and `completed_registrations`
# -- the transcript -- lists Completed rows, so routing a fail to Failed would
# quietly drop the F off the transcript it belongs on.
FINISHED_STATUS = "Completed"

# A withdrawal is a decision somebody made here. A mark arriving from the LMS
# must never walk it back, the same way the fee gate only ever narrows.
NEVER_OVERWRITE = ("Withdrawn",)

# Offerings nobody is being taught on cannot have results. Draft is excluded
# because it is pushed to the LMS as unpublished and carries no registrations.
TAUGHT_STATES = ("Published", "Running", "Completed")

# How long after a term ends a result already on file is still re-read, so a
# marker correcting a mistake still reaches the transcript. Outstanding work is
# asked about for as long as it stays outstanding, window or no window -- it is
# only the *finished* offerings that age out, and an offering whose every mark
# is recorded has nothing left to say after a term or two.
CORRECTION_WINDOW_DAYS = 120


def offerings_to_ask_about(limit=200):
	"""Offerings whose teaching the registrar considers over.

	One query for the whole college, not one per offering: this runs on a
	schedule and the box has better things to do. The term's end date is the
	ordinary signal and `status = Completed` is the explicit one, so a term
	that over-runs can still be closed by hand.

	**The set is work outstanding, not all of history.** An offering is asked
	about while any registration on it is still unrecorded, and for
	`CORRECTION_WINDOW_DAYS` after its term ends once they all are. Without
	that second clause an offering would be re-read for ever; without the
	first, `limit` would silently cut off the oldest unrecorded offerings and
	those marks would never arrive at all -- which is much the worse failure,
	because nothing would say so. `limit` is left as a safety valve on a
	runaway query, not as the thing that decides the work.
	"""
	return frappe.db.sql(
		"""
		select o.name
		from `tabCourse Offering` o
		left join `tabAcademic Term` t on t.name = o.term
		where o.status in %(states)s
		  and (
			o.status = 'Completed'
			or (t.end_date is not null and t.end_date < %(today)s)
		  )
		  and exists (
			select 1 from `tabCourse Registration` r
			where r.course_offering = o.name
			  and r.status not in %(dead)s
			  and (
				r.status != %(finished)s
				or t.end_date is null
				or t.end_date >= %(window_opens)s
			  )
		  )
		-- Oldest first: if there is ever a backlog, the marks that have been
		-- waiting longest are the ones to clear, and a cap then delays this
		-- hour's results rather than starving last year's for ever.
		order by t.end_date asc
		limit %(limit)s
		""",
		{
			"states": TAUGHT_STATES,
			"dead": NEVER_OVERWRITE,
			"finished": FINISHED_STATUS,
			"today": nowdate(),
			"window_opens": add_days(nowdate(), -CORRECTION_WINDOW_DAYS),
			"limit": cint(limit) or 200,
		},
		pluck=True,
	)


def pull_released_marks(limit=200):
	"""Record every course result the LMS has finished and released.

	Scheduled hourly. Idempotent: a result already on the registration at the
	same figure is left alone, and a figure that has *changed* is written --
	a teacher correcting a mark is the one case where the LMS should win.
	"""
	report = {"offerings": 0, "recorded": [], "skipped": []}
	if not campus_lms.configured():
		return report

	for offering in offerings_to_ask_about(limit):
		report["offerings"] += 1
		try:
			_pull_one(offering, report)
		except Exception:
			# One offering must never stop the rest, and a bookkeeping failure
			# here must never be allowed to look like a marking failure to the
			# teacher who released it.
			frappe.log_error(
				title=f"Course mark pull failed for {offering}",
				message=frappe.get_traceback(),
			)
			report["skipped"].append((offering, "error -- see the error log"))
	return report


def _pull_one(offering, report):
	from sibbcs.api import lms_bridge

	known = {
		row.name: row
		for row in frappe.get_all(
			"Course Registration",
			filters={"course_offering": offering},
			fields=["name", "status", "final_marks"],
		)
	}

	answer = campus_lms.course_grades(offering)
	if answer is None:
		# A 404 means the LMS has never heard of this offering -- it was never
		# pushed, or it was archived and removed over there. That is an answer,
		# not a fault.
		report["skipped"].append((offering, "not in the LMS"))
		return

	for row in answer.get("students") or []:
		registration = row.get("enrollmentExternalId")
		if not registration:
			# Enrolled by hand over there, with no registration behind them.
			# Not ours to record, and `unmanagedStudents` already counts them.
			continue

		current = known.get(registration)
		if not current:
			report["skipped"].append((registration, "no registration here"))
			continue
		if current.status in NEVER_OVERWRITE:
			report["skipped"].append((registration, f"registration is {current.status}"))
			continue
		if cint(row.get("awaitingMarking")):
			report["skipped"].append((registration, "still being marked"))
			continue
		if cint(row.get("gradedUnposted")):
			# Somebody has marked this and not released it. That is a decision
			# in progress, and the totals withhold it, so the figure would be
			# short by exactly the piece of work being reconsidered.
			report["skipped"].append((registration, "marked but not released"))
			continue

		percent = (row.get("final") or {}).get("percent")
		if percent is None:
			report["skipped"].append((registration, "nothing gradable on the course"))
			continue
		percent = flt(percent, 2)

		if current.status == FINISHED_STATUS and flt(current.final_marks, 2) == percent:
			continue

		try:
			lms_bridge.post_final_mark(registration, percent, status=FINISHED_STATUS)
		except Exception:
			# Per student, not per offering. One registration in an odd state --
			# an offering with a scheme nobody finished, a grade scale that has
			# gone missing -- must not cost the other twenty-nine people in the
			# class their results.
			frappe.log_error(
				title=f"Course mark could not be recorded for {registration}",
				message=frappe.get_traceback(),
			)
			report["skipped"].append((registration, "could not be recorded -- see the error log"))
			continue
		report["recorded"].append((registration, percent))
