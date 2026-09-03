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
# The two address trees the React app is served under. Both are one small HTML
# shell that names a content-hashed bundle.
APP_SHELL_PREFIXES = ("/staff", "/portal")


def no_store_on_app_shell(response=None, request=None):
	"""Stop the browser keeping the app shell.

	Two reasons, and the second is the serious one.

	It names a content-hashed bundle, so a cached shell keeps loading the
	*previous* build: a change ships, the page still runs the old code, and
	the deploy looks like it did nothing. That is exactly how the photographs
	in the admissions list came to be "not showing" -- they were there, in a
	bundle the browser was not fetching.

	And the shell is not a public document. It carries a boot payload with the
	viewer's name, their roles and a **CSRF token**, so it must never be
	written to a cache another person could read. `no-store` is the directive
	for a page that carries a token.

	It is 1.8 KB, fetched once per full page load -- the router handles every
	navigation after that -- so there is nothing to save by caching it.
	"""
	if not response or not request:
		return

	path = request.path or ""
	if not any(path == prefix or path.startswith(prefix + "/") for prefix in APP_SHELL_PREFIXES):
		return

	response.headers["Cache-Control"] = "no-store, must-revalidate"
	response.headers["Pragma"] = "no-cache"
