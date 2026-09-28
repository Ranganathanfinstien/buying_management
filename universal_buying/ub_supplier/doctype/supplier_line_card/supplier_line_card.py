# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt
"""Supplier Line Card (BRD 6.7): the MPNs a supplier can ship, with lead time, MOQ and SPQ.

MPNs are plain text matched against Item Manufacturer.manufacturer_part_no (BUILD_SPEC 6.2).
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt


class SupplierLineCard(Document):
	def validate(self):
		self.validate_unique_card()
		self.validate_rows()

	def validate_unique_card(self):
		other = frappe.db.get_value(
			"Supplier Line Card",
			{"supplier": self.supplier, "company": self.company, "name": ("!=", self.name), "disabled": 0},
			"name",
		)
		if other and not self.disabled:
			frappe.throw(
				_("Supplier {0} already has an active Line Card {1} for {2}.").format(
					frappe.bold(self.supplier), frappe.utils.get_link_to_form(self.doctype, other), self.company
				),
				title=_("Duplicate Line Card"),
			)

	def validate_rows(self):
		"""V-7.1: an MPN may appear only once per card (case / space insensitive)."""
		seen = {}
		for row in self.items:
			row.manufacturer_part_no = (row.manufacturer_part_no or "").strip()
			if not row.manufacturer_part_no:
				frappe.throw(_("Row {0}: Manufacturer Part No is required.").format(row.idx))
			key = row.manufacturer_part_no.upper().replace(" ", "")
			if key in seen:
				frappe.throw(
					_("Row {0}: MPN {1} is already on row {2}.").format(row.idx, frappe.bold(row.manufacturer_part_no), seen[key]),
					title=_("Duplicate MPN"),
				)
			seen[key] = row.idx
			for field in ("lead_time_days", "min_order_qty", "standard_packing_qty"):
				if flt(row.get(field)) < 0:
					frappe.throw(_("Row {0}: {1} cannot be negative.").format(row.idx, row.meta.get_label(field)))
			if cint(row.lead_time_days) != flt(row.lead_time_days):
				row.lead_time_days = cint(row.lead_time_days)


def get_line_card_rows(supplier=None, company=None, manufacturer_part_no=None):
	"""Active line card rows, optionally filtered. Helper for planning / sourcing lookups."""
	filters = {"disabled": 0}
	if supplier:
		filters["supplier"] = supplier
	if company:
		filters["company"] = company
	cards = frappe.get_all("Supplier Line Card", filters=filters, fields=["name", "supplier", "company"])
	if not cards:
		return []
	by_name = {c.name: c for c in cards}
	row_filters = {"parent": ("in", list(by_name)), "parenttype": "Supplier Line Card"}
	if manufacturer_part_no:
		row_filters["manufacturer_part_no"] = manufacturer_part_no
	rows = frappe.get_all(
		"Supplier Line Card Item",
		filters=row_filters,
		fields=["parent", "manufacturer_part_no", "manufacturer", "lead_time_days", "min_order_qty", "standard_packing_qty"],
	)
	for r in rows:
		r.supplier = by_name[r.parent].supplier
		r.company = by_name[r.parent].company
	return rows
