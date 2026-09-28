// UB Planning - Material Request: create draft POs for consumable lines (origin "Material Request").
frappe.ui.form.on("Material Request", {
	refresh(frm) {
		if (
			frm.doc.docstatus === 1 &&
			frm.doc.material_request_type === "Purchase" &&
			!["Stopped", "Ordered", "Received"].includes(frm.doc.status) &&
			frappe.model.can_create("Purchase Order")
		) {
			frm.add_custom_button(
				__("Consumables Auto PO"),
				() => {
					frappe
						.xcall("universal_buying.ub_planning.jobs.create_consumables_po_for_mr", {
							material_request: frm.doc.name,
						})
						.then((names) => {
							if (names && names.length) {
								frappe.msgprint(
									__("Draft Purchase Orders created: {0}", [
										names.map((n) => frappe.utils.get_form_link("Purchase Order", n, true)).join(", "),
									])
								);
							} else {
								frappe.msgprint(
									__("No consumable lines with a supplier and a valid price are pending on this request.")
								);
							}
							frm.reload_doc();
						});
				},
				__("Create")
			);
		}
	},
});
