// Copyright (c) 2026, Finstein and contributors

frappe.query_reports["Delayed PO"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "supplier", label: __("Supplier"), fieldtype: "Link", options: "Supplier" },
		{ fieldname: "item_code", label: __("Item"), fieldtype: "Link", options: "Item" },
		{ fieldname: "as_on_date", label: __("As On"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "min_days_delayed", label: __("Min Days Delayed"), fieldtype: "Int", default: 0 },
	],
};
