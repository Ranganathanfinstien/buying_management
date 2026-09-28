"""Purchase Invoice override (BRD v2 section 6.27).

V-27.1  PO Type of the linked Purchase Orders decides the match: 2-Way needs a PO, 3-Way needs a
        PO and a receipt. Supplier flags ``allow_purchase_invoice_creation_without_purchase_order`` /
        ``..._receipt`` are honoured. Rows without a PO use the default PO Type.
V-27.2  Invoice total must not exceed the linked PO total plus the PO Type tolerance. Above it,
        save is blocked until ``ub_override_reason`` is filled; then a warning is shown and a
        timeline comment is added.
V-27.3  Credit To account currency must equal the invoice currency (mode setting
        ``invoice_account_currency_check``, default Block).
A-27.1  TDS opening balance (see ub_finance/tds.py).
Import flag from the supplier address country vs the company country.
Background submit / cancel above ``background_submit_rows`` rows.

Dropped from the sources: WBS / subsidy / SEZ / equipment variance / capital project, freeform
(item-less) rows, Capex/Revex reference stamping.
"""

import frappe
from frappe import _
from frappe.utils import flt

from erpnext.accounts.doctype.purchase_invoice.purchase_invoice import PurchaseInvoice

from universal_buying.ub_finance import background, tds
from universal_buying.universal_buying.doctype.po_type.po_type import get_po_type
from universal_buying.universal_buying.settings import apply_mode, get_setting

PO_TYPE_FIELD = "ub_po_type"


def allowed_invoice_total(po_rows):
	"""po_rows: iterable of (po_total, tolerance_percent). Returns the maximum invoice total."""
	return sum(flt(total) * (1 + flt(tol) / 100.0) for total, tol in po_rows)


class UBPurchaseInvoice(PurchaseInvoice):
	# ------------------------------------------------------------------ validate
	def validate(self):
		self.ub_set_import_flag()
		super().validate()
		if not self.is_return:
			self.ub_validate_invoice_within_po()
		tds.apply_opening_balance_tds(self)

	def before_submit(self):
		super().before_submit()
		self.ub_validate_account_currency()

	def on_update(self):
		super().on_update()
		self.ub_comment_override_reason()

	def on_submit(self):
		super().on_submit()
		tds.update_running_balance(self)
		if self.flags.get("ub_over_po_message"):
			self.add_comment(
				"Comment",
				_("Submitted above Purchase Order total + tolerance. {0}<br>Reason: {1}").format(
					self.flags.ub_over_po_message, frappe.utils.escape_html(self.ub_override_reason or "")
				),
			)

	def on_cancel(self):
		super().on_cancel()
		tds.update_running_balance(self, cancel=True)

	# ------------------------------------------------------------------ background submit / cancel
	@frappe.whitelist()
	def submit(self):
		if background.should_run_in_background(self):
			# save first so validation errors still show immediately
			self.docstatus = 0
			self.save()
			return background.queue_action_with_message(self, "submit")
		return self._submit()

	@frappe.whitelist()
	def cancel(self):
		if background.should_run_in_background(self):
			return background.queue_action_with_message(self, "cancel")
		return self._cancel()

	# ------------------------------------------------------------------ PO Type helpers
	def ub_linked_pos(self):
		return sorted({d.purchase_order for d in self.get("items") or [] if d.get("purchase_order")})

	def ub_po_type_map(self):
		"""{purchase_order: PO Type doc} for the linked POs (default type when the PO has none)."""
		pos = self.ub_linked_pos()
		if not pos:
			return {}
		has_field = frappe.get_meta("Purchase Order").has_field(PO_TYPE_FIELD)
		out = {}
		for po in pos:
			name = frappe.db.get_value("Purchase Order", po, PO_TYPE_FIELD) if has_field else None
			out[po] = get_po_type(name)
		return out

	def ub_type_for_row(self, row, type_map=None):
		type_map = self.ub_po_type_map() if type_map is None else type_map
		if row.get("purchase_order") and row.purchase_order in type_map:
			return type_map[row.purchase_order]
		return get_po_type()

	def ub_supplier_flag(self, fieldname):
		return bool(self.supplier and frappe.get_cached_value("Supplier", self.supplier, fieldname))

	# ------------------------------------------------------------------ V-27.1
	def po_required(self):
		"""PO Type driven replacement of the Buying Settings rule."""
		if self.is_internal_transfer():
			return
		if self.ub_supplier_flag("allow_purchase_invoice_creation_without_purchase_order"):
			return
		default_type = get_po_type()
		if not default_type.po_required_on_invoice:
			return
		missing = [d for d in self.get("items") if not d.get("purchase_order")]
		if missing:
			frappe.throw(
				_("Row {0}: Purchase Order is required for item {1} (PO Type {2}).").format(
					missing[0].idx, frappe.bold(missing[0].item_code), frappe.bold(default_type.name or _("default"))
				)
				+ "<br><br>"
				+ _("To allow it for this supplier, tick 'Allow Purchase Invoice Creation Without Purchase Order' on the Supplier."),
				title=_("Mandatory Purchase Order"),
			)

	def pr_required(self):
		"""3-Way: stock / asset rows need a Purchase Receipt when the PO Type says receipt_required."""
		if self.get("update_stock"):
			return  # the invoice itself receives the goods
		if self.ub_supplier_flag("allow_purchase_invoice_creation_without_purchase_receipt"):
			return
		stock_items = set(self.get_stock_items()) | set(self.get_asset_items())
		type_map = self.ub_po_type_map()
		for d in self.get("items"):
			if d.get("purchase_receipt") or d.item_code not in stock_items:
				continue
			po_type = self.ub_type_for_row(d, type_map)
			if po_type.receipt_required:
				frappe.throw(
					_("Row {0}: Purchase Receipt is required for item {1}: PO Type {2} is a 3-Way match.").format(
						d.idx, frappe.bold(d.item_code), frappe.bold(po_type.name or "3-Way")
					)
					+ "<br><br>"
					+ _("To allow it for this supplier, tick 'Allow Purchase Invoice Creation Without Purchase Receipt' on the Supplier."),
					title=_("Mandatory Purchase Receipt"),
				)

	# ------------------------------------------------------------------ V-27.2
	def ub_po_totals(self):
		"""[(po_base_grand_total, tolerance_percent)] for the linked POs."""
		type_map = self.ub_po_type_map()
		rows = []
		for po, po_type in type_map.items():
			total = flt(frappe.db.get_value("Purchase Order", po, "base_grand_total"))
			rows.append((total, flt(po_type.invoice_tolerance_percent)))
		return rows

	def ub_validate_invoice_within_po(self):
		self.flags.ub_over_po_message = None
		rows = self.ub_po_totals()
		if not rows or not sum(flt(r[0]) for r in rows):
			return
		allowed = allowed_invoice_total(rows)
		invoice_total = flt(self.base_grand_total)
		if invoice_total <= allowed + 0.01:
			return

		ccy = frappe.get_cached_value("Company", self.company, "default_currency")
		po_total = sum(flt(r[0]) for r in rows)
		msg = _("Invoice total {0} is above the Purchase Order total {1} plus the PO Type tolerance (allowed {2}).").format(
			frappe.bold(frappe.utils.fmt_money(invoice_total, currency=ccy)),
			frappe.bold(frappe.utils.fmt_money(po_total, currency=ccy)),
			frappe.bold(frappe.utils.fmt_money(allowed, currency=ccy)),
		)
		reason = (self.get("ub_override_reason") or "").strip()
		if not reason:
			frappe.throw(
				msg + "<br><br>" + _("Enter an Override Reason to save this invoice."),
				title=_("Invoice Exceeds Purchase Order"),
			)
		self.flags.ub_over_po_message = msg
		frappe.msgprint(
			msg + "<br>" + _("Proceeding with reason: {0}").format(frappe.utils.escape_html(reason)),
			title=_("Invoice Exceeds Purchase Order"),
			indicator="orange",
		)

	def ub_comment_override_reason(self):
		if not self.flags.get("ub_over_po_message"):
			return
		before = self.get_doc_before_save()
		if before and (before.get("ub_override_reason") or "") == (self.get("ub_override_reason") or ""):
			return
		self.add_comment(
			"Comment",
			_("Invoice above Purchase Order total + tolerance. {0}<br>Override reason: {1}").format(
				self.flags.ub_over_po_message, frappe.utils.escape_html(self.ub_override_reason or "")
			),
		)

	# ------------------------------------------------------------------ V-27.3
	def ub_validate_account_currency(self):
		if not self.credit_to:
			return
		account_currency = frappe.get_cached_value("Account", self.credit_to, "account_currency")
		if account_currency and account_currency != self.currency:
			apply_mode(
				get_setting("invoice_account_currency_check", company=self.company, default="Block"),
				_("Credit To account {0} is in {1} but the invoice is in {2}. Select a payable account in {2}.").format(
					frappe.bold(self.credit_to), frappe.bold(account_currency), frappe.bold(self.currency)
				),
				title=_("Account Currency Mismatch"),
			)

	# ------------------------------------------------------------------ import flag
	def ub_set_import_flag(self):
		if not self.get("supplier_address"):
			return
		supplier_country = frappe.db.get_value("Address", self.supplier_address, "country")
		company_country = frappe.get_cached_value("Company", self.company, "country")
		if supplier_country and company_country:
			self.ub_is_import = 1 if supplier_country != company_country else 0
