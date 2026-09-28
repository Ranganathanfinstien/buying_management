"""Small shared lookups for the planning module (line card, MPN, supplier, UOM)."""

import frappe
from frappe.utils import cint, flt

from universal_buying.universal_buying.settings import get_setting
from universal_buying.universal_buying.utils import supplier_is_enabled

LINE_CARD = "Supplier Line Card"
LINE_CARD_ITEM = "Supplier Line Card Item"


def line_card_available():
	return bool(frappe.db.exists("DocType", LINE_CARD) and frappe.db.exists("DocType", LINE_CARD_ITEM))


def get_item_mpns(item_code):
	"""MPN texts of an item: enabled Item Manufacturer rows plus Item.default_manufacturer_part_no."""
	filters = {"item_code": item_code}
	if frappe.get_meta("Item Manufacturer").has_field("ub_disabled"):
		filters["ub_disabled"] = 0
	mpns = [m for m in frappe.get_all("Item Manufacturer", filters=filters, pluck="manufacturer_part_no") if m]
	default_mpn = frappe.db.get_value("Item", item_code, "default_manufacturer_part_no")
	if default_mpn and default_mpn not in mpns:
		mpns.append(default_mpn)
	return mpns


def get_line_card_rows(item_code, company):
	"""Line card rows matching the item's MPN text for a company, shortest lead time first.

	Supplier Line Card (worker A): parent has supplier + company, child Supplier Line Card Item has
	manufacturer_part_no, manufacturer, lead_time_days, min_order_qty, standard_packing_qty.
	"""
	if not line_card_available():
		return []
	mpns = get_item_mpns(item_code)
	if not mpns:
		return []

	parent_meta = frappe.get_meta(LINE_CARD)
	conditions = ["lci.manufacturer_part_no in %(mpns)s", "lc.company = %(company)s"]
	if parent_meta.is_submittable:
		conditions.append("lc.docstatus = 1")
	else:
		conditions.append("lc.docstatus < 2")
	if parent_meta.has_field("disabled"):
		conditions.append("ifnull(lc.disabled, 0) = 0")

	rows = frappe.db.sql(
		f"""
		select lc.supplier, lci.manufacturer_part_no, lci.manufacturer,
			ifnull(lci.lead_time_days, 0) as lead_time_days,
			ifnull(lci.min_order_qty, 0) as min_order_qty,
			ifnull(lci.standard_packing_qty, 0) as standard_packing_qty
		from `tab{LINE_CARD_ITEM}` lci
		inner join `tab{LINE_CARD}` lc on lc.name = lci.parent and lci.parenttype = %(parenttype)s
		where {" and ".join(conditions)}
		order by ifnull(lci.lead_time_days, 0) asc, lc.modified desc
		""",
		{"mpns": tuple(mpns), "company": company, "parenttype": LINE_CARD},
		as_dict=True,
	)
	return rows


def get_default_supplier(item_code, company):
	return frappe.db.get_value("Item Default", {"parent": item_code, "parenttype": "Item", "company": company},
		"default_supplier")


def resolve_supplier(item_code, company):
	"""Supplier for auto ordering: Item Default supplier, else (setting) shortest-lead-time line card supplier.

	Returns (supplier or None, line_card_row or None). Suppliers that are not Enabled are ignored.
	"""
	supplier = get_default_supplier(item_code, company)
	card_rows = get_line_card_rows(item_code, company)
	card_row = None
	if supplier:
		card_row = next((r for r in card_rows if r.supplier == supplier), None)
		if supplier_is_enabled(supplier):
			return supplier, card_row
		supplier = None
	if cint(get_setting("line_card_supplier_fallback", company=company)):
		for row in card_rows:
			if supplier_is_enabled(row.supplier):
				return row.supplier, row
	return None, card_row


def get_min_lead_time(item_code, company):
	"""Shortest line card lead time for the item's MPN; fallback Item.lead_time_days."""
	rows = get_line_card_rows(item_code, company)
	if rows:
		return cint(rows[0].lead_time_days)
	return cint(frappe.db.get_value("Item", item_code, "lead_time_days"))


def get_conversion_factor(item_code, uom):
	stock_uom = frappe.get_cached_value("Item", item_code, "stock_uom")
	if not uom or uom == stock_uom:
		return 1.0
	cf = frappe.db.get_value("UOM Conversion Detail", {"parent": item_code, "parenttype": "Item", "uom": uom},
		"conversion_factor")
	return flt(cf) or 1.0


def get_purchase_uom(item_code):
	purchase_uom, stock_uom = frappe.get_cached_value("Item", item_code, ["purchase_uom", "stock_uom"])
	return purchase_uom or stock_uom


def item_has_field(fieldname):
	return frappe.get_meta("Item").has_field(fieldname)


def get_spq(item_code, card_row=None):
	spq = flt(frappe.db.get_value("Item", item_code, "ub_standard_packing_qty")) if item_has_field(
		"ub_standard_packing_qty") else 0
	if not spq and card_row:
		spq = flt(card_row.get("standard_packing_qty"))
	return spq or 1.0


def get_moq(item_code, card_row=None):
	moq = flt(frappe.db.get_value("Item", item_code, "min_order_qty"))
	if not moq and card_row:
		moq = flt(card_row.get("min_order_qty"))
	return moq or 1.0


def supplier_moq_per_line(supplier):
	if not supplier or not frappe.get_meta("Supplier").has_field("ub_moq_per_line"):
		return 0
	return cint(frappe.db.get_value("Supplier", supplier, "ub_moq_per_line"))


def get_item_class(item_code, company, project=None):
	"""ABC class from Item Classification; scope from setting abc_scope. None when not classified."""
	scope = get_setting("abc_scope") or "Project"
	filters = {"item_code": item_code, "company": company}
	if scope == "Project":
		if not project:
			return None
		filters["project"] = project
	else:
		filters["project"] = ("is", "not set")
	return frappe.db.get_value("Item Classification", filters, "item_class", order_by="computed_on desc")


# ------------------------------------------------------------------------------ report helpers


def company_with_descendants(company):
	"""The company plus its child companies when it is a group company."""
	if not company:
		return []
	companies = [company]
	if frappe.db.get_value("Company", company, "is_group"):
		from frappe.utils.nestedset import get_descendants_of

		companies += get_descendants_of("Company", company, ignore_permissions=True) or []
	return companies


def month_key(date):
	d = frappe.utils.getdate(date)
	return f"m_{d.year}_{d.month:02d}"


def month_label(date):
	return frappe.utils.getdate(date).strftime("%b %Y")
