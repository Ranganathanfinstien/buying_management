# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt

"""Purchase Receipt to be Billed (BRD v2 section 12, Finance).

Submitted receipts not yet fully billed, grouped by supplier and supplier invoice number so
Accounts can book one Purchase Invoice per supplier invoice ("Receipts by Supplier Invoice No" on
the Purchase Invoice). The earlier version only listed status "To Bill" and ignored partly
billed receipts); the pending amount is now shown per group.
"""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(filters), get_data(filters)


def _has_bill_field():
	return frappe.get_meta("Purchase Receipt").has_field("ub_supplier_invoice_no")


def get_columns(filters):
	cols = [
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 160},
		{"label": _("Supplier Name"), "fieldname": "supplier_name", "fieldtype": "Data", "width": 180},
		{"label": _("Supplier Invoice No"), "fieldname": "supplier_invoice_no", "fieldtype": "Data", "width": 150},
	]
	if filters.get("show_receipts"):
		cols.append({"label": _("Purchase Receipt"), "fieldname": "purchase_receipt", "fieldtype": "Link", "options": "Purchase Receipt", "width": 160})
	else:
		cols.append({"label": _("Receipts"), "fieldname": "receipts", "fieldtype": "Int", "width": 80})
	cols += [
		{"label": _("Oldest Receipt Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 110},
		{"label": _("Currency"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "width": 80},
		{"label": _("Receipt Value"), "fieldname": "total", "fieldtype": "Currency", "options": "currency", "width": 130},
		{"label": _("Billed"), "fieldname": "billed", "fieldtype": "Currency", "options": "currency", "width": 130},
		{"label": _("To Bill"), "fieldname": "pending", "fieldtype": "Currency", "options": "currency", "width": 130},
	]
	return cols


def get_data(filters):
	bill_expr = "ifnull(pr.ub_supplier_invoice_no, '')" if _has_bill_field() else "''"
	conditions = ["pr.docstatus = 1", "pr.is_return = 0", "pr.status in ('To Bill', 'Partly Billed')"]
	values = {}
	for key, cond in (
		("company", "pr.company = %(company)s"),
		("supplier", "pr.supplier = %(supplier)s"),
		("from_date", "pr.posting_date >= %(from_date)s"),
		("to_date", "pr.posting_date <= %(to_date)s"),
	):
		if filters.get(key):
			conditions.append(cond)
			values[key] = filters.get(key)
	if filters.get("supplier_invoice_no") and _has_bill_field():
		conditions.append("pr.ub_supplier_invoice_no like %(bill)s")
		values["bill"] = f"%{filters.supplier_invoice_no}%"

	group = "pr.supplier, supplier_invoice_no, pr.currency" + (", pr.name" if filters.get("show_receipts") else "")
	rows = frappe.db.sql(
		f"""
		select pr.supplier, max(pr.supplier_name) as supplier_name, {bill_expr} as supplier_invoice_no, pr.currency,
			min(pr.name) as purchase_receipt, count(distinct pr.name) as receipts, min(pr.posting_date) as posting_date,
			sum(pri.amount) as total, sum(ifnull(pri.billed_amt, 0)) as billed
		from `tabPurchase Receipt` pr
		inner join `tabPurchase Receipt Item` pri on pri.parent = pr.name
		where {" and ".join(conditions)}
		group by {group}
		order by posting_date, pr.supplier
		""",
		values,
		as_dict=True,
	)
	out = []
	for r in rows:
		r.pending = flt(r.total) - flt(r.billed)
		if r.pending > 0.005:
			out.append(r)
	return out
