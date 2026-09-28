// Copyright (c) 2026, Finstein and contributors

frappe.ui.form.on("Supplier Audit Log", {
	setup(frm) {
		frm.set_query("supplier_audit_checklist", () => {
			const filters = { is_active: 1 };
			return { filters: filters };
		});
	},

	refresh(frm) {
		const grid = frm.get_field("audit_rows").grid;
		grid.cannot_add_rows = true;
		grid.wrapper.find(".grid-add-row, .grid-remove-rows, .grid-remove-all-rows").hide();

		if (frm.doc.docstatus === 0 && frm.doc.supplier_audit_checklist) {
			frm.add_custom_button(__("Get Questions"), () => {
				const go = () => frm.call("get_questions").then(() => frm.refresh_fields());
				if ((frm.doc.audit_rows || []).length) {
					frappe.confirm(__("Replace the current questions and ratings?"), go);
				} else {
					go();
				}
			});
		}
		if (frm.doc.supplier_onboarding) {
			frm.add_custom_button(__("Supplier Onboarding"), () => {
				frappe.set_route("Form", "Supplier Onboarding", frm.doc.supplier_onboarding);
			}, __("View"));
		}
	},

	supplier_audit_type(frm) {
		if (frm.doc.docstatus === 0 && !frm.is_new()) frm.save();
	},
});

frappe.ui.form.on("Supplier Audit Log Detail", {
	form_render(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		let opts = [];
		try {
			opts = JSON.parse(row.option_list || "[]");
		} catch (e) {
			opts = [];
		}
		const grid_row = frm.fields_dict[row.parentfield].grid.get_grid_row(row.name);
		const field = grid_row && grid_row.get_field("answer");
		if (field && opts.length) {
			field.df.description = opts.map((o, i) => `<b>${i}</b>: ${frappe.utils.escape_html(o)}`).join("<br>");
			field.refresh();
		}
	},
	company_rating(frm, cdt, cdn) {
		clamp(cdt, cdn, "company_rating");
	},
	supplier_self_rating(frm, cdt, cdn) {
		clamp(cdt, cdn, "supplier_self_rating");
	},
});

function clamp(cdt, cdn, field) {
	const row = locals[cdt][cdn];
	if (row.max_score && row[field] > row.max_score) {
		frappe.model.set_value(cdt, cdn, field, row.max_score);
	} else if (row[field] < 0) {
		frappe.model.set_value(cdt, cdn, field, 0);
	}
}
