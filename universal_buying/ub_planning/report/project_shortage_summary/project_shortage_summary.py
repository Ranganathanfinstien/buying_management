# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt

"""Project Shortage Summary - number of distinct short items per project for the current and next months.

The earlier version ignored overdue shortages (it started at the first day of the current month); they are now
counted in the current month.
"""

import frappe
from frappe import _
from frappe.utils import add_months, cint, get_first_day, nowdate

from universal_buying.ub_planning.common import company_with_descendants, month_key, month_label


def execute(filters=None):
	filters = frappe._dict(filters or {})
	months_count = cint(filters.get("months") or 4)
	month0 = get_first_day(nowdate())
	months = [add_months(month0, i) for i in range(months_count)]
	columns = [
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 150},
		{"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 140},
		{"label": _("Project Name"), "fieldname": "project_name", "fieldtype": "Data", "width": 200},
	] + [{"label": month_label(m), "fieldname": month_key(m), "fieldtype": "Int", "width": 110} for m in months]

	companies = company_with_descendants(filters.company)
	if not companies:
		return columns, []
	rows = frappe.db.sql(
		"""select rl.company, rl.project, p.project_name,
			greatest(rl.grouped_delivery_date, %(month0)s) as month, count(distinct rl.item_code) as items
		from `tabRequirement Log` rl left join `tabProject` p on p.name = rl.project
		where rl.company in %(companies)s and rl.reservation_type = 'Shortage' and ifnull(rl.level, 0) > 0
			and rl.grouped_delivery_date < %(upto)s
		group by rl.company, rl.project, p.project_name, month
		order by rl.company, rl.project""",
		{"companies": tuple(companies), "month0": month0, "upto": add_months(month0, months_count)},
		as_dict=True,
	)
	out = {}
	for r in rows:
		row = out.setdefault((r.company, r.project), {"company": r.company, "project": r.project,
			"project_name": r.project_name})
		row[month_key(r.month)] = row.get(month_key(r.month), 0) + cint(r["items"])
	return columns, list(out.values())
