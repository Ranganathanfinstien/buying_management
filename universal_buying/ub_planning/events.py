"""DOC_EVENTS of UB Planning (Item, Item Price, Item Manufacturer, Purchase Order)."""

import frappe
from frappe import _
from frappe.utils import cint


def item_validate(doc, method=None):
	"""V-8.2: Is Purchase Item and Is Customer Provided Item cannot both be set."""
	if cint(doc.get("is_purchase_item")) and cint(doc.get("is_customer_provided_item")):
		frappe.throw(_("An item cannot be both a Purchase Item and a Customer Provided Item."))
	if doc.get("ub_standard_packing_qty") and doc.ub_standard_packing_qty < 0:
		frappe.throw(_("Standard Packing Qty cannot be negative."))


def item_manufacturer_validate(doc, method=None):
	"""A disabled MPN cannot stay the default one."""
	if cint(doc.get("ub_disabled")) and cint(doc.get("is_default")):
		doc.is_default = 0
		frappe.msgprint(_("A disabled MPN cannot be the default MPN; the default flag was removed."), alert=True)


def item_price_validate(doc, method=None):
	"""Keep ub_item_manufacturer consistent with the item and copy its manufacturer."""
	im_name = doc.get("ub_item_manufacturer")
	if not im_name:
		return
	im = frappe.db.get_value("Item Manufacturer", im_name, ["item_code", "manufacturer"], as_dict=True)
	if not im or im.item_code != doc.item_code:
		frappe.throw(_("MPN {0} does not belong to item {1}.").format(im_name, doc.item_code))
	if doc.meta.has_field("ub_manufacturer"):
		doc.ub_manufacturer = im.manufacturer


def purchase_order_validate_mpn(doc, method=None):
	"""V-8.1: a PO line with a disabled manufacturer / MPN (Item Manufacturer.ub_disabled) is blocked."""
	if not frappe.get_meta("Item Manufacturer").has_field("ub_disabled"):
		return
	for row in doc.get("items") or []:
		if not row.get("manufacturer_part_no") and not row.get("manufacturer"):
			continue
		filters = {"item_code": row.item_code, "ub_disabled": 1}
		if row.get("manufacturer"):
			filters["manufacturer"] = row.manufacturer
		if row.get("manufacturer_part_no"):
			filters["manufacturer_part_no"] = row.manufacturer_part_no
		if frappe.db.exists("Item Manufacturer", filters):
			frappe.throw(_("Row #{0}: manufacturer / MPN {1} of item {2} is disabled.").format(
				row.idx, row.get("manufacturer_part_no") or row.get("manufacturer"), frappe.bold(row.item_code)))
