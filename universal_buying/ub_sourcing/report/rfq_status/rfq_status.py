# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt

"""RFQ Status (BRD v2 section 12, Sourcing): one row per RFQ with bidding and approval progress."""

import frappe
from frappe import _

from universal_buying.ub_sourcing.bidding import get_bid_state


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("RFQ"), "fieldname": "name", "fieldtype": "Link", "options": "Request for Quotation", "width": 170},
		{"label": _("Date"), "fieldname": "transaction_date", "fieldtype": "Date", "width": 95},
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 150},
		{"label": _("PO Type"), "fieldname": "ub_po_type", "fieldtype": "Link", "options": "PO Type", "width": 80},
		{"label": _("Workflow State"), "fieldname": "workflow_state", "fieldtype": "Data", "width": 190},
		{"label": _("Bidding"), "fieldname": "bid_state", "fieldtype": "Data", "width": 120},
		{"label": _("Bid Deadline"), "fieldname": "ub_bid_deadline", "fieldtype": "Datetime", "width": 150},
		{"label": _("Invited"), "fieldname": "invited", "fieldtype": "Int", "width": 70},
		{"label": _("Quoted"), "fieldname": "quoted", "fieldtype": "Int", "width": 70},
		{"label": _("Awarded Quotation"), "fieldname": "ub_awarded_quotation", "fieldtype": "Link",
		 "options": "Supplier Quotation", "width": 160},
		{"label": _("Owner"), "fieldname": "owner", "fieldtype": "Link", "options": "User", "width": 150},
	]


def get_data(filters):
	conditions = {"docstatus": ["<", 2]}
	if filters.company:
		conditions["company"] = filters.company
	if filters.from_date and filters.to_date:
		conditions["transaction_date"] = ["between", [filters.from_date, filters.to_date]]
	if filters.workflow_state:
		conditions["workflow_state"] = filters.workflow_state
	rfqs = frappe.get_all(
		"Request for Quotation",
		filters=conditions,
		fields=["name", "transaction_date", "company", "ub_po_type", "workflow_state", "ub_bid_status",
			"ub_bid_deadline", "ub_awarded_quotation", "owner", "docstatus"],
		order_by="transaction_date desc, name desc",
		limit_page_length=0,
	)
	if not rfqs:
		return []
	names = [r.name for r in rfqs]
	invited = dict(frappe.db.sql(
		"""SELECT parent, COUNT(*) FROM `tabRequest for Quotation Supplier`
		WHERE parenttype = 'Request for Quotation' AND parent IN %(names)s GROUP BY parent""",
		{"names": names},
	))
	quoted = dict(frappe.db.sql(
		"""SELECT sqi.request_for_quotation, COUNT(DISTINCT COALESCE(NULLIF(sq.supplier, ''), sq.ub_prospective_supplier))
		FROM `tabSupplier Quotation` sq JOIN `tabSupplier Quotation Item` sqi ON sqi.parent = sq.name
		WHERE sq.docstatus < 2 AND IFNULL(sq.ub_revised, 0) = 0 AND sqi.request_for_quotation IN %(names)s
		GROUP BY sqi.request_for_quotation""",
		{"names": names},
	))
	for r in rfqs:
		r.bid_state = get_bid_state(r).label
		r.invited = invited.get(r.name, 0)
		r.quoted = quoted.get(r.name, 0)
	if filters.open_only:
		rfqs = [r for r in rfqs if r.bid_state in (_("Open"), _("Closing Soon"))]
	return rfqs
