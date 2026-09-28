# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from universal_buying.ub_ordering import portal


class POShipment(Document):
	"""Supplier dispatch against PO lines (BRD 6.21). Own doctype instead of ERPNext's Shipment, whose
	parcel / pickup / carrier-service model does not fit a supplier dispatch note and has many mandatory
	fields; this keeps the standard Shipment untouched."""

	def validate(self):
		po = frappe.db.get_value("Purchase Order", self.purchase_order, ["supplier", "company", "docstatus"], as_dict=True)
		if not po or po.docstatus != 1:
			frappe.throw(_("A shipment can be raised only against a submitted Purchase Order."))
		self.supplier, self.company = po.supplier, po.company

		ordered = portal.ordered_map(self.purchase_order)
		other = portal.shipped_map(self.purchase_order, exclude=self.name)
		this = {}
		for row in self.items:
			line = ordered.get(row.po_item)
			if not line:
				frappe.throw(_("Row {0}: the line is not part of Purchase Order {1}.").format(row.idx, self.purchase_order))
			if flt(row.shipped_qty) <= 0:
				frappe.throw(_("Row {0}: shipped quantity must be greater than zero.").format(row.idx))
			row.item_code, row.item_name, row.uom = line.item_code, line.item_name, line.uom
			row.ordered_qty = flt(line.qty)
			row.already_shipped_qty = flt(other.get(row.po_item)) + flt(this.get(row.po_item))
			remaining = row.ordered_qty - row.already_shipped_qty
			if flt(row.shipped_qty) > remaining + portal.QTY_TOLERANCE:
				frappe.throw(_("Row {0}: cannot ship {1} of {2}; only {3} remains on the Purchase Order.").format(
					row.idx, flt(row.shipped_qty), row.item_name or row.item_code, max(remaining, 0)),
					title=_("Over Shipping"))
			row.remaining_qty = remaining - flt(row.shipped_qty)
			this[row.po_item] = flt(this.get(row.po_item)) + flt(row.shipped_qty)

		self.total_shipped_qty = sum(flt(r.shipped_qty) for r in self.items)
		full = all(flt(other.get(k)) + flt(this.get(k)) >= flt(r.qty) - portal.QTY_TOLERANCE for k, r in ordered.items())
		self.shipment_status = "Fully Shipped" if full else "Partially Shipped"
		if not self.delivery_status:
			self.delivery_status = "In Transit"

	def on_submit(self):
		portal.refresh_po_dispatch_status(self.purchase_order)
		status = portal.delivery_status(self.purchase_order)
		if status:
			self.db_set("delivery_status", status, update_modified=False)

	def on_cancel(self):
		portal.refresh_po_dispatch_status(self.purchase_order)


@frappe.whitelist()
def get_lines(purchase_order, shipment=None):
	"""Desk helper: PO lines with the quantity still to ship."""
	frappe.has_permission("Purchase Order", "read", doc=purchase_order, throw=True)
	return portal.shipment_lines(purchase_order, shipment)
