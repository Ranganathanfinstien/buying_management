// Universal Buying - Quality Inspection (BRD v2 6.24)

frappe.ui.form.on("Quality Inspection", {
	setup(frm) {
		frm.set_query("ub_received_manufacturer", () => ({
			query: "universal_buying.ub_inward.api.approved_manufacturer_query",
			filters: { item_code: frm.doc.item_code },
		}));
	},

	refresh(frm) {
		if (frm.doc.reference_type === "Purchase Receipt" && frm.doc.inspection_type === "Incoming") {
			const taken = flt(frm.doc.ub_sample_taken);
			const size = flt(frm.doc.sample_size);
			if (frm.doc.docstatus === 0 && size) {
				frm.dashboard.set_headline(
					__("Sample size {0} (lot {1}). Sample taken: {2}.", [size, flt(frm.doc.ub_batch_qty), taken]),
					taken >= size ? "green" : "orange"
				);
			}
		}
		if (frm.doc.ub_item_non_conformance) {
			frm.add_custom_button(__("Item Non Conformance"), () =>
				frappe.set_route("Form", "Item Non Conformance", frm.doc.ub_item_non_conformance)
			);
		}
	},

	ub_received_manufacturer(frm) {
		if (!frm.doc.ub_received_manufacturer || frm.doc.ub_alternate_mpn || !frm.doc.item_code) return;
		frappe.call({
			method: "erpnext.stock.doctype.item_manufacturer.item_manufacturer.get_item_manufacturer_part_no",
			args: { item_code: frm.doc.item_code, manufacturer: frm.doc.ub_received_manufacturer },
			callback(r) {
				if (r.message) frm.set_value("ub_received_manufacturer_part_no", r.message);
			},
		});
	},

	ub_alternate_mpn(frm) {
		frm.set_df_property("ub_received_manufacturer", "only_select", frm.doc.ub_alternate_mpn ? 0 : 1);
	},
});
