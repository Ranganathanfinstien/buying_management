// Universal Buying - Landed Cost Voucher: fetch receipts by Bill of Entry number.

frappe.ui.form.on("Landed Cost Voucher", {
	ub_boe_no(frm) {
		if (frm.doc.docstatus !== 0) return;
		frm.clear_table("purchase_receipts");
		frm.clear_table("items");
		frm.refresh_fields(["purchase_receipts", "items"]);
	},

	ub_fetch_receipts(frm) {
		if (frm.doc.docstatus !== 0) return;
		if (!frm.doc.company || !frm.doc.ub_boe_no) {
			frappe.msgprint(__("Set Company and Bill of Entry No first."));
			return;
		}
		frappe.call({
			method: "universal_buying.ub_inward.api.get_receipts_by_boe",
			args: { company: frm.doc.company, boe_no: frm.doc.ub_boe_no },
			freeze: true,
			callback(r) {
				const rows = r.message || [];
				frm.clear_table("purchase_receipts");
				frm.clear_table("items");
				rows.forEach((d) => {
					const row = frm.add_child("purchase_receipts");
					row.receipt_document_type = "Purchase Receipt";
					row.receipt_document = d.name;
					row.supplier = d.supplier;
					row.grand_total = d.grand_total;
					row.posting_date = d.posting_date;
				});
				frm.refresh_fields(["purchase_receipts", "items"]);
				if (!rows.length) {
					frappe.msgprint(__("No submitted Purchase Receipt found for Bill of Entry {0}.", [frm.doc.ub_boe_no]));
					return;
				}
				frm.call({
					doc: frm.doc,
					method: "get_items_from_purchase_receipts",
					callback() {
						frm.refresh_field("items");
						frm.dirty();
					},
				});
			},
		});
	},
});
