// Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
// For license information, please see license.txt

frappe.ui.form.on("Admission Application", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.trigger("show_gate_status");

		if (frm.doc.reference_requests?.some((r) => !r.submitted_on)) {
			frm.add_custom_button(
				__("Send Reference Requests"),
				() => frm.trigger("send_reference_requests"),
				__("Admissions")
			);
		}

		if (frm.doc.mentor_consents?.some((r) => !r.consented_on)) {
			frm.add_custom_button(
				__("Send Mentor Consent"),
				() => frm.trigger("send_mentor_consent"),
				__("Admissions")
			);
		}

		if (frm.doc.admission_fee_paid && !frm.doc.student) {
			frm.add_custom_button(__("Convert to Student"), () =>
				frm.trigger("convert_to_student")
			).addClass("btn-primary");
		}

		if (frm.doc.student) {
			frm.add_custom_button(__("Open Student"), () =>
				frappe.set_route("Form", "Student", frm.doc.student)
			);
		}
	},

	show_gate_status(frm) {
		// A compact read of where this application actually stands, so an
		// officer does not have to open three child tables to find out.
		const pending_refs = (frm.doc.reference_requests || []).filter(
			(r) => !r.submitted_on
		).length;
		const has_mentor = (frm.doc.mentor_consents || []).some((c) => c.consented_on);

		const rows = [
			[__("Application fee"), frm.doc.application_fee_paid],
			[__("Documents verified"), frm.doc.docs_verified],
			[__("References received"), pending_refs === 0],
			[__("Mentor consent"), has_mentor],
			[__("Admission fee"), frm.doc.admission_fee_paid],
		];

		const html = rows
			.map(([label, done]) => {
				const colour = done ? "green" : "orange";
				const mark = done ? "&#10003;" : "&#8226;";
				return `<div style="margin-bottom:4px">
					<span style="color:var(--text-on-${colour}, ${colour});font-weight:600">${mark}</span>
					<span style="margin-left:6px">${label}</span>
				</div>`;
			})
			.join("");

		frm.dashboard.add_section(
			`<div style="padding:4px 0">${html}</div>`,
			__("Admission Gates")
		);
	},

	send_reference_requests(frm) {
		frappe.call({
			method:
				"sibbcs.admissions.doctype.admission_application.admission_application.send_reference_requests",
			args: { application_name: frm.doc.name },
			freeze: true,
			freeze_message: __("Queueing reference requests…"),
			callback: () => frm.reload_doc(),
		});
	},

	send_mentor_consent(frm) {
		frappe.call({
			method:
				"sibbcs.admissions.doctype.admission_application.admission_application.send_mentor_consent_requests",
			args: { application_name: frm.doc.name },
			freeze: true,
			freeze_message: __("Queueing mentor consent requests…"),
			callback: () => frm.reload_doc(),
		});
	},

	convert_to_student(frm) {
		frappe.confirm(
			__(
				"This creates the Student, their login, and their Program Enrollment. Continue?"
			),
			() => {
				frappe.call({
					method: "sibbcs.admissions.conversion.convert_application",
					args: { application_name: frm.doc.name },
					freeze: true,
					freeze_message: __("Enrolling…"),
					callback: () => frm.reload_doc(),
				});
			}
		);
	},
});
