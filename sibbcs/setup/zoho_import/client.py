# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""A read-only client for the Zoho Creator REST API (v2.1).

Credentials come from `~/.zoho-credentials` (mode 0600), written by
`credentials.py` at the server. Nothing here writes to Zoho: it reads report
records and downloads files, and that is all the token's scope allows.
"""

import json
import os
import stat
import time
from urllib.parse import parse_qs, urlparse

import requests

CREDENTIALS = os.path.expanduser("~/.zoho-credentials")
OWNER = "admissions.online_sibbc"
APP = "online-education-administration"

# Records per page. 1000 is the most v2.1 returns in one call.
PAGE = 1000
TIMEOUT = 60


class ZohoError(Exception):
	pass


def load_credentials(path=CREDENTIALS):
	if not os.path.exists(path):
		raise ZohoError(
			f"{path} does not exist. Create it at the server with:\n"
			"  cd ~/frappe-bench && ./env/bin/python -m sibbcs.setup.zoho_import.credentials"
		)
	mode = stat.S_IMODE(os.stat(path).st_mode)
	if mode & 0o077:
		raise ZohoError(f"{path} is readable by others (mode {oct(mode)}); run: chmod 600 {path}")
	with open(path) as handle:
		return json.load(handle)


class Client:
	def __init__(self, credentials=None, owner=OWNER, app=APP, session=None):
		self.credentials = credentials or load_credentials()
		self.owner = owner
		self.app = app
		self.session = session or requests.Session()
		self._token = None
		self._token_expires = 0
		self.calls = 0

	# -- auth ---------------------------------------------------------------

	@property
	def accounts_url(self):
		return f"https://accounts.zoho.{self.credentials['dc']}"

	@property
	def api_url(self):
		return self.credentials.get("api_domain") or f"https://www.zohoapis.{self.credentials['dc']}"

	def token(self):
		if self._token and time.time() < self._token_expires - 120:
			return self._token
		response = self.session.post(
			f"{self.accounts_url}/oauth/v2/token",
			params={
				"refresh_token": self.credentials["refresh_token"],
				"client_id": self.credentials["client_id"],
				"client_secret": self.credentials["client_secret"],
				"grant_type": "refresh_token",
			},
			timeout=TIMEOUT,
		)
		body = response.json()
		if "access_token" not in body:
			# The body names the error ("invalid_code", "invalid_client"); it
			# carries no secret.
			raise ZohoError(f"Zoho refused to issue an access token: {body.get('error') or body}")
		self._token = body["access_token"]
		self._token_expires = time.time() + int(body.get("expires_in", 3600))
		return self._token

	def _get(self, url, params=None, headers=None, stream=False):
		for attempt in range(5):
			self.calls += 1
			response = self.session.get(
				url,
				params=params,
				headers={"Authorization": f"Zoho-oauthtoken {self.token()}", **(headers or {})},
				timeout=TIMEOUT,
				stream=stream,
			)
			if response.status_code == 401:
				self._token = None
				continue
			if response.status_code == 429 or response.status_code >= 500:
				time.sleep(5 * (attempt + 1))
				continue
			return response
		raise ZohoError(f"GET {url} kept failing (last status {response.status_code})")

	# -- records ------------------------------------------------------------

	def report_url(self, report):
		return f"{self.api_url}/creator/v2.1/data/{self.owner}/{self.app}/report/{report}"

	def records(self, report):
		"""Every record in a report, every field, following the cursor."""
		rows, cursor = [], None
		while True:
			headers = {"record_cursor": cursor} if cursor else {}
			response = self._get(
				self.report_url(report),
				params={"max_records": PAGE, "field_config": "all"},
				headers=headers,
			)
			body = response.json()
			code = body.get("code")
			if code == 3100:  # "No records exist"
				break
			if code != 3000:
				raise ZohoError(f"report {report}: code {code}, {body.get('message') or body.get('description')}")
			rows.extend(body.get("data") or [])
			cursor = response.headers.get("record_cursor")
			if not cursor:
				break
		return rows

	# -- files --------------------------------------------------------------

	def download(self, report, record_id, field, filepath=None):
		"""One file's bytes. `filepath` picks one file of a multi-file field."""
		url = f"{self.report_url(report)}/{record_id}/{field}/download"
		params = {"filepath": filepath} if filepath else None
		response = self._get(url, params=params, stream=True)
		if response.status_code != 200:
			raise ZohoError(f"download {report}/{record_id}/{field}: HTTP {response.status_code}")
		return response.content


def file_references(value):
	"""Every file a field value points at, as filepath strings.

	Creator renders a file, image or signature field as a download address,
	`/api/v2.1/.../<field>/download?filepath=<name>`, or -- for a multi-file
	field -- a list of them (sometimes as dicts with a `value` or `url` key).
	"""
	found = []

	def walk(item):
		if isinstance(item, str):
			if "download" in item and "filepath=" in item:
				query = parse_qs(urlparse(item).query)
				for path in query.get("filepath") or []:
					found.append(path)
		elif isinstance(item, dict):
			for inner in item.values():
				walk(inner)
		elif isinstance(item, list | tuple):
			for inner in item:
				walk(inner)

	walk(value)
	return found
