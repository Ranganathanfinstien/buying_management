"""Desk helpers for the Purchase Order form (UB Ordering)."""

import frappe
from frappe.utils import flt

from universal_buying.ub_ordering.pricing import expected_rate
from universal_buying.universal_buying.settings import get_setting


@frappe.whitelist()
def get_line_rate(item_code, supplier, company, transaction_date=None, schedule_date=None, uom=None,
		stock_uom=None, conversion_factor=1, currency=None, conversion_rate=1, supplier_quotation_item=None):
	"""Rate a PO line must carry under price control (client mirror of the server rule)."""
	frappe.has_permission("Purchase Order", "read", throw=True)
	company_currency = frappe.get_cached_value("Company", company, "default_currency") if company else None
	po = frappe._dict(supplier=supplier, company=company, transaction_date=transaction_date,
		currency=currency or company_currency, conversion_rate=flt(conversion_rate) or 1)
	row = frappe._dict(item_code=item_code, uom=uom, stock_uom=stock_uom, conversion_factor=flt(conversion_factor) or 1,
		schedule_date=schedule_date, supplier_quotation_item=supplier_quotation_item)
	rate, source = expected_rate(po, row)
	return {"rate": rate, "source": source, "mode": get_setting("price_control_mode", company=company) or "Strict"}


@frappe.whitelist()
def get_form_settings(company=None, po_type=None):
	"""Settings the PO form needs in one call."""
	frappe.has_permission("Purchase Order", "read", throw=True)
	from universal_buying.universal_buying.doctype.po_type.po_type import get_default_po_type, get_po_type

	pt = get_po_type(po_type)
	return {
		"price_control_mode": get_setting("price_control_mode", company=company) or "Strict",
		"po_approval_enabled": get_setting("po_approval_enabled", company=company),
		"default_po_type": get_default_po_type(),
		"item_required": 1 if pt.get("item_required") is None else pt.get("item_required"),
	}
