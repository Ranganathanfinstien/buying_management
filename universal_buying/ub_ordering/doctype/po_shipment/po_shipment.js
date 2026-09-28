// Copyright (c) 2026, Finstein and contributors

frappe.ui.form.on("PO Shipment", {
	setup(frm) {
		frm.set_query("purchase_order", () => ({ filters: { docstatus: 1 } }));
	},
	purchase_order(frm) {
		if (!frm.doc.purchase_order) return;
		frappe.call({
			method: "universal_buying.ub_ordering.doctype.po_shipment.po_shipment.get_lines",
			args: { purchase_order: frm.doc.purchase_order, shipment: frm.is_new() ? null : frm.doc.name },
			callback(r) {
				frm.clear_table("items");
				(r.message || []).forEach((l) => {
					if (l.remaining_qty > 0) {
						frm.add_child("items", Object.assign({}, l, { shipped_qty: l.remaining_qty }));
					}
				});
				frm.refresh_field("items");
			},
		});
	},
});
