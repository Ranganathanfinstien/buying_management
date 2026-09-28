// Copyright (c) 2026, Finstein and contributors

frappe.query_reports["Auto PO Exception"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", reqd: 1,
			default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project",
			get_query: () => ({ filters: { company: frappe.query_report.get_filter_value("company") } }) },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", reqd: 1,
			default: frappe.datetime.add_days(frappe.datetime.get_today(), 90) },
		{ fieldname: "lead_time_order", label: __("Lead-time Mode"), fieldtype: "Check", default: 0 },
		{ fieldname: "exception_type", label: __("Exception Type"), fieldtype: "Select",
			options: ["", "No Supplier", "No Price", "MOQ Exception"] },
	],
};
