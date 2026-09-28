"""Purchase Order rules: strict price control (6.17), MOQ with skip flag (V-17.2), negative tax (V-17.6)."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from universal_buying.ub_ordering import po_rules
from universal_buying.ub_ordering.tests import helpers


def new_po(rows, **header):
	po = frappe.new_doc("Purchase Order")
	po.update({"company": helpers.get_company(), "supplier": helpers.SUPPLIER, "currency": "INR", "conversion_rate": 1})
	po.update(header)
	for r in rows:
		po.append("items", r)
	return po


def mode(value):
	return patch("universal_buying.ub_ordering.po_rules.get_setting", side_effect=helpers.settings({"price_control_mode": value}))


class TestPriceControl(IntegrationTestCase):
	def test_strict_locks_rate_to_valid_price(self):
		po = new_po([{"item_code": "X", "qty": 1, "rate": 120}])
		with mode("Strict"), patch("universal_buying.ub_ordering.po_rules.expected_rate", return_value=(100.0, "Item Price")):
			changed = po_rules.enforce_price_control(po)
		self.assertTrue(changed)
		self.assertEqual(po.items[0].rate, 100.0)

	def test_strict_blocks_missing_or_zero_price(self):
		po = new_po([{"item_code": "X", "qty": 1, "rate": 120}])
		with mode("Strict"), patch("universal_buying.ub_ordering.po_rules.expected_rate", return_value=(None, None)):
			self.assertRaises(frappe.ValidationError, po_rules.enforce_price_control, po)
		with mode("Strict"), patch("universal_buying.ub_ordering.po_rules.expected_rate", return_value=(0.0, "Item Price")):
			self.assertRaises(frappe.ValidationError, po_rules.enforce_price_control, po)

	def test_warn_and_free_keep_buyer_rate(self):
		for m in ("Warn", "Free"):
			po = new_po([{"item_code": "X", "qty": 1, "rate": 120}])
			with mode(m), patch("universal_buying.ub_ordering.po_rules.expected_rate", return_value=(100.0, "Item Price")):
				self.assertFalse(po_rules.enforce_price_control(po))
			self.assertEqual(po.items[0].rate, 120)

	def test_internal_supplier_is_exempt(self):
		po = new_po([{"item_code": "X", "qty": 1, "rate": 120}], is_internal_supplier=1)
		with mode("Strict"), patch("universal_buying.ub_ordering.po_rules.expected_rate", return_value=(None, None)):
			self.assertFalse(po_rules.enforce_price_control(po))

	def test_strict_with_real_item_price(self):
		company = helpers.get_company()
		helpers.make_item()
		helpers.make_supplier()
		helpers.make_item_price(helpers.ITEM, helpers.SUPPLIER, 95, company)
		po = new_po([{"item_code": helpers.ITEM, "qty": 1, "rate": 150, "uom": "Nos", "stock_uom": "Nos",
			"conversion_factor": 1, "schedule_date": frappe.utils.today()}], transaction_date=frappe.utils.today())
		with mode("Strict"):
			po_rules.enforce_price_control(po)
		self.assertEqual(po.items[0].rate, 95)


class TestMOQ(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		helpers.make_item(moq=100)

	def test_moq_blocks_small_qty(self):
		po = new_po([{"item_code": helpers.ITEM, "qty": 10, "stock_qty": 10}])
		self.assertRaises(frappe.ValidationError, po_rules.validate_moq, po)

	def test_skip_moq_line_is_exempt(self):
		po = new_po([{"item_code": helpers.ITEM, "qty": 10, "stock_qty": 10, "ub_skip_moq": 1}],
			ub_origin_doctype="Auto PO Exception")
		po_rules.sync_skip_moq(po)
		po_rules.validate_moq(po)  # no error

	def test_skip_moq_only_from_auto_po_exception(self):
		po = new_po([{"item_code": helpers.ITEM, "qty": 10, "stock_qty": 10, "ub_skip_moq": 1}])
		po_rules.sync_skip_moq(po)
		self.assertEqual(po.items[0].ub_skip_moq, 0)
		self.assertRaises(frappe.ValidationError, po_rules.validate_moq, po)

	def test_moq_counts_all_lines_of_the_item(self):
		po = new_po([{"item_code": helpers.ITEM, "qty": 60, "stock_qty": 60}, {"item_code": helpers.ITEM, "qty": 40, "stock_qty": 40}])
		po_rules.validate_moq(po)  # 100 in total -> ok


class TestTaxRules(IntegrationTestCase):
	def test_negative_tax_blocked(self):
		po = new_po([])
		po.append("taxes", {"charge_type": "On Net Total", "rate": -5, "description": "x"})
		self.assertRaises(frappe.ValidationError, po_rules.validate_negative_taxes, po)
		po = new_po([])
		po.append("taxes", {"charge_type": "Actual", "tax_amount": -5, "description": "x"})
		self.assertRaises(frappe.ValidationError, po_rules.validate_negative_taxes, po)

	def test_template_scope_keywords(self):
		with patch("frappe.db.get_value", return_value=frappe._dict(title="GST Out State", tax_category=None)):
			self.assertEqual(po_rules.template_scope("T1"), "out")
		with patch("frappe.db.get_value", return_value=frappe._dict(title="In State GST", tax_category=None)):
			self.assertEqual(po_rules.template_scope("T2"), "in")
		with patch("frappe.db.get_value", return_value=frappe._dict(title="VAT", tax_category=None)):
			self.assertIsNone(po_rules.template_scope("T3"))
