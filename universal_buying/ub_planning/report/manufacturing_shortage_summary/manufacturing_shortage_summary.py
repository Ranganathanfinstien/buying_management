# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt

"""Manufacturing Shortage Summary - purchase components not covered by stock, pivoted by month.

Rewritten on the Requirement Log (no raw reservation table, no pandas).
"Include open supply" (default on) adds the quantity already covered by open
Purchase / Work Orders; switched off the figures equal the Requirement Log Shortage rows (AC-10.2).
Overdue quantities are shown in the current month.
"""

import frappe
from frappe import _
from frappe.utils import cint, get_first_day, nowdate

from universal_buying.ub_planning.api import get_current_item_price
from universal_buying.ub_planning.common import company_with_descendants, month_key, month_label


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = get_rows(filters)
	months = sorted({r.month for r in rows})
	columns = get_columns() + [
		{"label": month_label(m), "fieldname": month_key(m), "fieldtype": "Float", "width": 110} for m in months
	] + [{"label": _("Total"), "fieldname": "total", "fieldtype": "Float", "width": 110}]
	return columns, pivot(rows)


def get_rows(filters):
	companies = company_with_descendants(filters.company)
	if not companies:
		return []
	types = ["Shortage", "Purchase Order", "Work Order"] if cint(filters.get("include_open_supply", 1)) else ["Shortage"]
	conditions = ["rl.company in %(companies)s", "rl.reservation_type in %(types)s", "ifnull(rl.level, 0) > 0",
		"it.is_purchase_item = 1"]
	params = {"companies": tuple(companies), "types": tuple(types), "month0": get_first_day(nowdate())}
	for field in ("cost_center", "project", "item_code"):
		if filters.get(field):
			conditions.append(f"rl.{field} = %({field})s")
			params[field] = filters.get(field)
	return frappe.db.sql(
		f"""select rl.company, rl.cost_center, rl.project, rl.item_code, it.item_name, it.description,
			it.min_order_qty as moq, greatest(rl.grouped_delivery_date, %(month0)s) as month, sum(rl.qty) as qty
		from `tabRequirement Log` rl inner join `tabItem` it on it.name = rl.item_code
		where {" and ".join(conditions)}
		group by rl.company, rl.cost_center, rl.project, rl.item_code, month
		having qty > 0
		order by rl.company, rl.project, rl.item_code, month""",
		params,
		as_dict=True,
	)


def pivot(rows):
	out = {}
	price_cache = {}
	projects = {}
	for r in rows:
		key = (r.company, r.cost_center, r.project, r.item_code)
		row = out.get(key)
		if not row:
			if (r.item_code, r.company) not in price_cache:
				price_cache[(r.item_code, r.company)] = get_current_item_price(r.item_code, company=r.company) or {}
			price = price_cache[(r.item_code, r.company)]
			if r.project and r.project not in projects:
				projects[r.project] = frappe.db.get_value("Project", r.project, "project_name")
			row = out[key] = {
				"company": r.company, "cost_center": r.cost_center, "project": r.project,
				"project_name": projects.get(r.project), "item_code": r.item_code, "item_name": r.item_name,
				"description": r.description, "default_supplier": price.get("supplier"),
				"default_price": price.get("price_list_rate"), "currency": price.get("currency"),
				"moq": r.moq, "total": 0.0,
			}
		row[month_key(r.month)] = row.get(month_key(r.month), 0) + r.qty
		row["total"] += r.qty
	return list(out.values())


def get_columns():
	return [
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 150},
		{"label": _("Cost Center"), "fieldname": "cost_center", "fieldtype": "Link", "options": "Cost Center", "width": 130},
		{"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 120},
		{"label": _("Project Name"), "fieldname": "project_name", "fieldtype": "Data", "width": 160},
		{"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 150},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 160},
		{"label": _("Description"), "fieldname": "description", "fieldtype": "Data", "width": 180},
		{"label": _("Default Supplier"), "fieldname": "default_supplier", "fieldtype": "Link", "options": "Supplier",
			"width": 140},
		{"label": _("Default Price"), "fieldname": "default_price", "fieldtype": "Currency", "options": "currency",
			"width": 110},
		{"label": _("Currency"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "width": 80},
		{"label": _("MOQ"), "fieldname": "moq", "fieldtype": "Float", "width": 80},
	]
