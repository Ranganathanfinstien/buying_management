# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt

"""IQC Pending: receipt rows of inspection-required items without a submitted Quality Inspection."""

import frappe
from frappe import _
from frappe.utils import date_diff, getdate, nowdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{
			"fieldname": "purchase_receipt",
			"label": _("Purchase Receipt"),
			"fieldtype": "Link",
			"options": "Purchase Receipt",
			"width": 160,
		},
		{"fieldname": "receipt_status", "label": _("Receipt Status"), "fieldtype": "Data", "width": 100},
		{"fieldname": "posting_date", "label": _("Posting Date"), "fieldtype": "Date", "width": 95},
		{
			"fieldname": "supplier",
			"label": _("Supplier"),
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 150,
		},
		{"fieldname": "ub_green_card", "label": _("Green Card"), "fieldtype": "Check", "width": 80},
		{"fieldname": "idx", "label": _("Row"), "fieldtype": "Int", "width": 50},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 140},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 160},
		{"fieldname": "received_qty", "label": _("Received Qty"), "fieldtype": "Float", "width": 100},
		{"fieldname": "batch_no", "label": _("Batch"), "fieldtype": "Link", "options": "Batch", "width": 130},
		{
			"fieldname": "draft_inspection",
			"label": _("Draft Inspection"),
			"fieldtype": "Link",
			"options": "Quality Inspection",
			"width": 150,
		},
		{"fieldname": "days_pending", "label": _("Days Pending"), "fieldtype": "Int", "width": 95},
	]


def get_data(filters):
	conditions = ["pr.company = %(company)s", "pr.is_return = 0", "ifnull(pr.ub_is_bonded, 0) = 0"]
	status = filters.get("receipt_status") or "Draft"
	if status == "Draft":
		conditions.append("pr.docstatus = 0")
	elif status == "Submitted":
		conditions.append("pr.docstatus = 1")
	else:
		conditions.append("pr.docstatus < 2")
	if filters.get("supplier"):
		conditions.append("pr.supplier = %(supplier)s")
	if filters.get("from_date"):
		conditions.append("pr.posting_date >= %(from_date)s")
	if filters.get("to_date"):
		conditions.append("pr.posting_date <= %(to_date)s")

	rows = frappe.db.sql(
		f"""
		select pr.name as purchase_receipt, pr.docstatus, pr.posting_date, pr.supplier, pr.ub_green_card,
			pri.idx, pri.item_code, pri.item_name, pri.received_qty, pri.batch_no,
			(select qi.name from `tabQuality Inspection` qi
				where qi.docstatus = 0 and qi.reference_type = 'Purchase Receipt' and qi.reference_name = pr.name
					and qi.item_code = pri.item_code
				order by qi.creation limit 1) as draft_inspection
		from `tabPurchase Receipt Item` pri
		inner join `tabPurchase Receipt` pr on pr.name = pri.parent
		inner join `tabItem` item on item.name = pri.item_code
		where {" and ".join(conditions)}
			and item.inspection_required_before_purchase = 1
			and not exists (
				select 1 from `tabQuality Inspection` qi
				where qi.docstatus = 1 and qi.reference_type = 'Purchase Receipt' and qi.reference_name = pr.name
					and qi.item_code = pri.item_code
					and (qi.name = pri.quality_inspection or qi.child_row_reference = pri.name
						or (ifnull(qi.batch_no, '') != '' and qi.batch_no = pri.batch_no))
			)
		order by pr.posting_date, pr.name, pri.idx
		""",
		filters,
		as_dict=True,
	)
	today = getdate(nowdate())
	for r in rows:
		r.receipt_status = _("Draft") if r.docstatus == 0 else _("Submitted")
		r.days_pending = max(date_diff(today, r.posting_date), 0)
	return rows
