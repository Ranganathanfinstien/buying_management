# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt

"""Inward Discrepancy (BRD v2 6.26).

V-26.1 buyer comments required at submit. A-26.1 submit links the discrepancy to the receipt, it closes
when every row is closed, and cancelling either document cancels the other.
"""

import frappe
from frappe import _
from frappe.model.document import Document


class InwardDiscrepancy(Document):
	def validate(self):
		if self.purchase_receipt:
			pr = frappe.db.get_value(
				"Purchase Receipt",
				self.purchase_receipt,
				["supplier", "company", "docstatus", "is_return"],
				as_dict=True,
			)
			if not pr:
				frappe.throw(_("Purchase Receipt {0} not found.").format(self.purchase_receipt))
			if pr.is_return:
				frappe.throw(_("An Inward Discrepancy cannot be raised on a return."))
			if pr.supplier != self.supplier or pr.company != self.company:
				frappe.throw(
					_("Supplier and company must match Purchase Receipt {0}.").format(self.purchase_receipt)
				)
			if self.is_new() and pr.docstatus != 0:
				frappe.throw(_("Raise the discrepancy from a draft Purchase Receipt."))
		if self.docstatus == 0:
			self.status = "Draft"

	def before_submit(self):
		if not (self.buyer_comments or "").strip():
			frappe.throw(_("Buyer Comments are mandatory."), title=_("Buyer Comments"))
		self.status = self._row_status()

	def on_submit(self):
		existing = frappe.db.get_value("Purchase Receipt", self.purchase_receipt, "ub_inward_discrepancy")
		if (
			existing
			and existing != self.name
			and frappe.db.get_value("Inward Discrepancy", existing, "docstatus") == 1
		):
			frappe.throw(
				_("Purchase Receipt {0} is already linked to {1}.").format(self.purchase_receipt, existing)
			)
		frappe.db.set_value("Purchase Receipt", self.purchase_receipt, "ub_inward_discrepancy", self.name)

	def on_update_after_submit(self):
		status = self._row_status()
		if status != self.status:
			self.db_set("status", status)

	def on_cancel(self):
		self.db_set("status", "Cancelled")
		if not self.purchase_receipt:
			return
		docstatus = frappe.db.get_value("Purchase Receipt", self.purchase_receipt, "docstatus")
		if docstatus == 1 and not self.flags.ub_cancelled_by_receipt:
			pr = frappe.get_doc("Purchase Receipt", self.purchase_receipt)
			pr.flags.ignore_permissions = True
			pr.cancel()
		elif docstatus == 0:
			frappe.db.set_value("Purchase Receipt", self.purchase_receipt, "ub_inward_discrepancy", None)

	def _row_status(self):
		return "Open" if any((row.status or "Open") == "Open" for row in self.items) else "Closed"
