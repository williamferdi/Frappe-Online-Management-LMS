# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""Context every guest page gets, whoever renders it."""

import frappe
from frappe.utils import get_build_version


def add_asset_version(context):
	"""Give the guest stylesheet a version, so a change to it actually lands.

	`/assets/sibbcs/css/public.css` is served with a long cache life and its
	name never changes, so an applicant who opened /apply last week keeps the
	stylesheet they downloaded then -- new rules simply do not apply, and the
	page half-renders the old design. This was found the honest way: a restyled
	form came back looking exactly as it had before.

	`get_build_version()` is the mtime of `assets.json`, which `bench build`
	rewrites, so the query changes exactly when the assets do and not on every
	request.

	Not reachable from Jinja itself -- `frappe.utils` is not in the template
	sandbox -- which is why it arrives through this hook.
	"""
	context.asset_version = get_build_version()
	return context
