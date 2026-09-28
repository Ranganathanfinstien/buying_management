# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document


class SupplierChannel(Document):
	"""Integration channel for a supplier (BRD 6.19). Credentials live here, not on the Supplier."""

	def validate(self):
		if self.connector == "Custom" and not self.connector_class:
			frappe.throw(_("Connector Class is required for a Custom connector."))
		if self.extra_config:
			try:
				json.loads(self.extra_config)
			except ValueError:
				frappe.throw(_("Extra Config must be valid JSON."))
