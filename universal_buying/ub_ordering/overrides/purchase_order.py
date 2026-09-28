"""Purchase Order controller for Universal Buying (BRD v2 6.17 - 6.21).

Keeps only generic rules:
discount / margin reset, MOQ with per-line skip, negative tax block, item code optional by PO Type,
source Material Request / Supplier Quotation origin. Recommendation Note rate lock, Capex / WBS /
Capital Project / subsidy / SEZ / equipment variance and legacy freeze are removed.
"""

import frappe
from erpnext.buying.doctype.purchase_order.purchase_order import PurchaseOrder
from frappe import _
from frappe.utils import cstr

from universal_buying.ub_ordering import approval, po_rules
from universal_buying.universal_buying.doctype.po_type.po_type import get_default_po_type, get_po_type
from universal_buying.universal_buying.settings import get_setting
from universal_buying.universal_buying.utils import assert_supplier_enabled, autoname_with_company


class CustomPurchaseOrder(PurchaseOrder):
	# ------------------------------------------------------------------ naming (A-17.1)
	def autoname(self):
		pattern = get_setting("po_naming_series", company=self.company)
		if pattern and self.company:
			self.name = autoname_with_company(pattern, self.company)

	# ------------------------------------------------------------------ totals
	def calculate_taxes_and_totals(self):
		super().calculate_taxes_and_totals()
		po_rules.reset_discount_and_margin(self)

	def before_validate(self):
		super().before_validate()
		po_rules.reset_discount_and_margin(self)

	# ------------------------------------------------------------------ validate
	def validate(self):
		if not self.get("ub_po_type"):
			self.ub_po_type = get_default_po_type()
		if not self.get("ub_approval_status"):
			self.ub_approval_status = approval.DRAFT
		po_rules.set_default_origin(self)
		po_rules.sync_skip_moq(self)

		freeform = self.validate_line_items()
		if freeform:
			self._validate_with_freeform_lines()
		else:
			super().validate()

		# after ERPNext filled addresses / party taxes
		recalc = po_rules.apply_tax_rules(self)
		po_rules.validate_negative_taxes(self)
		po_rules.validate_uom_conversion(self)
		po_rules.validate_consumables_role(self)
		recalc = po_rules.enforce_price_control(self) or recalc
		if recalc:
			self.calculate_taxes_and_totals()
			self.set_total_in_words()
		po_rules.reset_discount_and_margin(self)
		approval.on_validate(self)

	def validate_minimum_order_qty(self):
		"""V-17.2 - replaces the ERPNext check: lines flagged ub_skip_moq and lines without item are exempt."""
		po_rules.validate_moq(self)

	def validate_line_items(self):
		"""Item code is optional only when the PO Type says item_required = 0. Returns the freeform rows."""
		po_type = get_po_type(self.get("ub_po_type"))
		freeform = [d for d in self.get("items") or [] if not d.item_code]
		if not freeform:
			return []
		if po_type.get("item_required"):
			frappe.throw(_("Item Code is required on rows {0} for PO Type {1}.").format(
				", ".join(str(d.idx) for d in freeform), frappe.bold(po_type.name or _("(default)"))))
		for d in freeform:
			text = cstr(d.get("item_name") or d.get("description")).strip()
			if not text:
				frappe.throw(_("Row #{0}: Either Item Code or Description is required.").format(d.idx))
			d.item_name = text[:140]
			d.description = d.description or text
			d.uom = d.uom or "Nos"
			d.stock_uom = d.stock_uom or d.uom
			d.conversion_factor = 1
			d.stock_qty = d.qty
			if not d.project and self.project:
				d.project = self.project
			if not d.cost_center and self.get("cost_center"):
				d.cost_center = self.cost_center
		return freeform

	def _validate_with_freeform_lines(self):
		"""Run ERPNext validation on item lines only, then recalculate over every line.

		Fix from the source design: the earlier version left the totals computed on the item lines only.
		"""
		all_rows = list(self.items)
		item_rows = [d for d in all_rows if d.item_code]
		if item_rows:
			self.items = item_rows
			try:
				super().validate()
			finally:
				self.items = all_rows
				for idx, row in enumerate(self.items, 1):
					row.idx = idx
		else:
			self.set_missing_values(for_validate=True)
			self.set_status()
		self.calculate_taxes_and_totals()

	# ------------------------------------------------------------------ submit
	def before_submit(self):
		parent = super()
		if hasattr(parent, "before_submit"):
			parent.before_submit()
		assert_supplier_enabled(self.supplier, _("Purchase Order {0}").format(self.name))
		po_rules.validate_addresses(self)
		approval.check_before_submit(self)

	def on_submit(self):
		super().on_submit()
		from universal_buying.ub_ordering import inter_company, portal

		portal.on_po_submit(self)
		inter_company.make_inter_company_sales_order(self)

	def on_cancel(self):
		super().on_cancel()
		self.db_set("ub_portal_status", None, update_modified=False)
