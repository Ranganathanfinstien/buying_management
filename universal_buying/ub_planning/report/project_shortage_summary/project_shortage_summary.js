// Copyright (c) 2026, Finstein and contributors

frappe.query_reports["Project Shortage Summary"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", reqd: 1,
			default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "months", label: __("Months"), fieldtype: "Int", default: 4 },
	],
};
