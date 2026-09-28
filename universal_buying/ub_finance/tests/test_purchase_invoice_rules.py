"""V-27.1 (2-Way / 3-Way), V-27.2 (tolerance + override reason), V-27.3 (account currency)."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from universal_buying.ub_finance.overrides import purchase_invoice as pi_mod
from universal_buying.ub_finance.overrides.purchase_invoice import UBPurchaseInvoice, allowed_invoice_total

THREE_WAY = frappe._dict(name="3-Way", receipt_required=1, po_required_on_invoice=1, invoice_tolerance_percent=0)
TWO_WAY = frappe._dict(name="2-Way", receipt_required=0, po_required_on_invoice=1, invoice_tolerance_percent=0)
NO_PO = frappe._dict(name="Open", receipt_required=0, po_required_on_invoice=0, invoice_tolerance_percent=0)


def _company():
	return frappe.db.get_value("Company", {}, "name")


def make_pi(items, **kw):
	doc = UBPurchaseInvoice({"doctype": "Purchase Invoice", "company": _company(), "supplier": "_UB Test Supplier",
		"currency": "INR", "items": items, **kw})
	return doc


class TestMatchByPOType(IntegrationTestCase):
	def _run(self, doc, type_map, default=THREE_WAY, supplier_flag=False, stock_items=("STOCK",)):
		with (
			patch.object(UBPurchaseInvoice, "ub_po_type_map", return_value=type_map),
			patch.object(UBPurchaseInvoice, "ub_supplier_flag", return_value=supplier_flag),
			patch.object(UBPurchaseInvoice, "get_stock_items", return_value=list(stock_items)),
			patch.object(UBPurchaseInvoice, "get_asset_items", return_value=[]),
			patch.object(pi_mod, "get_po_type", return_value=default),
		):
			doc.po_required()
			doc.pr_required()

	def test_three_way_needs_receipt(self):
		doc = make_pi([{"item_code": "STOCK", "qty": 1, "rate": 10, "purchase_order": "PO-1"}])
		with self.assertRaises(frappe.ValidationError):
			self._run(doc, {"PO-1": THREE_WAY})

	def test_three_way_with_receipt_passes(self):
		doc = make_pi([{"item_code": "STOCK", "qty": 1, "rate": 10, "purchase_order": "PO-1", "purchase_receipt": "PR-1"}])
		self._run(doc, {"PO-1": THREE_WAY})

	def test_two_way_needs_no_receipt(self):
		doc = make_pi([{"item_code": "STOCK", "qty": 1, "rate": 10, "purchase_order": "PO-1"}])
		self._run(doc, {"PO-1": TWO_WAY})

	def test_po_required_for_rows_without_po(self):
		doc = make_pi([{"item_code": "SERVICE", "qty": 1, "rate": 10}])
		with self.assertRaises(frappe.ValidationError):
			self._run(doc, {}, default=TWO_WAY)

	def test_default_type_without_po_requirement(self):
		doc = make_pi([{"item_code": "SERVICE", "qty": 1, "rate": 10}])
		self._run(doc, {}, default=NO_PO)

	def test_supplier_exception_skips_both(self):
		doc = make_pi([{"item_code": "STOCK", "qty": 1, "rate": 10}])
		self._run(doc, {}, default=THREE_WAY, supplier_flag=True)

	def test_update_stock_invoice_is_its_own_receipt(self):
		doc = make_pi([{"item_code": "STOCK", "qty": 1, "rate": 10, "purchase_order": "PO-1"}], update_stock=1)
		self._run(doc, {"PO-1": THREE_WAY})


class TestInvoiceTolerance(IntegrationTestCase):
	def test_allowed_total(self):
		self.assertAlmostEqual(allowed_invoice_total([(1000, 5), (500, 0)]), 1550)

	def _doc(self, total, reason=None):
		doc = make_pi([{"item_code": "STOCK", "qty": 1, "rate": total, "purchase_order": "PO-1"}], ub_override_reason=reason)
		doc.base_grand_total = total
		return doc

	def test_within_tolerance(self):
		doc = self._doc(1049)
		with patch.object(UBPurchaseInvoice, "ub_po_totals", return_value=[(1000, 5)]):
			doc.ub_validate_invoice_within_po()
		self.assertFalse(doc.flags.ub_over_po_message)

	def test_above_tolerance_blocks_without_reason(self):
		doc = self._doc(1060)
		with patch.object(UBPurchaseInvoice, "ub_po_totals", return_value=[(1000, 5)]):
			with self.assertRaises(frappe.ValidationError):
				doc.ub_validate_invoice_within_po()

	def test_above_tolerance_with_reason_warns(self):
		doc = self._doc(1060, reason="Freight charged on invoice")
		with patch.object(UBPurchaseInvoice, "ub_po_totals", return_value=[(1000, 5)]):
			doc.ub_validate_invoice_within_po()
		self.assertTrue(doc.flags.ub_over_po_message)


class TestAccountCurrency(IntegrationTestCase):
	def _check(self, account_currency, invoice_currency):
		doc = make_pi([], credit_to="_UB Test Payable", currency=invoice_currency)
		real = frappe.get_cached_value

		def fake(doctype, name, field, *a, **k):
			if doctype == "Account":
				return account_currency
			return real(doctype, name, field, *a, **k)

		with patch.object(pi_mod.frappe, "get_cached_value", side_effect=fake), \
			patch.object(pi_mod, "get_setting", return_value="Block"):
			doc.ub_validate_account_currency()

	def test_same_currency_passes(self):
		self._check("USD", "USD")

	def test_mismatch_blocks(self):
		with self.assertRaises(frappe.ValidationError):
			self._check("INR", "USD")
