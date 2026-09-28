"""V-22.1: gate entry required for non-bonded receipts, with lookback days."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from universal_buying.ub_inward import receipt
from universal_buying.ub_inward.tests.helpers import fake_receipt, settings


class TestGateEntryRule(IntegrationTestCase):
	def run_rule(self, doc, values, gate_entry=None):
		with (
			patch.object(receipt, "get_setting", side_effect=settings(values)),
			patch("universal_buying.ub_inward.utils.get_setting", side_effect=settings(values)),
			patch.object(receipt, "get_gate_entry", return_value=gate_entry),
		):
			receipt.validate_gate_entry(doc)

	def test_required_and_missing_blocks(self):
		doc = fake_receipt(ub_gate_entry=None)
		with self.assertRaises(frappe.ValidationError):
			self.run_rule(doc, {"gate_entry_required": 1})

	def test_not_required_passes(self):
		self.run_rule(fake_receipt(ub_gate_entry=None), {"gate_entry_required": 0})

	def test_bonded_route_is_exempt(self):
		doc = fake_receipt(ub_gate_entry=None, ub_is_bonded=1)
		self.run_rule(doc, {"gate_entry_required": 1, "bonded_goods_enabled": 1})

	def test_bonded_flag_ignored_when_route_disabled(self):
		doc = fake_receipt(ub_gate_entry=None, ub_is_bonded=1)
		with self.assertRaises(frappe.ValidationError):
			self.run_rule(doc, {"gate_entry_required": 1, "bonded_goods_enabled": 0})

	def test_returns_are_exempt(self):
		self.run_rule(fake_receipt(ub_gate_entry=None, is_return=1), {"gate_entry_required": 1})

	def gate_entry(self, **kw):
		ge = frappe._dict(
			docstatus=1,
			entry_type="In",
			company="_Test UB Company",
			entry_date="2026-09-20 10:00:00",
			party_type="Supplier",
			party="_Test UB Supplier",
		)
		ge.update(kw)
		return ge

	def test_valid_gate_entry_passes(self):
		doc = fake_receipt(ub_gate_entry="GE-1")
		self.run_rule(doc, {"gate_entry_required": 1, "gate_entry_lookback_days": 90}, self.gate_entry())

	def test_old_gate_entry_blocks(self):
		doc = fake_receipt(ub_gate_entry="GE-1")
		with self.assertRaises(frappe.ValidationError):
			self.run_rule(
				doc,
				{"gate_entry_required": 1, "gate_entry_lookback_days": 90},
				self.gate_entry(entry_date="2026-01-01 10:00:00"),
			)

	def test_draft_or_outward_gate_entry_blocks(self):
		doc = fake_receipt(ub_gate_entry="GE-1")
		with self.assertRaises(frappe.ValidationError):
			self.run_rule(doc, {"gate_entry_required": 1}, self.gate_entry(docstatus=0))
		with self.assertRaises(frappe.ValidationError):
			self.run_rule(doc, {"gate_entry_required": 1}, self.gate_entry(entry_type="Out"))
