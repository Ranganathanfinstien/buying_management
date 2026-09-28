# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt

"""PO Shortage Summary - net shortage (after stock and open POs) per item and month.

The earlier version computed Shortage - Purchase Order rows; the Requirement Log Shortage rows are already net.
Overdue quantities are shown in the current month.
"""

import frappe
from frappe import _
from frappe.utils import get_first_day, nowdate

from universal_buying.ub_planning.common import company_with_descendants, month_key, month_label


def execute(filters=None):
	filters = frappe._dict(filters or {})
	companies = company_with_descendants(filters.company)
	if not companies:
		return get_columns(), []
	conditions = ["rl.company in %(companies)s", "rl.reservation_type = 'Shortage'"]
	params = {"companies": tuple(companies), "month0": get_first_day(nowdate())}
	for field in ("cost_center", "project", "item_code"):
		if filters.get(field):
			conditions.append(f"rl.{field} = %({field})s")
			params[field] = filters.get(field)
	if filters.get("purchase_items_only"):
		conditions.append("it.is_purchase_item = 1")
	rows = frappe.db.sql(
		f"""select rl.company, rl.cost_center, rl.project, rl.item_code, it.item_name, it.description,
			if(it.is_purchase_item = 1, 'Yes', 'No') as is_purchase_item,
			greatest(rl.grouped_delivery_date, %(month0)s) as month, sum(rl.qty) as qty
		from `tabRequirement Log` rl inner join `tabItem` it on it.name = rl.item_code
		where {" and ".join(conditions)}
		group by rl.company, rl.cost_center, rl.project, rl.item_code, month
		having qty > 0
		order by rl.company, rl.project, rl.item_code, month""",
		params,
		as_dict=True,
	)
	months = sorted({r.month for r in rows})
	out = {}
	for r in rows:
		key = (r.company, r.cost_center, r.project, r.item_code)
		row = out.setdefault(key, {
			"company": r.company, "cost_center": r.cost_center, "project": r.project, "item_code": r.item_code,
			"item_name": r.item_name, "description": r.description, "is_purchase_item": r.is_purchase_item,
			"total": 0.0,
		})
		row[month_key(r.month)] = row.get(month_key(r.month), 0) + r.qty
		row["total"] += r.qty
	columns = get_columns() + [
		{"label": month_label(m), "fieldname": month_key(m), "fieldtype": "Float", "width": 110} for m in months
	] + [{"label": _("Total"), "fieldname": "total", "fieldtype": "Float", "width": 110}]
	return columns, list(out.values())


def get_columns():
	return [
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 150},
		{"label": _("Cost Center"), "fieldname": "cost_center", "fieldtype": "Link", "options": "Cost Center", "width": 130},
		{"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 120},
		{"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 150},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 160},
		{"label": _("Description"), "fieldname": "description", "fieldtype": "Data", "width": 200},
		{"label": _("Is Purchase Item"), "fieldname": "is_purchase_item", "fieldtype": "Data", "width": 90},
	]
