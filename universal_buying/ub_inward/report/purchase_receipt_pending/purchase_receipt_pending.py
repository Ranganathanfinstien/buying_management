# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt

"""Purchase Receipt Pending: open Purchase Order lines not (fully) received."""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, nowdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{
			"fieldname": "purchase_order",
			"label": _("Purchase Order"),
			"fieldtype": "Link",
			"options": "Purchase Order",
			"width": 160,
		},
		{"fieldname": "transaction_date", "label": _("PO Date"), "fieldtype": "Date", "width": 95},
		{
			"fieldname": "supplier",
			"label": _("Supplier"),
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 150,
		},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 140},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 160},
		{"fieldname": "uom", "label": _("UOM"), "fieldtype": "Link", "options": "UOM", "width": 70},
		{"fieldname": "ordered_qty", "label": _("Ordered Qty"), "fieldtype": "Float", "width": 100},
		{"fieldname": "received_qty", "label": _("Received Qty"), "fieldtype": "Float", "width": 100},
		{"fieldname": "pending_qty", "label": _("Pending Qty"), "fieldtype": "Float", "width": 100},
		{
			"fieldname": "draft_receipt_qty",
			"label": _("On Draft Receipts"),
			"fieldtype": "Float",
			"width": 110,
		},
		{
			"fieldname": "rate",
			"label": _("Rate"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 100,
		},
		{
			"fieldname": "pending_amount",
			"label": _("Pending Amount"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 120,
		},
		{
			"fieldname": "currency",
			"label": _("Currency"),
			"fieldtype": "Link",
			"options": "Currency",
			"hidden": 1,
		},
		{"fieldname": "schedule_date", "label": _("Required By"), "fieldtype": "Date", "width": 95},
		{"fieldname": "overdue_days", "label": _("Overdue Days"), "fieldtype": "Int", "width": 95},
		{
			"fieldname": "warehouse",
			"label": _("Warehouse"),
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 140,
		},
	]


def get_data(filters):
	conditions = [
		"po.docstatus = 1",
		"po.status not in ('Closed', 'On Hold', 'Completed')",
		"po.company = %(company)s",
	]
	for field in ("supplier", "purchase_order", "item_code"):
		if filters.get(field):
			column = (
				"po.name"
				if field == "purchase_order"
				else ("po.supplier" if field == "supplier" else "poi.item_code")
			)
			conditions.append(f"{column} = %({field})s")
	if filters.get("from_date"):
		conditions.append("poi.schedule_date >= %(from_date)s")
	if filters.get("to_date"):
		conditions.append("poi.schedule_date <= %(to_date)s")

	rows = frappe.db.sql(
		f"""
		select po.name as purchase_order, po.transaction_date, po.supplier, po.currency,
			poi.item_code, poi.item_name, poi.uom, poi.qty as ordered_qty, poi.rate, poi.schedule_date, poi.warehouse,
			ifnull(sub.received, 0) as received_qty,
			ifnull(dr.qty, 0) as draft_receipt_qty
		from `tabPurchase Order Item` poi
		inner join `tabPurchase Order` po on po.name = poi.parent
		left join (
			select pri.purchase_order_item,
				sum(case when pr.is_return = 1 then pri.qty else pri.received_qty end) as received
			from `tabPurchase Receipt Item` pri
			inner join `tabPurchase Receipt` pr on pr.name = pri.parent
			where pr.docstatus = 1 and pr.company = %(company)s and pri.purchase_order_item is not null
			group by pri.purchase_order_item
		) sub on sub.purchase_order_item = poi.name
		left join (
			select pri.purchase_order_item, sum(pri.received_qty) as qty
			from `tabPurchase Receipt Item` pri
			inner join `tabPurchase Receipt` pr on pr.name = pri.parent
			where pr.docstatus = 0 and pr.is_return = 0 and pr.company = %(company)s
				and pri.purchase_order_item is not null
			group by pri.purchase_order_item
		) dr on dr.purchase_order_item = poi.name
		where {" and ".join(conditions)}
			and ifnull(poi.delivered_by_supplier, 0) = 0
			and poi.qty - ifnull(sub.received, 0) > 0
		order by poi.schedule_date, po.name, poi.idx
		""",
		filters,
		as_dict=True,
	)
	today = getdate(nowdate())
	out = []
	for r in rows:
		r.pending_qty = flt(r.ordered_qty) - flt(r.received_qty)
		r.pending_amount = r.pending_qty * flt(r.rate)
		r.overdue_days = max(date_diff(today, r.schedule_date), 0) if r.schedule_date else 0
		if filters.get("overdue_only") and not r.overdue_days:
			continue
		out.append(r)
	return out
