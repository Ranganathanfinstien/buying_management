"""Whitelisted helpers for the Purchase Invoice form (BRD v2 6.27 Entry)."""

import json

import frappe
from frappe import _
from frappe.utils import flt

PR_MAKE_PI = "erpnext.stock.doctype.purchase_receipt.purchase_receipt.make_purchase_invoice"


def _pr_has(fieldname):
	return frappe.get_meta("Purchase Receipt").has_field(fieldname)


def _fallback_pending_rows(company, supplier, supplier_invoice_no):
	"""Receipt rows of submitted receipts with this supplier invoice number that still have qty to bill."""
	if not _pr_has("ub_supplier_invoice_no"):
		return []
	return frappe.db.sql(
		"""
		select pri.name as pr_detail, pri.parent as purchase_receipt, pri.purchase_order,
			pri.purchase_order_item as po_detail, pri.item_code, pri.qty,
			pri.qty - ifnull(billed.qty, 0) as pending_qty
		from `tabPurchase Receipt Item` pri
		inner join `tabPurchase Receipt` pr on pr.name = pri.parent
		left join (
			select pii.pr_detail, sum(pii.qty) as qty
			from `tabPurchase Invoice Item` pii
			inner join `tabPurchase Invoice` pi on pi.name = pii.parent
			where pi.docstatus = 1 and pi.supplier = %(supplier)s and pi.company = %(company)s
			group by pii.pr_detail
		) billed on billed.pr_detail = pri.name
		where pr.docstatus = 1 and pr.is_return = 0 and pr.status not in ('Closed', 'Completed')
			and pr.company = %(company)s and pr.supplier = %(supplier)s
			and pr.ub_supplier_invoice_no = %(bill)s
			and pri.qty - ifnull(billed.qty, 0) > 0
		order by pr.posting_date, pri.idx
		""",
		{"company": company, "supplier": supplier, "bill": supplier_invoice_no},
		as_dict=True,
	)


def get_pending_rows(company, supplier, supplier_invoice_no):
	"""Rows from worker E's contract, falling back to a local query."""
	try:
		from universal_buying.ub_inward.api import get_pending_receipt_rows
	except ImportError:
		get_pending_receipt_rows = None

	rows = None
	if get_pending_receipt_rows:
		try:
			rows = get_pending_receipt_rows(company, supplier, supplier_invoice_no)
		except Exception:
			frappe.log_error(title="UB Finance: get_pending_receipt_rows failed")
			rows = None
	if rows is None:
		rows = _fallback_pending_rows(company, supplier, supplier_invoice_no)

	out = []
	for r in rows or []:
		r = frappe._dict(r)
		pr_detail = r.get("pr_detail") or r.get("purchase_receipt_item") or r.get("name")
		receipt = r.get("purchase_receipt") or r.get("parent")
		if pr_detail and receipt:
			out.append(frappe._dict(pr_detail=pr_detail, purchase_receipt=receipt))
	return out


def _make_pi_method():
	overrides = frappe.get_hooks("override_whitelisted_methods") or {}
	path = overrides.get(PR_MAKE_PI)
	path = path[-1] if isinstance(path, list) else path
	return frappe.get_attr(path or PR_MAKE_PI)


@frappe.whitelist()
def get_items_by_supplier_invoice(target_doc, supplier_invoice_no=None):
	"""Replace the invoice lines with every unbilled receipt row carrying this supplier invoice number.

	Rows are mapped with ERPNext's standard Purchase Receipt -> Purchase Invoice mapper so
	po_detail / pr_detail / pending qty / warehouses / taxes stay standard. Cost centre and
	expense account are left as ERPNext sets them (no "blank by design" step).
	"""
	if isinstance(target_doc, str):
		target_doc = json.loads(target_doc)
	doc = frappe.get_doc(target_doc)
	doc.check_permission("write" if not doc.is_new() else "create")

	bill_no = (supplier_invoice_no or doc.get("bill_no") or "").strip()
	if not (doc.company and doc.supplier and bill_no):
		frappe.throw(_("Set Company, Supplier and Supplier Invoice No first."))

	rows = get_pending_rows(doc.company, doc.supplier, bill_no)
	if not rows:
		frappe.throw(
			_("No unbilled Purchase Receipt rows found for supplier {0} with supplier invoice no {1}.").format(
				frappe.bold(doc.supplier), frappe.bold(bill_no)
			)
		)

	by_receipt = {}
	for r in rows:
		by_receipt.setdefault(r.purchase_receipt, []).append(r.pr_detail)

	doc.set("items", [])
	doc.set("taxes", [])
	make_pi = _make_pi_method()
	# taxes are not merged: ERPNext's merge_taxes adds whole-receipt tax amounts, which overstates
	# partly billed receipts. The last receipt's (rate based) tax rows are kept and recomputed.
	for receipt, details in by_receipt.items():
		doc = make_pi(receipt, target_doc=doc, args={"filtered_children": details})

	doc.bill_no = bill_no
	receipt_names = list(by_receipt)
	if _pr_has("ub_boe_no") and not doc.get("ub_boe_no"):
		boe = frappe.db.get_value("Purchase Receipt", {"name": ("in", receipt_names), "ub_boe_no": ("is", "set")},
			["ub_boe_no", "ub_boe_date"] if _pr_has("ub_boe_date") else ["ub_boe_no"], as_dict=True)
		if boe:
			doc.ub_boe_no = boe.ub_boe_no
			doc.ub_boe_date = boe.get("ub_boe_date")
	return doc.as_dict()


@frappe.whitelist()
def get_receipt_exchange_rate(boe_no, company=None, supplier=None):
	"""Exchange rate of the latest submitted Purchase Receipt with this Bill of Entry number."""
	if not boe_no:
		frappe.throw(_("Enter the Bill of Entry No first."))
	if not _pr_has("ub_boe_no"):
		return {"status": "error", "message": _("Purchase Receipt has no Bill of Entry field.")}
	filters = {"ub_boe_no": boe_no, "docstatus": 1}
	if company:
		filters["company"] = company
	if supplier:
		filters["supplier"] = supplier
	fields = ["name", "conversion_rate", "currency"] + (["ub_boe_date"] if _pr_has("ub_boe_date") else [])
	rows = frappe.get_all("Purchase Receipt", filters=filters, fields=fields, order_by="posting_date desc, creation desc", limit=1)
	if not rows or not flt(rows[0].conversion_rate):
		return {"status": "error", "message": _("No submitted Purchase Receipt found for Bill of Entry {0}.").format(boe_no)}
	r = rows[0]
	return {
		"status": "success",
		"conversion_rate": flt(r.conversion_rate),
		"currency": r.currency,
		"purchase_receipt": r.name,
		"boe_date": r.get("ub_boe_date"),
	}
