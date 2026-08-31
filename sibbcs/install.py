# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""Test-run setup, wired as `before_tests` in hooks.py."""

import frappe
from frappe.installer import update_site_config

# Frappe refuses more than 60 new Users a minute (throttle_user_creation).
# This suite makes several hundred in about a minute, and the tests that then
# fail are whichever module was running when the budget ran out -- which reads
# as an unrelated regression rather than a rate limit.
#
# Written to the test site's own config rather than held in memory: the test
# runner re-initialises frappe.local between modules, so an in-memory value
# survives only the first one.
TEST_USER_LIMIT = 100_000


def before_tests():
	if frappe.conf.get("throttle_user_limit") != TEST_USER_LIMIT:
		update_site_config("throttle_user_limit", TEST_USER_LIMIT)
		frappe.conf["throttle_user_limit"] = TEST_USER_LIMIT
