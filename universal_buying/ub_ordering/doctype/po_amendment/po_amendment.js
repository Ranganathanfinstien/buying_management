// Copyright (c) 2026, Finstein and contributors

frappe.ui.form.on("PO Amendment", {
	setup(frm) {
		frm.set_query("purchase_order", () => ({
			filters: { docstatus: 1, status: ["not in", ["Closed", "Completed"]] },
		}));
	},
	purchase_order(frm) {
		if (!frm.doc.purchase_order || frm.doc.docstatus !== 0) return;
		frm.trigger("load_po_lines");
	},
	load_po_lines(frm) {
		frappe.call({
			method: "universal_buying.ub_ordering.doctype.po_amendment.po_amendment.get_po_lines",
			args: { purchase_order: frm.doc.purchase_order },
			callback(r) {
				frm.clear_table("items");
				(r.message || []).forEach((l) => {
					frm.add_child("items", Object.assign({}, l, {
						revised_qty: l.original_qty,
						revised_rate: l.original_rate,
						revised_schedule_date: l.original_schedule_date,
						revised_amount: l.original_amount,
					}));
				});
				frm.refresh_field("items");
			},
		});
	},
	refresh(frm) {
		if (frm.doc.docstatus === 0 && frm.doc.purchase_order) {
			frm.add_custom_button(__("Reload PO Lines"), () => frm.trigger("load_po_lines"));
		}
	},
});

frappe.ui.form.on("PO Amendment Item", {
	revised_qty(frm, cdt, cdn) {
		const r = locals[cdt][cdn];
		frappe.model.set_value(cdt, cdn, "revised_amount", flt(r.revised_qty) * flt(r.revised_rate));
	},
	revised_rate(frm, cdt, cdn) {
		const r = locals[cdt][cdn];
		frappe.model.set_value(cdt, cdn, "revised_amount", flt(r.revised_qty) * flt(r.revised_rate));
	},
});
