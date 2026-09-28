# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt

"""PO lines with open quantity whose promised date has passed.

Promised date = supplier delivery date on the line, else the confirmed delivery date from the portal,
else the line's required-by date (schedule_date).
"""

import frappe
from frappe import _
from frappe.utils import date_diff, getdate, today


def execute(filters=None):
	filters = frappe._dict(filters or {})
	as_on = getdate(filters.get("as_on_date") or today())
	return get_columns(), get_data(filters, as_on)


def get_columns():
	return [
		{"label": _("Purchase Order"), "fieldname": "name", "fieldtype": "Link", "options": "Purchase Order", "width": 170},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 160},
		{"label": _("Supplier Name"), "fieldname": "supplier_name", "fieldtype": "Data", "width": 170},
		{"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 140},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 170},
		{"label": _("Required By"), "fieldname": "schedule_date", "fieldtype": "Date", "width": 100},
		{"label": _("Promised Date"), "fieldname": "promised_date", "fieldtype": "Date", "width": 100},
		{"label": _("Days Delayed"), "fieldname": "days_delayed", "fieldtype": "Int", "width": 100},
		{"label": _("Open Qty"), "fieldname": "open_qty", "fieldtype": "Float", "width": 90},
		{"label": _("Open Amount"), "fieldname": "open_amount", "fieldtype": "Currency", "options": "currency", "width": 120},
		{"label": _("Currency"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "width": 70},
		{"label": _("Portal Status"), "fieldname": "ub_portal_status", "fieldtype": "Data", "width": 130},
		{"label": _("Material Status"), "fieldname": "ub_material_status", "fieldtype": "Data", "width": 120},
		{"label": _("Buyer"), "fieldname": "owner", "fieldtype": "Link", "options": "User", "width": 150},
	]


def get_data(filters, as_on):
	conditions = ["po.docstatus = 1", "po.status not in ('Closed', 'Completed', 'On Hold')",
		"poi.qty > ifnull(poi.received_qty, 0)"]
	for key, cond in (
		("company", "po.company = %(company)s"),
		("supplier", "po.supplier = %(supplier)s"),
		("item_code", "poi.item_code = %(item_code)s"),
	):
		if filters.get(key):
			conditions.append(cond)
	filters["as_on"] = as_on
	rows = frappe.db.sql(
		f"""
		select po.name, po.supplier, po.supplier_name, poi.item_code, poi.item_name, poi.schedule_date,
			coalesce(poi.ub_supplier_delivery_date, po.ub_confirmed_delivery_date, poi.schedule_date) as promised_date,
			round(poi.qty - ifnull(poi.received_qty, 0), 6) as open_qty,
			round((poi.qty - ifnull(poi.received_qty, 0)) * poi.rate, 2) as open_amount,
			po.currency, po.ub_portal_status, po.ub_material_status, po.owner
		from `tabPurchase Order` po
		join `tabPurchase Order Item` poi on poi.parent = po.name and poi.parenttype = 'Purchase Order'
		where {" and ".join(conditions)}
			and coalesce(poi.ub_supplier_delivery_date, po.ub_confirmed_delivery_date, poi.schedule_date) < %(as_on)s
		order by promised_date, po.name, poi.idx
		""",
		filters,
		as_dict=True,
	)
	min_days = int(filters.get("min_days_delayed") or 0)
	out = []
	for r in rows:
		r.days_delayed = date_diff(as_on, r.promised_date)
		if r.days_delayed >= min_days:
			out.append(r)
	return out
