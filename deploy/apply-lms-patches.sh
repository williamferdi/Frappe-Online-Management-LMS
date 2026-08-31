#!/bin/bash
# Re-apply our patches to the vendored Frappe LMS app.
#
# `bench update` pulls a fresh copy of apps/lms and silently discards anything
# we changed there. Run this after every LMS update, then rebuild:
#
#     bash deploy/apply-lms-patches.sh
#     cd apps/lms/frontend && NODE_OPTIONS=--max-old-space-size=5120 yarn build
#
# The default 2 GB node heap is not enough to build the LMS frontend on this
# box; without NODE_OPTIONS the build dies with "Reached heap limit".
#
# sibbcs/admissions/test_entrance_exam.py fails if a patch has gone missing,
# so a lost patch surfaces in the test run rather than in a student's exam.
set -euo pipefail

LMS="${LMS:-$HOME/frappe-bench/apps/lms}"
HERE="$(cd "$(dirname "$0")" && pwd)"

for patch in "$HERE"/lms-patches/*.patch; do
	name="$(basename "$patch")"
	if git -C "$LMS" apply --check --reverse "$patch" 2>/dev/null; then
		echo "already applied: $name"
		continue
	fi
	git -C "$LMS" apply "$patch"
	echo "applied: $name"
done
