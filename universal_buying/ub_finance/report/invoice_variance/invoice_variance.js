// Copyright (c) 2026, Finstein and contributors

frappe.query_reports["Invoice Variance"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", reqd: 1, default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.get_today(), -1) },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "supplier", label: __("Supplier"), fieldtype: "Link", options: "Supplier" },
		{ fieldname: "purchase_order", label: __("Purchase Order"), fieldtype: "Link", options: "Purchase Order" },
		{ fieldname: "item_code", label: __("Item"), fieldtype: "Link", options: "Item" },
		{ fieldname: "only_variance", label: __("Only Rows with Variance"), fieldtype: "Check", default: 1 },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && ["rate_variance", "amount_variance", "qty_variance", "rate_variance_pct"].includes(column.fieldname)) {
			const v = flt(data[column.fieldname]);
			if (v > 0) value = `<span style="color: var(--red-600)">${value}</span>`;
			else if (v < 0) value = `<span style="color: var(--green-600)">${value}</span>`;
		}
		return value;
	},
};
