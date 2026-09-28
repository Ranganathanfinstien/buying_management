// Copyright (c) 2026, Finstein and contributors

frappe.ui.form.on("Prospective Supplier", {
	refresh(frm) {
		if (frm.is_new()) return;

		if (frm.doc.linked_supplier) {
			frm.add_custom_button(__("Supplier"), () => {
				frappe.set_route("Form", "Supplier", frm.doc.linked_supplier);
			}, __("View"));
		}
		if (frm.doc.supplier_onboarding) {
			frm.add_custom_button(__("Supplier Onboarding"), () => {
				frappe.set_route("Form", "Supplier Onboarding", frm.doc.supplier_onboarding);
			}, __("View"));
		}

		if (frm.doc.status !== "Onboarded") {
			frm.add_custom_button(__("Create Onboarding"), () => create_onboarding(frm, 0), __("Create"));
			frm.add_custom_button(__("Send Onboarding Link"), () => create_onboarding(frm, 1), __("Create"));
		}
	},

	pan(frm) {
		const pan = (frm.doc.pan || "").trim().toUpperCase();
		if (pan !== (frm.doc.pan || "")) {
			frm.set_value("pan", pan);
			return;
		}
		if (pan && !/^[A-Z]{5}[0-9]{4}[A-Z]$/.test(pan)) {
			frappe.show_alert({ message: __("PAN format is AAAAA9999A"), indicator: "red" });
		}
	},

	gstin(frm) {
		const gstin = (frm.doc.gstin || "").trim().toUpperCase();
		if (gstin !== (frm.doc.gstin || "")) {
			frm.set_value("gstin", gstin);
			return;
		}
		if (gstin && gstin.length !== 15) {
			frappe.show_alert({ message: __("GSTIN must be 15 characters"), indicator: "red" });
		} else if (gstin && frm.doc.pan && gstin.substring(2, 12) !== frm.doc.pan) {
			frappe.show_alert({ message: __("GSTIN does not match PAN"), indicator: "red" });
		} else if (gstin && !frm.doc.pan) {
			frm.set_value("pan", gstin.substring(2, 12));
		}
	},
});

function create_onboarding(frm, send_email) {
	frm.call("create_onboarding", { send_email: send_email }).then((r) => {
		if (!r.message) return;
		if (send_email) {
			frappe.show_alert({ message: __("Onboarding link sent to {0}", [frm.doc.email]), indicator: "green" });
		}
		frappe.set_route("Form", "Supplier Onboarding", r.message);
	});
}
