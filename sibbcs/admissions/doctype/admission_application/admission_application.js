// Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
// For license information, please see license.txt

frappe.ui.form.on("Admission Application", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.trigger("show_gate_status");
		frm.trigger("show_submitted_references");
		frm.trigger("show_submitted_mentor");

		// Top level, not inside a group. add_custom_button's third argument
		// buries the action in a dropdown named after the group, which is fine
		// for occasional actions but wrong for one an officer reaches for daily.
		if (frm.doc.reference_requests?.length || frm.doc.mentor_consents?.length) {
			frm.add_custom_button(__("Resend Reference / Mentor Email"), () =>
				frm.trigger("open_resend_dialog")
			);
		}

		if (frm.doc.reference_requests?.some((r) => !r.submitted_on && !r.sent_on)) {
			frm.add_custom_button(
				__("Send Reference Requests"),
				() => frm.trigger("send_reference_requests"),
				__("Send")
			);
		}

		if (frm.doc.mentor_consents?.some((r) => !r.consented_on && !r.sent_on)) {
			frm.add_custom_button(
				__("Send Mentor Consent"),
				() => frm.trigger("send_mentor_consent"),
				__("Send")
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

	show_submitted_mentor(frm) {
		const done = (frm.doc.mentor_consents || []).filter((m) => m.consented_on);
		done.forEach((row) => {
			frm.add_custom_button(
				__("View: {0}", [row.mentor_name || __("Mentor")]),
				() => {
					frappe.call({
						method: "sibbcs.admissions.mentor_form.view",
						args: { application: frm.doc.name, row: row.name },
						freeze: true,
						callback: ({ message }) => {
							if (!message) return;
							frappe.msgprint({
								title: __("Mentor form — {0}", [message.mentor]),
								indicator: "blue",
								wide: true,
								message: `
									<p class="text-muted" style="margin-bottom:14px">
										${frappe.utils.escape_html(message.email || "")}
										${message.consented_on ? "&middot; " + frappe.datetime.str_to_user(message.consented_on) : ""}
									</p>
									${message.html || __("No answers recorded.")}
								`,
							});
						},
					});
				},
				__("Mentor")
			);
		});
	},

	show_submitted_references(frm) {
		// A submitted reference is a dozen answers in a JSON blob; nobody should
		// have to read that raw to make an admissions decision.
		const submitted = (frm.doc.reference_requests || []).filter((r) => r.submitted_on);
		if (!submitted.length) return;

		submitted.forEach((row) => {
			frm.add_custom_button(
				__("View: {0}", [row.referee_name || __("Referee")]),
				() => {
					frappe.call({
						method: "sibbcs.admissions.reference_form.view",
						args: { application: frm.doc.name, row: row.name },
						freeze: true,
						callback: ({ message }) => {
							if (!message) return;
							frappe.msgprint({
								title: __("Reference from {0}", [message.referee]),
								indicator: "blue",
								wide: true,
								message: `
									<p class="text-muted" style="margin-bottom:14px">
										${frappe.utils.escape_html(message.email || "")}
										${message.type ? "&middot; " + frappe.utils.escape_html(message.type) : ""}
										${message.submitted_on ? "&middot; " + frappe.datetime.str_to_user(message.submitted_on) : ""}
									</p>
									${message.html || __("No answers recorded.")}
								`,
							});
						},
					});
				},
				__("References")
			);
		});
	},

	open_resend_dialog(frm) {
		frappe.call({
			method: "sibbcs.admissions.notifications.list_requests",
			args: { application: frm.doc.name },
			freeze: true,
			callback: ({ message }) => {
				if (!message) return;
				frm.events.render_resend_dialog(frm, message);
			},
		});
	},

	render_resend_dialog(frm, data) {
		if (!data.mail_configured) {
			frappe.msgprint({
				title: __("Email Not Configured"),
				indicator: "orange",
				message: __(
					"No outgoing email account is set up, so nothing can be sent. Add one under Email Account first."
				),
			});
			return;
		}

		// One checkbox per person, with where each one stands, so an officer
		// chases the right people rather than emailing everyone again.
		const fields = [
			{
				fieldtype: "HTML",
				options: `<p class="text-muted small">${__(
					"Select who should receive the link again. Anyone who has already replied is listed but cannot be re-sent — their link is used up."
				)}</p>`,
			},
		];

		let section = null;
		data.rows.forEach((row, index) => {
			const heading = row.kind === "reference" ? __("Referees") : __("Mentors");
			if (heading !== section) {
				section = heading;
				fields.push({ fieldtype: "Section Break", label: heading });
			}

			let state;
			if (row.done) {
				state = `<span style="color:var(--green-600)">${__("replied")} ${
					frappe.datetime.str_to_user(row.done_on) || ""
				}</span>`;
			} else if (row.sent_on) {
				state = `${__("sent")} ${frappe.datetime.str_to_user(row.sent_on)}`;
			} else {
				state = `<span style="color:var(--orange-600)">${__("never sent")}</span>`;
			}

			fields.push({
				fieldtype: "Check",
				fieldname: `pick_${index}`,
				label: `${frappe.utils.escape_html(row.label)} &lt;${frappe.utils.escape_html(
					row.email || __("no email")
				)}&gt; — ${state}`,
				read_only: row.done || !row.email ? 1 : 0,
				default: row.done || !row.email ? 0 : 1,
			});
		});

		const dialog = new frappe.ui.Dialog({
			title: __("Resend to referees and mentors"),
			fields: fields,
			primary_action_label: __("Send Now"),
			primary_action: (values) => {
				const targets = data.rows
					.map((row, index) => ({ row, picked: values[`pick_${index}`] }))
					.filter((entry) => entry.picked && !entry.row.done && entry.row.email)
					.map((entry) => ({ kind: entry.row.kind, row: entry.row.row }));

				if (!targets.length) {
					frappe.msgprint(__("Select at least one person."));
					return;
				}

				frappe.call({
					method: "sibbcs.admissions.notifications.resend_selected",
					args: { application: frm.doc.name, targets: JSON.stringify(targets) },
					freeze: true,
					freeze_message: __("Sending…"),
					callback: () => {
						dialog.hide();
						frm.reload_doc();
					},
				});
			},
		});

		dialog.show();
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
