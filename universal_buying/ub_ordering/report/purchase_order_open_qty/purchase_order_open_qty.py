# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt

"""Open quantity per PO line (plus portal / delivery dates)."""

import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Purchase Order"), "fieldname": "name", "fieldtype": "Link", "options": "Purchase Order", "width": 170},
		{"label": _("Date"), "fieldname": "transaction_date", "fieldtype": "Date", "width": 100},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 160},
		{"label": _("Supplier Name"), "fieldname": "supplier_name", "fieldtype": "Data", "width": 180},
		{"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 150},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 180},
		{"label": _("Required By"), "fieldname": "schedule_date", "fieldtype": "Date", "width": 100},
		{"label": _("Supplier Date"), "fieldname": "supplier_date", "fieldtype": "Date", "width": 100},
		{"label": _("Qty"), "fieldname": "qty", "fieldtype": "Float", "width": 90},
		{"label": _("Received Qty"), "fieldname": "received_qty", "fieldtype": "Float", "width": 100},
		{"label": _("Open Qty"), "fieldname": "open_po_qty", "fieldtype": "Float", "width": 100},
		{"label": _("Draft Receipt Qty"), "fieldname": "draft_pr_qty", "fieldtype": "Float", "width": 110},
		{"label": _("Rate"), "fieldname": "rate", "fieldtype": "Currency", "options": "currency", "width": 110},
		{"label": _("Open Amount"), "fieldname": "open_amount", "fieldtype": "Currency", "options": "currency", "width": 120},
		{"label": _("Currency"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "width": 70},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 130},
		{"label": _("Portal Status"), "fieldname": "ub_portal_status", "fieldtype": "Data", "width": 130},
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 150},
	]


def get_data(filters):
	conditions = ["po.docstatus = 1", "po.status not in ('Closed', 'Completed')", "poi.qty > ifnull(poi.received_qty, 0)"]
	for key, cond in (
		("company", "po.company = %(company)s"),
		("supplier", "po.supplier = %(supplier)s"),
		("purchase_order", "po.name = %(purchase_order)s"),
		("item_code", "poi.item_code = %(item_code)s"),
		("from_date", "po.transaction_date >= %(from_date)s"),
		("to_date", "po.transaction_date <= %(to_date)s"),
		("po_type", "po.ub_po_type = %(po_type)s"),
	):
		if filters.get(key):
			conditions.append(cond)

	return frappe.db.sql(
		f"""
		select po.name, po.transaction_date, po.supplier, po.supplier_name, poi.item_code, poi.item_name,
			poi.schedule_date,
			coalesce(poi.ub_supplier_delivery_date, po.ub_confirmed_delivery_date, poi.expected_delivery_date) as supplier_date,
			poi.qty, ifnull(poi.received_qty, 0) as received_qty,
			round(poi.qty - ifnull(poi.received_qty, 0), 6) as open_po_qty,
			round(ifnull(draft_pr.qty, 0), 6) as draft_pr_qty,
			poi.rate, round((poi.qty - ifnull(poi.received_qty, 0)) * poi.rate, 2) as open_amount,
			po.currency, po.status, po.ub_portal_status, po.company
		from `tabPurchase Order` po
		join `tabPurchase Order Item` poi on poi.parent = po.name and poi.parenttype = 'Purchase Order'
		left join (
			select pri.purchase_order_item, sum(pri.qty) as qty
			from `tabPurchase Receipt Item` pri join `tabPurchase Receipt` pr on pr.name = pri.parent
			where pr.docstatus = 0 and ifnull(pri.purchase_order_item, '') != ''
			group by pri.purchase_order_item
		) draft_pr on draft_pr.purchase_order_item = poi.name
		where {" and ".join(conditions)}
		order by poi.schedule_date, po.name, poi.idx
		""",
		filters,
		as_dict=True,
	)
