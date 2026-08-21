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

		// Step 7. Once the account exists the button becomes a resend, because
		// the common follow-up is "they never got the email", not "make them a
		// second account".
		if (frm.doc.email) {
			frm.add_custom_button(
				frm.doc.applicant_user
					? __("Resend Login and Exam Link")
					: __("Create LMS Account"),
				() => frm.trigger("create_lms_account"),
				__("Send")
			);
		}

		// Step 12.
		if (!frm.is_new()) {
			frm.add_custom_button(
				__("Send Reading Manuals"),
				() => frm.trigger("send_manuals"),
				__("Send")
			);
		}

		// Step 13. The primary action once it is reachable, because it is the
		// end of the process and the one an officer is looking for.
		if (!frm.doc.student) {
			frm.add_custom_button(__("Onboard Student"), () =>
				frm.trigger("onboard_student")
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

	create_lms_account(frm) {
		const again = Boolean(frm.doc.applicant_user);
		const question = again
			? __(
					"This sends {0} their login and the entrance exam link again, with a fresh set-password link. Continue?",
					[frm.doc.email]
				)
			: __(
					"This creates an LMS account for {0} and emails them a set-password link and the entrance exam link. Continue?",
					[frm.doc.email]
				);

		frappe.confirm(question, () => {
			frappe.call({
				method: again
					? "sibbcs.admissions.lms_account.resend_exam_link"
					: "sibbcs.admissions.lms_account.create_account",
				args: { application: frm.doc.name },
				freeze: true,
				freeze_message: __("Creating the account…"),
				callback: () => frm.reload_doc(),
			});
		});
	},

	send_manuals(frm) {
		frappe.call({
			method: "sibbcs.admissions.manuals.status",
			args: { application: frm.doc.name },
			freeze: true,
			callback: ({ message }) => {
				if (!message) return;
				frm.events.render_manual_dialog(frm, message);
			},
		});
	},

	render_manual_dialog(frm, data) {
		if (!data.applicable.length) {
			frappe.msgprint({
				title: __("No Manuals"),
				indicator: "orange",
				message: __(
					"No active Reading Manual applies to this program. Add one under Reading Manual first."
				),
			});
			return;
		}

		const rows = data.rows.length
			? data.rows
					.map((row) => {
						let state;
						if (row.acknowledged_on) {
							state = `<span style="color:var(--green-600)">${__("read by")} ${frappe.utils.escape_html(
								row.acknowledged_name || ""
							)} ${frappe.datetime.str_to_user(row.acknowledged_on)}</span>`;
						} else if (row.sent_on) {
							state = `${__("sent")} ${frappe.datetime.str_to_user(row.sent_on)}`;
						} else {
							state = `<span style="color:var(--orange-600)">${__("never sent")}</span>`;
						}
						return `<div style="margin-bottom:6px">${frappe.utils.escape_html(
							row.manual
						)} — ${state}</div>`;
					})
					.join("")
			: `<p class="text-muted">${__("Nothing sent yet. {0} manual(s) apply.", [
					data.applicable.length,
				])}</p>`;

		const dialog = new frappe.ui.Dialog({
			title: __("Reading manuals"),
			fields: [
				{ fieldtype: "HTML", options: rows },
				{
					fieldtype: "Check",
					fieldname: "force",
					label: __("Send again to those who have already been emailed"),
					default: 0,
				},
			],
			primary_action_label: __("Send"),
			primary_action: (values) => {
				frappe.call({
					method: "sibbcs.admissions.manuals.send",
					args: { application: frm.doc.name, force: values.force ? 1 : 0 },
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

	onboard_student(frm) {
		const level = frm.doc.onboard_level;
		const term = frm.doc.onboard_term || frm.doc.intake_term;

		frappe.confirm(
			__(
				"This creates the Student, their login and their Program Enrollment at level <b>{0}</b> in <b>{1}</b>. Continue?",
				[level || __("1 (nothing chosen)"), term || __("no term")]
			),
			() => {
				frappe.call({
					method: "sibbcs.admissions.conversion.onboard_application",
					args: { application_name: frm.doc.name },
					freeze: true,
					freeze_message: __("Onboarding…"),
					callback: () => frm.reload_doc(),
				});
			}
		);
	},
});
