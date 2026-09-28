// Copyright (c) 2026, Finstein and contributors

frappe.query_reports["Manufacturing Shortage Summary"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", reqd: 1,
			default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "cost_center", label: __("Cost Center"), fieldtype: "Link", options: "Cost Center",
			get_query: () => ({ filters: { company: frappe.query_report.get_filter_value("company") } }) },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project",
			get_query: () => ({ filters: { company: frappe.query_report.get_filter_value("company") } }) },
		{ fieldname: "item_code", label: __("Item"), fieldtype: "Link", options: "Item" },
		{ fieldname: "include_open_supply", label: __("Include qty covered by open PO / WO"), fieldtype: "Check", default: 1 },
	],
};
