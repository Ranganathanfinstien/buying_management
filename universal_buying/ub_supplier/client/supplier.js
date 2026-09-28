// UB Supplier: Supplier form (BRD 6.5). Everything is scoped inside functions so this
// script can share the form bundle with other apps' Supplier scripts.

frappe.ui.form.on("Supplier", {
	refresh(frm) {
		if (frm.is_new()) return;
		ub_supplier_bank_headline(frm);

		frm.add_custom_button(__("Line Card"), () => {
			frappe.route_options = { supplier: frm.doc.name };
			frappe.set_route("List", "Supplier Line Card");
		}, __("View"));
		frm.add_custom_button(__("Profile Change Requests"), () => {
			frappe.route_options = { supplier: frm.doc.name };
			frappe.set_route("List", "Supplier Profile Change Request");
		}, __("View"));
		if (frm.doc.ub_onboarding) {
			frm.add_custom_button(__("Supplier Onboarding"), () => {
				frappe.set_route("Form", "Supplier Onboarding", frm.doc.ub_onboarding);
			}, __("View"));
		}
		frm.add_custom_button(__("Supplier Audit Log"), () => {
			frappe.new_doc("Supplier Audit Log", {
				supplier: frm.doc.name,
				audit_type: "Supplier Requalification",
			});
		}, __("Create"));
	},

	ub_bank_ifsc(frm) {
		const v = (frm.doc.ub_bank_ifsc || "").trim().toUpperCase();
		if (v !== (frm.doc.ub_bank_ifsc || "")) frm.set_value("ub_bank_ifsc", v);
	},

	ub_pan(frm) {
		const v = (frm.doc.ub_pan || "").trim().toUpperCase();
		if (v !== (frm.doc.ub_pan || "")) frm.set_value("ub_pan", v);
	},
});

function ub_supplier_bank_headline(frm) {
	frappe.db
		.get_list("Bank Account", {
			filters: { party_type: "Supplier", party: frm.doc.name, disabled: 0 },
			limit: 1,
		})
		.then((rows) => {
			if ((rows || []).length) return;
			const msg = frm.doc.workflow_state === "Draft"
				? __("Add a Bank Account (Buying tab > Bank Details, or Create > Bank Account) before sending this supplier for approval.")
				: __("This supplier has no active Bank Account.");
			frm.dashboard.set_headline(msg, "red");
		});
}
