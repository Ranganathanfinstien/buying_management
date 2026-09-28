# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt
"""Prospective Supplier (BRD 6.2): a light record that can be invited to an RFQ before registration."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import validate_email_address

from universal_buying.ub_supplier.utils import (
	check_duplicate_gstin,
	validate_gstin,
	validate_pan,
)


class ProspectiveSupplier(Document):
	def validate(self):
		self.supplier_name = (self.supplier_name or "").strip()
		self.validate_email()
		# V-2.2 / V-2.3
		self.pan = validate_pan(self.pan)
		self.gstin = validate_gstin(self.gstin, self.pan)
		# V-2.4
		if self.gstin:
			check_duplicate_gstin(self, self.gstin)
		if not self.status:
			self.status = "Active"

	def validate_email(self):
		# V-2.1
		self.email = (self.email or "").strip()
		if not self.email or not validate_email_address(self.email):
			frappe.throw(_("Invalid email address: {0}").format(self.email or "-"), title=_("Invalid Email"))

	@frappe.whitelist()
	def create_onboarding(self, send_email=0):
		"""A-2.1: create (or return) the Supplier Onboarding pre-filled from this record."""
		self.check_permission("write")
		from universal_buying.ub_supplier.api import create_onboarding_from_prospective

		return create_onboarding_from_prospective(self.name, send_email=send_email)
