# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt

"""Inward Discrepancy Register: one line per discrepancy row."""

import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{
			"fieldname": "inward_discrepancy",
			"label": _("Inward Discrepancy"),
			"fieldtype": "Link",
			"options": "Inward Discrepancy",
			"width": 150,
		},
		{"fieldname": "date", "label": _("Date"), "fieldtype": "Date", "width": 95},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 80},
		{
			"fieldname": "supplier",
			"label": _("Supplier"),
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 150,
		},
		{
			"fieldname": "supplier_invoice_no",
			"label": _("Supplier Invoice No"),
			"fieldtype": "Data",
			"width": 130,
		},
		{
			"fieldname": "purchase_receipt",
			"label": _("Purchase Receipt"),
			"fieldtype": "Link",
			"options": "Purchase Receipt",
			"width": 150,
		},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 140},
		{"fieldname": "invoice_qty", "label": _("Invoice Qty"), "fieldtype": "Float", "width": 90},
		{"fieldname": "received_qty", "label": _("Received Qty"), "fieldtype": "Float", "width": 90},
		{"fieldname": "difference_qty", "label": _("Difference"), "fieldtype": "Float", "width": 90},
		{"fieldname": "rate", "label": _("Rate"), "fieldtype": "Currency", "width": 100},
		{
			"fieldname": "discrepancy_type",
			"label": _("Type"),
			"fieldtype": "Link",
			"options": "Inward Discrepancy Type",
			"width": 120,
		},
		{"fieldname": "row_status", "label": _("Row Status"), "fieldtype": "Data", "width": 80},
		{"fieldname": "remarks", "label": _("Remarks"), "fieldtype": "Data", "width": 180},
		{"fieldname": "buyer_comments", "label": _("Buyer Comments"), "fieldtype": "Data", "width": 180},
	]


def get_data(filters):
	conditions = ["idc.company = %(company)s", "idc.docstatus < 2"]
	if filters.get("from_date"):
		conditions.append("idc.date >= %(from_date)s")
	if filters.get("to_date"):
		conditions.append("idc.date <= %(to_date)s")
	if filters.get("supplier"):
		conditions.append("idc.supplier = %(supplier)s")
	if filters.get("status"):
		conditions.append("idc.status = %(status)s")
	if filters.get("discrepancy_type"):
		conditions.append("item.discrepancy_type = %(discrepancy_type)s")

	return frappe.db.sql(
		f"""
		select idc.name as inward_discrepancy, idc.date, idc.status, idc.supplier, idc.supplier_invoice_no,
			idc.purchase_receipt, item.item_code, item.invoice_qty, item.received_qty,
			item.invoice_qty - item.received_qty as difference_qty, item.rate, item.discrepancy_type,
			item.status as row_status, item.remarks, idc.buyer_comments
		from `tabInward Discrepancy` idc
		inner join `tabInward Discrepancy Item` item on item.parent = idc.name
		where {" and ".join(conditions)}
		order by idc.date desc, idc.name, item.idx
		""",
		filters,
		as_dict=True,
	)
