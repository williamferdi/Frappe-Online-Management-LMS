// Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
// For license information, please see license.txt

frappe.ui.form.on("Scholarship Request", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.trigger("show_statement");

		// Approve and Reject go through scholarship.decide rather than letting
		// the Registrar type into status: the decision has to stamp who made
		// it, check the program cap, and move step 5 on the application. A
		// hand-edited status would do none of those.
		if (frm.doc.status === "Submitted") {
			frm.add_custom_button(__("Approve"), () =>
				frm.trigger("decide_approve")
			).addClass("btn-primary");

			frm.add_custom_button(__("Reject"), () => frm.trigger("decide_reject"));
		}

		if (frm.doc.application) {
			frm.add_custom_button(__("Open Application"), () =>
				frappe.set_route("Form", "Admission Application", frm.doc.application)
			);
		}
	},

	show_statement(frm) {
		// The whole point of the form is one paragraph of prose; reading it in
		// a collapsed Text control is needless work.
		if (!frm.doc.justification) return;

		const words = frm.doc.justification.trim().split(/\s+/).filter(Boolean).length;

		frm.dashboard.add_section(
			`<div style="white-space:pre-wrap;line-height:1.7">${frappe.utils.escape_html(
				frm.doc.justification
			)}</div>
			<div class="text-muted small" style="margin-top:8px">${__("{0} words", [
				words,
			])}</div>`,
			__("Stated Need")
		);
	},

	decide_approve(frm) {
		frappe.call({
			method: "frappe.client.get_value",
			args: {
				doctype: "Program",
				filters: { name: frm.doc.program },
				fieldname: "scholarship_max",
			},
			callback: ({ message }) => {
				const cap = (message && message.scholarship_max) || 0;

				const dialog = new frappe.ui.Dialog({
					title: __("Approve scholarship"),
					fields: [
						{
							fieldtype: "HTML",
							options: cap
								? `<p class="text-muted small">${__(
										"The maximum for {0} is {1} in total.",
										[frm.doc.program, format_currency(cap, "INR")]
									)}</p>`
								: `<p class="text-muted small" style="color:var(--orange-600)">${__(
										"No ceiling is set for {0}. Set Scholarship Maximum on the Program to have approvals checked against it.",
										[frm.doc.program]
									)}</p>`,
						},
						{
							fieldtype: "Currency",
							fieldname: "approved_amount",
							label: __("Approved Total"),
							reqd: 1,
							default: cap || frm.doc.requested_amount,
							description: __(
								"The cap on the award. Tuition stops being discounted once this much has been spent."
							),
						},
						{
							fieldtype: "Currency",
							fieldname: "monthly_discount",
							label: __("Monthly Discount"),
							reqd: 1,
							description: __("Deducted from each month's tuition."),
						},
						{
							fieldtype: "Small Text",
							fieldname: "remarks",
							label: __("Remark"),
							description: __("Recorded against step 5 on the application."),
						},
					],
					primary_action_label: __("Approve"),
					primary_action: (values) => {
						frm.events.decide(frm, "Approved", values);
						dialog.hide();
					},
				});

				dialog.show();
			},
		});
	},

	decide_reject(frm) {
		frappe.prompt(
			{
				fieldtype: "Small Text",
				fieldname: "remarks",
				label: __("Reason"),
				reqd: 1,
				description: __("Recorded against step 5 on the application."),
			},
			(values) => frm.events.decide(frm, "Rejected", values),
			__("Reject scholarship"),
			__("Reject")
		);
	},

	decide(frm, outcome, values) {
		frappe.call({
			method: "sibbcs.admissions.scholarship.decide",
			args: {
				request: frm.doc.name,
				outcome: outcome,
				approved_amount: values.approved_amount || 0,
				monthly_discount: values.monthly_discount || 0,
				remarks: values.remarks,
			},
			freeze: true,
			callback: () => frm.reload_doc(),
		});
	},
});
