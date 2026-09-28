# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt

"""PO Amendment (BRD v2 6.20 / 8.4).

Workflow "UB PO Amendment": Draft -> Pending Approval -> Approved (submit) / Rejected.
On Approved (on_submit) the lines are applied through ERPNext's standard
``erpnext.controllers.accounts_controller.update_child_qty_rate`` so taxes, totals, payment schedule,
ordered / requested qty and MOQ are recalculated.

Fix from the source design: the earlier version wrote the lines with SQL and set grand_total = net_total,
dropping every tax (AC-20.1).
"""

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, now_datetime

from universal_buying.ub_ordering.pricing import get_valid_price, price_in_row_terms
from universal_buying.universal_buying.settings import get_setting

EPS = 1e-9
_OPEN_STATES = ("Draft", "Pending Approval")


class POAmendment(Document):
	def validate(self):
		po = self._get_po()
		self.supplier, self.company, self.currency = po.supplier, po.company, po.currency
		self.original_grand_total = flt(po.grand_total)
		self._check_other_open_amendments()
		self._fill_and_validate_rows(po)
		self._set_totals()

	def _get_po(self):
		if not self.purchase_order:
			frappe.throw(_("Purchase Order is required."))
		po = frappe.get_doc("Purchase Order", self.purchase_order)
		if po.docstatus != 1:
			frappe.throw(_("Only a submitted Purchase Order can be amended."))
		if po.status in ("Closed", "Completed"):
			frappe.throw(_("Purchase Order {0} is {1} and cannot be amended.").format(po.name, po.status))
		return po

	def _check_other_open_amendments(self):
		other = frappe.get_all("PO Amendment", filters={
			"purchase_order": self.purchase_order, "docstatus": 0, "name": ["!=", self.name or ""],
			"workflow_state": "Pending Approval"}, pluck="name")
		if other:
			frappe.throw(_("PO Amendment {0} is already pending approval for this Purchase Order.").format(other[0]))

	def _fill_and_validate_rows(self, po):
		if not self.items:
			frappe.throw(_("Add at least one line."))
		lines = {d.name: d for d in po.items}
		cap = flt(get_setting("amendment_rate_cap_percent", company=po.company))
		changed = False
		for row in self.items:
			src = lines.get(row.po_item) if row.po_item else None
			if row.po_item and not src:
				frappe.throw(_("Row {0}: line {1} is not part of Purchase Order {2}.").format(row.idx, row.po_item, po.name))

			if row.split:
				if not row.item_code and src:
					row.item_code = src.item_code
				if not row.item_code:
					frappe.throw(_("Row {0}: Item Code is required for a split line.").format(row.idx))
				row.original_qty = row.original_rate = row.original_amount = row.received_qty = 0
				row.original_schedule_date = None
				row.uom = (src.uom if src else None) or frappe.get_cached_value("Item", row.item_code, "stock_uom")
				row.conversion_factor = flt(src.conversion_factor) if src else 0
				row.item_name = frappe.get_cached_value("Item", row.item_code, "item_name")
				if flt(row.revised_qty) <= 0:
					frappe.throw(_("Row {0}: a split line needs a quantity.").format(row.idx))
				row.revised_schedule_date = row.revised_schedule_date or (src.schedule_date if src else po.schedule_date)
				if not flt(row.revised_rate) and src:
					row.revised_rate = src.rate
				ref_rate = flt(src.rate) if src else None
				changed = True
			else:
				if not src:
					frappe.throw(_("Row {0}: select the PO line to amend, or tick Split for a new line.").format(row.idx))
				row.item_code, row.item_name, row.uom = src.item_code, src.item_name, src.uom
				row.conversion_factor = flt(src.conversion_factor)
				row.received_qty = flt(src.received_qty)
				row.original_qty, row.original_rate = flt(src.qty), flt(src.rate)
				row.original_schedule_date = src.schedule_date
				row.original_amount = flt(src.amount)
				if row.revised_qty in (None, ""):
					row.revised_qty = row.original_qty
				if not flt(row.revised_rate):
					row.revised_rate = row.original_rate
				row.revised_schedule_date = row.revised_schedule_date or row.original_schedule_date
				ref_rate = row.original_rate
				if (abs(flt(row.revised_qty) - row.original_qty) > EPS or abs(flt(row.revised_rate) - row.original_rate) > EPS
					or getdate(row.revised_schedule_date) != getdate(row.original_schedule_date)):
					changed = True

			# V-20.2
			if flt(row.revised_qty) < 0 or flt(row.revised_rate) < 0:
				frappe.throw(_("Row {0}: quantity and rate cannot be negative.").format(row.idx))
			if flt(row.revised_qty) < flt(row.received_qty) - EPS:
				frappe.throw(_("Row {0}: new quantity {1} is below the quantity already received ({2}).").format(
					row.idx, flt(row.revised_qty), flt(row.received_qty)))

			# V-20.1
			if ref_rate is not None and flt(row.revised_rate) > flt(ref_rate) * (1 + cap / 100.0) + EPS:
				supported = self._price_supports(po, row)
				if not supported:
					frappe.throw(_("Row {0}: rate increase from {1} to {2} is above the {3}% cap and no valid Item Price supports it.").format(
						row.idx, flt(ref_rate), flt(row.revised_rate), cap), title=_("Rate Cap"))

			row.revised_amount = flt(row.revised_qty) * flt(row.revised_rate)

		if not changed:
			frappe.throw(_("Nothing is changed on the lines."))

	def _price_supports(self, po, row):
		price = get_valid_price(row.item_code, supplier=po.supplier, company=po.company,
			date=row.revised_schedule_date or getdate(), uom=row.uom)
		rate = price_in_row_terms(price, po, frappe._dict(uom=row.uom, stock_uom=frappe.get_cached_value(
			"Item", row.item_code, "stock_uom"), conversion_factor=row.conversion_factor or 1))
		return rate is not None and flt(row.revised_rate) <= flt(rate) + EPS

	def _set_totals(self):
		self.original_total = sum(flt(r.original_amount) for r in self.items if not r.split)
		self.revised_total = sum(flt(r.revised_amount) for r in self.items)

	# ------------------------------------------------------------------ apply (A-20.1)
	def on_submit(self):
		if self.workflow_state and self.workflow_state != "Approved":
			frappe.throw(_("A PO Amendment is submitted only through approval."))
		self.apply_to_po()

	def on_cancel(self):
		if self.applied:
			frappe.throw(_("An applied amendment cannot be cancelled. Raise a new PO Amendment to change the order again."))

	def build_trans_items(self, po):
		rows = {r.po_item: r for r in self.items if not r.split and r.po_item}
		data = []
		for d in po.items:
			r = rows.get(d.name)
			item = {
				"docname": d.name, "item_code": d.item_code, "idx": d.idx, "description": d.description,
				"uom": d.uom, "conversion_factor": d.conversion_factor,
				"qty": flt(r.revised_qty) if r else flt(d.qty),
				"rate": flt(r.revised_rate) if r else flt(d.rate),
				"schedule_date": str(r.revised_schedule_date if r and r.revised_schedule_date else d.schedule_date),
			}
			if po.get("is_subcontracted"):
				item["fg_item"], item["fg_item_qty"] = d.get("fg_item"), d.get("fg_item_qty")
			data.append(item)
		for r in self.items:
			if r.split:
				data.append({
					"item_code": r.item_code, "qty": flt(r.revised_qty), "rate": flt(r.revised_rate),
					"uom": r.uom, "conversion_factor": r.conversion_factor or None,
					"schedule_date": str(r.revised_schedule_date), "idx": len(data) + 1,
					"description": frappe.get_cached_value("Item", r.item_code, "description"),
				})
		return data

	def apply_to_po(self):
		from erpnext.controllers.accounts_controller import update_child_qty_rate

		po = frappe.get_doc("Purchase Order", self.purchase_order)
		update_child_qty_rate("Purchase Order", json.dumps(self.build_trans_items(po), default=str), po.name)
		po.reload()
		self.db_set({"applied": 1, "applied_on": now_datetime(), "revised_grand_total": flt(po.grand_total)})
		po.add_comment("Info", _("PO Amendment {0} applied. Grand total {1} -> {2} (taxes recalculated). Reason: {3}").format(
			self.name, flt(self.original_grand_total), flt(po.grand_total), self.reason))


@frappe.whitelist()
def get_po_lines(purchase_order):
	"""Client helper: current PO lines to prefill the amendment grid."""
	frappe.has_permission("Purchase Order", "read", doc=purchase_order, throw=True)
	return frappe.get_all("Purchase Order Item", filters={"parent": purchase_order, "parenttype": "Purchase Order"},
		fields=["name as po_item", "item_code", "item_name", "uom", "conversion_factor", "received_qty",
			"qty as original_qty", "rate as original_rate", "amount as original_amount",
			"schedule_date as original_schedule_date"], order_by="idx")
