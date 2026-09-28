// Copyright (c) 2026, Finstein and contributors

const UB_APE = "universal_buying.ub_planning.doctype.auto_po_exception.auto_po_exception";

frappe.ui.form.on("Auto PO Exception", {
	setup(frm) {
		frm.set_query("project", () => ({ filters: { company: frm.doc.company } }));
	},
	refresh(frm) {
		if (frm.doc.docstatus === 0 && !frm.doc.auto_po_reference) {
			frm.add_custom_button(__("Get Exceptions"), () => {
				frm.call("get_exceptions").then(() => frm.refresh_field("items"));
			});
		}
		if (frm.doc.docstatus !== 1) return;

		const rows = frm.doc.items || [];
		if (rows.some((r) => r.exception_type === "No Price" && !r.item_price_request)) {
			frm.add_custom_button(__("Item Price Request"), () => create_price_requests(frm), __("Create"));
		}
		if (rows.some((r) => r.exception_type === "MOQ Exception" && !r.purchase_order && r.default_supplier)) {
			frm.add_custom_button(__("Purchase Order for MOQ Items"), () => create_moq_po(frm), __("Create"));
		}
		frm.fields_dict.items.grid.wrapper.find(".grid-remove-rows").hide();
	},
});

function create_price_requests(frm) {
	const rows = frm.doc.items.filter((r) => r.exception_type === "No Price" && !r.item_price_request);
	const dialog = new frappe.ui.Dialog({
		title: __("Create Item Price Requests"),
		size: "extra-large",
		fields: [
			{
				fieldname: "rows",
				fieldtype: "Table",
				label: __("No Price rows"),
				cannot_add_rows: true,
				in_place_edit: true,
				data: rows.map((r) => ({
					row_name: r.name,
					item_code: r.item_code,
					supplier: r.default_supplier,
					moq: r.moq,
					spq: r.spq,
					lead_time_days: 0,
					valid_from: frappe.datetime.get_today(),
					valid_upto: frappe.datetime.add_months(frappe.datetime.get_today(), 12),
				})),
				fields: [
					{ fieldname: "row_name", fieldtype: "Data", hidden: 1 },
					{ fieldname: "item_code", fieldtype: "Link", options: "Item", label: __("Item"), read_only: 1, in_list_view: 1, columns: 2 },
					{ fieldname: "supplier", fieldtype: "Link", options: "Supplier", label: __("Supplier"), reqd: 1, in_list_view: 1, columns: 2 },
					{ fieldname: "price_list", fieldtype: "Link", options: "Price List", label: __("Price List"), reqd: 1, in_list_view: 1, columns: 1,
						get_query: () => ({ filters: { buying: 1, enabled: 1 } }) },
					{ fieldname: "rate", fieldtype: "Float", label: __("Rate"), reqd: 1, in_list_view: 1, columns: 1 },
					{ fieldname: "item_manufacturer", fieldtype: "Link", options: "Item Manufacturer", label: __("MPN"), in_list_view: 1, columns: 1 },
					{ fieldname: "lead_time_days", fieldtype: "Int", label: __("Lead Time"), reqd: 1, in_list_view: 1, columns: 1 },
					{ fieldname: "valid_from", fieldtype: "Date", label: __("Valid From"), reqd: 1, in_list_view: 1, columns: 1 },
					{ fieldname: "valid_upto", fieldtype: "Date", label: __("Valid Upto"), reqd: 1, in_list_view: 1, columns: 1 },
					{ fieldname: "moq", fieldtype: "Float", label: __("MOQ") },
					{ fieldname: "spq", fieldtype: "Float", label: __("SPQ") },
				],
			},
		],
		primary_action_label: __("Create"),
		primary_action(values) {
			const data = (values.rows || []).filter((r) => r.supplier && r.rate && r.price_list);
			if (!data.length) {
				frappe.msgprint(__("Enter supplier, price list and rate for at least one row."));
				return;
			}
			frappe.xcall(`${UB_APE}.create_item_price_requests`, { docname: frm.doc.name, rows: data }).then((created) => {
				dialog.hide();
				frappe.msgprint(
					__("Item Price Requests: {0}", [
						(created || []).map((c) => frappe.utils.get_form_link("Item Price Request", c.item_price_request, true)).join(", ") ||
							__("none"),
					])
				);
				frm.reload_doc();
			});
		},
	});
	dialog.show();
}

function create_moq_po(frm) {
	const rows = frm.doc.items.filter((r) => r.exception_type === "MOQ Exception" && !r.purchase_order && r.default_supplier);
	const selected = frm.fields_dict.items.grid.get_selected_children().filter((r) => rows.includes(r));
	const names = (selected.length ? selected : rows).map((r) => r.name);
	frappe.confirm(
		__("Create draft Purchase Orders at MOQ for {0} MOQ row(s)? Rows beyond the MOQ tolerance are refused.", [names.length]),
		() => {
			frappe.xcall(`${UB_APE}.make_purchase_order`, { docname: frm.doc.name, row_names: names }).then((r) => {
				let html = "";
				if (r.purchase_orders.length) {
					html += `<p>${__("Draft Purchase Orders created")}:</p><ul>` +
						r.purchase_orders.map((po) => `<li>${frappe.utils.get_form_link("Purchase Order", po.name, true)} - ${frappe.utils.escape_html(po.supplier)}</li>`).join("") +
						"</ul>";
				}
				if (r.refused.length) {
					html += `<p>${__("Refused (tolerance {0}%)", [r.tolerance])}:</p><ul>` +
						r.refused.map((x) => `<li>${frappe.utils.escape_html(x.item_code)}: ${x.reason ? frappe.utils.escape_html(x.reason) : __("{0}% below MOQ", [x.tolerance_percent])} (${__("shortage")} ${x.shortage}, MOQ ${x.moq})</li>`).join("") +
						"</ul>";
				}
				frappe.msgprint(html || __("Nothing to create."), __("Purchase Order for MOQ Items"));
				frm.reload_doc();
			});
		}
	);
}
