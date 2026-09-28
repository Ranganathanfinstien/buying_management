// Copyright (c) 2026, Finstein and contributors

frappe.ui.form.on("Payment Indent", {
	setup(frm) {
		frm.set_query("purchase_order", "purchase_orders", () => ({
			filters: {
				supplier: frm.doc.supplier,
				company: frm.doc.company,
				docstatus: 1,
				status: ["not in", ["Closed", "On Hold", "Completed"]],
			},
		}));
	},

	refresh(frm) {
		frm.set_df_property("supplier", "read_only", (frm.doc.purchase_orders || []).length ? 1 : 0);
		if (frm.doc.docstatus === 1) {
			(frm.doc.purchase_orders || []).forEach((d) => {
				if (d.payment_request) {
					frm.add_custom_button(d.payment_request, () => frappe.set_route("Form", "Payment Request", d.payment_request), __("Payment Requests"));
				}
			});
		}
	},

	supplier(frm) {
		frm.clear_table("purchase_orders");
		frm.clear_table("items");
		frm.refresh_fields();
	},

	get_items(frm) {
		if (!(frm.doc.purchase_orders || []).length) {
			frappe.msgprint(__("Add Purchase Orders first."));
			return;
		}
		frm.call({
			doc: frm.doc,
			method: "get_po_items",
			freeze: true,
			callback(r) {
				frm.clear_table("items");
				(r.message || []).forEach((d) => frm.add_child("items", d));
				ub_indent_totals(frm);
				frm.refresh_fields();
			},
		});
	},

	requested_amount(frm) {
		ub_indent_totals(frm);
	},
});

frappe.ui.form.on("Payment Indent PO", {
	purchase_orders_remove(frm) {
		const pos = (frm.doc.purchase_orders || []).map((d) => d.purchase_order);
		frm.doc.items = (frm.doc.items || []).filter((d) => pos.includes(d.purchase_order));
		ub_indent_totals(frm);
		frm.refresh_fields();
	},
});

frappe.ui.form.on("Payment Indent Item", {
	indent_qty(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (flt(row.indent_qty) > flt(row.qty)) {
			frappe.msgprint(__("Row {0}: Indent Qty cannot be more than the PO line qty {1}", [row.idx, row.qty]));
			row.indent_qty = row.qty;
		}
		frappe.model.set_value(cdt, cdn, "value", flt(row.indent_qty) * flt(row.rate));
		ub_indent_totals(frm);
	},
	items_remove(frm) {
		ub_indent_totals(frm);
	},
});

function ub_indent_totals(frm) {
	const total = (frm.doc.items || []).reduce((s, d) => s + flt(d.value), 0);
	frm.set_value("total_value", total);
}
