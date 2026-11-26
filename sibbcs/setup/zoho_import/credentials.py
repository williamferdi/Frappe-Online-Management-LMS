# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""Create `~/.zoho-credentials` at the server, by hand, once.

    cd ~/frappe-bench && ./env/bin/python -m sibbcs.setup.zoho_import.credentials

Run by a person at the server's terminal, because it asks for a client secret
and a one-time grant code: they are typed (not echoed), exchanged with Zoho for
a long-lived refresh token, and written to a file only the bench user can read.
No secret is printed, logged, or sent anywhere but Zoho's own token endpoint.

Before running it, in the Zoho API console (https://api-console.zoho.in, or
.com if the college's Zoho account is on the global data centre), signed in as
the account that owns the Creator app:

  1. Add Client -> Self Client -> Create.
  2. "Generate Code" tab: scope  ZohoCreator.report.READ
     time duration 10 minutes, any description -> Create. Copy the code.
  3. "Client Secret" tab: the Client ID and Client Secret.

The scope is read-only: the token can read report records and download their
files, and cannot change anything in Zoho.
"""

import getpass
import json
import os
import sys

import requests

from sibbcs.setup.zoho_import.client import CREDENTIALS, Client, ZohoError


def main():
	print(__doc__.split("Before running it")[0].strip().splitlines()[0])
	print()
	dc = (input("Zoho data centre [in]: ").strip() or "in").lower().lstrip(".")
	if dc not in ("in", "com", "eu", "com.au", "jp", "ca", "sa", "uk"):
		sys.exit(f"Unknown data centre {dc!r}.")
	client_id = input("Client ID: ").strip()
	client_secret = getpass.getpass("Client Secret (hidden): ").strip()
	code = getpass.getpass("Grant code from 'Generate Code' (hidden): ").strip()
	if not (client_id and client_secret and code):
		sys.exit("All three are needed.")

	response = requests.post(
		f"https://accounts.zoho.{dc}/oauth/v2/token",
		params={
			"grant_type": "authorization_code",
			"client_id": client_id,
			"client_secret": client_secret,
			"code": code,
		},
		timeout=60,
	)
	body = response.json()
	if "refresh_token" not in body:
		# e.g. "invalid_code" when the 10 minutes ran out; no secret in it.
		sys.exit(f"Zoho did not issue a refresh token: {body.get('error') or body}")

	credentials = {
		"dc": dc,
		"api_domain": body.get("api_domain") or f"https://www.zohoapis.{dc}",
		"client_id": client_id,
		"client_secret": client_secret,
		"refresh_token": body["refresh_token"],
	}
	descriptor = os.open(CREDENTIALS, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
	with os.fdopen(descriptor, "w") as handle:
		json.dump(credentials, handle)
	os.chmod(CREDENTIALS, 0o600)
	print(f"Saved {CREDENTIALS} (readable by this user only).")

	# Prove it works on something with no personal data in it.
	try:
		programmes = Client(credentials).records("All_Programs")
		print(f"Checked: the token reads the Creator app ({len(programmes)} programmes).")
	except ZohoError as exc:
		sys.exit(f"Saved, but the test read failed: {exc}")


if __name__ == "__main__":
	main()
