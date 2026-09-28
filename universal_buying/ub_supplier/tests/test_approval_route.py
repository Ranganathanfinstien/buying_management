"""Supplier approval route and V-5.3 bank account gate (BRD 6.5)."""

import frappe
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase

from universal_buying.ub_supplier.tests.helpers import (
	make_incoterm,
	make_parent_group,
	make_supplier_group,
	set_supplier_settings,
	unique,
)
from universal_buying.ub_supplier.utils import get_approval_route


class TestApprovalRoute(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.full = make_supplier_group("_Test UB Raw Material")
		cls.finance = make_supplier_group("_Test UB Services")
		cls.other = make_supplier_group("_Test UB Others")
		cls.parent = make_parent_group("_Test UB Full Parent")
		cls.child = make_supplier_group("_Test UB Full Child", parent=cls.parent)
		set_supplier_settings(full=[cls.full, cls.parent], finance=[cls.finance], require_bank=1)

	def make_supplier(self, group, **kw):
		return frappe.get_doc({
			"doctype": "Supplier", "supplier_name": unique("_Test UB Route"), "supplier_group": group, **kw,
		}).insert(ignore_permissions=True)

	def test_route_from_settings(self):
		self.assertEqual(get_approval_route(self.full), "Full")
		self.assertEqual(get_approval_route(self.finance), "Finance")
		self.assertEqual(get_approval_route(self.other), "Direct")
		# a setting on a parent group covers its children
		self.assertEqual(get_approval_route(self.child), "Full")
		self.assertEqual(get_approval_route(None), "Direct")

	def test_route_stored_on_supplier(self):
		self.assertEqual(self.make_supplier(self.full).ub_approval_route, "Full")
		self.assertEqual(self.make_supplier(self.finance).ub_approval_route, "Finance")
		self.assertEqual(self.make_supplier(self.other).ub_approval_route, "Direct")

	def test_route_follows_settings_change(self):
		sup = self.make_supplier(self.other)
		self.assertEqual(sup.ub_approval_route, "Direct")
		set_supplier_settings(full=[self.full, self.parent], finance=[self.finance, self.other], require_bank=1)
		self.assertEqual(frappe.db.get_value("Supplier", sup.name, "ub_approval_route"), "Finance")
		set_supplier_settings(full=[self.full, self.parent], finance=[self.finance], require_bank=1)

	def test_bank_account_required_before_approval(self):
		if not frappe.db.exists("Workflow", "UB Supplier Approval"):
			self.skipTest("UB Supplier Approval workflow not installed")
		sup = self.make_supplier(self.full, ub_incoterm=make_incoterm())
		self.assertEqual(sup.workflow_state, "Draft")
		self.assertRaises(frappe.ValidationError, apply_workflow, sup.as_dict(), "Send for Approval")

		# bank details typed on the supplier become a Bank Account and unblock the transition
		sup.reload()
		sup.ub_bank = "_Test UB Bank"
		sup.ub_bank_account_no = "000111222333"
		if not frappe.db.exists("Bank", "_Test UB Bank"):
			frappe.get_doc({"doctype": "Bank", "bank_name": "_Test UB Bank"}).insert(ignore_permissions=True)
		sup.save(ignore_permissions=True)
		self.assertTrue(frappe.db.exists("Bank Account", {"party_type": "Supplier", "party": sup.name}))
		doc = apply_workflow(frappe.get_doc("Supplier", sup.name).as_dict(), "Send for Approval")
		self.assertEqual(doc.workflow_state, "Pending Purchase Approval")

	def test_direct_route_approves_in_one_step(self):
		if not frappe.db.exists("Workflow", "UB Supplier Approval"):
			self.skipTest("UB Supplier Approval workflow not installed")
		set_supplier_settings(full=[self.full, self.parent], finance=[self.finance], require_bank=0)
		sup = self.make_supplier(self.other, ub_incoterm=make_incoterm())
		doc = apply_workflow(sup.as_dict(), "Approve")
		self.assertEqual(doc.workflow_state, "Enabled")
		set_supplier_settings(full=[self.full, self.parent], finance=[self.finance], require_bank=1)
