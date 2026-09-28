// Copyright (c) 2026, Finstein and contributors

const UB_SEVERITY_RANK = {
	"Loss of Company Reputation": 5,
	"Customer dissatisfaction": 4,
	"Time and cost Overrunning of the Project": 3,
	"Marginal effect on the project": 2,
	"No effect on the project": 1,
};
const UB_OCCURRENCE_RANK = {
	"Very high chance of occurance": 5,
	"High chance of occurance": 4,
	"Medium chance of occurance": 3,
	"Low chance of occurance": 2,
	"Very low chance of occurance": 1,
};
const UB_PREVENTION_RANK = {
	"No control available": 5,
	"Guide lines not available for design": 4,
	"Minor changes in proven design": 3,
	"Control available but not followed": 2,
	"Already proven parameters used in the project": 1,
};

frappe.ui.form.on("Supplier Onboarding", {
	setup(frm) {
		frm.set_query("supplier_group", () => ({ filters: { is_group: 0 } }));
	},

	refresh(frm) {
		render_risk_legend(frm);
		lock_question_grids(frm);
		set_ranking_options(frm);

		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			if (frm.doc.status !== "Rejected") {
				frm.add_custom_button(__("Send Onboarding Link"), () => {
					frm.call("send_onboarding_link").then(() => frm.reload_doc());
				}, __("Actions"));
				frm.add_custom_button(__("Reject"), () => {
					frappe.prompt(
						{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason") },
						(v) => frm.call("reject", { reason: v.reason }).then(() => frm.reload_doc()),
						__("Reject Onboarding")
					);
				}, __("Actions"));
			}
			if (frm.doc.questionnaire_enabled) {
				frm.add_custom_button(__("Reload Questions"), () => {
					frappe.confirm(__("Replace all questionnaire answers with fresh questions from the Question Bank?"), () =>
						frm.call("reload_questions").then(() => frm.reload_doc())
					);
				}, __("Actions"));
			}
			if (frm.doc.audit_required) {
				if (frm.doc.supplier_audit_type) {
					frm.add_custom_button(__("Load Self Assessment"), () => {
						frm.call("load_self_assessment").then(() => frm.reload_doc());
					}, __("Audit"));
				}
				if (!frm.doc.supplier_audit_log) {
					frm.add_custom_button(__("Create Audit Log"), () => {
						frm.call("create_audit_log").then((r) => {
							if (r.message) frappe.set_route("Form", "Supplier Audit Log", r.message);
						});
					}, __("Audit"));
				}
			}
		}
		if (frm.doc.supplier_audit_log) {
			frm.add_custom_button(__("Supplier Audit Log"), () => {
				frappe.set_route("Form", "Supplier Audit Log", frm.doc.supplier_audit_log);
			}, __("View"));
		}
		if (frm.doc.supplier) {
			frm.add_custom_button(__("Supplier"), () => frappe.set_route("Form", "Supplier", frm.doc.supplier), __("View"));
		}

		if (frm.doc.status === "Pending Approval" && frm.doc.docstatus === 0) {
			frm.dashboard.set_headline(__("Submitted by the supplier. Review the details and submit to create the Supplier."), "orange");
		}
	},

	pan(frm) {
		const pan = (frm.doc.pan || "").trim().toUpperCase();
		if (pan !== (frm.doc.pan || "")) return frm.set_value("pan", pan);
		if (pan && !/^[A-Z]{5}[0-9]{4}[A-Z]$/.test(pan)) {
			frappe.show_alert({ message: __("PAN format is AAAAA9999A"), indicator: "red" });
		}
	},

	gstin(frm) {
		const gstin = (frm.doc.gstin || "").trim().toUpperCase();
		if (gstin !== (frm.doc.gstin || "")) return frm.set_value("gstin", gstin);
		if (gstin && gstin.length !== 15) {
			frappe.show_alert({ message: __("GSTIN must be 15 characters"), indicator: "red" });
		} else if (gstin && frm.doc.pan && gstin.substring(2, 12) !== frm.doc.pan) {
			frappe.show_alert({ message: __("GSTIN does not match PAN"), indicator: "red" });
		} else if (gstin && !frm.doc.pan) {
			frm.set_value("pan", gstin.substring(2, 12));
		}
	},

	ifsc_code(frm) {
		const v = (frm.doc.ifsc_code || "").trim().toUpperCase();
		if (v !== (frm.doc.ifsc_code || "")) frm.set_value("ifsc_code", v);
	},
});

frappe.ui.form.on("Supplier Risk Analysis", {
	severity_ranking: update_rpn,
	probability_of_occurance: update_rpn,
	prevention_control_if_any: update_rpn,
});

frappe.ui.form.on("Supplier Evaluation Ranking", {
	form_render(frm, cdt, cdn) {
		set_row_ranking_options(frm, locals[cdt][cdn]);
	},
	ranking_select(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		let rating = 0;
		for (let i = 5; i >= 1; i--) {
			if (row["option_" + i] && row["option_" + i] === row.ranking_select) {
				rating = i;
				break;
			}
		}
		frappe.model.set_value(cdt, cdn, "rating", rating);
		let total = 0;
		(frm.doc.evaluation_ranking || []).forEach((r) => (total += r.rating || 0));
		frm.set_value("evaluation_score", total);
	},
});

function update_rpn(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const s = UB_SEVERITY_RANK[row.severity_ranking] || 0;
	const o = UB_OCCURRENCE_RANK[row.probability_of_occurance] || 0;
	const p = UB_PREVENTION_RANK[row.prevention_control_if_any] || 0;
	frappe.model.set_value(cdt, cdn, {
		severity_value: s,
		occurrence_value: o,
		prevention_value: p,
		risk_priority_no: s && o && p ? s * o * p : 0,
	});
}

function lock_question_grids(frm) {
	["risk_analysis", "evaluation", "evaluation_ranking", "audit_self_assessment"].forEach((f) => {
		const field = frm.get_field(f);
		if (!field || !field.grid) return;
		field.grid.cannot_add_rows = true;
		field.grid.wrapper.find(".grid-add-row, .grid-remove-rows, .grid-remove-all-rows").hide();
	});
}

function set_row_ranking_options(frm, row) {
	const opts = [row.option_5, row.option_4, row.option_3, row.option_2, row.option_1].filter((o) => o);
	const grid_row = frm.fields_dict.evaluation_ranking.grid.get_grid_row(row.name);
	if (!grid_row) return;
	const update = (field) => {
		if (field && field.df) {
			field.df.options = [""].concat(opts).join("\n");
			field.refresh && field.refresh();
		}
	};
	update(grid_row.get_field("ranking_select"));
	if (grid_row.on_grid_fields_dict) update(grid_row.on_grid_fields_dict.ranking_select);
}

function set_ranking_options(frm) {
	const field = frm.get_field("evaluation_ranking");
	if (!field || !field.grid || field.grid.__ub_bound) return;
	field.grid.__ub_bound = true;
	// in-grid editing: set the per-row options just before the select opens
	field.grid.wrapper.on("mousedown focusin", ".grid-row", function () {
		const name = $(this).attr("data-name");
		const row = name && locals["Supplier Evaluation Ranking"] && locals["Supplier Evaluation Ranking"][name];
		if (row) set_row_ranking_options(frm, row);
	});
}

function render_risk_legend(frm) {
	const field = frm.get_field("risk_legend");
	if (!field) return;
	const table = (title, map) =>
		`<table class="table table-bordered table-sm" style="margin-bottom:8px">
			<tr><th>${__(title)}</th><th style="width:70px;text-align:center">${__("Rank")}</th></tr>
			${Object.keys(map).map((k) => `<tr><td>${__(k)}</td><td style="text-align:center">${map[k]}</td></tr>`).join("")}
		</table>`;
	field.$wrapper.html(
		`<div class="row">
			<div class="col-md-4">${table("Severity of Risk", UB_SEVERITY_RANK)}</div>
			<div class="col-md-4">${table("Occurrence of Risk", UB_OCCURRENCE_RANK)}</div>
			<div class="col-md-4">${table("Prevention of Risk", UB_PREVENTION_RANK)}</div>
		</div>
		<p class="text-muted small">${__("Risk Priority Number (RPN) = Severity x Occurrence x Prevention. Mitigation details are required when RPN reaches the threshold in Buying Control Settings.")}</p>`
	);
}
