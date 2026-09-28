# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class SupplierOnboardingQuestionBank(Document):
	def validate(self):
		for row in self.questions:
			if row.category == "Ranking" and not (row.option_5 and row.option_1):
				frappe.throw(_("Row {0}: a Ranking question needs at least the Score 5 and Score 1 options.").format(row.idx))

	def on_update(self):
		# only one default bank
		if self.is_default:
			frappe.db.sql(
				"update `tabSupplier Onboarding Question Bank` set is_default = 0 where name != %s and is_default = 1",
				self.name,
			)
