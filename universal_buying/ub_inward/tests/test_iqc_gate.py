"""V-23.5: the IQC gate is a real server block driven by iqc_gate Off / Warn / Block."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from universal_buying.ub_inward import iqc
from universal_buying.ub_inward.tests.helpers import fake_receipt, settings

ROW = {
	"idx": 1,
	"name": "row-1",
	"item_code": "_UB IQC Item",
	"batch_no": "B1",
	"ub_manufacturer_batch_no": "M1",
}


class TestIQCGate(IntegrationTestCase):
	def gate(self, mode, pending, submitting=True, exempt=False):
		doc = fake_receipt(items=[ROW])
		with (
			patch.object(iqc, "get_setting", side_effect=settings({"iqc_gate": mode})),
			patch.object(iqc, "iqc_exempt", return_value=exempt),
			patch.object(iqc, "get_rows_pending_iqc", return_value=[doc["items"][0]] if pending else []),
		):
			iqc.check_iqc_gate(doc, submitting=submitting)
		return doc

	def test_block_mode_blocks_submit(self):
		with self.assertRaises(frappe.ValidationError):
			self.gate("Block", pending=True)

	def test_block_mode_does_not_block_save(self):
		doc = self.gate("Block", pending=True, submitting=False)
		self.assertEqual(doc.ub_iqc_complete, 0)

	def test_warn_mode_only_warns(self):
		with patch("frappe.msgprint") as msgprint:
			doc = self.gate("Warn", pending=True)
		self.assertTrue(msgprint.called)
		self.assertEqual(doc.ub_iqc_complete, 0)

	def test_off_mode_passes(self):
		doc = self.gate("Off", pending=True)
		self.assertEqual(doc.ub_iqc_complete, 0)

	def test_complete_sets_flag(self):
		doc = self.gate("Block", pending=False)
		self.assertEqual(doc.ub_iqc_complete, 1)

	def test_exempt_receipt_passes(self):
		doc = self.gate("Block", pending=True, exempt=True)
		self.assertEqual(doc.ub_iqc_complete, 1)

	def test_pending_rows_and_sibling_rule(self):
		rows = [
			dict(ROW),
			{
				"idx": 2,
				"name": "row-2",
				"item_code": "_UB IQC Item",
				"batch_no": "B2",
				"ub_manufacturer_batch_no": "M1",
			},
			{
				"idx": 3,
				"name": "row-3",
				"item_code": "_UB IQC Item",
				"batch_no": "B3",
				"ub_manufacturer_batch_no": "M9",
			},
		]
		doc = fake_receipt(items=rows)
		inspections = [
			frappe._dict(name="QI-1", item_code="_UB IQC Item", batch_no="B1", child_row_reference=None)
		]
		with patch.object(iqc, "item_needs_inspection", return_value=True):
			pending = iqc.get_rows_pending_iqc(doc, inspections=inspections)
		# row 1 covered by batch, row 2 covered through the same manufacturer batch, row 3 pending
		self.assertEqual([r.idx for r in pending], [3])
