# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt

"""Pending Supplier Quotations (BRD v2 section 12, Sourcing): invited parties that have not quoted yet
on RFQs whose bidding is still open."""

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from universal_buying.ub_sourcing.bidding import RFQ_BID_FIELDS, get_bid_state, quoted_parties


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("RFQ"), "fieldname": "rfq", "fieldtype": "Link", "options": "Request for Quotation", "width": 170},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 160},
		{"label": _("Prospective Supplier"), "fieldname": "prospective_supplier", "fieldtype": "Link",
		 "options": "Prospective Supplier", "width": 170},
		{"label": _("Name"), "fieldname": "supplier_name", "fieldtype": "Data", "width": 170},
		{"label": _("Email"), "fieldname": "email_id", "fieldtype": "Data", "width": 190},
		{"label": _("Invitation Sent"), "fieldname": "email_sent", "fieldtype": "Check", "width": 90},
		{"label": _("Bid Deadline"), "fieldname": "deadline", "fieldtype": "Datetime", "width": 150},
		{"label": _("Hours Left"), "fieldname": "hours_left", "fieldtype": "Float", "precision": 1, "width": 90},
		{"label": _("Bidding"), "fieldname": "bid_state", "fieldtype": "Data", "width": 110},
	]


def get_data(filters):
	conditions = {"docstatus": 1}
	if filters.company:
		conditions["company"] = filters.company
	if filters.rfq:
		conditions["name"] = filters.rfq
	data = []
	now = now_datetime()
	for r in frappe.get_all("Request for Quotation", filters=conditions, fields=RFQ_BID_FIELDS, limit_page_length=0):
		state = get_bid_state(r, now=now)
		if state.closed and not filters.include_closed:
			continue
		quoted, quoted_ps = quoted_parties(r.name)
		rows = frappe.get_all(
			"Request for Quotation Supplier",
			filters={"parent": r.name, "parenttype": "Request for Quotation"},
			fields=["supplier", "ub_prospective_supplier", "supplier_name", "email_id", "email_sent"],
			order_by="idx",
		)
		for row in rows:
			if (row.supplier and row.supplier in quoted) or (
				not row.supplier and row.ub_prospective_supplier in quoted_ps
			):
				continue
			data.append({
				"rfq": r.name,
				"supplier": row.supplier,
				"prospective_supplier": row.ub_prospective_supplier,
				"supplier_name": row.supplier_name,
				"email_id": row.email_id,
				"email_sent": row.email_sent,
				"deadline": state.deadline,
				"hours_left": flt(state.seconds_left) / 3600 if state.seconds_left else None,
				"bid_state": state.label,
			})
	return data
