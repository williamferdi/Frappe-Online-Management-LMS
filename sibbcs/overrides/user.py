# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""A password link somebody can actually open.

Frappe builds every "set your password" address with `frappe.utils.get_url()`,
and on this deployment that appends the dev webserver's port:

    https://online.sibbc.org:8000/update-password?key=...

Nothing outside the box answers on 8000 -- nginx holds 443 and proxies in --
so the link times out in the browser. It is the same fault `gateway.public_url`
was written for, and the same one `lms_account` already works around by hand;
this closes it at the only place all three password mails pass through.

Three mails, one method. `User._reset_password` is called by the "Forgot
Password" form on the sign-in page (through the module-level `reset_password`
function), by the **Reset Password** button in Desk, and by Frappe's own
`send_welcome_mail_to_user`. Overriding the method rather than the callers
means none of them can be missed, and a fourth caller added by a future
Frappe is covered the day it arrives.

`get_url()` is wrong for everything else it touches too -- the footer of every
outgoing mail carries the same dead address. That is fixed on the site rather
than in code, by making `frappe.conf.webserver_port` falsy for this site:

    bench --site online.sibbc.org set-config -p webserver_port 0

`get_url` appends `conf.http_port or conf.webserver_port` unless the site is
run by supervisor or systemd, and this bench is neither (`bench start` under a
unit of its own). The key is set on the **site**, not on
`common_site_config.json`, where bench still needs the real 8000 to write the
Procfile and the nginx upstream.

This class stays either way. A site config is one restored backup away from
being the old one, and a password link that times out locks somebody out of
their own account -- that is worth two belts.
"""

from urllib.parse import urlsplit, urlunsplit

from frappe.core.doctype.user.user import User

from sibbcs.finance.gateway import public_url


def external(link):
	"""The same address on the host the college publishes.

	Only the host is replaced; the path, the query and the key in it are
	Frappe's and are carried over untouched.
	"""
	if not link:
		return link

	parts = urlsplit(link)
	tail = urlunsplit(("", "", parts.path or "/", parts.query, parts.fragment))
	return public_url(tail)


class SIBBCSUser(User):
	"""Frappe's User, with password links that resolve from the internet."""

	def _reset_password(self, send_email=False, password_expired=False):
		# Underscored, and that is Frappe's name for it: the public
		# `reset_password` in that module is a function taking a user id, and
		# it calls this. So does `send_welcome_mail_to_user`, and so does the
		# Reset Password button -- which is why this is the one place to fix.
		#
		# Asked not to send, then sent from here, so the mail carries the
		# corrected address rather than the one the base class built.
		# Everything else -- generating the key, storing its hash, stamping
		# when it was issued -- stays the base class's job, because
		# re-implementing it here is how an upgrade silently breaks it.
		link = external(
			super()._reset_password(send_email=False, password_expired=password_expired)
		)
		if send_email:
			self.password_reset_mail(link)
		return link
