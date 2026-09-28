"""V-28.1 indent cap, V-28.2 approval limit, allocation of the requested amount over POs."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from universal_buying.ub_finance.doctype.payment_indent import payment_indent as pi_mod

SETTINGS = {
	"indent_cap_percent": 110,
	"indent_approval_limit_inr": 500000,
	"indent_approval_limit_fx": 5000,
}


def fake_setting(fieldname, company=None, default=None):
	return SETTINGS.get(fieldname, default)


def _company():
	return frappe.db.get_value("Company", {}, "name")


def make_indent(total_by_po, requested, currency=None):
	company = _company()
	currency = currency or frappe.get_cached_value("Company", company, "default_currency")
	doc = frappe.get_doc({
		"doctype": "Payment Indent",
		"company": company,
		"supplier": "_UB Test Supplier",
		"currency": currency,
		"requested_amount": requested,
		"purchase_orders": [{"purchase_order": po} for po in total_by_po],
		"items": [
			{"purchase_order": po, "item_code": "X", "qty": 10, "indent_qty": 10, "rate": value / 10.0, "value": value}
			for po, value in total_by_po.items()
		],
	})
	doc.set_totals()
	return doc


class TestIndentCap(IntegrationTestCase):
	def test_within_cap(self):
		doc = make_indent({"PO-1": 1000}, 1100)
		with patch.object(pi_mod, "get_setting", side_effect=fake_setting):
			doc.validate_requested_amount()

	def test_above_cap_blocks(self):
		doc = make_indent({"PO-1": 1000}, 1101)
		with patch.object(pi_mod, "get_setting", side_effect=fake_setting):
			with self.assertRaises(frappe.ValidationError):
				doc.validate_requested_amount()

	def test_indent_qty_above_po_qty_blocks(self):
		doc = make_indent({"PO-1": 1000}, 100)
		doc.items[0].indent_qty = 11
		with self.assertRaises(frappe.ValidationError):
			doc.validate_items()

	def test_allocation_over_pos(self):
		doc = make_indent({"PO-1": 3000, "PO-2": 1000}, 2000)
		doc.allocate_requested_amount()
		alloc = {d.purchase_order: d.allocated_amount for d in doc.purchase_orders}
		self.assertAlmostEqual(alloc["PO-1"], 1500)
		self.assertAlmostEqual(alloc["PO-2"], 500)
		self.assertAlmostEqual(sum(alloc.values()), 2000)


from contextlib import contextmanager


@contextmanager
def _as_user(user):
	"""frappe.session is a dict-like object, so patch.object cannot patch .user; swap it directly."""
	previous = frappe.session.user
	frappe.session.user = user
	try:
		yield
	finally:
		frappe.session.user = previous


class TestIndentApproval(IntegrationTestCase):
	def _check(self, doc, has_role):
		with (
			patch.object(pi_mod, "get_setting", side_effect=fake_setting),
			patch.object(pi_mod, "get_list", return_value=["Purchase Manager"]),
			patch.object(pi_mod, "has_any_role", return_value=has_role),
		):
			doc.check_approval()

	def test_below_limit_needs_no_role(self):
		doc = make_indent({"PO-1": 500000}, 500000)
		with _as_user("someone@example.com"):
			self._check(doc, has_role=False)
		self.assertFalse(doc.approved_by)

	def test_above_company_currency_limit_needs_role(self):
		doc = make_indent({"PO-1": 600000}, 500001)
		with _as_user("someone@example.com"):
			with self.assertRaises(frappe.PermissionError):
				self._check(doc, has_role=False)

	def test_above_limit_with_role_is_approved(self):
		doc = make_indent({"PO-1": 600000}, 500001)
		with _as_user("approver@example.com"):
			self._check(doc, has_role=True)
		self.assertEqual(doc.approved_by, "approver@example.com")

	def test_foreign_currency_uses_fx_limit(self):
		company_ccy = frappe.get_cached_value("Company", _company(), "default_currency")
		fx = "USD" if company_ccy != "USD" else "EUR"
		doc = make_indent({"PO-1": 6000}, 5001, currency=fx)
		with patch.object(pi_mod, "get_setting", side_effect=fake_setting):
			self.assertEqual(doc.approval_limit(), 5000)
			self.assertTrue(doc.needs_approval())
