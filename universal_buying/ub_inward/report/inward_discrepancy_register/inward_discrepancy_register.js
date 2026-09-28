// Copyright (c) 2026, Finstein and contributors

frappe.query_reports["Inward Discrepancy Register"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", reqd: 1, default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.get_today(), -1) },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "supplier", label: __("Supplier"), fieldtype: "Link", options: "Supplier" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: "\nDraft\nOpen\nClosed" },
		{ fieldname: "discrepancy_type", label: __("Type"), fieldtype: "Link", options: "Inward Discrepancy Type" },
	],
};
