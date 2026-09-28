# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt

"""Submitted POs the supplier has not acknowledged on the portal yet (portal status Pending Acceptance)."""

import frappe
from frappe import _
from frappe.utils import date_diff, getdate, today


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Purchase Order"), "fieldname": "name", "fieldtype": "Link", "options": "Purchase Order", "width": 170},
		{"label": _("Date"), "fieldname": "transaction_date", "fieldtype": "Date", "width": 100},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 160},
		{"label": _("Supplier Name"), "fieldname": "supplier_name", "fieldtype": "Data", "width": 180},
		{"label": _("Required By"), "fieldname": "schedule_date", "fieldtype": "Date", "width": 100},
		{"label": _("Days Waiting"), "fieldname": "days_waiting", "fieldtype": "Int", "width": 100},
		{"label": _("Grand Total"), "fieldname": "grand_total", "fieldtype": "Currency", "options": "currency", "width": 130},
		{"label": _("Currency"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "width": 70},
		{"label": _("Portal Users"), "fieldname": "portal_users", "fieldtype": "Int", "width": 100},
		{"label": _("Buyer"), "fieldname": "owner", "fieldtype": "Link", "options": "User", "width": 150},
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 150},
	]


def get_data(filters):
	conditions = ["po.docstatus = 1", "po.status not in ('Closed', 'Completed')",
		"ifnull(po.ub_portal_status, '') in ('', 'Pending Acceptance')",
		"not exists (select 1 from `tabPO Acknowledgement` a where a.purchase_order = po.name)"]
	for key, cond in (
		("company", "po.company = %(company)s"),
		("supplier", "po.supplier = %(supplier)s"),
		("from_date", "po.transaction_date >= %(from_date)s"),
		("to_date", "po.transaction_date <= %(to_date)s"),
	):
		if filters.get(key):
			conditions.append(cond)
	rows = frappe.db.sql(
		f"""
		select po.name, po.transaction_date, po.supplier, po.supplier_name, po.schedule_date, po.grand_total,
			po.currency, po.owner, po.company,
			(select count(*) from `tabPortal User` pu where pu.parent = po.supplier and pu.parenttype = 'Supplier') as portal_users
		from `tabPurchase Order` po
		where {" and ".join(conditions)}
		order by po.transaction_date, po.name
		""",
		filters,
		as_dict=True,
	)
	min_days = int(filters.get("min_days_waiting") or 0)
	now = getdate(today())
	out = []
	for r in rows:
		r.days_waiting = date_diff(now, r.transaction_date)
		if r.days_waiting >= min_days:
			out.append(r)
	return out
