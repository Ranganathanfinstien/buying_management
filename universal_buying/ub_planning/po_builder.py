"""Draft Purchase Order builder used by Auto PO Run, Auto PO Exception and the consumables job.

Taxes are not hard-coded (no forced In-State / Out-State templates): ERPNext resolves them through
``set_missing_values()`` (party details -> Tax Rule / supplier / address based template) and, when that
yields nothing, the company default template via ``set_taxes()``. Import POs are flagged with
``ub_is_import`` when the supplier address country differs from the company country.
"""

import frappe
from frappe.utils import flt, getdate, nowdate

from universal_buying.universal_buying.utils import set_po_origin


def _has(meta, fieldname):
	return bool(meta.has_field(fieldname))


def build_purchase_order(company, supplier, lines, origin_doctype, origin_name=None, currency=None,
		price_list=None, project=None, insert=True):
	"""Create (and insert) one draft Purchase Order.

	lines: dicts with item_code, qty, uom, rate, schedule_date and optional project, manufacturer,
	manufacturer_part_no, required_by, supplier_delivery_date, material_request, material_request_item,
	skip_moq, warehouse, description.
	"""
	today = getdate(nowdate())
	po = frappe.new_doc("Purchase Order")
	po.company = company
	po.supplier = supplier
	po.transaction_date = today
	if currency:
		po.currency = currency
	if price_list:
		po.buying_price_list = price_list
	if project:
		po.project = project
	po.ignore_pricing_rule = 1
	set_po_origin(po, origin_doctype, origin_name)

	item_meta = frappe.get_meta("Purchase Order Item")
	schedule_dates = []
	for line in lines:
		schedule_date = max(getdate(line.get("schedule_date") or today), today)
		schedule_dates.append(schedule_date)
		row = {
			"item_code": line["item_code"],
			"qty": flt(line["qty"]),
			"uom": line.get("uom"),
			"schedule_date": schedule_date,
			"rate": flt(line.get("rate")),
			"price_list_rate": flt(line.get("rate")),
			"discount_percentage": 0,
			"margin_rate_or_amount": 0,
			"project": line.get("project") or project,
			"manufacturer": line.get("manufacturer"),
			"manufacturer_part_no": line.get("manufacturer_part_no"),
			"material_request": line.get("material_request"),
			"material_request_item": line.get("material_request_item"),
		}
		if line.get("warehouse"):
			row["warehouse"] = line["warehouse"]
		if line.get("description"):
			row["description"] = line["description"]
		optional = {
			"ub_required_by": line.get("required_by"),
			"ub_supplier_delivery_date": line.get("supplier_delivery_date"),
			"ub_skip_moq": 1 if line.get("skip_moq") else None,
		}
		for fieldname, value in optional.items():
			if value is not None and _has(item_meta, fieldname):
				row[fieldname] = value
		po.append("items", {k: v for k, v in row.items() if v is not None})

	po.schedule_date = min(schedule_dates) if schedule_dates else today
	po.set_missing_values()

	# keep our rates (set_missing_values only fills blanks, this is a guard)
	for row, line in zip(po.items, lines, strict=False):
		row.rate = flt(line.get("rate"))
		row.price_list_rate = row.price_list_rate or row.rate
		row.discount_percentage = 0
		row.discount_amount = 0
		row.margin_rate_or_amount = 0

	if not po.get("taxes"):
		# no Tax Rule / party template matched: fall back to the company default template
		po.set_taxes()

	set_import_flag(po)
	po.calculate_taxes_and_totals()
	if insert:
		po.flags.ignore_permissions = True
		po.insert()
	return po


def set_import_flag(po):
	if not _has(po.meta, "ub_is_import"):
		return
	supplier_country = None
	if po.get("supplier_address"):
		supplier_country = frappe.db.get_value("Address", po.supplier_address, "country")
	if not supplier_country:
		supplier_country = frappe.db.get_value("Supplier", po.supplier, "country")
	company_country = frappe.get_cached_value("Company", po.company, "country")
	po.ub_is_import = 1 if (supplier_country and company_country and supplier_country != company_country) else 0
