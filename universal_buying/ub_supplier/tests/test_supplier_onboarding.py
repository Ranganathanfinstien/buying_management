"""Supplier Onboarding submit (BRD A-3.2 .. A-3.4, AC-3.1, AC-3.2)."""

import frappe
from frappe.tests import IntegrationTestCase

from universal_buying.ub_supplier.api import create_onboarding_from_prospective, get_supplier_for_prospective
from universal_buying.ub_supplier.tests.helpers import (
	gstin_for,
	make_supplier_group,
	random_pan,
	set_supplier_settings,
	unique,
)


class TestSupplierOnboarding(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.group = make_supplier_group("_Test UB Onboarding Group")
		set_supplier_settings(questionnaire=0, require_bank=1)

	def make_prospective(self):
		pan = random_pan()
		return frappe.get_doc({
			"doctype": "Prospective Supplier",
			"supplier_name": unique("_Test UB Onboard"),
			"email": f"ub-{frappe.generate_hash(length=8)}@example.com",
			"contact_person": "Ravi Kumar",
			"phone": "+91 80 1234 5678",
			"pan": pan,
			"gstin": gstin_for(pan),
			"country": "India",
			"address_line1": "12 Industrial Area",
			"city": "Bengaluru",
			"state": "Karnataka",
			"pincode": "560001",
		}).insert(ignore_permissions=True)

	def fill(self, so):
		so.supplier_group = self.group
		so.country = "India"
		so.bank_name = "_Test UB Onboarding Bank"
		so.account_holder_name = so.supplier_name
		so.bank_account_no = "123456789012"
		so.ifsc_code = "hdfc0001234"
		so.save(ignore_permissions=True)
		return so

	def test_create_onboarding_from_prospective(self):
		ps = self.make_prospective()
		name = create_onboarding_from_prospective(ps.name, send_email=0)
		so = frappe.get_doc("Supplier Onboarding", name)
		self.assertEqual(so.prospective_supplier, ps.name)
		self.assertEqual(so.supplier_name, ps.supplier_name)
		self.assertEqual(so.gstin, ps.gstin)
		self.assertTrue(so.onboarding_token)
		self.assertEqual(frappe.db.get_value("Prospective Supplier", ps.name, "status"), "Onboarding Sent")
		# idempotent
		self.assertEqual(create_onboarding_from_prospective(ps.name, send_email=0), name)

	def test_submit_creates_supplier_address_contact_bank_user(self):
		ps = self.make_prospective()
		so = frappe.get_doc("Supplier Onboarding", create_onboarding_from_prospective(ps.name, send_email=0))
		self.fill(so)
		so.submit()
		so.reload()

		supplier = so.supplier
		self.assertTrue(supplier)
		self.assertEqual(so.status, "Approved")
		self.assertEqual(so.token_expired, 1)
		sup = frappe.get_doc("Supplier", supplier)
		self.assertEqual(sup.ub_onboarding, so.name)
		self.assertEqual(sup.tax_id, ps.gstin)
		self.assertEqual(sup.supplier_group, self.group)

		# Address (the source apps skipped it)
		address = sup.supplier_primary_address
		self.assertTrue(address)
		addr = frappe.get_doc("Address", address)
		self.assertEqual(addr.city, "Bengaluru")
		self.assertTrue(any(lnk.link_doctype == "Supplier" and lnk.link_name == supplier for lnk in addr.links))

		# Contact
		self.assertTrue(sup.supplier_primary_contact)
		contact = frappe.get_doc("Contact", sup.supplier_primary_contact)
		self.assertEqual(contact.email_id, ps.email)
		self.assertTrue(any(lnk.link_doctype == "Supplier" and lnk.link_name == supplier for lnk in contact.links))

		# Bank Account mapped from the onboarding bank fields (broken in the source app)
		ba = frappe.get_all("Bank Account", filters={"party_type": "Supplier", "party": supplier},
			fields=["bank", "bank_account_no", "branch_code", "disabled"])
		self.assertEqual(len(ba), 1)
		self.assertEqual(ba[0].bank, "_Test UB Onboarding Bank")
		self.assertEqual(ba[0].bank_account_no, "123456789012")
		self.assertEqual(ba[0].branch_code, "HDFC0001234")

		# Portal user with the Supplier role
		user = ps.email.lower()
		self.assertTrue(frappe.db.exists("User", user))
		self.assertIn("Supplier", frappe.get_roles(user))
		self.assertIn(user, [p.user for p in sup.portal_users])

		# Prospective supplier closed out
		self.assertEqual(frappe.db.get_value("Prospective Supplier", ps.name, "status"), "Onboarded")
		self.assertEqual(get_supplier_for_prospective(ps.name), supplier)

		# new supplier starts the approval workflow in Draft
		if frappe.db.exists("Workflow", "UB Supplier Approval"):
			self.assertEqual(sup.workflow_state, "Draft")

	def test_submit_requires_bank_details(self):
		ps = self.make_prospective()
		so = frappe.get_doc("Supplier Onboarding", create_onboarding_from_prospective(ps.name, send_email=0))
		so.supplier_group = self.group
		so.save(ignore_permissions=True)
		self.assertRaises(frappe.ValidationError, so.submit)

	def test_duplicate_supplier_name_blocked(self):
		ps = self.make_prospective()
		so = frappe.get_doc("Supplier Onboarding", create_onboarding_from_prospective(ps.name, send_email=0))
		other = frappe.new_doc("Supplier Onboarding")
		other.update({"supplier_name": so.supplier_name, "supplier_group": self.group, "country": "India",
			"email": "other@example.com", "supplier_type": "Company"})
		self.assertRaises(frappe.ValidationError, other.insert)

	def test_audit_required_group_blocks_submit_without_audit(self):
		audit_group = make_supplier_group("_Test UB Custom Built")
		set_supplier_settings(audit=[audit_group], questionnaire=0, require_bank=1)
		try:
			ps = self.make_prospective()
			so = frappe.get_doc("Supplier Onboarding", create_onboarding_from_prospective(ps.name, send_email=0))
			self.fill(so)
			so.supplier_group = audit_group
			so.supplier_audit_type = "Industrial"
			so.save(ignore_permissions=True)
			self.assertEqual(so.audit_required, 1)
			self.assertRaises(frappe.ValidationError, so.submit)
		finally:
			set_supplier_settings(questionnaire=0, require_bank=1)

	def test_questionnaire_rpn_threshold(self):
		set_supplier_settings(questionnaire=1, require_bank=1)
		try:
			ps = self.make_prospective()
			so = frappe.get_doc("Supplier Onboarding", create_onboarding_from_prospective(ps.name, send_email=0))
			self.fill(so)
			if not so.risk_analysis:
				self.skipTest("Question bank not seeded")
			for row in so.risk_analysis:
				row.effect = "x"
				row.severity_ranking = "No effect on the project"
				row.probability_of_occurance = "Very low chance of occurance"
				row.prevention_control_if_any = "Already proven parameters used in the project"
			for row in so.evaluation:
				row.response = "Yes"
			for row in so.evaluation_ranking:
				row.ranking_select = row.option_5
			high = so.risk_analysis[0]
			high.severity_ranking = "Loss of Company Reputation"
			high.probability_of_occurance = "Very high chance of occurance"
			high.prevention_control_if_any = "No control available"
			so.save(ignore_permissions=True)
			self.assertEqual(so.risk_analysis[0].risk_priority_no, 125)
			self.assertRaises(frappe.ValidationError, so.submit)
			so.reload()
			so.risk_analysis[0].update({"mitigation_plan": "Dual source", "responsibility": "Administrator",
				"target_date": frappe.utils.add_days(frappe.utils.nowdate(), 30), "status": "Open"})
			so.save(ignore_permissions=True)
			so.submit()
			self.assertTrue(so.supplier)
		finally:
			set_supplier_settings(questionnaire=0, require_bank=1)
