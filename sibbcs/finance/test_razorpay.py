# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""The gateway module had no tests at all, and it showed.

All three of its write paths named a field or a Select value the DocType did not
have, so Razorpay would have failed the first time it was switched on -- after
taking the money. `payment_provider` was added to `phase4_finance` *after* both
DocTypes existed, and `ensure_doctype` leaves an existing DocType untouched, so
the recipe and the artifact disagreed and nothing compared them. The payment
mode went the same way: the builder said `Online`, the stored Select still
offered `Razorpay`, and `_validate_selects` would have refused every row.

So these tests read the module's own source and check what it writes against the
DocType metadata. That catches the class of bug rather than one instance of it:
rename a field in the builder and not in the writer, and this fails -- with no
network, no keys and no webhook.
"""

import ast
import inspect

import frappe
from frappe.tests.utils import FrappeTestCase

from sibbcs.finance import razorpay
from sibbcs.setup.phase4_finance import PAYMENT_MODES

# `db_set` is a method on a loaded document, so the DocType is not in the call.
# Receivers are mapped by name, and an unmapped one fails rather than being
# skipped -- a write path nobody checked is exactly what this is for.
DB_SET_RECEIVERS = {
	"invoice": "Fee Invoice",
	"entry": "Payment Entry",
}

# Keys that are not fields: "doctype" names the DocType.
NOT_FIELDS = {"doctype"}

# Child tables, checked against their own DocType instead of as a column.
CHILD_TABLES = {"allocations": "Payment Allocation"}


def _module_tree():
	return ast.parse(inspect.getsource(razorpay))


def _pairs(dict_node):
	"""(key, literal string value or None) for each string key in a dict node."""
	out = []
	for key, value in zip(dict_node.keys, dict_node.values):
		if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
			continue
		literal = (
			value.value
			if isinstance(value, ast.Constant) and isinstance(value.value, str)
			else None
		)
		out.append((key.value, literal))
	return out


def _writes():
	"""Every (doctype, fieldname, literal value or None, lineno) the module writes.

	Only `frappe.get_doc({...})` and `<doc>.db_set({...})` count. Walking every
	dict literal instead would drag in each function's return payload, whose
	keys are not fields and never were.
	"""
	out = []
	for node in ast.walk(_module_tree()):
		if not isinstance(node, ast.Call) or not node.args:
			continue
		func = node.func
		if not isinstance(func, ast.Attribute) or not isinstance(node.args[0], ast.Dict):
			continue

		payload = node.args[0]

		if func.attr == "get_doc":
			doctype = dict(_pairs(payload)).get("doctype")
			if doctype:
				out.extend(
					(doctype, name, value, node.lineno) for name, value in _pairs(payload)
				)

		elif func.attr == "db_set":
			receiver = func.value.id if isinstance(func.value, ast.Name) else None
			assert receiver in DB_SET_RECEIVERS, (
				f"razorpay.py line {node.lineno}: db_set on an unmapped receiver "
				f"{receiver!r}. Add it to DB_SET_RECEIVERS so its fields are checked."
			)
			out.extend(
				(DB_SET_RECEIVERS[receiver], name, value, node.lineno)
				for name, value in _pairs(payload)
			)

	return out


class TestEveryFieldTheGatewayWritesExists(FrappeTestCase):
	def test_the_module_writes_something(self):
		"""If the walk finds nothing, every test below passes vacuously."""
		self.assertGreaterEqual(len(_writes()), 10)

	def test_no_write_names_a_field_that_does_not_exist(self):
		missing = []
		for doctype, field, _value, lineno in _writes():
			if field in NOT_FIELDS or field in CHILD_TABLES:
				continue
			if not frappe.get_meta(doctype).get_field(field):
				missing.append(f"{doctype}.{field} (razorpay.py:{lineno})")

		self.assertFalse(
			missing,
			"razorpay.py writes field(s) that do not exist: "
			+ ", ".join(sorted(set(missing)))
			+ ". The DocType JSON is the artifact -- ensure_doctype will not add a "
			"field to a DocType that already exists, so declaring it in the builder "
			"is not enough.",
		)

	def test_the_child_table_rows_are_allocations(self):
		for field, target in CHILD_TABLES.items():
			meta = frappe.get_meta("Payment Entry").get_field(field)
			self.assertTrue(meta, f"Payment Entry.{field}")
			self.assertEqual(meta.options, target)

	def test_the_payment_provider_field_exists_on_both(self):
		"""The point of making the gateway pluggable is that a row records which
		gateway handled it. Three call sites write it."""
		for doctype in ("Fee Invoice", "Payment Entry"):
			self.assertTrue(
				frappe.get_meta(doctype).get_field("payment_provider"), doctype
			)


class TestPaymentModeIsVendorNeutral(FrappeTestCase):
	def _options(self):
		return frappe.get_meta("Payment Entry").get_field("mode").options.split("\n")

	def test_every_select_value_the_gateway_writes_is_offered(self):
		"""Read the value out of the source rather than assuming it."""
		written = {
			value
			for doctype, field, value, _lineno in _writes()
			if doctype == "Payment Entry" and field == "mode" and value
		}
		self.assertTrue(written, "the webhook no longer sets a payment mode")
		for value in written:
			self.assertIn(value, self._options())

	def test_the_mode_list_names_no_brand(self):
		self.assertNotIn(
			"Razorpay", self._options(), "a payment mode must not name a brand"
		)

	def test_the_builder_and_the_doctype_agree(self):
		self.assertEqual(self._options(), list(PAYMENT_MODES))

	def test_no_stored_payment_still_names_the_brand(self):
		self.assertFalse(
			frappe.get_all("Payment Entry", filters={"mode": "Razorpay"}, limit=1),
			"sibbcs.patches.gateway_neutral_payment_mode has not run",
		)


class TestTheGatewayIsNotConfigured(FrappeTestCase):
	def test_is_configured_is_false_without_keys(self):
		"""Nothing in the suite should start talking to a real gateway."""
		self.assertFalse(razorpay.is_configured())
