# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SupplierDocumentType(Document):
	def validate(self):
		self.document_key = frappe.scrub((self.document_key or "").strip())
