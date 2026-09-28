# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime


class POAcknowledgement(Document):
	"""Append-only acknowledgement log (BRD 6.21). The latest entry wins on the PO."""

	def validate(self):
		if not self.is_new():
			frappe.throw(_("Acknowledgements are append-only and cannot be edited."))
		po = frappe.db.get_value("Purchase Order", self.purchase_order,
			["supplier", "docstatus", "status", "transaction_date"], as_dict=True)
		if not po or po.docstatus != 1:
			frappe.throw(_("Only a submitted Purchase Order can be acknowledged."))
		if po.status in ("Closed", "Completed"):
			frappe.throw(_("Purchase Order {0} is {1}.").format(self.purchase_order, po.status))
		self.supplier = po.supplier
		if not self.confirmed_delivery_date:
			frappe.throw(_("Confirmed delivery date is required to acknowledge a Purchase Order."))
		if getdate(self.confirmed_delivery_date) < getdate(po.transaction_date):
			frappe.throw(_("Confirmed delivery date cannot be before the PO date."))

	def before_insert(self):
		prior = frappe.db.count("PO Acknowledgement", {"purchase_order": self.purchase_order})
		self.event_type = "Revised" if prior else "Acknowledged"
		self.acknowledged_by = frappe.session.user
		self.acknowledged_on = now_datetime()

	def after_insert(self):
		from universal_buying.ub_ordering.portal import sync_acknowledgement

		sync_acknowledgement(self)

	def on_trash(self):
		if "System Manager" not in frappe.get_roles():
			frappe.throw(_("Acknowledgements are append-only and cannot be deleted."))
