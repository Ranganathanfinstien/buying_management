"""V-15.1: a quotation of an RFQ is approved only by the award; the award rejects every other quotation."""

import frappe
from frappe.tests import IntegrationTestCase

from universal_buying.ub_sourcing.comparison import _reject_quotations
from universal_buying.ub_sourcing.tests.test_tokens_and_revisions import make_rfq, make_sq


class TestAwardGuard(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.rfq = make_rfq("UB-AWD-RFQ-" + frappe.generate_hash(length=6), workflow_state="Pending Final Approval").name

	def test_approve_without_award_blocked(self):
		sq = frappe.get_doc("Supplier Quotation", make_sq("UB-AWD-SQ-" + frappe.generate_hash(length=6), self.rfq).name)
		sq.workflow_state = "Approved"
		self.assertRaises(frappe.ValidationError, sq.before_submit)
		frappe.db.set_value("Request for Quotation", self.rfq, "ub_awarded_quotation", sq.name)
		sq.before_submit()

	def test_award_rejects_quotation_approved_earlier(self):
		winner = make_sq("UB-AWD-SQ-" + frappe.generate_hash(length=6), self.rfq).name
		loser = make_sq("UB-AWD-SQ-" + frappe.generate_hash(length=6), self.rfq).name
		frappe.db.set_value("Supplier Quotation", loser, {"docstatus": 1, "workflow_state": "Approved"})
		self.assertIn(loser, _reject_quotations(self.rfq, exclude=winner))
		self.assertEqual(frappe.db.get_value("Supplier Quotation", loser, "workflow_state"), "Rejected")
