"""TDS opening balance (BRD v2 A-27.1), based on calculate_cumulative_threshold /
update_cumulative_balance and rebuilt on the ERPNext v16 tax withholding engine.

v16 no longer has ``get_tax_withholding_details`` / ``get_tax_row_for_tds``. TDS is computed by
``erpnext.accounts.doctype.tax_withholding_entry.tax_withholding_entry.PurchaseTaxWithholding``
which writes Tax Withholding Entry rows and the tax row. We subclass it and change only the
threshold rule for categories that are in "opening balance" mode for the supplier:

	B = supplier running balance for the company (opening + invoices billed in this system)
	T = cumulative threshold of the category, A = TDS applicable amount of this invoice
	B >= T          -> tax on A
	A + B > T       -> tax on A + B - T (the part above the threshold)
	otherwise       -> no tax (the whole amount is a threshold exemption)

The engine then records the exempt part as a "Threshold Exemption" entry and taxes the rest,
so GL, Tax Withholding Entries and reports stay standard. On submit the running balance is
increased by A; on cancel it is reduced again (the source never reversed it).
"""

import frappe
from frappe.utils import flt

from erpnext.accounts.doctype.tax_withholding_entry.tax_withholding_entry import PurchaseTaxWithholding

from universal_buying.universal_buying.settings import get_setting


def split_on_threshold(applicable, balance, threshold):
	"""Return (exempt_amount, taxable_amount) for the opening balance rule."""
	applicable, balance, threshold = flt(applicable), flt(balance), flt(threshold)
	if applicable <= 0:
		return 0.0, 0.0
	if balance >= threshold:
		return 0.0, applicable
	if applicable + balance > threshold:
		taxable = applicable + balance - threshold
		return applicable - taxable, taxable
	return applicable, 0.0


def tds_amount(applicable, balance, threshold, rate):
	"""Formula: tax = taxable part x rate / 100."""
	return split_on_threshold(applicable, balance, threshold)[1] * flt(rate) / 100.0


def opening_mode_on(company=None):
	return bool(get_setting("tds_opening_balance_mode", company=company, default=0))


def get_opening_categories(supplier):
	if not supplier or not frappe.get_meta("Supplier").has_field("ub_tax_withholding_details"):
		return set()
	return set(
		frappe.get_all(
			"UB Supplier TDS Category",
			filters={"parent": supplier, "parenttype": "Supplier", "enabled": 1},
			pluck="tax_withholding_category",
		)
	)


def get_balance_row(supplier, company):
	rows = frappe.get_all(
		"UB Supplier TDS Balance",
		filters={"parent": supplier, "parenttype": "Supplier", "company": company},
		fields=["name", "existing_balance", "updated_balance"],
		limit=1,
	)
	return rows[0] if rows else None


def get_running_balance(supplier, company):
	row = get_balance_row(supplier, company)
	if not row:
		return None
	return flt(row.updated_balance) if row.updated_balance else flt(row.existing_balance)


def applies_to_invoice(doc):
	"""True when the opening balance rule must be used for this invoice."""
	if doc.get("is_return") or not doc.get("apply_tds") or doc.get("override_tax_withholding_entries"):
		return False
	if not opening_mode_on(doc.company):
		return False
	cats = get_opening_categories(doc.supplier)
	if not cats:
		return False
	if get_balance_row(doc.supplier, doc.company) is None:
		return False
	return any(d.get("apply_tds") and d.get("tax_withholding_category") in cats for d in doc.items)


def applicable_amount(doc, categories=None):
	categories = categories if categories is not None else get_opening_categories(doc.supplier)
	return sum(
		flt(d.base_net_amount)
		for d in doc.items
		if d.get("apply_tds") and d.get("tax_withholding_category") in categories
	)


class UBPurchaseTaxWithholding(PurchaseTaxWithholding):
	"""v16 TDS engine with the opening balance threshold rule for the supplier's opening categories."""

	def __init__(self, doc):
		super().__init__(doc)
		self.opening_categories = get_opening_categories(doc.supplier)
		self.opening_balance = flt(get_running_balance(doc.supplier, doc.company))

	def _uses_opening(self, category):
		return (
			category.name in self.opening_categories
			and flt(category.cumulative_threshold) > 0
			and not category.disable_cumulative_threshold
		)

	def _is_threshold_crossed_for_category(self, category):
		if self._uses_opening(category):
			# always "crossed": the part below the threshold is handled as a threshold exemption,
			# so no Under Withheld entries are created that would be taxed back later
			return True
		return super()._is_threshold_crossed_for_category(category)

	def _get_unused_threshold(self, category):
		if self._uses_opening(category):
			return max(0.0, flt(category.cumulative_threshold) - self.opening_balance)
		return super()._get_unused_threshold(category)


def apply_opening_balance_tds(doc):
	"""Called from the Purchase Invoice override after the standard validate."""
	if not applies_to_invoice(doc):
		doc.ub_tds_opening_applied = 0
		doc.ub_tds_opening_amount = 0
		return
	UBPurchaseTaxWithholding(doc).on_validate()
	doc.ub_tds_opening_applied = 1
	doc.ub_tds_opening_amount = applicable_amount(doc)


def update_running_balance(doc, cancel=False):
	"""on_submit / on_cancel: move the supplier running balance by the invoice's applicable amount."""
	if not doc.get("ub_tds_opening_applied") or not flt(doc.get("ub_tds_opening_amount")):
		return
	row = get_balance_row(doc.supplier, doc.company)
	if not row:
		return
	current = flt(row.updated_balance) if row.updated_balance else flt(row.existing_balance)
	delta = -flt(doc.ub_tds_opening_amount) if cancel else flt(doc.ub_tds_opening_amount)
	frappe.db.set_value("UB Supplier TDS Balance", row.name, "updated_balance", current + delta, update_modified=False)


def supplier_validate(doc, method=None):
	"""Supplier validate: one balance row per company; running balance starts at the opening balance."""
	seen = set()
	for row in doc.get("ub_tds_opening_balances") or []:
		if row.company in seen:
			frappe.throw(frappe._("TDS Opening Balance: company {0} is entered twice").format(frappe.bold(row.company)))
		seen.add(row.company)
		if not flt(row.updated_balance) and flt(row.existing_balance):
			row.updated_balance = row.existing_balance
