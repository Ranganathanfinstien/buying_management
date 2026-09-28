"""V-23.2: over-receipt is checked at save (not only at submit)."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from universal_buying.ub_inward import receipt
from universal_buying.ub_inward.tests.helpers import fake_receipt

PO_ROW = frappe._dict(name="poi-1", parent="PO-1", item_code="_UB Item", qty=100)


class TestOverReceipt(IntegrationTestCase):
	def run_rule(self, rows, already=0, allowance=0, roles=None, bypass_role=None):
		doc = fake_receipt(items=rows)
		with (
			patch("frappe.get_all", return_value=[PO_ROW]),
			patch.object(receipt, "get_already_received", return_value={"poi-1": already}),
			patch(
				"erpnext.controllers.status_updater.get_allowance_for",
				side_effect=lambda item, a, q, m, kind: (allowance, a or {}, q, m),
			),
			patch("frappe.get_single_value", return_value=bypass_role),
			patch("frappe.get_roles", return_value=roles or []),
			patch("frappe.msgprint"),
		):
			receipt.validate_over_receipt(doc)

	def row(self, idx, qty, rejected=0):
		return {
			"idx": idx,
			"purchase_order_item": "poi-1",
			"qty": qty,
			"rejected_qty": rejected,
			"received_qty": qty + rejected,
		}

	def test_within_order_passes(self):
		self.run_rule([self.row(1, 60)], already=40)

	def test_over_order_blocks_at_save(self):
		with self.assertRaises(frappe.ValidationError):
			self.run_rule([self.row(1, 61)], already=40)

	def test_duplicate_rows_are_summed(self):
		with self.assertRaises(frappe.ValidationError):
			self.run_rule([self.row(1, 30), self.row(2, 30, rejected=1)], already=40)

	def test_allowance_is_respected(self):
		self.run_rule([self.row(1, 70)], already=40, allowance=10)

	def test_bypass_role_only_warns(self):
		self.run_rule([self.row(1, 80)], already=40, roles=["Stock Manager"], bypass_role="Stock Manager")

	def test_returns_skip(self):
		doc = fake_receipt(is_return=1, items=[self.row(1, -500)])
		receipt.validate_over_receipt(doc)
