# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class POType(Document):
	def validate(self):
		if self.is_default:
			frappe.db.sql("update `tabPO Type` set is_default = 0 where name != %s", self.name)


def get_default_po_type():
	return frappe.db.get_value("PO Type", {"is_default": 1}, "name") or frappe.db.get_value("PO Type", {}, "name")


def get_po_type(name=None):
	"""Return the PO Type doc (falls back to the default type, then to a 3-Way stand-in)."""
	name = name or get_default_po_type()
	if not name:
		return frappe._dict(name=None, receipt_required=1, po_required_on_invoice=1, item_required=1, invoice_tolerance_percent=0)
	return frappe.get_cached_doc("PO Type", name)
