"""6.25: each Item Non Conformance disposition creates the right standard document."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from universal_buying.ub_inward.doctype.item_non_conformance import item_non_conformance as inc_module

ROW = frappe._dict(
	name="pri-1",
	item_code="_UB Item",
	warehouse="Stores - UBD",
	rejected_warehouse="Rejected Goods - UBD",
	base_net_rate=50,
	base_rate=50,
	conversion_factor=1,
	batch_no="B-1",
	stock_uom="Nos",
)


def make_inc(disposition, **kw):
	inc = frappe._dict(
		name="INC-TEST",
		company="_Test UB Company",
		reference_type="Purchase Receipt",
		reference_name="PR-1",
		item_code="_UB Item",
		batch_no="B-1",
		rejected_qty=5,
		rate=0,
		disposition=disposition,
		rejected_warehouse="Rejected Goods - UBD",
		target_warehouse=None,
	)
	inc.update(kw)
	return inc


class TestINCDisposition(IntegrationTestCase):
	def plan(self, inc, scrap_warehouse=None):
		with patch.object(inc_module, "get_company_warehouse", return_value=scrap_warehouse):
			return inc_module.stock_entry_plan(inc, ROW)

	def test_scrap_without_scrap_warehouse_is_material_issue(self):
		self.assertEqual(self.plan(make_inc("Scrap")), ("Material Issue", "Rejected Goods - UBD", None))

	def test_scrap_with_scrap_warehouse_is_transfer(self):
		self.assertEqual(
			self.plan(make_inc("Scrap"), scrap_warehouse="Scrap - UBD"),
			("Material Transfer", "Rejected Goods - UBD", "Scrap - UBD"),
		)

	def test_transfer_needs_target(self):
		with self.assertRaises(frappe.ValidationError):
			self.plan(make_inc("Transfer"))
		self.assertEqual(
			self.plan(make_inc("Transfer", target_warehouse="Work In Progress - UBD")),
			("Material Transfer", "Rejected Goods - UBD", "Work In Progress - UBD"),
		)

	def test_rework_and_deviation_go_back_to_accepted_warehouse(self):
		for disposition in ("Rework", "Accept On Deviation"):
			self.assertEqual(
				self.plan(make_inc(disposition)),
				("Material Transfer", "Rejected Goods - UBD", "Stores - UBD"),
			)

	def test_return_to_supplier_is_not_a_stock_entry(self):
		with self.assertRaises(frappe.ValidationError):
			self.plan(make_inc("Return to Supplier"))

	def test_built_stock_entry_uses_receipt_rate_and_link(self):
		with patch.object(inc_module, "get_company_warehouse", return_value=None):
			se = inc_module.build_stock_entry(make_inc("Scrap"), ROW)
		self.assertEqual(se.stock_entry_type, "Material Issue")
		self.assertEqual(se.purpose, "Material Issue")
		self.assertEqual(se.ub_item_non_conformance, "INC-TEST")
		row = se.items[0]
		self.assertEqual(row.s_warehouse, "Rejected Goods - UBD")
		self.assertFalse(row.t_warehouse)
		self.assertEqual(row.basic_rate, 50)
		self.assertEqual(row.batch_no, "B-1")
