"""Public contracts of UB Planning (BUILD_SPEC 6.3). Keep the signatures stable."""

import frappe
from frappe.utils import add_months, flt, get_first_day, getdate, nowdate

from universal_buying.ub_planning.common import get_default_supplier

PRICE_FIELDS = ("ub_company", "ub_manufacturer", "ub_item_manufacturer")


def _price_meta_fields():
	meta = frappe.get_meta("Item Price")
	return {f: meta.has_field(f) for f in PRICE_FIELDS}


@frappe.whitelist()
def get_current_item_price(item_code, supplier=None, company=None, date=None, uom=None):
	"""Winning buying Item Price row valid on `date` (default today).

	Order of preference: rows stamped with the company (ub_company) before unstamped rows, rows in the
	supplier's default currency, latest valid_from, newest row. When no supplier is given the Item
	Default supplier of the company is tried first, then any supplier.

	Returns {name, price_list, price_list_rate, currency, uom, supplier, ub_item_manufacturer, manufacturer,
	manufacturer_part_no, valid_from, valid_upto, lead_time_days} or None.
	"""
	if not item_code:
		return None
	date = getdate(date or nowdate())
	has = _price_meta_fields()

	if not supplier and company:
		default_supplier = get_default_supplier(item_code, company)
		if default_supplier:
			row = get_current_item_price(item_code, default_supplier, company, date, uom)
			if row:
				return row

	conditions = [
		"ip.item_code = %(item_code)s",
		"ip.buying = 1",
		"ifnull(ip.valid_from, '1900-01-01') <= %(date)s",
		"ifnull(ip.valid_upto, '2999-12-31') >= %(date)s",
	]
	params = {"item_code": item_code, "date": date, "company": company or "", "uom": uom or "", "currency": ""}
	order = []
	if supplier:
		conditions.append("ip.supplier = %(supplier)s")
		params["supplier"] = supplier
		params["currency"] = frappe.db.get_value("Supplier", supplier, "default_currency") or ""
	if uom:
		conditions.append("(ifnull(ip.uom, '') = '' or ip.uom = %(uom)s)")
		order.append("(ip.uom = %(uom)s) desc")
	if has["ub_company"]:
		if company:
			conditions.append("(ifnull(ip.ub_company, '') = '' or ip.ub_company = %(company)s)")
			order.append("(ip.ub_company = %(company)s) desc")
	order += ["(ip.currency = %(currency)s) desc", "ifnull(ip.valid_from, '1900-01-01') desc", "ip.creation desc"]

	select = ["ip.name", "ip.price_list", "ip.price_list_rate", "ip.currency", "ip.uom", "ip.supplier",
		"ip.valid_from", "ip.valid_upto", "ip.lead_time_days"]
	select.append("ip.ub_item_manufacturer" if has["ub_item_manufacturer"] else "null as ub_item_manufacturer")
	select.append("ip.ub_manufacturer as manufacturer" if has["ub_manufacturer"] else "null as manufacturer")

	rows = frappe.db.sql(
		f"""select {", ".join(select)} from `tabItem Price` ip
		where {" and ".join(conditions)}
		order by {", ".join(order)} limit 1""",
		params,
		as_dict=True,
	)
	if not rows:
		return None
	row = rows[0]
	row.price_list_rate = flt(row.price_list_rate)
	row.manufacturer_part_no = None
	if row.ub_item_manufacturer:
		im = frappe.db.get_value("Item Manufacturer", row.ub_item_manufacturer,
			["manufacturer", "manufacturer_part_no"], as_dict=True)
		if im:
			row.manufacturer = row.manufacturer or im.manufacturer
			row.manufacturer_part_no = im.manufacturer_part_no
	return dict(row)


@frappe.whitelist()
def get_shortage_map(item_codes, company, months=0):
	"""Net shortage (stock UOM) per item from Requirement Log: overdue + current month + `months` months.

	Returns {item_code: qty}. Items without a shortage are returned with 0.
	"""
	if isinstance(item_codes, str):
		item_codes = frappe.parse_json(item_codes) if item_codes.startswith("[") else [item_codes]
	item_codes = [i for i in dict.fromkeys(item_codes or []) if i]
	result = {i: 0.0 for i in item_codes}
	if not item_codes or not company:
		return result
	upto = add_months(get_first_day(nowdate()), int(months or 0) + 1)
	rows = frappe.db.sql(
		"""select item_code, sum(qty) from `tabRequirement Log`
		where company = %s and reservation_type = 'Shortage' and item_code in %s and delivery_date < %s
		group by item_code""",
		(company, tuple(item_codes), upto),
	)
	for item_code, qty in rows:
		result[item_code] = flt(qty)
	return result
