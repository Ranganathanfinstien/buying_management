"""A-27.1 TDS opening balance threshold math and the v16 engine hooks."""

import frappe
from frappe.tests import IntegrationTestCase

from universal_buying.ub_finance.tds import UBPurchaseTaxWithholding, split_on_threshold, tds_amount


class TestThresholdMath(IntegrationTestCase):
	def test_balance_already_above_threshold_taxes_everything(self):
		self.assertEqual(split_on_threshold(50000, 120000, 100000), (0.0, 50000.0))
		self.assertAlmostEqual(tds_amount(50000, 120000, 100000, 2), 1000)

	def test_crossing_taxes_only_the_excess(self):
		# 80k opening + 50k invoice, threshold 100k -> 30k taxable
		self.assertEqual(split_on_threshold(50000, 80000, 100000), (20000.0, 30000.0))
		self.assertAlmostEqual(tds_amount(50000, 80000, 100000, 1), 300)

	def test_below_threshold_no_tax(self):
		self.assertEqual(split_on_threshold(10000, 20000, 100000), (10000.0, 0.0))
		self.assertEqual(tds_amount(10000, 20000, 100000, 2), 0)

	def test_exactly_at_threshold_no_tax(self):
		self.assertEqual(split_on_threshold(20000, 80000, 100000), (20000.0, 0.0))

	def test_zero_amount(self):
		self.assertEqual(split_on_threshold(0, 80000, 100000), (0.0, 0.0))


class TestEngineOverride(IntegrationTestCase):
	def _controller(self, balance, categories=("194C",)):
		ctl = object.__new__(UBPurchaseTaxWithholding)
		ctl.opening_categories = set(categories)
		ctl.opening_balance = balance
		return ctl

	def test_unused_threshold_is_threshold_minus_balance(self):
		ctl = self._controller(80000)
		cat = frappe._dict(name="194C", cumulative_threshold=100000, disable_cumulative_threshold=0)
		self.assertTrue(ctl._is_threshold_crossed_for_category(cat))
		self.assertEqual(ctl._get_unused_threshold(cat), 20000)

	def test_unused_threshold_never_negative(self):
		ctl = self._controller(150000)
		cat = frappe._dict(name="194C", cumulative_threshold=100000, disable_cumulative_threshold=0)
		self.assertEqual(ctl._get_unused_threshold(cat), 0)

	def test_other_categories_use_standard_rule(self):
		ctl = self._controller(80000)
		cat = frappe._dict(name="194J", cumulative_threshold=30000, disable_cumulative_threshold=0)
		self.assertFalse(ctl._uses_opening(cat))
