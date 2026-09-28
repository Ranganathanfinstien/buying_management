// Copyright (c) 2026, Finstein and contributors

frappe.ui.form.on("Gate Entry", {
	setup(frm) {
		frm.set_query("document_number", () => ({
			filters: { company: frm.doc.company, docstatus: 1 },
		}));
		frm.set_query("employee", () => ({ filters: { company: frm.doc.company, status: "Active" } }));
	},

	refresh(frm) {
		ub_gate_entry_labels(frm);
		if (frm.doc.docstatus === 1 && frm.doc.entry_type === "In" && frm.doc.party_type === "Supplier") {
			frm.add_custom_button(__("Purchase Receipt"), () => {
				frappe.new_doc("Purchase Receipt", {
					company: frm.doc.company,
					supplier: frm.doc.party,
					ub_gate_entry: frm.doc.name,
				});
			}, __("Create"));
		}
	},

	entry_type(frm) {
		ub_gate_entry_labels(frm);
		if (frm.doc.entry_type === "In") {
			frm.set_value("party_type", "Supplier");
			frm.set_value("document_type", "");
		}
	},

	party_type(frm) {
		frm.set_value("party", "");
	},

	document_type(frm) {
		frm.set_value("document_number", "");
	},

	document_number(frm) {
		if (!frm.doc.document_number) return;
		frappe.call({
			method: "universal_buying.ub_inward.doctype.gate_entry.gate_entry.get_document_party",
			args: { document_type: frm.doc.document_type, document_number: frm.doc.document_number },
			callback(r) {
				if (r.message && r.message.party) {
					frm.set_value("party_type", r.message.party_type);
					frm.set_value("party", r.message.party);
				}
			},
		});
	},
});

function ub_gate_entry_labels(frm) {
	const inward = frm.doc.entry_type !== "Out";
	frm.set_df_property("employee", "label", inward ? __("Received By (Employee)") : __("Handed Over By (Employee)"));
	frm.set_df_property("external_party", "label", inward ? __("Delivered By") : __("Handed Over To"));
}
