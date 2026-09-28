# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt

"""Gate Entry (BRD v2 6.22). Inward entries are picked on Purchase Receipts (ub_gate_entry)."""

import frappe
from frappe import _
from frappe.model.document import Document

from universal_buying.universal_buying.utils import autoname_with_company

NAMING_PATTERN = "GE-.{abbr}.-.YYYY.-.#####"


class GateEntry(Document):
	def autoname(self):
		self.name = autoname_with_company(NAMING_PATTERN, self.company)

	def validate(self):
		self.set_party_name()
		if self.entry_type == "Out":
			self.validate_outward_document()

	def set_party_name(self):
		if not (self.party_type and self.party):
			self.party_name = None
			return
		field = {"Supplier": "supplier_name", "Customer": "customer_name", "Employee": "employee_name"}.get(
			self.party_type
		)
		self.party_name = frappe.db.get_value(self.party_type, self.party, field) if field else self.party

	def validate_outward_document(self):
		if not (self.document_type and self.document_number):
			return
		existing = frappe.db.get_value(
			"Gate Entry",
			{
				"entry_type": "Out",
				"document_type": self.document_type,
				"document_number": self.document_number,
				"docstatus": ("<", 2),
				"name": ("!=", self.name),
			},
			"name",
		)
		if existing:
			frappe.throw(
				_("Gate Entry {0} already exists for {1}.").format(
					frappe.bold(existing), self.document_number
				)
			)

	def on_cancel(self):
		linked = frappe.get_all(
			"Purchase Receipt", filters={"ub_gate_entry": self.name, "docstatus": 1}, pluck="name", limit=5
		)
		if linked:
			frappe.throw(
				_("Gate Entry is used on submitted Purchase Receipt(s): {0}").format(", ".join(linked))
			)


@frappe.whitelist()
def get_document_party(document_type, document_number):
	"""Party of an outward document (Delivery Note / Sales Invoice customer, Stock Entry supplier)."""
	if not (document_type and document_number) or document_type not in (
		"Delivery Note",
		"Sales Invoice",
		"Stock Entry",
		"Purchase Receipt",
	):
		return {}
	doc = frappe.get_doc(document_type, document_number)
	doc.check_permission("read")
	if doc.get("customer"):
		return {"party_type": "Customer", "party": doc.customer}
	if doc.get("supplier"):
		return {"party_type": "Supplier", "party": doc.supplier}
	return {}
