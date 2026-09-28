# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt

"""Excess PO - open PO quantity of BOM components that no demand in the Requirement Log needs.

Excess = pending stock qty of a submitted open PO line - quantity the Requirement Engine reserved on it.
It lists components of active default BOMs that have no BOM of their own.
"""

import frappe
from frappe import _

from universal_buying.ub_planning.common import company_with_descendants


def execute(filters=None):
	filters = frappe._dict(filters or {})
	companies = company_with_descendants(filters.company)
	if not companies:
		return get_columns(), []
	conditions = ["po.company in %(companies)s"]
	params = {"companies": tuple(companies)}
	for field in ("project", "cost_center", "item_code", "item_group"):
		if filters.get(field):
			conditions.append(f"poi.{field} = %({field})s")
			params[field] = filters.get(field)
	data = frappe.db.sql(
		f"""
		select po.company, poi.cost_center, poi.project, p.project_name, po.name as purchase_order,
			po.supplier, poi.idx as line_no, poi.item_code, poi.item_name, poi.item_group, poi.stock_uom,
			(poi.qty - ifnull(poi.received_qty, 0)) * ifnull(nullif(poi.conversion_factor, 0), 1)
				- ifnull(res.qty, 0) as excess_qty,
			poi.base_net_rate / ifnull(nullif(poi.conversion_factor, 0), 1) as rate,
			po.status, poi.schedule_date
		from `tabPurchase Order Item` poi
		inner join `tabPurchase Order` po on po.name = poi.parent
		inner join `tabItem` it on it.name = poi.item_code
		left join `tabProject` p on p.name = poi.project
		left join (
			select purchase_order_item, sum(qty) as qty from `tabRequirement Log`
			where reservation_type = 'Purchase Order' group by purchase_order_item
		) res on res.purchase_order_item = poi.name
		where po.docstatus = 1 and po.status not in ('Closed', 'On Hold', 'Completed', 'Delivered')
			and poi.qty > ifnull(poi.received_qty, 0)
			and ifnull(it.default_bom, '') = ''
			and exists (
				select 1 from `tabBOM Explosion Item` bei inner join `tabBOM` b on b.name = bei.parent
				where b.docstatus = 1 and b.is_active = 1 and b.is_default = 1 and bei.item_code = poi.item_code
			)
			and {" and ".join(conditions)}
		having excess_qty > 0.000001
		order by po.company, poi.project, po.name, poi.idx
		""",
		params,
		as_dict=True,
	)
	for row in data:
		row.excess_value = (row.excess_qty or 0) * (row.rate or 0)
	return get_columns(), data


def get_columns():
	return [
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 150},
		{"label": _("Cost Center"), "fieldname": "cost_center", "fieldtype": "Link", "options": "Cost Center", "width": 120},
		{"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 120},
		{"label": _("Purchase Order"), "fieldname": "purchase_order", "fieldtype": "Link", "options": "Purchase Order",
			"width": 150},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 140},
		{"label": _("Line"), "fieldname": "line_no", "fieldtype": "Int", "width": 50},
		{"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 140},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 150},
		{"label": _("Item Group"), "fieldname": "item_group", "fieldtype": "Link", "options": "Item Group", "width": 110},
		{"label": _("Excess Qty"), "fieldname": "excess_qty", "fieldtype": "Float", "width": 100},
		{"label": _("Stock UOM"), "fieldname": "stock_uom", "fieldtype": "Link", "options": "UOM", "width": 80},
		{"label": _("Rate (Company Currency)"), "fieldname": "rate", "fieldtype": "Currency", "width": 110},
		{"label": _("Excess Value"), "fieldname": "excess_value", "fieldtype": "Currency", "width": 120},
		{"label": _("Required By"), "fieldname": "schedule_date", "fieldtype": "Date", "width": 100},
		{"label": _("PO Status"), "fieldname": "status", "fieldtype": "Data", "width": 120},
	]
