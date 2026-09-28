// UB Planning - Item Price: MPN must belong to the item and must not be disabled.
frappe.ui.form.on("Item Price", {
	setup(frm) {
		frm.set_query("ub_item_manufacturer", () => ({
			filters: { item_code: frm.doc.item_code, ub_disabled: 0 },
		}));
	},
	item_code(frm) {
		if (frm.doc.ub_item_manufacturer) frm.set_value("ub_item_manufacturer", null);
	},
});
