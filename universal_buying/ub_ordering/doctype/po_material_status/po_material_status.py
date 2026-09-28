# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

DELAYED = "Delayed"
DISPATCHED = "Dispatched"
# forward order of the production lifecycle; Delayed is a flag that can be raised before dispatch
RANK = {"In Production": 1, "Partial": 2, "Ready to Dispatch": 3, DISPATCHED: 4}
ACCEPTED_STATES = ("Accepted", "Partially Dispatched", "Dispatched")


class POMaterialStatus(Document):
	"""Append-only material readiness log (BRD 6.21).

	* allowed only after the supplier accepted the PO,
	* remarks are required,
	* the same status cannot be logged twice in a row,
	* Dispatched needs an uploaded invoice and a submitted shipment,
	* the status never moves backwards (Delayed may be raised any time before Dispatched).
	"""

	def validate(self):
		if not self.is_new():
			frappe.throw(_("Material status entries are append-only and cannot be edited."))
		if self.status not in RANK and self.status != DELAYED:
			frappe.throw(_("Invalid material status {0}.").format(self.status))
		if not (self.remarks or "").strip():
			frappe.throw(_("Remarks are required."))

		po = frappe.db.get_value("Purchase Order", self.purchase_order,
			["supplier", "docstatus", "ub_portal_status"], as_dict=True)
		if not po or po.docstatus != 1:
			frappe.throw(_("Material status can be posted only on a submitted Purchase Order."))
		self.supplier = po.supplier
		if po.ub_portal_status not in ACCEPTED_STATES:
			frappe.throw(_("Please acknowledge the Purchase Order before posting material status."))

		history = frappe.get_all("PO Material Status", filters={"purchase_order": self.purchase_order},
			fields=["status"], order_by="creation desc")
		statuses = [h.status for h in history]
		if statuses and statuses[0] == self.status:
			frappe.throw(_("Material status is already {0}. Pick a different one.").format(self.status))
		if DISPATCHED in statuses:
			frappe.throw(_("The Purchase Order is already Dispatched; the status cannot change any more."))
		if self.status != DELAYED:
			reached = max([RANK[s] for s in statuses if s in RANK] or [0])
			if RANK[self.status] < reached:
				frappe.throw(_("Material status cannot move backwards (already reached {0}).").format(
					next(s for s, r in RANK.items() if r == reached)))

		if self.status == DISPATCHED:
			if not frappe.db.exists("Portal PO Invoice", {"parent": self.purchase_order, "parenttype": "Purchase Order"}):
				frappe.throw(_("Upload the invoice for this Purchase Order before marking it Dispatched."))
			if not frappe.db.exists("PO Shipment", {"purchase_order": self.purchase_order, "docstatus": 1}):
				frappe.throw(_("Create a shipment for this Purchase Order before marking it Dispatched."))

	def before_insert(self):
		self.created_by = frappe.session.user
		self.created_on = now_datetime()

	def after_insert(self):
		from universal_buying.ub_ordering.portal import sync_material_status

		sync_material_status(self)

	def on_trash(self):
		if "System Manager" not in frappe.get_roles():
			frappe.throw(_("Material status entries are append-only and cannot be deleted."))
