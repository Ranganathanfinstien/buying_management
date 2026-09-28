# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt

"""Item Price Request (BRD v2 6.9) - sets an item's approved source.

V-9.1 Item Default row for the company is required.
V-9.2 Lead time > 0, valid from <= valid upto.
V-9.3 Only one open (draft) Buying request per item + company (the earlier rule blocked any second request and
      redirected to a Recommendation Note - removed).
Roles: setting ``price_request_roles`` (System Manager always allowed).

A-9.1 on submit (Buying): expire earlier buying Item Price rows of the item, create the new Item Price
(supplier, rate, validity, MPN, company), write MOQ / SPQ on the Item, set the Item Default supplier and
mark the chosen Item Manufacturer as default (ERPNext then sets Item.default_item_manufacturer /
default_manufacturer_part_no).
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, cint, flt, getdate

from universal_buying.universal_buying.settings import get_list, has_any_role


class ItemPriceRequest(Document):
	def validate(self):
		validate_roles()
		self.validate_rows()
		if self.type == "Buying":
			self.validate_single_open_request()

	def on_submit(self):
		validate_roles()
		for row in self.item_price_details:
			if self.type == "Buying":
				expire_previous_prices(row, self.company, buying=True)
			else:
				expire_previous_prices(row, self.company, buying=False)
			item_price = create_item_price(row, self.company, self.type, self.name)
			row.db_set("item_price", item_price)
			if self.type == "Buying":
				update_item_source(row, self.company)

	def on_cancel(self):
		"""Remove the Item Price rows created by this request (the item master changes stay)."""
		for row in self.item_price_details:
			if row.item_price and frappe.db.exists("Item Price", row.item_price):
				frappe.delete_doc("Item Price", row.item_price, ignore_permissions=True)
			row.db_set("item_price", None)

	# ------------------------------------------------------------------ validation
	def validate_rows(self):
		seen = set()
		for row in self.item_price_details:
			# V-9.1
			if not frappe.db.exists("Item Default", {"parent": row.item_code, "parenttype": "Item",
					"company": self.company}):
				frappe.throw(_("Row #{0}: item {1} has no Item Default row for company {2}.").format(
					row.idx, frappe.bold(row.item_code), frappe.bold(self.company)))
			# V-9.2
			if cint(row.lead_time_days) <= 0:
				frappe.throw(_("Row #{0}: Lead Time Days must be greater than 0.").format(row.idx))
			if row.valid_from and row.valid_upto and getdate(row.valid_from) > getdate(row.valid_upto):
				frappe.throw(_("Row #{0}: Valid From cannot be after Valid Upto.").format(row.idx))
			if flt(row.rate) <= 0:
				frappe.throw(_("Row #{0}: Rate must be greater than 0.").format(row.idx))
			if flt(row.moq) < 0 or flt(row.spq) < 0:
				frappe.throw(_("Row #{0}: MOQ and SPQ cannot be negative.").format(row.idx))

			if self.type == "Buying":
				if not row.supplier:
					frappe.throw(_("Row #{0}: Supplier is required for a Buying request.").format(row.idx))
				row.customer = None
				if row.item_code in seen:
					frappe.throw(_("Row #{0}: item {1} appears twice.").format(row.idx, frappe.bold(row.item_code)))
				seen.add(row.item_code)
				buying = frappe.db.get_value("Price List", row.price_list, "buying")
				if not buying:
					frappe.throw(_("Row #{0}: Price List {1} is not a buying price list.").format(row.idx, row.price_list))
			else:
				if not row.customer:
					frappe.throw(_("Row #{0}: Customer is required for a Selling request.").format(row.idx))
				row.supplier = None
				if not frappe.db.get_value("Price List", row.price_list, "selling"):
					frappe.throw(_("Row #{0}: Price List {1} is not a selling price list.").format(row.idx, row.price_list))

			row.currency = frappe.db.get_value("Price List", row.price_list, "currency") or row.currency

			if row.item_manufacturer:
				im = frappe.db.get_value("Item Manufacturer", row.item_manufacturer,
					["item_code", "manufacturer", "manufacturer_part_no"], as_dict=True)
				if not im or im.item_code != row.item_code:
					frappe.throw(_("Row #{0}: MPN {1} does not belong to item {2}.").format(
						row.idx, row.item_manufacturer, row.item_code))
				if frappe.get_meta("Item Manufacturer").has_field("ub_disabled") and frappe.db.get_value(
						"Item Manufacturer", row.item_manufacturer, "ub_disabled"):
					frappe.throw(_("Row #{0}: MPN {1} is disabled.").format(row.idx, im.manufacturer_part_no))
				row.manufacturer = im.manufacturer
				row.manufacturer_part_no = im.manufacturer_part_no

	def validate_single_open_request(self):
		"""V-9.3: one open (draft) Buying request per item and company."""
		for row in self.item_price_details:
			other = frappe.db.sql(
				"""select ipr.name from `tabItem Price Request` ipr
				inner join `tabItem Price Request Detail` d on d.parent = ipr.name
					and d.parenttype = 'Item Price Request'
				where d.item_code = %s and ipr.company = %s and ipr.type = 'Buying' and ipr.docstatus = 0
					and ipr.name != %s
				limit 1""",
				(row.item_code, self.company, self.name or ""),
			)
			if other:
				frappe.throw(_("Row #{0}: item {1} already has an open Item Price Request {2}. Submit or delete it "
					"first.").format(row.idx, frappe.bold(row.item_code), frappe.bold(other[0][0])))


def validate_roles():
	roles = get_list("price_request_roles")
	if "System Manager" in frappe.get_roles() or frappe.session.user == "Administrator":
		return
	if not has_any_role(roles):
		frappe.throw(_("Only these roles may create or submit an Item Price Request: {0}").format(
			", ".join(roles) or _("(none configured in Buying Control Settings)")), frappe.PermissionError)


# ---------------------------------------------------------------------- submit effects


def expire_previous_prices(row, company, buying=True):
	"""End earlier Item Price rows of the item on valid_from - 1.

	Buying: every buying row of the item in this company (or without company) - the approved source is
	replaced. Selling: rows of the same customer and price list. Rows that already ended before the new
	valid_from are left untouched (the earlier version also rewrote those and could revive expired prices).
	"""
	valid_from = getdate(row.valid_from)
	end = add_days(valid_from, -1)
	ip = frappe.qb.DocType("Item Price")
	query = (
		frappe.qb.update(ip)
		.set(ip.valid_upto, end)
		.where(ip.item_code == row.item_code)
		.where(ip.valid_upto.isnull() | (ip.valid_upto >= valid_from))
	)
	if buying:
		query = query.where(ip.buying == 1)
		if frappe.get_meta("Item Price").has_field("ub_company"):
			query = query.where(ip.ub_company.isnull() | (ip.ub_company == "") | (ip.ub_company == company))
	else:
		query = query.where(ip.selling == 1).where(ip.customer == row.customer).where(ip.price_list == row.price_list)
	query.run()


def create_item_price(row, company, request_type, request_name):
	meta = frappe.get_meta("Item Price")
	doc = frappe.new_doc("Item Price")
	doc.item_code = row.item_code
	doc.uom = row.uom
	doc.price_list = row.price_list
	doc.price_list_rate = flt(row.rate)
	doc.valid_from = row.valid_from
	doc.valid_upto = row.valid_upto
	doc.lead_time_days = cint(row.lead_time_days)
	doc.note = _("Created from Item Price Request {0}").format(request_name)
	if request_type == "Buying":
		doc.supplier = row.supplier
	else:
		doc.customer = row.customer
	for fieldname, value in (("ub_company", company), ("ub_item_manufacturer", row.item_manufacturer),
			("ub_manufacturer", row.manufacturer)):
		if meta.has_field(fieldname) and value:
			doc.set(fieldname, value)
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name


def update_item_source(row, company):
	values = {}
	if flt(row.moq):
		values["min_order_qty"] = flt(row.moq)
	if flt(row.spq) and frappe.get_meta("Item").has_field("ub_standard_packing_qty"):
		values["ub_standard_packing_qty"] = flt(row.spq)
	if values:
		frappe.db.set_value("Item", row.item_code, values)

	item_default = frappe.db.get_value("Item Default", {"parent": row.item_code, "parenttype": "Item",
		"company": company}, "name")
	if item_default:
		frappe.db.set_value("Item Default", item_default, "default_supplier", row.supplier)

	if row.item_manufacturer:
		im = frappe.get_doc("Item Manufacturer", row.item_manufacturer)
		if not im.is_default:
			im.is_default = 1
			# ERPNext unsets the other defaults and writes Item.default_item_manufacturer / part no
			im.save(ignore_permissions=True)
		else:
			frappe.db.set_value("Item", row.item_code, {
				"default_item_manufacturer": im.manufacturer,
				"default_manufacturer_part_no": im.manufacturer_part_no,
			})
	frappe.clear_document_cache("Item", row.item_code)


# ---------------------------------------------------------------------- client helpers


@frappe.whitelist()
def get_party_defaults(party_type, party):
	if party_type not in ("Supplier", "Customer"):
		frappe.throw(_("Invalid party type"))
	frappe.has_permission(party_type, "read", party, throw=True)
	return frappe.db.get_value(party_type, party, ["default_currency", "default_price_list"], as_dict=True)


@frappe.whitelist()
def get_previous_requests(item_code, company=None, type=None):
	frappe.has_permission("Item Price Request", "read", throw=True)
	d = frappe.qb.DocType("Item Price Request Detail")
	p = frappe.qb.DocType("Item Price Request")
	query = (
		frappe.qb.from_(d)
		.join(p)
		.on(d.parent == p.name)
		.select(p.name, p.docstatus, p.type, p.company, d.item_code, d.manufacturer_part_no, d.supplier,
			d.customer, d.rate, d.currency, d.valid_from, d.valid_upto)
		.where(d.item_code == item_code)
		.where(p.docstatus < 2)
		.orderby(p.creation, order=frappe.qb.desc)
		.limit(20)
	)
	if company:
		query = query.where(p.company == company)
	if type:
		query = query.where(p.type == type)
	return query.run(as_dict=True)
