"""Price lookup used by PO price control (BRD 6.17) and PO Amendment rate cap (V-20.1).

The winning Item Price comes from the planning module contract
``universal_buying.ub_planning.api.get_current_item_price``. When that module is not present
(or the function is missing) a local query with the same priority rules is used.
"""

import frappe
from frappe.utils import flt, getdate


def get_valid_price(item_code, supplier=None, company=None, date=None, uom=None):
	"""Return the winning buying Item Price row as a dict or None.

	Keys (contract): name, price_list_rate, currency, supplier, ub_item_manufacturer, manufacturer,
	manufacturer_part_no, valid_from, valid_upto (+ uom when available).
	"""
	if not item_code:
		return None
	try:
		from universal_buying.ub_planning.api import get_current_item_price
	except (ImportError, AttributeError):
		get_current_item_price = None

	if get_current_item_price:
		row = get_current_item_price(item_code, supplier=supplier, company=company, date=date, uom=uom)
		return frappe._dict(row) if row else None
	return _fallback_price(item_code, supplier, company, date, uom)


def _fallback_price(item_code, supplier=None, company=None, date=None, uom=None):
	date = getdate(date) if date else getdate()
	meta = frappe.get_meta("Item Price")
	fields = ["name", "price_list_rate", "currency", "supplier", "uom", "valid_from", "valid_upto"]
	for f in ("ub_item_manufacturer", "ub_manufacturer", "ub_company"):
		if meta.has_field(f):
			fields.append(f)

	filters = {"item_code": item_code, "buying": 1}
	rows = frappe.get_all("Item Price", filters=filters, fields=fields, order_by="valid_from desc, creation desc")

	def ok(r):
		if r.valid_from and getdate(r.valid_from) > date:
			return False
		if r.valid_upto and getdate(r.valid_upto) < date:
			return False
		if r.supplier and supplier and r.supplier != supplier:
			return False
		if r.supplier and not supplier:
			return False
		if uom and r.uom and r.uom != uom:
			return False
		if company and r.get("ub_company") and r.ub_company != company:
			return False
		return True

	rows = [r for r in rows if ok(r)]
	if not rows:
		return None

	# supplier-specific first, then open-ended validity , then latest valid_from
	rows.sort(key=lambda r: (
		0 if (supplier and r.supplier == supplier) else 1,
		0 if not r.valid_upto else 1,
		-(getdate(r.valid_from).toordinal() if r.valid_from else 0),
	))
	r = rows[0]
	mfr = r.get("ub_manufacturer")
	mpn = None
	if r.get("ub_item_manufacturer"):
		mfr, mpn = frappe.db.get_value("Item Manufacturer", r.ub_item_manufacturer,
			["manufacturer", "manufacturer_part_no"]) or (mfr, None)
	return frappe._dict(
		name=r.name, price_list_rate=flt(r.price_list_rate), currency=r.currency, supplier=r.supplier,
		ub_item_manufacturer=r.get("ub_item_manufacturer"), manufacturer=mfr, manufacturer_part_no=mpn,
		valid_from=r.valid_from, valid_upto=r.valid_upto, uom=r.uom,
	)


def price_in_row_terms(price, po, row):
	"""Convert an Item Price to the PO row's currency and UOM. Returns a float or None."""
	if not price:
		return None
	rate = flt(price.get("price_list_rate"))

	price_uom = price.get("uom")
	if price_uom and row.get("uom") and price_uom != row.uom:
		if price_uom == row.get("stock_uom"):
			rate = rate * flt(row.conversion_factor or 1)
		else:
			return None

	currency = price.get("currency")
	if not currency or currency == po.currency:
		return rate
	company_currency = frappe.get_cached_value("Company", po.company, "default_currency")
	if currency == company_currency and flt(po.conversion_rate):
		return rate / flt(po.conversion_rate)
	return None


def expected_rate(po, row):
	"""Rate the PO row must carry under price control: (rate, source) or (None, None).

	Source order: the linked Supplier Quotation line, then the valid Item Price.
	"""
	if row.get("supplier_quotation_item"):
		sq_rate = frappe.db.get_value("Supplier Quotation Item", row.supplier_quotation_item, "rate")
		if sq_rate is not None:
			return flt(sq_rate), "Supplier Quotation"

	price = get_valid_price(
		row.item_code, supplier=po.supplier, company=po.company,
		date=row.get("schedule_date") or po.transaction_date, uom=row.get("uom"),
	)
	rate = price_in_row_terms(price, po, row)
	if rate is None:
		return None, None
	return rate, "Item Price {0}".format(price.get("name"))
