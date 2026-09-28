# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class BuyingControlSettings(Document):
	def validate(self):
		for f in ("abc_threshold_a", "abc_threshold_b", "abc_threshold_c", "moq_tolerance_percent", "min_remaining_shelf_life_percent"):
			if flt(self.get(f)) < 0 or flt(self.get(f)) > 100:
				frappe.throw(_("{0} must be between 0 and 100").format(self.meta.get_label(f)))
		meta = frappe.get_meta(self.doctype)
		for row in self.company_overrides or []:
			if not meta.get_field(row.setting_field):
				frappe.throw(_("Row {0}: {1} is not a field of Buying Control Settings").format(row.idx, row.setting_field))
		for row in self.po_approval_rules or []:
			if flt(row.to_amount) and flt(row.to_amount) < flt(row.from_amount):
				frappe.throw(_("PO Approval Rule row {0}: To Amount is below From Amount").format(row.idx))

	def on_update(self):
		frappe.clear_document_cache(self.doctype, self.doctype)
		for method in frappe.get_hooks("ub_on_settings_update"):
			frappe.get_attr(method)(self)
