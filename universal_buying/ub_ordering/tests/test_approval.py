"""PO approval: rule matching (8.3), sequencing, V-18.1 and AC-18.1."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from universal_buying.ub_ordering import approval
from universal_buying.ub_ordering.tests import helpers

L = 100000  # one lakh
BANDS = [
	(0, 5 * L, ["Purchase Executive"]),
	(5 * L, 100 * L, ["Purchase Executive", "Purchase Senior Manager"]),
	(100 * L, 200 * L, ["Purchase Executive", "Purchase Senior Manager", "Purchase HOD"]),
	(200 * L, 500 * L, ["Purchase Executive", "Purchase Senior Manager", "Purchase HOD", "President SCM"]),
	(500 * L, 0, ["Purchase Executive", "Purchase Senior Manager", "Purchase HOD", "President SCM", "Managing Director"]),
]


def default_rules():
	rows = []
	for lo, hi, roles in BANDS:
		for step, role in enumerate(roles, 1):
			rows.append(frappe._dict(company=None, origin=None, from_amount=lo, to_amount=hi, step=step, approver_role=role))
	return rows


def roles_of(steps):
	return [s["roles"] for s in steps]


class TestApprovalRuleMatching(IntegrationTestCase):
	def test_default_bands(self):
		rules = default_rules()
		self.assertEqual(roles_of(approval.match_rules(rules, "C", "Manual", 3 * L)), [["Purchase Executive"]])
		# the upper bound is inclusive: exactly 5 L is still the first band
		self.assertEqual(len(approval.match_rules(rules, "C", "Manual", 5 * L)), 1)
		self.assertEqual(roles_of(approval.match_rules(rules, "C", "Manual", 50 * L)),
			[["Purchase Executive"], ["Purchase Senior Manager"]])
		self.assertEqual(len(approval.match_rules(rules, "C", "Manual", 600 * L)), 5)
		self.assertEqual(approval.match_rules(rules, "C", "Manual", 600 * L)[-1]["roles"], ["Managing Director"])

	def test_zero_value_po_matches_first_band(self):
		self.assertEqual(len(approval.match_rules(default_rules(), "C", "Manual", 0)), 1)

	def test_most_specific_rule_wins(self):
		rules = default_rules() + [
			frappe._dict(company="C1", origin=None, from_amount=0, to_amount=0, step=1, approver_role="Company Approver"),
			frappe._dict(company="C1", origin="Auto PO Run", from_amount=0, to_amount=0, step=1, approver_role="Auto Approver"),
			frappe._dict(company=None, origin="Supplier Quotation", from_amount=0, to_amount=0, step=1, approver_role="SQ Approver"),
		]
		self.assertEqual(roles_of(approval.match_rules(rules, "C1", "Manual", 3 * L)), [["Company Approver"]])
		self.assertEqual(roles_of(approval.match_rules(rules, "C1", "Auto PO Run", 3 * L)), [["Auto Approver"]])
		self.assertEqual(roles_of(approval.match_rules(rules, "C2", "Supplier Quotation", 3 * L)), [["SQ Approver"]])
		self.assertEqual(roles_of(approval.match_rules(rules, "C2", "Manual", 3 * L)), [["Purchase Executive"]])

	def test_same_step_several_roles_and_ordering(self):
		rules = [
			frappe._dict(company=None, origin=None, from_amount=0, to_amount=0, step=2, approver_role="B"),
			frappe._dict(company=None, origin=None, from_amount=0, to_amount=0, step=1, approver_role="A1"),
			frappe._dict(company=None, origin=None, from_amount=0, to_amount=0, step=1, approver_role="A2"),
		]
		steps = approval.match_rules(rules, "C", "Manual", 10)
		self.assertEqual([s["step"] for s in steps], [1, 2])
		self.assertEqual(steps[0]["roles"], ["A1", "A2"])

	def test_no_rule(self):
		rules = [frappe._dict(company="Other", origin=None, from_amount=0, to_amount=0, step=1, approver_role="X")]
		self.assertEqual(approval.match_rules(rules, "C", "Manual", 10), [])


TWO_STEP = [
	frappe._dict(company=None, origin=None, from_amount=0, to_amount=0, step=1, approver_role="Purchase Executive"),
	frappe._dict(company=None, origin=None, from_amount=0, to_amount=0, step=2, approver_role="Purchase HOD"),
]


class TestApprovalFlow(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		for role in ("Purchase Executive", "Purchase HOD"):
			if not frappe.db.exists("Role", role):
				frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)
		helpers.make_item()
		helpers.make_supplier()
		cls.exec_user = helpers.make_user("ub-po-exec@example.com", ["Purchase Executive", "Purchase User"])
		cls.hod_user = helpers.make_user("ub-po-hod@example.com", ["Purchase HOD", "Purchase User"])
		cls.admin_like = helpers.make_user("ub-po-sysman@example.com", ["System Manager", "Purchase Manager"])

	def setUp(self):
		self.patches = [
			patch("universal_buying.ub_ordering.approval.get_settings", return_value=frappe._dict(po_approval_rules=TWO_STEP)),
			patch("universal_buying.ub_ordering.approval.get_setting",
				side_effect=helpers.settings({"po_approval_enabled": 1, "submit_po_on_final_approval": 0})),
			patch("universal_buying.ub_ordering.approval._notify_approvers"),
			patch("universal_buying.ub_ordering.approval._notify_owner"),
			patch("universal_buying.ub_ordering.po_rules.validate_addresses"),
			patch("universal_buying.universal_buying.utils.supplier_is_enabled", return_value=True),
			patch("universal_buying.ub_ordering.po_rules.get_setting", side_effect=helpers.settings({"price_control_mode": "Free"})),
		]
		for p in self.patches:
			p.start()
		self.po = helpers.make_po()

	def tearDown(self):
		frappe.set_user("Administrator")
		for p in self.patches:
			p.stop()

	def test_submit_blocked_until_approved(self):
		"""V-18.1"""
		self.po.reload()
		with patch("universal_buying.ub_ordering.overrides.purchase_order.assert_supplier_enabled"):
			self.assertRaises(frappe.ValidationError, self.po.submit)

	def test_sequence_and_history(self):
		state = approval.send_for_approval(self.po.name)
		self.assertEqual(state["status"], approval.PENDING)
		self.assertEqual(state["step"], 1)
		self.assertEqual(state["pending_roles"], ["Purchase Executive"])

		frappe.set_user(self.exec_user)
		state = approval.approve(self.po.name, remarks="ok")
		self.assertEqual(state["status"], approval.PENDING)
		self.assertEqual(state["step"], 2)

		frappe.set_user(self.hod_user)
		state = approval.approve(self.po.name)
		self.assertEqual(state["status"], approval.APPROVED)
		actions = [h["action"] for h in state["history"]]
		self.assertEqual(actions, ["Sent", "Approved", "Approved"])
		self.assertTrue(all(s["status"] == approval.APPROVED for s in state["steps"]))

	def test_lower_role_and_system_manager_cannot_approve(self):
		"""AC-18.1: no System Manager bypass; the step role is required."""
		approval.send_for_approval(self.po.name)
		frappe.set_user(self.hod_user)  # holds step 2 role, not step 1
		self.assertRaises(frappe.PermissionError, approval.approve, self.po.name)
		frappe.set_user(self.admin_like)
		self.assertRaises(frappe.PermissionError, approval.approve, self.po.name)
		# frappe.get_roles("Administrator") returns every role; only assigned roles may count.
		# (A site may have given Administrator the step role on purpose - then approving is allowed.)
		frappe.set_user("Administrator")
		step_roles = set(approval.get_approval_state(self.po.name)["pending_roles"])
		if step_roles & approval._user_roles("Administrator"):
			approval.approve(self.po.name)
		else:
			self.assertRaises(frappe.PermissionError, approval.approve, self.po.name)

	def test_reject_needs_reason_and_restart(self):
		approval.send_for_approval(self.po.name)
		frappe.set_user(self.exec_user)
		self.assertRaises(frappe.ValidationError, approval.reject, self.po.name, "")
		state = approval.reject(self.po.name, "price too high")
		self.assertEqual(state["status"], approval.REJECTED)
		frappe.set_user("Administrator")
		state = approval.send_for_approval(self.po.name)
		self.assertEqual(state["status"], approval.PENDING)
		self.assertEqual(state["step"], 1)

	def test_edit_after_approval_resets(self):
		approval.send_for_approval(self.po.name)
		frappe.set_user(self.exec_user)
		approval.approve(self.po.name)
		frappe.set_user("Administrator")
		po = frappe.get_doc("Purchase Order", self.po.name)
		po.items[0].qty = 20
		po.save(ignore_permissions=True)
		self.assertEqual(po.ub_approval_status, approval.DRAFT)

	def test_manual_status_edit_is_ignored(self):
		po = frappe.get_doc("Purchase Order", self.po.name)
		po.ub_approval_status = approval.APPROVED
		po.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Purchase Order", po.name, "ub_approval_status"), approval.DRAFT)
