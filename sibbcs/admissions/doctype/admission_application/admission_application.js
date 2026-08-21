// Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
// For license information, please see license.txt

frappe.ui.form.on("Admission Application", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.trigger("render_board");
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

		// Step 5.
		if (frm.doc.email && !frm.doc.scholarship_request) {
			frm.add_custom_button(
				frm.doc.scholarship_form_sent_on
					? __("Resend Scholarship Form")
					: __("Send Scholarship Form"),
				() => frm.trigger("send_scholarship_form"),
				__("Send")
			);
		}

		if (frm.doc.scholarship_request) {
			frm.add_custom_button(__("Open Scholarship Request"), () =>
				frappe.set_route("Form", "Scholarship Request", frm.doc.scholarship_request)
			);
		}

		// Step 9.
		if (frm.doc.email) {
			frm.add_custom_button(
				frm.doc.interview_link_sent_on
					? __("Resend Interview Booking Link")
					: __("Send Interview Booking Link"),
				() => frm.trigger("send_interview_invite"),
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

	render_board(frm) {
		const field = frm.get_field("checklist_board");
		if (!field) return;

		frappe.call({
			method: "sibbcs.admissions.checklist.board",
			args: { application: frm.doc.name },
			callback: ({ message }) => {
				if (message) frm.events.draw_board(frm, field, message);
			},
		});
	},

	draw_board(frm, field, data) {
		const esc = frappe.utils.escape_html;
		const done = data.progress.done;
		const total = data.progress.total || 13;
		const pct = total ? Math.round((done / total) * 100) : 0;

		// One action per step that has something to do, so the officer works
		// the board rather than hunting through the toolbar for the button
		// that belongs to the row they are looking at.
		const ACTION_LABELS = {
			resend_requests: __("Resend"),
			send_scholarship_form: __("Form"),
			create_lms_account: __("Account"),
			send_interview_invite: __("Invite"),
			send_manuals: __("Send"),
			onboard_student: __("Onboard"),
		};

		const rows = data.rows
			.map((row) => {
				const options = row.statuses
					.map((status) => {
						// A blocked step can still move to an intermediate status;
						// only the ones that would complete it are shut off.
						const shuts = row.blocked && row.done_statuses.includes(status);
						return `<option value="${esc(status)}"${
							status === row.status ? " selected" : ""
						}${shuts ? " disabled" : ""}>${esc(status)}</option>`;
					})
					.join("");

				const mark = row.done
					? `<span class="sib-tick" title="${__("Complete")}">&#10003;</span>`
					: row.blocked
						? `<span class="sib-lock" title="${esc(row.blocked)}">&#9679;</span>`
						: `<span class="sib-open">&#9675;</span>`;

				let meta = "";
				if (row.updated_on) {
					meta = `${esc(frappe.user.full_name(row.updated_by) || "")} · ${frappe.datetime.str_to_user(
						row.updated_on
					)}`;
				}
				if (row.remarks) {
					meta += `${meta ? "<br>" : ""}<i>${esc(row.remarks)}</i>`;
				}

				const action =
					row.action && data.can_write
						? `<button class="btn btn-xs btn-default sib-act" data-action="${esc(
								row.action
							)}">${ACTION_LABELS[row.action] || __("Open")}</button>`
						: "";

				return `
					<div class="sib-row${row.done ? " is-done" : ""}${row.blocked ? " is-blocked" : ""}">
						<div class="sib-no">${row.step_no}</div>
						<div class="sib-mark">${mark}</div>
						<div class="sib-name">
							<div class="sib-title">${esc(row.step)}</div>
							<div class="sib-role">${esc(row.owner_role)}</div>
						</div>
						<div class="sib-status">
							<select class="form-control sib-select" data-step="${row.step_no}"
							        ${data.can_write ? "" : "disabled"}>${options}</select>
							${row.blocked ? `<div class="sib-why">${esc(row.blocked)}</div>` : ""}
						</div>
						<div class="sib-meta">${meta}</div>
						<div class="sib-actions">
							${action}
							<button class="btn btn-xs btn-default sib-note" data-step="${row.step_no}"
							        title="${__("Add a remark")}">&#9998;</button>
						</div>
					</div>`;
			})
			.join("");

		field.$wrapper.html(`
			<style>
				.sib-board { font-size: 13px; }
				.sib-head { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
				.sib-count { font-weight: 600; white-space: nowrap; }
				.sib-bar { flex: 1; height: 6px; border-radius: 3px;
				           background: var(--control-bg, #eee); overflow: hidden; }
				.sib-fill { height: 100%; background: var(--green-500, #28a745); }
				.sib-row { display: grid; grid-template-columns: 24px 20px 1fr 200px 1fr 92px;
				           gap: 10px; align-items: start; padding: 8px 6px;
				           border-top: 1px solid var(--border-color, #ebeef0); }
				.sib-row:last-child { border-bottom: 1px solid var(--border-color, #ebeef0); }
				.sib-row.is-done { background: var(--bg-green, transparent); }
				.sib-no { color: var(--text-muted, #8d99a6); padding-top: 5px; }
				.sib-mark { padding-top: 4px; font-size: 14px; }
				.sib-tick { color: var(--green-600, #28a745); font-weight: 700; }
				.sib-lock { color: var(--orange-500, #f0a500); }
				.sib-open { color: var(--text-muted, #b9c0c7); }
				.sib-title { padding-top: 4px; }
				.sib-role { color: var(--text-muted, #8d99a6); font-size: 11px; }
				.sib-select { height: 26px; padding: 2px 6px; font-size: 12px; }
				.sib-why { color: var(--orange-600, #b97400); font-size: 11px; margin-top: 3px; }
				.sib-meta { color: var(--text-muted, #8d99a6); font-size: 11px; padding-top: 6px; }
				.sib-actions { text-align: right; padding-top: 2px; white-space: nowrap; }
				.sib-actions .btn { margin-left: 3px; }
				@media (max-width: 991px) {
					.sib-row { grid-template-columns: 24px 20px 1fr; }
					.sib-status, .sib-meta, .sib-actions { grid-column: 3; text-align: left; }
				}
			</style>
			<div class="sib-board">
				<div class="sib-head">
					<span class="sib-count">${done} / ${total} ${__("complete")}</span>
					<span class="sib-bar"><span class="sib-fill" style="width:${pct}%"></span></span>
					<span class="text-muted">${esc(data.state || "")}</span>
				</div>
				${rows}
			</div>
		`);

		field.$wrapper.find(".sib-select").on("change", function () {
			frm.events.move_step(frm, $(this).data("step"), $(this).val());
		});

		field.$wrapper.find(".sib-act").on("click", function () {
			frm.trigger($(this).data("action"));
		});

		field.$wrapper.find(".sib-note").on("click", function () {
			const step = $(this).data("step");
			const row = data.rows.find((r) => r.step_no === step);
			frappe.prompt(
				{
					fieldtype: "Small Text",
					fieldname: "remarks",
					label: __("Remark"),
					default: row ? row.remarks : "",
				},
				(values) => frm.events.move_step(frm, step, row.status, values.remarks),
				__("{0} — remark", [row ? row.step : ""]),
				__("Save")
			);
		});
	},

	move_step(frm, step_no, status, remarks) {
		frappe.call({
			method: "sibbcs.admissions.checklist.update_step",
			args: {
				application: frm.doc.name,
				step_no: step_no,
				status: status,
				remarks: remarks,
			},
			freeze: true,
			// reload_doc re-runs refresh, which redraws the board -- so a
			// refused move puts the select back to what the server believes
			// rather than leaving the officer looking at a status that was
			// never saved.
			callback: () => frm.reload_doc(),
			error: () => frm.reload_doc(),
		});
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

	send_scholarship_form(frm) {
		if (frm.doc.scholarship_request) {
			frappe.set_route("Form", "Scholarship Request", frm.doc.scholarship_request);
			return;
		}
		frappe.confirm(
			__(
				"This emails {0} the scholarship form. Applying does not affect their admission decision. Continue?",
				[frm.doc.email]
			),
			() => {
				frappe.call({
					method: "sibbcs.admissions.scholarship.send",
					args: { application: frm.doc.name },
					freeze: true,
					freeze_message: __("Sending…"),
					callback: () => frm.reload_doc(),
				});
			}
		);
	},

	send_interview_invite(frm) {
		const again = Boolean(frm.doc.interview_link_sent_on);
		frappe.confirm(
			again
				? __("Send {0} the interview booking link again?", [frm.doc.email])
				: __(
						"This emails {0} a Calendly link to pick their own interview slot. Continue?",
						[frm.doc.email]
					),
			() => {
				frappe.call({
					method: "sibbcs.admissions.interview.send",
					args: { application: frm.doc.name },
					freeze: true,
					freeze_message: __("Sending…"),
					callback: () => frm.reload_doc(),
				});
			}
		);
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
