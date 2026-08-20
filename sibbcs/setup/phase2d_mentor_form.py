"""Extend Mentor Consent to hold the college's full mentor form.

    bench --site online.sibbc.org execute sibbcs.setup.phase2d_mentor_form.build

Idempotent.

The original child row held only name, email, mobile and church -- enough to
send a consent link, nowhere near enough for the form the college actually
uses, which collects the mentor's ministry position, denomination, full postal
address, photograph and experience.
"""

import frappe

from sibbcs.setup.schema import add_fields, check, column, f, section, select

GENDERS = ["", "Male", "Female"]


def build():
	add_fields(
		"Mentor Consent",
		[
			section("sb_mentor_detail", "Mentor Details"),
			select("mentor_gender", "Gender", GENDERS),
			f("mentor_age", "Age", "Int"),
			f("mentor_image", "Photograph", "Attach Image"),
			column("cb_mentor_detail"),
			f("current_position", "Current Position in Ministry", "Small Text"),
			f("denomination", "Denomination", "Data"),
			f("years_of_ministry", "Years of Ministry Experience", "Int"),
			section("sb_mentor_address", "Address"),
			f("address_line_1", "Address Line 1", "Data"),
			f("address_line_2", "Address Line 2", "Data"),
			f("city", "City / District", "Data"),
			column("cb_mentor_address"),
			f("state", "State / Province", "Data"),
			f("postal_code", "Postal Code", "Data", length=20),
			f("country", "Country", "Data", default="India"),
			section("sb_mentor_background", "Background"),
			f("prior_theological_education", "Any Prior Theological Education?", "Small Text"),
			f("mentoring_experience", "Any Mentoring Experience?", "Small Text"),
			section("sb_mentor_declaration"),
			check(
				"handbook_acknowledged",
				"Confirmed reading the Mentor Handbook",
				description=(
					"INFERRED from the form's instruction to read the handbook "
					"thoroughly -- confirm this is wanted before real intakes."
				),
			),
		],
		insert_after="church",
	)

	frappe.db.commit()
	frappe.clear_cache()

	meta = frappe.get_meta("Mentor Consent")
	added = [
		df.fieldname
		for df in meta.fields
		if df.fieldname
		in (
			"mentor_gender", "mentor_age", "mentor_image", "current_position",
			"denomination", "years_of_ministry", "address_line_1", "city",
			"prior_theological_education", "mentoring_experience",
			"handbook_acknowledged",
		)
	]
	print(f"Mentor Consent now carries {len(added)} of the form's fields.")
	print("Set the two document links with:")
	print("  bench --site <site> set-config mentor_role_description_url '<url>'")
	print("  bench --site <site> set-config mentor_handbook_url '<url>'")
