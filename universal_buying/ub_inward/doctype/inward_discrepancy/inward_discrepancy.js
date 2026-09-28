// Copyright (c) 2026, Finstein and contributors

frappe.ui.form.on("Inward Discrepancy", {
	setup(frm) {
		frm.set_query("purchase_receipt", () => ({
			filters: { company: frm.doc.company, supplier: frm.doc.supplier, docstatus: 0, is_return: 0 },
		}));
		frm.set_query("project", () => ({ filters: { company: frm.doc.company } }));
	},

	refresh(frm) {
		if (frm.doc.purchase_receipt) {
			frm.add_custom_button(__("Purchase Receipt"), () =>
				frappe.set_route("Form", "Purchase Receipt", frm.doc.purchase_receipt)
			);
		}
	},
});
