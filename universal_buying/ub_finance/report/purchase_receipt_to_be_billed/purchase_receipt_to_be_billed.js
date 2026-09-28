// Copyright (c) 2026, Finstein and contributors

frappe.query_reports["Purchase Receipt to be Billed"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", reqd: 1, default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.get_today(), -3) },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "supplier", label: __("Supplier"), fieldtype: "Link", options: "Supplier" },
		{ fieldname: "supplier_invoice_no", label: __("Supplier Invoice No"), fieldtype: "Data" },
		{ fieldname: "show_receipts", label: __("One Row per Receipt"), fieldtype: "Check" },
	],
};
