// Copyright (c) 2026, Finstein and contributors

const UB_IPR = "universal_buying.ub_planning.doctype.item_price_request.item_price_request";

frappe.ui.form.on("Item Price Request", {
	setup(frm) {
		frm.get_docfield("item_price_details").allow_bulk_edit = 1;
		frm.set_query("item_manufacturer", "item_price_details", (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			return { filters: { item_code: row.item_code, ub_disabled: 0 } };
		});
		frm.set_query("price_list", "item_price_details", () => ({
			filters: frm.doc.type === "Selling" ? { selling: 1, enabled: 1 } : { buying: 1, enabled: 1 },
		}));
		frm.set_query("uom", "item_price_details", (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			return {
				query: "erpnext.controllers.queries.get_item_uom_query",
				filters: { item_code: row.item_code },
			};
		});
	},
	refresh(frm) {
		toggle_party_columns(frm);
	},
	type(frm) {
		toggle_party_columns(frm);
	},
});

frappe.ui.form.on("Item Price Request Detail", {
	item_code(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.item_code) return;
		if (frm.doc.type === "Buying") {
			const dup = (frm.doc.item_price_details || []).find((r) => r.item_code === row.item_code && r.name !== row.name);
			if (dup) {
				frappe.msgprint(__("Item {0} is already in row {1}.", [row.item_code, dup.idx]));
				frappe.model.set_value(cdt, cdn, "item_code", "");
				return;
			}
		}
		frappe.db.get_value("Item", row.item_code, ["purchase_uom", "stock_uom", "sales_uom", "min_order_qty", "ub_standard_packing_qty", "lead_time_days"]).then(({ message: it }) => {
			if (!it) return;
			const uom = frm.doc.type === "Selling" ? it.sales_uom || it.stock_uom : it.purchase_uom || it.stock_uom;
			if (!row.uom) frappe.model.set_value(cdt, cdn, "uom", uom);
			if (frm.doc.type === "Buying") {
				if (!row.moq && it.min_order_qty) frappe.model.set_value(cdt, cdn, "moq", it.min_order_qty);
				if (!row.spq && it.ub_standard_packing_qty) frappe.model.set_value(cdt, cdn, "spq", it.ub_standard_packing_qty);
				if (!row.lead_time_days && it.lead_time_days) frappe.model.set_value(cdt, cdn, "lead_time_days", it.lead_time_days);
			}
		});
		show_previous(frm, row);
	},
	supplier(frm, cdt, cdn) {
		set_party_defaults(frm, cdt, cdn, "Supplier", locals[cdt][cdn].supplier);
	},
	customer(frm, cdt, cdn) {
		set_party_defaults(frm, cdt, cdn, "Customer", locals[cdt][cdn].customer);
	},
});

function toggle_party_columns(frm) {
	const grid = frm.fields_dict.item_price_details.grid;
	const buying = frm.doc.type !== "Selling";
	grid.toggle_reqd("supplier", buying);
	grid.toggle_display("supplier", buying);
	grid.toggle_reqd("customer", !buying);
	grid.toggle_display("customer", !buying);
	grid.toggle_display("moq", buying);
	grid.toggle_display("spq", buying);
	grid.toggle_display("item_manufacturer", buying);
}

function set_party_defaults(frm, cdt, cdn, party_type, party) {
	if (!party) return;
	frappe.xcall(`${UB_IPR}.get_party_defaults`, { party_type, party }).then((r) => {
		if (r && r.default_price_list) frappe.model.set_value(cdt, cdn, "price_list", r.default_price_list);
	});
}

function show_previous(frm, row) {
	frappe.xcall(`${UB_IPR}.get_previous_requests`, { item_code: row.item_code, company: frm.doc.company, type: frm.doc.type }).then((data) => {
		const esc = frappe.utils.escape_html;
		let html = `<p class="text-muted">${__("No earlier requests for {0}.", [esc(row.item_code)])}</p>`;
		if (data && data.length) {
			html = `<p><b>${esc(row.item_code)}</b></p><table class="table table-bordered table-sm"><thead><tr>
				<th>${__("Request")}</th><th>${__("MPN")}</th><th>${__("Party")}</th><th>${__("Rate")}</th>
				<th>${__("Valid")}</th><th>${__("Status")}</th></tr></thead><tbody>` +
				data.map((d) => `<tr><td>${frappe.utils.get_form_link("Item Price Request", d.name, true)}</td>
					<td>${esc(d.manufacturer_part_no || "-")}</td><td>${esc(d.supplier || d.customer || "-")}</td>
					<td>${format_currency(d.rate, d.currency)}</td>
					<td>${frappe.datetime.str_to_user(d.valid_from) || ""} - ${frappe.datetime.str_to_user(d.valid_upto) || ""}</td>
					<td>${d.docstatus === 1 ? __("Submitted") : __("Draft")}</td></tr>`).join("") +
				"</tbody></table>";
		}
		frm.fields_dict.previous_prices.$wrapper.html(html);
	});
}
