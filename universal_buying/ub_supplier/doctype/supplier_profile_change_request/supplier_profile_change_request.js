// Copyright (c) 2026, Finstein and contributors

frappe.ui.form.on("Supplier Profile Change Request", {
	refresh(frm) {
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.dashboard.set_headline_alert(__("Awaiting approval. Submit to apply these changes to the Supplier."), "yellow");
		} else if (frm.doc.docstatus === 1) {
			frm.dashboard.set_headline_alert(__("Approved. The changes have been applied to the Supplier."), "green");
		} else if (frm.doc.docstatus === 2) {
			frm.dashboard.set_headline_alert(__("Rejected. No changes were applied."), "red");
		}
		if (frm.doc.supplier && !frm.is_new()) {
			frm.add_custom_button(__("Supplier"), () => frappe.set_route("Form", "Supplier", frm.doc.supplier), __("View"));
		}
		render_changes_summary(frm);
	},
});

function render_changes_summary(frm) {
	const field = frm.get_field("changes_summary_html");
	if (!field) return;
	if (frm.is_new() || !frm.doc.supplier) {
		field.$wrapper.html(`<div class="text-muted">${__("Save the request to see the Current to Requested comparison.")}</div>`);
		return;
	}
	frm.call("get_changes_summary").then((r) => {
		const res = (r && r.message) || {};
		field.$wrapper.html(res.html || "");
		const s = res.sections || {};
		if (frm.doc.docstatus !== 0) return;
		frm.toggle_display(["section_break_contacts", "contacts"], !!s.contacts || (frm.doc.contacts || []).length > 0);
		frm.toggle_display(["section_break_addresses", "addresses"], !!s.addresses || (frm.doc.addresses || []).length > 0);
		frm.toggle_display(["section_break_bank", "bank_accounts"], !!s.bank || (frm.doc.bank_accounts || []).length > 0);
	});
}
