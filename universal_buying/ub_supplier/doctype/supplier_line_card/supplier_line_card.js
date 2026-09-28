// Copyright (c) 2026, Finstein and contributors

frappe.ui.form.on("Supplier Line Card", {
	setup(frm) {
		frm.set_query("supplier", () => ({ filters: { disabled: 0 } }));
	},
});

frappe.ui.form.on("Supplier Line Card Item", {
	manufacturer_part_no(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.manufacturer_part_no || row.manufacturer) return;
		// suggest the manufacturer from Item Manufacturer when the MPN is known
		frappe.db
			.get_value("Item Manufacturer", { manufacturer_part_no: row.manufacturer_part_no.trim() }, "manufacturer")
			.then((r) => {
				if (r.message && r.message.manufacturer) {
					frappe.model.set_value(cdt, cdn, "manufacturer", r.message.manufacturer);
				}
			});
	},
});
