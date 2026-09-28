// Copyright (c) 2026, Finstein and contributors

const UB_INC = "universal_buying.ub_inward.doctype.item_non_conformance.item_non_conformance";

frappe.ui.form.on("Item Non Conformance", {
	setup(frm) {
		frm.set_query("reference_name", () => ({ filters: { company: frm.doc.company, is_return: 0 } }));
		frm.set_query("target_warehouse", () => ({ filters: { company: frm.doc.company, is_group: 0 } }));
		frm.set_query("rejected_warehouse", () => ({ filters: { company: frm.doc.company, is_group: 0 } }));
		frm.set_query("batch_no", () => ({ filters: { item: frm.doc.item_code } }));
	},

	refresh(frm) {
		if (frm.doc.docstatus !== 1 || !frm.doc.disposition) return;
		if (frm.doc.disposition === "Return to Supplier") {
			if (!frm.doc.purchase_return) {
				frm.add_custom_button(__("Purchase Return"), () => ub_inc_make(frm, "make_purchase_return", "Purchase Receipt"), __("Create"));
			}
		} else if (!frm.doc.stock_entry) {
			frm.add_custom_button(__("Stock Entry"), () => ub_inc_make(frm, "make_stock_entry", "Stock Entry"), __("Create"));
		}
	},
});

function ub_inc_make(frm, method, doctype) {
	frappe.call({
		method: `${UB_INC}.${method}`,
		args: { name: frm.doc.name },
		freeze: true,
		callback(r) {
			if (r.message) {
				frm.reload_doc();
				frappe.set_route("Form", doctype, r.message);
			}
		},
	});
}
