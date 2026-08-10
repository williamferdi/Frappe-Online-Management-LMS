"""Phase 4 -- the fee engine.

    bench --site online.sibbc.org execute sibbcs.setup.phase4_finance.build

Idempotent.

Architecture doc §5 defines four independent streams that must never be merged
into one invoice:

    1. One-time      Application, Admission, ATA (M.Div), Graduation
    2. Per-registration   Rs350 on every Course Registration, NOT discountable
    3. Recurring tuition  the paused subscription, billed per active term
    4. Scholarship        writes monthly_discount + cap onto Program Enrollment

The tuition ceiling (open decision #1) is answered "cap at Rs54,000,
pay-as-you-go": tuition bills only in terms where the student registered
something, and stops once the ceiling is reached. It lives on Program as
`tuition_total` rather than as a constant, so uncapped billing is a cleared
field rather than a code change.
"""

import frappe

from sibbcs.setup.schema import (
	add_fields,
	check,
	column,
	edit,
	ensure_doctype,
	ensure_module,
	f,
	fetched,
	full,
	link,
	multiselect,
	read,
	section,
	select,
	table,
)

FINANCE = "Finance"
ACADEMIC = "Academic"

CATEGORIES = ["One-Time", "Per-Registration", "Recurring Tuition"]

TRIGGERS = [
	"Manual",
	"Application Submitted",
	"Offer Sent",
	"Enrollment",
	"Course Registration",
	"Term Start",
	"Graduation",
]

# "Online" rather than a provider name: the gateway can change (Razorpay, Jodo,
# something else) without the payment *mode* meaning anything different. Which
# gateway handled it is recorded separately in `payment_provider`.
PAYMENT_MODES = ["Online", "UPI", "Bank Transfer", "Cash", "Cheque"]

INVOICE_STATUSES = ["Unpaid", "Partly Paid", "Paid", "Waived", "Cancelled"]

# §5 seed list
FEE_TYPES = [
	{
		"fee_name": "Application Fee",
		"category": "One-Time",
		"default_amount": 350,
		"trigger_event": "Application Submitted",
		"discountable": 0,
	},
	{
		"fee_name": "Admission Fee",
		"category": "One-Time",
		"default_amount": 2000,
		"trigger_event": "Offer Sent",
		"discountable": 0,
	},
	{
		"fee_name": "Course Registration Fee",
		"category": "Per-Registration",
		"default_amount": 350,
		"trigger_event": "Course Registration",
		"discountable": 0,
	},
	{
		"fee_name": "Monthly Tuition",
		"category": "Recurring Tuition",
		"default_amount": 1500,
		"trigger_event": "Term Start",
		"discountable": 1,
	},
	{
		"fee_name": "ATA Registration",
		"category": "One-Time",
		"default_amount": 2000,
		"trigger_event": "Enrollment",
		"discountable": 0,
		"programs": ["MDIV"],
	},
	{
		"fee_name": "Graduation & Transcript",
		"category": "One-Time",
		"default_amount": 2000,
		"trigger_event": "Graduation",
		"discountable": 0,
	},
]


def _fee_type():
	ensure_doctype(
		"Fee Type Program",
		FINANCE,
		istable=1,
		fields=[link("program", "Program", "Program", reqd=1, in_list_view=1)],
	)

	ensure_doctype(
		"Fee Type",
		FINANCE,
		fields=[
			section("sb_identity"),
			f("fee_name", "Fee Name", reqd=1, unique=1, in_list_view=1),
			select("category", "Category", CATEGORIES, reqd=1, in_list_view=1, in_standard_filter=1),
			column("cb_identity"),
			f("default_amount", "Default Amount", "Currency", reqd=1, in_list_view=1),
			check("is_active", "Is Active", default=1),
			section("sb_behaviour", "Behaviour"),
			select(
				"trigger_event",
				"Raised On",
				TRIGGERS,
				default="Manual",
				description="The lifecycle event that raises this fee automatically.",
			),
			column("cb_behaviour"),
			check(
				"discountable",
				"Scholarship May Discount",
				description=(
					"Only recurring tuition is discountable. The per-registration fee "
					"is deliberately not (§5 Stream 2)."
				),
			),
			f("gl_code", "GL Code"),
			section("sb_scope", "Scope"),
			multiselect(
				"applies_to_programs",
				"Applies To Programs",
				"Fee Type Program",
				description="Leave empty to apply to every program.",
			),
		],
		permissions=[
			full("System Manager"),
			full("Accounts"),
			read("Registrar"),
		],
		autoname="field:fee_name",
		naming_rule="By fieldname",
	)


def _fee_invoice():
	ensure_doctype(
		"Fee Invoice",
		FINANCE,
		fields=[
			section("sb_who", "Student"),
			f(
				"naming_series",
				"Series",
				"Select",
				options="FEE-.YYYY.-.#####",
				default="FEE-.YYYY.-.#####",
				reqd=1,
				hidden=1,
			),
			link("student", "Student", "Student", reqd=1, in_list_view=1),
			fetched("student_name", "Student Name", "student.full_name", in_list_view=1),
			column("cb_who"),
			link("program_enrollment", "Program Enrollment", "Program Enrollment"),
			select(
				"status",
				"Status",
				INVOICE_STATUSES,
				default="Unpaid",
				in_list_view=1,
				in_standard_filter=1,
			),
			section("sb_what", "Fee"),
			link("fee_type", "Fee Type", "Fee Type", reqd=1, in_list_view=1, in_standard_filter=1),
			fetched("category", "Category", "fee_type.category", in_standard_filter=1),
			column("cb_what"),
			link("term", "Term", "Academic Term", description="Set for recurring tuition."),
			f(
				"months_billed",
				"Months Billed",
				"Int",
				description="Recurring tuition only. Counts toward the programme ceiling.",
			),
			section("sb_link"),
			link(
				"course_registration",
				"Course Registration",
				"Course Registration",
				description="Set for the per-registration fee.",
			),
			section("sb_amounts", "Amounts"),
			f("gross_amount", "Gross", "Currency", reqd=1, in_list_view=1),
			f("discount_amount", "Scholarship Discount", "Currency"),
			column("cb_amounts"),
			f("net_amount", "Net", "Currency", read_only=1, in_list_view=1),
			f("paid_amount", "Paid", "Currency", read_only=1),
			f("outstanding_amount", "Outstanding", "Currency", read_only=1),
			section("sb_due", "Payment"),
			f("due_date", "Due Date", "Date", reqd=1, in_list_view=1),
			column("cb_due"),
			f("payment_link", "Payment Link", "Small Text", read_only=1),
			f("payment_reference", "Gateway Reference", "Data", read_only=1, hidden=1),
			f("payment_provider", "Gateway", "Data", read_only=1),
			section("sb_remarks"),
			f("remarks", "Remarks", "Small Text"),
		],
		permissions=[
			full("System Manager"),
			full("Accounts"),
			read("Registrar"),
			read("Student"),
		],
		autoname="naming_series:",
		naming_rule='By "Naming Series" field',
		title_field="student_name",
		search_fields="student,fee_type,term",
		sort_field="modified",
		sort_order="DESC",
	)


def _payment_entry():
	ensure_doctype(
		"Payment Allocation",
		FINANCE,
		istable=1,
		fields=[
			link("fee_invoice", "Fee Invoice", "Fee Invoice", reqd=1, in_list_view=1, columns=3),
			fetched("invoice_net", "Net", "fee_invoice.net_amount", "Currency", in_list_view=1, columns=2),
			fetched(
				"invoice_outstanding",
				"Outstanding",
				"fee_invoice.outstanding_amount",
				"Currency",
				in_list_view=1,
				columns=2,
			),
			f("allocated_amount", "Allocated", "Currency", reqd=1, in_list_view=1, columns=2),
		],
	)

	ensure_doctype(
		"Payment Entry",
		FINANCE,
		fields=[
			section("sb_who"),
			f(
				"naming_series",
				"Series",
				"Select",
				options="PAY-.YYYY.-.#####",
				default="PAY-.YYYY.-.#####",
				reqd=1,
				hidden=1,
			),
			link("student", "Student", "Student", reqd=1, in_list_view=1),
			fetched("student_name", "Student Name", "student.full_name", in_list_view=1),
			column("cb_who"),
			f("amount", "Amount", "Currency", reqd=1, in_list_view=1),
			f("received_on", "Received On", "Date", reqd=1, in_list_view=1),
			section("sb_mode", "Mode"),
			select("mode", "Mode", PAYMENT_MODES, reqd=1, in_list_view=1, in_standard_filter=1),
			f("reference_no", "Reference No"),
			column("cb_mode"),
			f("gateway_payment_id", "Gateway Payment ID", "Data", read_only=1),
			f("payment_provider", "Gateway", "Data", read_only=1),
			link("reconciled_by", "Reconciled By", "User", read_only=1),
			section("sb_allocation", "Allocation"),
			table("allocations", "Allocations", "Payment Allocation"),
			section("sb_totals"),
			f("allocated_amount", "Allocated", "Currency", read_only=1),
			column("cb_totals"),
			f(
				"unallocated_amount",
				"Unallocated",
				"Currency",
				read_only=1,
				description="Money received but not yet applied to an invoice.",
			),
			section("sb_remarks"),
			f("remarks", "Remarks", "Small Text"),
		],
		permissions=[
			full("System Manager"),
			full("Accounts"),
			read("Registrar"),
			read("Student"),
		],
		autoname="naming_series:",
		naming_rule='By "Naming Series" field',
		title_field="student_name",
		search_fields="student,gateway_payment_id,reference_no",
		sort_field="modified",
		sort_order="DESC",
	)


def _fee_invoice_for_applicants():
	"""An application fee is owed before any Student exists.

	Fee Invoice.student was mandatory, which made the §5 Stream 1 application
	fee impossible to raise -- an applicant has no Student record until the
	conversion point. Student becomes optional and an admission_application
	link is added; FeeInvoice.validate requires exactly one of the two.
	"""
	add_fields(
		"Fee Invoice",
		[
			link(
				"admission_application",
				"Admission Application",
				"Admission Application",
				description="Set for the application fee, which is owed before a Student exists.",
			)
		],
		insert_after="program_enrollment",
	)

	doc = frappe.get_doc("DocType", "Fee Invoice")
	changed = False
	for row in doc.fields:
		if row.fieldname == "student" and row.reqd:
			row.reqd = 0
			changed = True
	if changed:
		doc.save(ignore_permissions=True)
		print("  Fee Invoice.student is no longer mandatory (applicants have no Student)")


RENAMES = [
	("Fee Invoice", "razorpay_link", "payment_link", "Payment Link"),
	("Fee Invoice", "razorpay_link_id", "payment_reference", "Gateway Reference"),
	("Payment Entry", "razorpay_payment_id", "gateway_payment_id", "Gateway Payment ID"),
]


def _neutralise_gateway_fields():
	"""Rename provider-specific fields to neutral ones.

	The gateway is a decision that can change; the schema should not carry one
	vendor's name.

	Note frappe.rename_field is NOT enough here. For a standard (non-custom)
	DocType the JSON on disk is the source of truth, and the phase builders skip
	DocTypes that already exist -- so a renamed column is simply restored by the
	next `bench migrate`. The fieldname has to be changed on the DocType doc and
	saved, which regenerates the JSON.

	Guarded: refuses to touch a column that holds data, so running this on a
	live site can never lose a payment link or a gateway reference.
	"""
	for doctype, old, new, label in RENAMES:
		if not frappe.db.exists("DocType", doctype):
			continue

		# Two fields on the same DocType are renamed in turn; without this the
		# second iteration reads a meta cached before the first save and
		# silently finds nothing to do.
		frappe.clear_cache(doctype=doctype)
		meta = frappe.get_meta(doctype)
		if meta.get_field(new) or not meta.get_field(old):
			continue

		if frappe.db.has_column(doctype, old):
			in_use = frappe.db.sql(
				f"""select count(*) from `tab{doctype}`
				    where `{old}` is not null and `{old}` != ''"""
			)[0][0]
			if in_use:
				print(
					f"  ! {doctype}.{old} holds {in_use} value(s) -- skipping rename. "
					"Migrate the data first."
				)
				continue

		doc = frappe.get_doc("DocType", doctype)
		for row in doc.fields:
			if row.fieldname == old:
				row.fieldname = new
				row.label = label

		# A fieldname is referenced from DocType metadata too. Renaming the
		# field alone makes the save fail validation with
		# "Search field <old> is not valid".
		for attribute in ("search_fields", "title_field", "sort_field", "image_field"):
			value = doc.get(attribute)
			if value and old in value:
				doc.set(attribute, value.replace(old, new))

		doc.save(ignore_permissions=True)
		print(f"  renamed {doctype}.{old} -> {new}")

		if frappe.db.has_column(doctype, old):
			# DDL must go through sql_ddl; frappe.db.sql refuses it with
			# ImplicitCommitError because ALTER TABLE commits the transaction.
			frappe.db.sql_ddl(f"alter table `tab{doctype}` drop column `{old}`")
			print(f"    dropped orphaned column {old}")

	# The mode option was a vendor name; record the gateway separately instead.
	frappe.db.sql("""update `tabPayment Entry` set mode = 'Online' where mode = 'Razorpay'""")


def _program_tuition_fields():
	"""The tuition ceiling lives on Program, not in code."""
	add_fields(
		"Program",
		[
			section("sb_tuition", "Tuition"),
			f(
				"monthly_tuition",
				"Monthly Tuition",
				"Currency",
				default="1500",
				description="Billed per month of an active term.",
			),
			f(
				"tuition_total",
				"Tuition Ceiling",
				"Currency",
				default="54000",
				description=(
					"Stop billing tuition once this much has been billed. "
					"Clear it (0) for uncapped pay-as-you-go."
				),
			),
			check(
				"cap_on_gross",
				"Ceiling Applies to Gross",
				default=1,
				description=(
					"Measure the ceiling against gross tuition, before scholarship. "
					"If measured against net, a scholarship merely stretches the "
					"payment period instead of reducing the bill."
				),
			),
		],
	)


def _relink_registration_fee_field():
	"""Course Registration.registration_fee_invoice was Data until Fee Invoice existed."""
	meta_field = frappe.db.get_value(
		"DocField",
		{"parent": "Course Registration", "fieldname": "registration_fee_invoice"},
		["name", "fieldtype"],
		as_dict=True,
	)
	if not meta_field or meta_field.fieldtype == "Link":
		return

	doc = frappe.get_doc("DocType", "Course Registration")
	for row in doc.fields:
		if row.fieldname == "registration_fee_invoice":
			row.fieldtype = "Link"
			row.options = "Fee Invoice"
			row.description = None
	doc.save(ignore_permissions=True)
	print("  relinked Course Registration.registration_fee_invoice -> Fee Invoice")


def seed_fee_types():
	created = []
	for spec in FEE_TYPES:
		if frappe.db.exists("Fee Type", spec["fee_name"]):
			continue
		programs = spec.pop("programs", None)
		doc = frappe.get_doc({"doctype": "Fee Type", "is_active": 1, **spec})
		for program in programs or []:
			if frappe.db.exists("Program", program):
				doc.append("applies_to_programs", {"program": program})
		doc.insert(ignore_permissions=True)
		created.append(doc.name)

	print(f"Fee Types: {len(created)} created, {len(FEE_TYPES) - len(created)} already present")
	return created


def build():
	ensure_module(FINANCE)

	_fee_type()
	_fee_invoice()
	_payment_entry()
	_fee_invoice_for_applicants()
	_neutralise_gateway_fields()
	_program_tuition_fields()
	_relink_registration_fee_field()
	seed_fee_types()

	frappe.db.commit()

	names = frappe.get_all("DocType", filters={"module": FINANCE}, pluck="name", order_by="name")
	print(f"Finance DocTypes ({len(names)}):")
	for name in names:
		print(f"  - {name}")
