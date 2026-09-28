"""UB Inward public API (whitelisted endpoints and the BUILD_SPEC 6.3 contract)."""

import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, nowdate

from universal_buying.universal_buying.settings import get_list, get_setting, has_any_role

# ---------------------------------------------------------------------------
# contract (BUILD_SPEC 6.3) - used by UB Finance
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_pending_receipt_rows(company, supplier, supplier_invoice_no):
	"""Submitted receipt rows of a supplier invoice number that are not fully billed yet.

	Returns a list of dicts: purchase_receipt, purchase_receipt_item, posting_date, item_code, item_name,
	uom, qty, returned_qty, billed_qty, pending_qty, rate, base_rate, pending_amount, currency,
	purchase_order, purchase_order_item, warehouse, batch_no, ub_boe_no, ub_boe_date.
	"""
	if not frappe.has_permission("Purchase Receipt", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if not (company and supplier and supplier_invoice_no):
		return []

	rows = frappe.db.sql(
		"""
		select
			pr.name as purchase_receipt, pri.name as purchase_receipt_item, pr.posting_date,
			pri.item_code, pri.item_name, pri.uom, pri.qty, ifnull(pri.returned_qty, 0) as returned_qty,
			pri.rate, pri.base_rate, pr.currency, pri.purchase_order, pri.purchase_order_item,
			pri.warehouse, pri.batch_no, pr.ub_boe_no, pr.ub_boe_date,
			ifnull((
				select sum(pii.qty) from `tabPurchase Invoice Item` pii
				where pii.pr_detail = pri.name and pii.docstatus = 1
			), 0) as billed_qty
		from `tabPurchase Receipt Item` pri
		inner join `tabPurchase Receipt` pr on pr.name = pri.parent
		where pr.docstatus = 1 and pr.is_return = 0 and pr.status != 'Closed'
			and pr.company = %(company)s and pr.supplier = %(supplier)s
			and pr.ub_supplier_invoice_no = %(invoice)s
		order by pr.posting_date, pr.name, pri.idx
		""",
		{"company": company, "supplier": supplier, "invoice": supplier_invoice_no.strip()},
		as_dict=True,
	)
	out = []
	for r in rows:
		r.pending_qty = flt(r.qty) - flt(r.returned_qty) - flt(r.billed_qty)
		if r.pending_qty <= 0.000001:
			continue
		r.pending_amount = flt(r.pending_qty * flt(r.rate))
		out.append(r)
	return out


# ---------------------------------------------------------------------------
# settings for the client scripts
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_inward_settings(company=None):
	return {
		"gate_entry_required": cint(get_setting("gate_entry_required", company=company)),
		"gate_entry_lookback_days": cint(get_setting("gate_entry_lookback_days", company=company)),
		"iqc_gate": get_setting("iqc_gate", company=company) or "Block",
		"bonded_goods_enabled": cint(get_setting("bonded_goods_enabled", company=company)),
		"background_submit_rows": cint(get_setting("background_submit_rows", company=company)),
		"can_edit_invoice_no": cint(_can_edit_invoice_no()),
	}


# ---------------------------------------------------------------------------
# Get Items From > Purchase Order (step 2)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_purchase_order_items(supplier, company, exclude_pr=None):
	"""Open PO lines of a supplier with pending qty (net of submitted receipts and returns).

	Draft receipt qty is returned separately (draft_pr_qty / draft_pr_details) for the double-receipt warning.
	"""
	frappe.has_permission("Purchase Order", "read", throw=True)
	params = {"supplier": supplier, "company": company, "exclude": exclude_pr or ""}
	return frappe.db.sql(
		"""
		select
			poi.name, poi.parent as purchase_order, poi.idx, poi.item_code, poi.item_name, poi.uom,
			poi.qty as purchase_order_qty, poi.rate, po.currency, poi.schedule_date, poi.warehouse,
			ifnull(sub.received, 0) as total_received_qty,
			poi.qty - ifnull(sub.received, 0) as pending_qty,
			ifnull(dr.qty, 0) as draft_pr_qty,
			ifnull(dr.details, '') as draft_pr_details
		from `tabPurchase Order Item` poi
		inner join `tabPurchase Order` po on po.name = poi.parent
		left join (
			select pri.purchase_order_item,
				sum(case when pr.is_return = 1 then pri.qty else pri.received_qty end) as received
			from `tabPurchase Receipt Item` pri
			inner join `tabPurchase Receipt` pr on pr.name = pri.parent
			where pr.docstatus = 1 and pr.supplier = %(supplier)s and pr.company = %(company)s
				and pri.purchase_order_item is not null
			group by pri.purchase_order_item
		) sub on sub.purchase_order_item = poi.name
		left join (
			select pri.purchase_order_item, sum(pri.received_qty) as qty,
				group_concat(distinct concat(pr.name, ':', pri.received_qty) order by pr.name separator '|') as details
			from `tabPurchase Receipt Item` pri
			inner join `tabPurchase Receipt` pr on pr.name = pri.parent
			where pr.docstatus = 0 and pr.is_return = 0 and pr.supplier = %(supplier)s
				and pr.company = %(company)s and pr.name != %(exclude)s
				and pri.purchase_order_item is not null
			group by pri.purchase_order_item
		) dr on dr.purchase_order_item = poi.name
		where po.docstatus = 1 and po.status not in ('Closed', 'On Hold', 'Completed')
			and po.supplier = %(supplier)s and po.company = %(company)s
			and ifnull(poi.delivered_by_supplier, 0) = 0
			and poi.qty - ifnull(sub.received, 0) > 0
		order by poi.schedule_date, poi.parent, poi.idx
		""",
		params,
		as_dict=True,
	)


@frappe.whitelist()
def make_purchase_receipt(source_name, target_doc=None, args=None):
	"""ERPNext's PO -> PR mapper, with qty limited to what is still pending (net of this receipt's rows)."""
	from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt as erp_make

	if isinstance(args, str):
		args = json.loads(args)
	args = frappe._dict(args or {})
	if isinstance(target_doc, str):
		target_doc = frappe.get_doc(json.loads(target_doc))

	before = {id(r) for r in (target_doc.get("items") if target_doc else [])}
	in_doc = {}
	for r in target_doc.get("items") if target_doc else []:
		if r.get("purchase_order_item"):
			in_doc[r.purchase_order_item] = in_doc.get(r.purchase_order_item, 0) + flt(r.qty)

	doc = erp_make(source_name, target_doc, {"filtered_children": args.get("filtered_children") or []})

	new_rows = [r for r in doc.get("items") if id(r) not in before]
	po_items = [r.purchase_order_item for r in new_rows if r.get("purchase_order_item")]
	from universal_buying.ub_inward.receipt import get_already_received

	received = get_already_received(po_items, doc.get("name") if not doc.is_new() else None)
	po_qty = {
		r.name: flt(r.qty)
		for r in frappe.get_all(
			"Purchase Order Item", filters={"name": ("in", po_items or [""])}, fields=["name", "qty"]
		)
	}
	client_limit = args.get("filtered_children_qty") or {}

	remove = []
	for row in new_rows:
		key = row.get("purchase_order_item")
		if not key:
			continue
		pending = po_qty.get(key, 0) - flt(received.get(key)) - flt(in_doc.get(key))
		if key in client_limit:
			pending = min(pending, flt(client_limit[key]))
		if pending <= 0:
			remove.append(row)
			continue
		in_doc[key] = flt(in_doc.get(key)) + pending
		row.qty = pending
		row.received_qty = pending
		row.stock_qty = pending * flt(row.conversion_factor or 1)
		row.amount = pending * flt(row.rate)
	for row in remove:
		doc.remove(row)

	doc.ignore_pricing_rule = 1
	doc.run_method("calculate_taxes_and_totals")
	return doc


@frappe.whitelist()
def get_item_default_warehouse(item_code, company):
	if not (item_code and company):
		return None
	return frappe.db.get_value("Item Default", {"parent": item_code, "company": company}, "default_warehouse")


# ---------------------------------------------------------------------------
# receipt buttons
# ---------------------------------------------------------------------------


def _get_draft_receipt(name):
	pr = frappe.get_doc("Purchase Receipt", name)
	pr.check_permission("write")
	if pr.docstatus != 0:
		frappe.throw(_("Purchase Receipt {0} is not a draft.").format(name))
	return pr


@frappe.whitelist()
def create_batches(purchase_receipt):
	"""Create Batches button (step 4): shelf life + MPN checks, one batch per item / mfg date / mfr batch."""
	from universal_buying.ub_inward.batch import create_batches_for_receipt

	pr = _get_draft_receipt(purchase_receipt)
	count = create_batches_for_receipt(pr)
	if count:
		pr.save()
	return {"groups": count}


@frappe.whitelist()
def check_iqc(purchase_receipt):
	"""Re-evaluate the IQC gate and store ub_iqc_complete. Returns the pending rows."""
	from universal_buying.ub_inward.iqc import check_iqc_gate

	pr = frappe.get_doc("Purchase Receipt", purchase_receipt)
	pr.check_permission("read")
	pending = check_iqc_gate(pr, submitting=False)
	frappe.db.set_value(
		"Purchase Receipt", pr.name, "ub_iqc_complete", 0 if pending else 1, update_modified=False
	)
	return [{"idx": r.idx, "item_code": r.item_code, "batch_no": r.get("batch_no")} for r in pending]


@frappe.whitelist()
def make_quality_inspections(purchase_receipt):
	"""One draft Quality Inspection per item and batch (sample size from the template's sampling band)."""
	from universal_buying.ub_inward.quality_inspection import make_inspections_for_receipt

	pr = frappe.get_doc("Purchase Receipt", purchase_receipt)
	pr.check_permission("read")
	frappe.has_permission("Quality Inspection", "create", throw=True)
	return make_inspections_for_receipt(pr)


def _can_edit_invoice_no():
	roles = (
		get_list("invoice_no_edit_roles")
		if frappe.get_meta("Buying Control Settings").has_field("invoice_no_edit_roles")
		else []
	)
	return has_any_role(roles or ["Accounts Manager", "System Manager"])


@frappe.whitelist()
def update_supplier_invoice_no(purchase_receipt, supplier_invoice_no, supplier_invoice_date=None):
	"""Correct the supplier invoice number on a submitted, not yet completed receipt."""
	if not _can_edit_invoice_no():
		frappe.throw(_("You are not allowed to change the supplier invoice number."), frappe.PermissionError)
	status, docstatus = frappe.db.get_value("Purchase Receipt", purchase_receipt, ["status", "docstatus"])
	if docstatus != 1 or status in ("Completed", "Closed"):
		frappe.throw(_("Only submitted receipts that are not completed can be changed."))
	if not (supplier_invoice_no or "").strip():
		frappe.throw(_("Supplier Invoice No is required."))
	pr = frappe.get_doc("Purchase Receipt", purchase_receipt)
	old = pr.get("ub_supplier_invoice_no")
	pr.db_set("ub_supplier_invoice_no", supplier_invoice_no.strip())
	if supplier_invoice_date:
		pr.db_set("ub_supplier_invoice_date", getdate(supplier_invoice_date))
	pr.add_comment(
		"Edit", _("Supplier Invoice No changed from {0} to {1}").format(old or "-", supplier_invoice_no)
	)
	return supplier_invoice_no


@frappe.whitelist()
def make_purchase_return(source_name, target_doc=None, return_against_rejected_qty=0):
	"""Currency-safe Purchase Return (replaces the earlier make_purchase_return + validate_return_against patch).

	ERPNext v16 maps currency and exchange rate from the receipt and requires the return to use the same
	exchange rate, so the return keeps the receipt's rate (no monkey patch of validate_return_against).
	"""
	from erpnext.controllers.sales_and_purchase_return import make_return_doc

	source = frappe.db.get_value(
		"Purchase Receipt",
		source_name,
		["currency", "conversion_rate", "price_list_currency", "plc_conversion_rate", "buying_price_list"],
		as_dict=True,
	)
	doc = make_return_doc(
		"Purchase Receipt",
		source_name,
		target_doc,
		return_against_rejected_qty=bool(cint(return_against_rejected_qty)),
	)
	if source:
		changed = False
		for field in (
			"currency",
			"conversion_rate",
			"price_list_currency",
			"plc_conversion_rate",
			"buying_price_list",
		):
			if source.get(field) and doc.get(field) != source.get(field):
				doc.set(field, source.get(field))
				changed = True
		if changed:
			doc.run_method("calculate_taxes_and_totals")
	return doc


@frappe.whitelist()
def make_inward_discrepancy(source_name, target_doc=None):
	"""Inward Discrepancy from a draft receipt (6.26)."""
	from frappe.model.mapper import get_mapped_doc

	def update_item(source, target, source_parent):
		target.invoice_qty = flt(source.received_qty) or flt(source.qty)
		target.received_qty = flt(source.received_qty) or flt(source.qty)
		target.purchase_receipt_item = source.name

	def postprocess(source, target):
		target.purchase_receipt = source.name
		target.date = nowdate()
		target.status = "Draft"

	return get_mapped_doc(
		"Purchase Receipt",
		source_name,
		{
			"Purchase Receipt": {
				"doctype": "Inward Discrepancy",
				"field_map": {"ub_supplier_invoice_no": "supplier_invoice_no", "project": "project"},
				"validation": {"docstatus": ["=", 0]},
			},
			"Purchase Receipt Item": {
				"doctype": "Inward Discrepancy Item",
				"field_map": {"rate": "rate"},
				"postprocess": update_item,
			},
		},
		target_doc,
		postprocess,
	)


# ---------------------------------------------------------------------------
# Landed Cost Voucher / Quality Inspection helpers
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_receipts_by_boe(company, boe_no):
	from universal_buying.ub_inward.landed_cost_voucher import get_receipts_by_boe as _get

	frappe.has_permission("Purchase Receipt", "read", throw=True)
	return _get(company, boe_no)


@frappe.whitelist()
def get_manufacturing_shortage_for_pr(items, company=None):
	"""Informational shortage notice after Get Items From (uses UB Planning when installed)."""
	from universal_buying.ub_inward.receipt import get_shortage_for_items, shortage_message

	if isinstance(items, str):
		items = json.loads(items)
	codes = [(r.get("item_code") if isinstance(r, dict) else r) for r in items or []]
	shortage = get_shortage_for_items(codes, company)
	return {
		"has_shortage": 1 if shortage else 0,
		"shortage": shortage,
		"message": shortage_message(shortage) if shortage else "",
	}


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def approved_manufacturer_query(doctype, txt, searchfield, start, page_len, filters):
	"""Manufacturers approved for an item (Item Manufacturer, excluding ub_disabled rows)."""
	item_code = (filters or {}).get("item_code")
	if not item_code:
		return []
	items = [item_code]
	template = frappe.db.get_value("Item", item_code, "variant_of")
	if template:
		items.append(template)
	disabled_cond = (
		"and ifnull(ub_disabled, 0) = 0"
		if frappe.get_meta("Item Manufacturer").has_field("ub_disabled")
		else ""
	)
	return frappe.db.sql(
		f"""
		select manufacturer, manufacturer_part_no
		from `tabItem Manufacturer`
		where item_code in %(items)s {disabled_cond}
			and (manufacturer like %(txt)s or manufacturer_part_no like %(txt)s)
		order by is_default desc, manufacturer
		limit %(page_len)s offset %(start)s
		""",
		{"items": tuple(items), "txt": f"%{txt}%", "page_len": cint(page_len), "start": cint(start)},
	)


@frappe.whitelist()
def gate_entry_min_date(posting_date=None, company=None):
	"""Earliest gate entry date a buyer may pick (V-22.1 lookback)."""
	days = cint(get_setting("gate_entry_lookback_days", company=company))
	if not days:
		return None
	return add_days(getdate(posting_date or nowdate()), -days)
