// Copyright (c) 2026, Finstein and contributors

frappe.query_reports["RFQ Status"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.get_today(), -3) },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "workflow_state", label: __("Workflow State"), fieldtype: "Link", options: "Workflow State" },
		{ fieldname: "open_only", label: __("Bidding Open Only"), fieldtype: "Check" },
	],
};
