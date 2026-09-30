"""Supplier Quotation controller override (BRD v2 6.14 / 6.15).

* Prospective suppliers: an SQ may carry ``ub_prospective_supplier`` instead of ``supplier``
  (ERPNext would otherwise fill the supplier from the item default and fail the RFQ status update).
* BR-09 / A-14.2: one live quotation per supplier per RFQ; older ones get ``ub_revised``.
* Item code may be blank when the PO Type does not require it.
* Portal quotes: a priced line with no Item Tax Template carries 0 tax (same calculator for the
  preview and the saved document).
* ``make_purchase_order`` wrapper: PO origin = Supplier Quotation, PO Type carried, prospective supplier
  resolved to the onboarded Supplier; rejected / superseded quotations cannot be ordered.
"""

import frappe
from frappe import _
from frappe.utils import flt

from erpnext.buying.doctype.supplier_quotation.supplier_quotation import SupplierQuotation
from erpnext.buying.doctype.supplier_quotation.supplier_quotation import (
	make_purchase_order as _erpnext_make_purchase_order,
)


class UBSupplierQuotation(SupplierQuotation):
	# ---------------------------------------------------------------- totals

	def calculate_taxes_and_totals(self):
		"""Portal quotes (flag ``portal_zero_gst_untemplated``): lines without an Item Tax Template
		get a zero item tax map right after ERPNext rebuilds it from the template."""
		if not self.flags.get("portal_zero_gst_untemplated"):
			return super().calculate_taxes_and_totals()

		from erpnext.controllers.taxes_and_totals import calculate_taxes_and_totals as _Calc

		class _PortalCalc(_Calc):
			def update_item_tax_map(inner):
				super().update_item_tax_map()
				zero_tax_for_untemplated_lines(inner.doc)

		_PortalCalc(self)

	def set_total_in_words(self):
		if self.base_rounded_total is None:
			self.base_rounded_total = 0
		if self.rounded_total is None:
			self.rounded_total = 0
		super().set_total_in_words()

	# ---------------------------------------------------------------- party

	def set_supplier_from_item_default(self):
		if self.get("ub_prospective_supplier") and not self.supplier:
			return
		super().set_supplier_from_item_default()

	def validate_party(self):
		if not self.supplier and not self.get("ub_prospective_supplier"):
			frappe.throw(_("Set a Supplier or a Prospective Supplier."))
		if self.get("ub_prospective_supplier") and not self.supplier_name:
			self.supplier_name = frappe.db.get_value(
				"Prospective Supplier", self.ub_prospective_supplier, "supplier_name"
			) or self.ub_prospective_supplier

	# ---------------------------------------------------------------- validate

	def validate(self):
		self.validate_party()
		self.set_po_type_from_rfq()
		if self.item_code_required():
			super().validate()
		else:
			self.validate_freeform_items()
			self._validate_with_freeform_bypass()
		self.copy_lead_time_to_items()

	def set_po_type_from_rfq(self):
		if self.get("ub_po_type"):
			return
		rfq = next((d.request_for_quotation for d in self.items if d.get("request_for_quotation")), None)
		if rfq:
			self.ub_po_type = frappe.db.get_value("Request for Quotation", rfq, "ub_po_type")

	def item_code_required(self):
		from universal_buying.universal_buying.doctype.po_type.po_type import get_po_type

		return bool(get_po_type(self.get("ub_po_type")).item_required)

	def validate_freeform_items(self):
		for row in self.items:
			if not row.item_code and not row.get("ub_item_description"):
				frappe.throw(_("Row #{0}: either Item Code or Item Description is required").format(row.idx))
			if not row.item_code:
				row.item_name = (row.item_name or row.ub_item_description or "")[:140]
				row.description = row.description or row.ub_item_description
				row.uom = row.uom or "Nos"
				row.stock_uom = row.stock_uom or row.uom
				row.conversion_factor = row.conversion_factor or 1
				row.stock_qty = flt(row.qty) * flt(row.conversion_factor)

	def _validate_with_freeform_bypass(self):
		original = list(self.items)
		self.items = [d for d in original if d.item_code]
		try:
			super().validate()
		finally:
			self.items = original
		# totals again with every line (free-text lines were hidden above)
		self.calculate_taxes_and_totals()
		if self.base_rounded_total is None:
			self.base_rounded_total = 0
		if self.rounded_total is None:
			self.rounded_total = 0

	def before_submit(self):
		"""V-15.1: a quotation of an RFQ is approved only through the award (Quotation Comparison)."""
		if hasattr(super(), "before_submit"):
			super().before_submit()
		if self.get("workflow_state") != "Approved":
			return
		rfq = next((d.request_for_quotation for d in self.items if d.get("request_for_quotation")), None)
		if rfq and frappe.db.get_value("Request for Quotation", rfq, "ub_awarded_quotation") != self.name:
			frappe.throw(
				_("Supplier Quotation {0} belongs to RFQ {1}. Approve it by awarding it from the Quotation "
				  "Comparison.").format(self.name, rfq),
				title=_("Award required"),
			)

	def after_insert(self):
		"""BR-09: a new quotation (portal or desk) supersedes the party's earlier live ones on the RFQ."""
		rfq = next((d.request_for_quotation for d in self.items if d.get("request_for_quotation")), None)
		if not rfq:
			return
		if self.supplier:
			supersede_older_quotations(self.name, rfq, supplier=self.supplier)
		elif self.get("ub_prospective_supplier"):
			supersede_older_quotations(self.name, rfq, prospective_supplier=self.ub_prospective_supplier)

	def copy_lead_time_to_items(self):
		if self.get("ub_lead_time_days"):
			for row in self.items:
				if not row.get("lead_time_days"):
					row.lead_time_days = self.ub_lead_time_days

	# ---------------------------------------------------------------- RFQ status

	def update_rfq_supplier_status(self, include_me):
		if self.supplier:
			return super().update_rfq_supplier_status(include_me)
		ps = self.get("ub_prospective_supplier")
		if not ps:
			return
		for rfq in {d.request_for_quotation for d in self.items if d.request_for_quotation}:
			row = frappe.db.get_value("Request for Quotation Supplier",
				{"parent": rfq, "parenttype": "Request for Quotation", "ub_prospective_supplier": ps}, "name")
			if not row:
				continue
			rfq_items = frappe.get_all("Request for Quotation Item", filters={"parent": rfq}, pluck="name")
			mine = {d.request_for_quotation_item for d in self.items} if include_me else set()
			quote_status = "Received"
			for rqi in rfq_items:
				count = frappe.db.sql(
					"""SELECT COUNT(sqi.name) FROM `tabSupplier Quotation Item` sqi
					JOIN `tabSupplier Quotation` sq ON sq.name = sqi.parent
					WHERE sq.ub_prospective_supplier = %s AND sqi.docstatus = 1 AND sq.name != %s
					AND sqi.request_for_quotation_item = %s""",
					(ps, self.name, rqi),
				)[0][0]
				if not count and rqi not in mine:
					quote_status = "Pending"
			frappe.db.set_value("Request for Quotation Supplier", row, "quote_status", quote_status)


def zero_tax_for_untemplated_lines(sq):
	"""Lines with no Item Tax Template carry no tax on portal quotes (never the header's nominal rate)."""
	accounts = [t.account_head for t in (sq.taxes or []) if t.account_head]
	if not accounts:
		return
	zero_map = frappe.as_json({acct: 0 for acct in accounts})
	for item in sq.items:
		if not item.get("item_tax_template"):
			item.item_tax_rate = zero_map


# ---------------------------------------------------------------------------
# A-14.2 one live quotation per supplier per RFQ
# ---------------------------------------------------------------------------


def supersede_older_quotations(sq_name, rfq_name, supplier=None, prospective_supplier=None):
	"""Mark every earlier live quotation of the same party on the same RFQ as revised.

	Only quotations created BEFORE ``sq_name`` are touched (creation, name is a strict order), so two
	near-simultaneous submissions can never flag each other and leave the party without a live bid.
	Returns the names that were flagged.
	"""
	if prospective_supplier:
		field, value = "ub_prospective_supplier", prospective_supplier
	elif supplier:
		field, value = "supplier", supplier
	else:
		return []
	creation = frappe.db.get_value("Supplier Quotation", sq_name, "creation")
	older = frappe.db.sql(
		f"""
		SELECT DISTINCT sq.name FROM `tabSupplier Quotation` sq
		JOIN `tabSupplier Quotation Item` sqi ON sqi.parent = sq.name
		WHERE sq.`{field}` = %(party)s AND sq.name != %(me)s AND sq.docstatus < 2
		  AND IFNULL(sq.ub_revised, 0) = 0
		  AND sqi.request_for_quotation = %(rfq)s
		  AND (sq.creation < %(creation)s OR (sq.creation = %(creation)s AND sq.name < %(me)s))
		""",
		{"party": value, "me": sq_name, "rfq": rfq_name, "creation": creation},
		pluck=True,
	)
	for name in older:
		frappe.db.set_value("Supplier Quotation", name, {"ub_revised": 1, "ub_revision_requested": 0},
			update_modified=False)
	return older


# ---------------------------------------------------------------------------
# Create -> Purchase Order (standard button) wrapper
# ---------------------------------------------------------------------------


@frappe.whitelist()
def make_purchase_order(source_name, target_doc=None, args=None):
	"""Override of erpnext...supplier_quotation.make_purchase_order (OVERRIDE_WHITELISTED_METHODS)."""
	src = frappe.db.get_value("Supplier Quotation", source_name,
		["supplier", "ub_prospective_supplier", "ub_po_type", "ub_revised", "workflow_state", "ub_sq_status"],
		as_dict=True) or frappe._dict()
	if src.ub_revised:
		frappe.throw(_("Supplier Quotation {0} was superseded by a newer version and cannot be ordered.").format(
			source_name))
	if src.ub_sq_status == "Rejected" or src.workflow_state == "Rejected":
		frappe.throw(_("Supplier Quotation {0} was rejected and cannot be ordered.").format(source_name))

	supplier = src.supplier
	if not supplier and src.ub_prospective_supplier:
		supplier = _supplier_for_prospective(src.ub_prospective_supplier)
		if not supplier:
			frappe.throw(
				_("Prospective Supplier {0} has not completed onboarding yet. Create the Purchase Order once the "
				  "Supplier is approved.").format(frappe.bold(src.ub_prospective_supplier)),
				title=_("Supplier not onboarded"),
			)

	target = _erpnext_make_purchase_order(source_name, target_doc, args)

	if supplier and not target.get("supplier"):
		target.supplier = supplier
		target.run_method("set_missing_values")
	from universal_buying.universal_buying.utils import set_po_origin

	if target.meta.has_field("ub_origin_doctype"):
		set_po_origin(target, "Supplier Quotation", source_name)
	if target.meta.has_field("ub_po_type") and src.ub_po_type:
		target.ub_po_type = src.ub_po_type
	return target


def _supplier_for_prospective(prospective_supplier):
	try:
		from universal_buying.ub_supplier.api import get_supplier_for_prospective
	except ImportError:
		return frappe.db.get_value("Prospective Supplier", prospective_supplier, "linked_supplier") if (
			frappe.get_meta("Prospective Supplier").has_field("linked_supplier")) else None
	return get_supplier_for_prospective(prospective_supplier)
