"""V-23.4: remaining shelf life must be at least min_remaining_shelf_life_percent at batch creation."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from universal_buying.ub_inward import batch
from universal_buying.ub_inward.tests.helpers import settings


class TestShelfLife(IntegrationTestCase):
	def test_percent_helper(self):
		self.assertAlmostEqual(batch.remaining_shelf_life_percent("2026-01-01", "2026-01-01", 100), 100.0)
		self.assertAlmostEqual(batch.remaining_shelf_life_percent("2026-01-01", "2026-01-31", 100), 70.0)
		self.assertEqual(batch.remaining_shelf_life_percent("2025-01-01", "2026-01-31", 100), 0.0)
		self.assertIsNone(batch.remaining_shelf_life_percent("2026-01-01", "2026-01-31", 0))

	def check(self, mfg_date, posting_date, shelf_life, minimum=75):
		row = frappe._dict(idx=1, item_code="_UB Shelf Item", ub_manufacturing_date=mfg_date)
		with patch.object(
			batch, "get_setting", side_effect=settings({"min_remaining_shelf_life_percent": minimum})
		):
			return batch.validate_remaining_shelf_life(row, posting_date, "_Test UB Company", shelf_life)

	def test_fresh_lot_passes(self):
		self.assertAlmostEqual(self.check("2026-09-01", "2026-09-26", 365), (365 - 25) / 365 * 100)

	def test_old_lot_blocks(self):
		with self.assertRaises(frappe.ValidationError):
			self.check("2026-01-01", "2026-09-26", 365)

	def test_boundary(self):
		self.check("2026-01-01", "2026-01-26", 100)  # exactly 75% left
		with self.assertRaises(frappe.ValidationError):
			self.check("2026-01-01", "2026-01-27", 100)

	def test_no_shelf_life_or_rule_off(self):
		self.assertIsNone(self.check("2020-01-01", "2026-09-26", 0))
		self.assertIsNone(self.check("2020-01-01", "2026-09-26", 365, minimum=0))

	def test_future_manufacturing_date_blocks(self):
		with self.assertRaises(frappe.ValidationError):
			self.check("2026-10-01", "2026-09-26", 365)
