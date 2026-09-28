// Copyright (c) 2026, Finstein and contributors

frappe.ui.form.on("Auto PO Run", {
	setup(frm) {
		frm.set_query("project", () => ({ filters: { company: frm.doc.company } }));
		frm.set_query("item_code", "items_filter", () => ({ filters: { is_purchase_item: 1, disabled: 0 } }));
	},
	onload(frm) {
		if (frm.is_new() && !frm.doc.to_date) {
			frm.set_value("to_date", frappe.datetime.add_days(frappe.datetime.get_today(), 90));
		}
	},
	refresh(frm) {
		const colors = { "Not Started": "gray", Queued: "blue", "In Progress": "orange", Completed: "green", Failed: "red" };
		if (frm.doc.docstatus === 1 && frm.doc.status) {
			frm.page.set_indicator(__(frm.doc.status), colors[frm.doc.status] || "gray");
		}
		if (frm.doc.docstatus === 1 && ["Queued", "In Progress"].includes(frm.doc.status)) {
			frm.dashboard.set_headline_alert(__("Auto PO run in progress. This form updates when it finishes."), "blue");
		}
		if (frm.doc.purchase_orders) {
			frm.add_custom_button(__("Purchase Orders"), () => {
				frappe.set_route("List", "Purchase Order", {
					ub_origin_doctype: "Auto PO Run",
					ub_origin_name: frm.doc.name,
				});
			}, __("View"));
		}
		if (frm.doc.auto_po_exception) {
			frm.add_custom_button(__("Auto PO Exception"), () => {
				frappe.set_route("Form", "Auto PO Exception", frm.doc.auto_po_exception);
			}, __("View"));
		}
	},
});
