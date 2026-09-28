# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt

"""Invoice Variance (BRD v2 section 12, Finance): Purchase Invoice lines against their Purchase Order lines.

Rate variance = invoice rate - PO rate (per unit, in the invoice's UOM converted to the PO's UOM
through stock qty); amount variance = rate variance x invoiced qty. Qty variance = total billed qty
of the PO line on all submitted invoices - PO line qty (positive = over billed).
"""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Purchase Invoice"), "fieldname": "purchase_invoice", "fieldtype": "Link", "options": "Purchase Invoice", "width": 150},
		{"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 140},
		{"label": _("Purchase Order"), "fieldname": "purchase_order", "fieldtype": "Link", "options": "Purchase Order", "width": 150},
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 140},
		{"label": _("Currency"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "width": 70},
		{"label": _("PO Qty"), "fieldname": "po_qty", "fieldtype": "Float", "width": 90},
		{"label": _("Received Qty"), "fieldname": "received_qty", "fieldtype": "Float", "width": 90},
		{"label": _("Invoiced Qty"), "fieldname": "pi_qty", "fieldtype": "Float", "width": 90},
		{"label": _("Total Billed Qty"), "fieldname": "billed_qty", "fieldtype": "Float", "width": 100},
		{"label": _("Qty Variance"), "fieldname": "qty_variance", "fieldtype": "Float", "width": 100},
		{"label": _("PO Rate"), "fieldname": "po_rate", "fieldtype": "Currency", "options": "currency", "width": 110},
		{"label": _("Invoice Rate"), "fieldname": "pi_rate", "fieldtype": "Currency", "options": "currency", "width": 110},
		{"label": _("Rate Variance"), "fieldname": "rate_variance", "fieldtype": "Currency", "options": "currency", "width": 110},
		{"label": _("Rate Variance %"), "fieldname": "rate_variance_pct", "fieldtype": "Percent", "width": 100},
		{"label": _("Amount Variance"), "fieldname": "amount_variance", "fieldtype": "Currency", "options": "currency", "width": 120},
	]


def get_data(filters):
	conditions = ["pi.docstatus = 1", "pi.is_return = 0", "ifnull(pii.po_detail, '') != ''"]
	values = {}
	for key, cond in (
		("company", "pi.company = %(company)s"),
		("supplier", "pi.supplier = %(supplier)s"),
		("from_date", "pi.posting_date >= %(from_date)s"),
		("to_date", "pi.posting_date <= %(to_date)s"),
		("purchase_order", "pii.purchase_order = %(purchase_order)s"),
		("item_code", "pii.item_code = %(item_code)s"),
	):
		if filters.get(key):
			conditions.append(cond)
			values[key] = filters.get(key)

	rows = frappe.db.sql(
		f"""
		select pi.name as purchase_invoice, pi.posting_date, pi.supplier, pi.currency, pi.conversion_rate as pi_conversion,
			pii.purchase_order, pii.po_detail, pii.item_code, pii.qty as pi_qty, pii.stock_qty as pi_stock_qty,
			pii.rate as pi_rate, pii.base_rate as pi_base_rate, pii.conversion_factor as pi_cf,
			poi.qty as po_qty, poi.received_qty, poi.rate as po_rate, poi.base_rate as po_base_rate,
			poi.conversion_factor as po_cf, po.currency as po_currency
		from `tabPurchase Invoice Item` pii
		inner join `tabPurchase Invoice` pi on pi.name = pii.parent
		inner join `tabPurchase Order Item` poi on poi.name = pii.po_detail
		inner join `tabPurchase Order` po on po.name = poi.parent
		where {" and ".join(conditions)}
		order by pi.posting_date desc, pi.name, pii.idx
		""",
		values,
		as_dict=True,
	)
	if not rows:
		return []

	billed = dict(
		frappe.db.sql(
			"""select pii.po_detail, sum(pii.stock_qty / ifnull(nullif(poi.conversion_factor, 0), 1))
			from `tabPurchase Invoice Item` pii
			inner join `tabPurchase Invoice` pi on pi.name = pii.parent
			inner join `tabPurchase Order Item` poi on poi.name = pii.po_detail
			where pi.docstatus = 1 and pi.is_return = 0 and pii.po_detail in %(details)s
			group by pii.po_detail""",
			{"details": tuple({r.po_detail for r in rows})},
		)
	)

	out = []
	for r in rows:
		same_ccy = r.currency == r.po_currency
		# compare per PO unit: invoice rate per stock unit x PO conversion factor
		pi_rate_txn = flt(r.pi_rate) / (flt(r.pi_cf) or 1) * (flt(r.po_cf) or 1)
		pi_rate_base = flt(r.pi_base_rate) / (flt(r.pi_cf) or 1) * (flt(r.po_cf) or 1)
		po_rate = flt(r.po_rate) if same_ccy else flt(r.po_base_rate)
		pi_rate = pi_rate_txn if same_ccy else pi_rate_base
		qty_po_uom = flt(r.pi_stock_qty) / (flt(r.po_cf) or 1)

		r.pi_rate = pi_rate
		r.po_rate = po_rate
		if not same_ccy:
			r.currency = frappe.get_cached_value("Company", filters.get("company"), "default_currency") if filters.get("company") else None
		r.pi_qty = qty_po_uom
		r.billed_qty = flt(billed.get(r.po_detail))
		r.qty_variance = r.billed_qty - flt(r.po_qty)
		r.rate_variance = pi_rate - po_rate
		r.rate_variance_pct = (r.rate_variance / po_rate * 100.0) if po_rate else 0
		r.amount_variance = r.rate_variance * qty_po_uom

		if filters.get("only_variance") and abs(r.rate_variance) < 0.005 and r.qty_variance <= 0.0001:
			continue
		out.append(r)
	return out
