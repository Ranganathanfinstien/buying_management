// Copyright (c) 2026, Finstein and contributors

frappe.query_reports["Unacknowledged PO"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "supplier", label: __("Supplier"), fieldtype: "Link", options: "Supplier" },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
		{ fieldname: "min_days_waiting", label: __("Min Days Waiting"), fieldtype: "Int", default: 0 },
	],
};
