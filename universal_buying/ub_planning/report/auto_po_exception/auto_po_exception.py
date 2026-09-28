# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt

"""Auto PO Exception report - what an Auto PO Run would put on the exception today (no anti-duplication).

Uses the same planning code as Auto PO Run (settings driven buffer, bucket, ABC thresholds, MOQ).
"""

import frappe
from frappe import _
from frappe.utils import cint

from universal_buying.ub_planning import planning
from universal_buying.universal_buying.settings import get_setting


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company or not filters.to_date:
		return get_columns(), []
	project = filters.project if cint(get_setting("plan_by_project", company=filters.company)) else None
	rows = planning.compute_exception_rows(filters.company, filters.to_date, project,
		cint(filters.lead_time_order), skip_handled=False)
	if filters.exception_type:
		rows = [r for r in rows if r.exception_type == filters.exception_type]
	return get_columns(), rows


def get_columns():
	return [
		{"label": _("Exception Type"), "fieldname": "exception_type", "fieldtype": "Data", "width": 120},
		{"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 120},
		{"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 150},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 160},
		{"label": _("Class"), "fieldname": "item_class", "fieldtype": "Data", "width": 60},
		{"label": _("Shortage"), "fieldname": "po_shortage", "fieldtype": "Float", "width": 100},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Link", "options": "UOM", "width": 70},
		{"label": _("MOQ"), "fieldname": "moq", "fieldtype": "Float", "width": 80},
		{"label": _("SPQ"), "fieldname": "spq", "fieldtype": "Float", "width": 80},
		{"label": _("Required By"), "fieldname": "required_by", "fieldtype": "Date", "width": 100},
		{"label": _("Default Supplier"), "fieldname": "default_supplier", "fieldtype": "Link", "options": "Supplier",
			"width": 150},
		{"label": _("Rate"), "fieldname": "rate", "fieldtype": "Float", "width": 90},
		{"label": _("Currency"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "width": 70},
		{"label": _("MPN"), "fieldname": "mpn", "fieldtype": "Data", "width": 130},
	]
