"""Weekly ABC classification of purchased items .

Value = consumption of the item in submitted Manufacture Stock Entries (raw material lines) over the
last ``abc_lookback_months`` months, limited to items the company has bought (submitted PO line).
Scope from setting ``abc_scope``: per Project (rows carry the project) or per Company (project empty).

Pareto split (settings ``abc_pareto_a_percent`` / ``abc_pareto_b_percent``, defaults 70 / 90): items are
ranked by value; an item is A while the cumulative share *before* it is below the A cut, B below the B
cut, else C. (The earlier code tested the share *including* the item, so a single dominant item became
B, and it silently dropped the last project of the loop.)
"""

from collections import defaultdict

import frappe
from frappe.utils import add_months, cint, flt, now_datetime, nowdate

from universal_buying.universal_buying.settings import get_setting

DOCTYPE = "Item Classification"


def scheduled_classification():
	frappe.enqueue(
		"universal_buying.ub_planning.item_classification.run_for_all_companies",
		queue="long",
		timeout=3600,
		job_id="ub_item_classification",
		deduplicate=True,
	)


@frappe.whitelist()
def enqueue_classification():
	frappe.has_permission("Requirement Rebuild", "create", throw=True)
	scheduled_classification()
	return "queued"


def run_for_all_companies():
	for company in frappe.get_all("Company", filters={"is_group": 0}, pluck="name"):
		try:
			rows = compute_classification(company)
			write_classification(company, rows)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"Item Classification failed for {company}")


def get_consumption(company, scope, months):
	group_project = scope == "Project"
	project_select = "se.project" if group_project else "null"
	project_group = ", se.project" if group_project else ""
	project_cond = "and ifnull(se.project, '') != ''" if group_project else ""
	return frappe.db.sql(
		f"""
		select sed.item_code, {project_select} as project, sum(sed.basic_amount) as value
		from `tabStock Entry Detail` sed
		inner join `tabStock Entry` se on se.name = sed.parent
		where se.docstatus = 1 and se.company = %(company)s and se.purpose = 'Manufacture'
			and ifnull(sed.is_finished_item, 0) = 0 and ifnull(sed.s_warehouse, '') != ''
			and se.posting_date >= %(from_date)s {project_cond}
			and exists (
				select 1 from `tabPurchase Order Item` poi
				inner join `tabPurchase Order` po on po.name = poi.parent
				where po.docstatus = 1 and po.company = %(company)s and poi.item_code = sed.item_code
			)
		group by sed.item_code{project_group}
		having value > 0
		""",
		{"company": company, "from_date": add_months(nowdate(), -months)},
		as_dict=True,
	)


def classify(values, cut_a=70.0, cut_b=90.0):
	"""values: list of (key, value). Returns {key: (class, cumulative_percent_before)}."""
	total = sum(flt(v) for _k, v in values)
	result = {}
	if total <= 0:
		return result
	cumulative = 0.0
	for key, value in sorted(values, key=lambda kv: (-flt(kv[1]), str(kv[0]))):
		before = cumulative / total * 100.0
		if before < cut_a:
			cls = "A"
		elif before < cut_b:
			cls = "B"
		else:
			cls = "C"
		result[key] = (cls, flt(before, 4))
		cumulative += flt(value)
	return result


def compute_classification(company):
	scope = get_setting("abc_scope") or "Project"
	months = cint(get_setting("abc_lookback_months", default=6)) or 6
	cut_a = flt(get_setting("abc_pareto_a_percent", default=70)) or 70.0
	cut_b = flt(get_setting("abc_pareto_b_percent", default=90)) or 90.0

	groups = defaultdict(list)
	for row in get_consumption(company, scope, months):
		groups[row.project].append((row.item_code, flt(row.value)))

	computed_on = now_datetime()
	rows = []
	for project, values in groups.items():
		value_map = dict(values)
		for item_code, (cls, before) in classify(values, cut_a, cut_b).items():
			rows.append({
				"item_code": item_code,
				"company": company,
				"project": project or None,
				"item_class": cls,
				"value": value_map[item_code],
				"cumulative_percent": before,
				"computed_on": computed_on,
			})
	return rows


def write_classification(company, rows):
	frappe.db.delete(DOCTYPE, {"company": company})
	if not rows:
		return
	prefix = frappe.generate_hash(length=8)
	ts = frappe.utils.now()
	user = frappe.session.user or "Administrator"
	fields = ["name", "item_code", "company", "project", "item_class", "value", "cumulative_percent", "computed_on",
		"creation", "modified", "owner", "modified_by", "docstatus"]
	values = (
		[f"{prefix}-{i}", r["item_code"], r["company"], r["project"], r["item_class"], r["value"],
			r["cumulative_percent"], r["computed_on"], ts, ts, user, user, 0]
		for i, r in enumerate(rows, 1)
	)
	frappe.db.bulk_insert(DOCTYPE, fields, values, chunk_size=5000)
