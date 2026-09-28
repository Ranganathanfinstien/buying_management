# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class SupplierAuditChecklist(Document):
	def validate(self):
		seen = set()
		for row in self.checklist_detail:
			key = ((row.group or "").strip().lower(), (row.question or "").strip().lower())
			if key in seen:
				frappe.throw(_("Row {0}: question {1} is repeated in group {2}.").format(row.idx, frappe.bold(row.question), row.group))
			seen.add(key)
			options = [o for o in (row.options or "").splitlines() if o.strip()]
			if not options:
				frappe.throw(_("Row {0}: enter at least one option.").format(row.idx))
			if not cint(row.max_score):
				row.max_score = len(options) - 1 if len(options) > 1 else 1
			for field in ("industrial", "railways", "automotive", "defence_aerospace", "medical"):
				if cint(row.get(field)) > cint(row.max_score):
					frappe.throw(_("Row {0}: minimum score for {1} is above the max score.").format(row.idx, row.meta.get_label(field)))
