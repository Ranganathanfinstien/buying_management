// UB Planning - Item Manufacturer: Sourcing creates MPN rows, Purchase may only disable them.
frappe.ui.form.on("Item Manufacturer", {
	refresh(frm) {
		if (frm.doc.ub_disabled) {
			frm.dashboard.set_headline_alert(
				__("This manufacturer / MPN is disabled and blocked on Purchase Orders."),
				"red"
			);
		}
	},
	ub_disabled(frm) {
		if (frm.doc.ub_disabled && frm.doc.is_default) {
			frm.set_value("is_default", 0);
		}
	},
});
