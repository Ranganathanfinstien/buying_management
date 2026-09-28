// Copyright (c) 2026, Finstein and contributors

frappe.query_reports["Pending Supplier Quotations"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "rfq", label: __("Request for Quotation"), fieldtype: "Link", options: "Request for Quotation" },
		{ fieldname: "include_closed", label: __("Include Closed Bidding"), fieldtype: "Check" },
	],
};
