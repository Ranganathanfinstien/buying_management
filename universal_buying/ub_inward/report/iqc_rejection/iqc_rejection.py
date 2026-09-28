# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt

"""IQC Rejection: rejected incoming inspections with the rejected qty and the non conformance follow-up (BR-18)."""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{
			"fieldname": "quality_inspection",
			"label": _("Quality Inspection"),
			"fieldtype": "Link",
			"options": "Quality Inspection",
			"width": 150,
		},
		{"fieldname": "report_date", "label": _("Date"), "fieldtype": "Date", "width": 95},
		{
			"fieldname": "purchase_receipt",
			"label": _("Purchase Receipt"),
			"fieldtype": "Link",
			"options": "Purchase Receipt",
			"width": 150,
		},
		{
			"fieldname": "supplier",
			"label": _("Supplier"),
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 150,
		},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 140},
		{"fieldname": "batch_no", "label": _("Batch"), "fieldtype": "Link", "options": "Batch", "width": 130},
		{"fieldname": "lot_qty", "label": _("Lot Qty"), "fieldtype": "Float", "width": 90},
		{"fieldname": "sample_size", "label": _("Sample Size"), "fieldtype": "Float", "width": 90},
		{"fieldname": "sample_taken", "label": _("Sample Taken"), "fieldtype": "Float", "width": 90},
		{"fieldname": "rejected_qty", "label": _("Rejected Qty"), "fieldtype": "Float", "width": 100},
		{"fieldname": "rejected_value", "label": _("Rejected Value"), "fieldtype": "Currency", "width": 120},
		{
			"fieldname": "item_non_conformance",
			"label": _("Non Conformance"),
			"fieldtype": "Link",
			"options": "Item Non Conformance",
			"width": 150,
		},
		{"fieldname": "disposition", "label": _("Disposition"), "fieldtype": "Data", "width": 130},
		{"fieldname": "inc_status", "label": _("INC Status"), "fieldtype": "Data", "width": 90},
		{"fieldname": "remarks", "label": _("Remarks"), "fieldtype": "Data", "width": 200},
	]


def get_data(filters):
	conditions = [
		"qi.docstatus = 1",
		"qi.status = 'Rejected'",
		"qi.reference_type = 'Purchase Receipt'",
		"qi.company = %(company)s",
	]
	if filters.get("from_date"):
		conditions.append("qi.report_date >= %(from_date)s")
	if filters.get("to_date"):
		conditions.append("qi.report_date <= %(to_date)s")
	if filters.get("item_code"):
		conditions.append("qi.item_code = %(item_code)s")
	if filters.get("supplier"):
		conditions.append("pr.supplier = %(supplier)s")

	rows = frappe.db.sql(
		f"""
		select qi.name as quality_inspection, qi.report_date, qi.reference_name as purchase_receipt, pr.supplier,
			qi.item_code, qi.batch_no, qi.ub_batch_qty as lot_qty, qi.sample_size, qi.ub_sample_taken as sample_taken,
			qi.remarks, inc.name as item_non_conformance, inc.disposition, inc.status as inc_status,
			inc.rejected_qty as inc_qty, inc.amount as inc_amount
		from `tabQuality Inspection` qi
		inner join `tabPurchase Receipt` pr on pr.name = qi.reference_name
		left join `tabItem Non Conformance` inc on inc.quality_inspection = qi.name and inc.docstatus < 2
		where {" and ".join(conditions)}
		order by qi.report_date desc, qi.name
		""",
		filters,
		as_dict=True,
	)
	for r in rows:
		if r.item_non_conformance:
			r.rejected_qty = flt(r.inc_qty)
			r.rejected_value = flt(r.inc_amount)
		else:
			cond = {"parent": r.purchase_receipt, "item_code": r.item_code}
			if r.batch_no:
				cond["batch_no"] = r.batch_no
			agg = frappe.get_all(
				"Purchase Receipt Item",
				filters=cond,
				fields=["rejected_qty", "conversion_factor", "base_net_rate"],
			)
			r.rejected_qty = sum(flt(a.rejected_qty) * flt(a.conversion_factor or 1) for a in agg)
			r.rejected_value = sum(flt(a.rejected_qty) * flt(a.base_net_rate) for a in agg)
	return rows
