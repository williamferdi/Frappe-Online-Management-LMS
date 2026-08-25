// Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
// For license information, please see license.txt

frappe.pages["level-promotions"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Level Promotions"),
		single_column: true,
	});

	const board = new LevelPromotions(page);
	board.refresh();
};

class LevelPromotions {
	constructor(page) {
		this.page = page;
		this.include_blocked = 0;

		// A toggle rather than two pages. "Who is nearly ready" is the same
		// question as "who is ready", asked a fortnight earlier.
		this.page.add_field({
			fieldtype: "Check",
			fieldname: "include_blocked",
			label: __("Show students who are not ready"),
			change: () => {
				this.include_blocked = this.page.fields_dict.include_blocked.get_value()
					? 1
					: 0;
				this.refresh();
			},
		});

		this.page.set_primary_action(__("Refresh"), () => this.refresh(), "refresh");

		this.body = $('<div class="promotions-body">').appendTo(this.page.main);
	}

	refresh() {
		this.body.html(
			`<div class="text-muted" style="padding:24px 0">${__("Loading…")}</div>`
		);

		frappe.call({
			method:
				"sibbcs.academic.doctype.level_promotion.level_promotion.promotion_board",
			args: { include_blocked: this.include_blocked },
			callback: ({ message }) => this.render(message || []),
		});
	}

	render(rows) {
		const esc = frappe.utils.escape_html;

		if (!rows.length) {
			this.body.html(`
				<div class="text-muted" style="padding:32px 0;text-align:center">
					${
						this.include_blocked
							? __("No active enrollments.")
							: __("Nobody is ready for promotion right now.")
					}
				</div>
			`);
			return;
		}

		const ready = rows.filter((r) => r.eligible).length;

		const body = rows
			.map((row) => {
				const bar = row.required
					? Math.min(100, Math.round((row.passed / row.required) * 100))
					: 100;

				const verdict = row.eligible
					? `<span class="lp-ready">${__("Ready for Level {0}", [row.to_level])}</span>`
					: `<span class="lp-blocked">${esc(row.blocked || "")}</span>`;

				const action = row.eligible
					? `<button class="btn btn-xs btn-primary lp-promote"
					        data-enrollment="${esc(row.program_enrollment)}"
					        data-student="${esc(row.student_name || row.student)}"
					        data-to="${row.to_level}">${__("Promote")}</button>`
					: "";

				return `
					<div class="lp-row${row.eligible ? " is-ready" : ""}">
						<div class="lp-who">
							<a href="/app/program-enrollment/${encodeURIComponent(
								row.program_enrollment
							)}">${esc(row.student_name || row.student)}</a>
							<div class="lp-sub">${esc(row.program)} &middot; ${__("Level")} ${row.from_level}</div>
						</div>
						<div class="lp-count">
							<div>${row.passed} / ${row.required || "—"}</div>
							<div class="lp-bar"><span style="width:${bar}%"></span></div>
						</div>
						<div class="lp-verdict">${verdict}</div>
						<div class="lp-action">${action}</div>
					</div>`;
			})
			.join("");

		this.body.html(`
			<style>
				.promotions-body { font-size: 13px; }
				.lp-head {
					display: flex; align-items: center; gap: 10px;
					margin: 4px 0 12px; color: var(--text-muted, #8d99a6);
				}
				.lp-row {
					display: grid; grid-template-columns: 1fr 130px 1fr 100px;
					gap: 12px; align-items: center; padding: 10px 6px;
					border-top: 1px solid var(--border-color, #ebeef0);
				}
				.lp-row:last-child { border-bottom: 1px solid var(--border-color, #ebeef0); }
				.lp-sub { color: var(--text-muted, #8d99a6); font-size: 11px; }
				.lp-count { text-align: center; }
				.lp-bar {
					height: 5px; border-radius: 3px; margin-top: 4px;
					background: var(--control-bg, #eee); overflow: hidden;
				}
				.lp-bar span { display: block; height: 100%; background: var(--green-500, #28a745); }
				.lp-ready { color: var(--green-600, #28a745); font-weight: 600; }
				.lp-blocked { color: var(--text-muted, #8d99a6); }
				.lp-action { text-align: right; }
			</style>
			<div class="lp-head">
				${__("{0} of {1} ready to promote", [ready, rows.length])}
			</div>
			${body}
		`);

		this.body.find(".lp-promote").on("click", (event) => {
			const button = $(event.currentTarget);
			this.promote(
				button.data("enrollment"),
				button.data("student"),
				button.data("to")
			);
		});
	}

	promote(enrollment, student, to_level) {
		// Remarks are asked for, not optional-in-passing: a level change is the
		// one thing on a transcript nobody can reconstruct later.
		const dialog = new frappe.ui.Dialog({
			title: __("Promote {0}", [student]),
			fields: [
				{
					fieldtype: "HTML",
					options: `<p>${__(
						"This moves the enrollment to <b>Level {0}</b> and records you as the approver.",
						[to_level]
					)}</p>`,
				},
				{
					fieldtype: "Small Text",
					fieldname: "remarks",
					label: __("Remarks"),
					reqd: 1,
				},
			],
			primary_action_label: __("Promote"),
			primary_action: (values) => {
				frappe.call({
					method:
						"sibbcs.academic.doctype.level_promotion.level_promotion.promote",
					args: {
						program_enrollment: enrollment,
						to_level: to_level,
						remarks: values.remarks,
					},
					freeze: true,
					freeze_message: __("Promoting…"),
					callback: ({ message }) => {
						dialog.hide();
						frappe.show_alert({
							message: __("Promoted. {0}", [message || ""]),
							indicator: "green",
						});
						this.refresh();
					},
				});
			},
		});

		dialog.show();
	}
}
