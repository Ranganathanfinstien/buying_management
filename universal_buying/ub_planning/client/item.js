// UB Planning - Item form: approved source summary and shortcut to an Item Price Request.
frappe.ui.form.on("Item", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (frm.doc.is_purchase_item) {
			frm.add_custom_button(
				__("Item Price Request"),
				() => frappe.model.with_doctype("Item Price Request", () => {
					const ipr = frappe.model.get_new_doc("Item Price Request");
					ipr.type = "Buying";
					const row = frappe.model.add_child(ipr, "item_price_details");
					row.item_code = frm.doc.name;
					row.item_name = frm.doc.item_name;
					row.uom = frm.doc.purchase_uom || frm.doc.stock_uom;
					row.moq = frm.doc.min_order_qty;
					row.spq = frm.doc.ub_standard_packing_qty;
					frappe.set_route("Form", "Item Price Request", ipr.name);
				}),
				__("Create")
			);
			show_current_price(frm);
		}
	},
	is_purchase_item(frm) {
		warn_customer_provided(frm);
	},
	is_customer_provided_item(frm) {
		warn_customer_provided(frm);
	},
});

function warn_customer_provided(frm) {
	if (frm.doc.is_purchase_item && frm.doc.is_customer_provided_item) {
		frappe.msgprint(__("An item cannot be both a Purchase Item and a Customer Provided Item."));
	}
}

function show_current_price(frm) {
	const company = frappe.defaults.get_user_default("Company");
	if (!company) return;
	frappe
		.xcall("universal_buying.ub_planning.api.get_current_item_price", {
			item_code: frm.doc.name,
			company: company,
		})
		.then((price) => {
			if (!price) {
				frm.dashboard.set_headline_alert(
					__("No valid buying price for {0}. Auto PO will list this item as an exception.", [company]),
					"orange"
				);
				return;
			}
			frm.dashboard.set_headline_alert(
				__("Approved source ({0}): {1} @ {2} {3}{4}", [
					company,
					price.supplier || "-",
					format_currency(price.price_list_rate, price.currency),
					price.manufacturer_part_no ? __(", MPN {0}", [price.manufacturer_part_no]) : "",
					price.valid_upto ? __(", valid upto {0}", [frappe.datetime.str_to_user(price.valid_upto)]) : "",
				]),
				"blue"
			);
		});
}
