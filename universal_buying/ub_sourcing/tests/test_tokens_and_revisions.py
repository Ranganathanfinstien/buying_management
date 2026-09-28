"""Token reuse (source-app fix) and quotation revisions (A-14.2 / A-14.4).

Records are written with ``db_insert`` (no controller validation) so the tests only exercise the
sourcing logic; the class-level rollback of IntegrationTestCase removes them.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_to_date, now_datetime

from universal_buying.ub_sourcing.api import get_or_create_rfq_token, mark_for_revision
from universal_buying.ub_sourcing.notifications import ensure_row_token, is_prospective_row
from universal_buying.ub_sourcing.overrides.supplier_quotation import supersede_older_quotations

RFQ = "Request for Quotation"


def make_rfq(name, workflow_state="Open", docstatus=1, deadline_days=3):
	doc = frappe.new_doc(RFQ)
	doc.name = name
	doc.company = frappe.db.get_value("Company", {}, "name")
	doc.transaction_date = frappe.utils.nowdate()
	doc.docstatus = docstatus
	doc.workflow_state = workflow_state
	doc.ub_bid_status = "Open"
	doc.ub_bid_deadline = add_days(now_datetime(), deadline_days)
	doc.db_insert()
	return doc


def make_rfq_row(rfq, supplier=None, prospective=None, token=None):
	row = frappe.get_doc({
		"doctype": "Request for Quotation Supplier",
		"parent": rfq,
		"parenttype": RFQ,
		"parentfield": "suppliers",
		"supplier": supplier,
		"ub_prospective_supplier": prospective,
		"ub_rfq_token": token,
		"email_id": "ub-test@example.com",
	})
	row.name = frappe.generate_hash(length=12)
	row.db_insert()
	return row


def make_sq(name, rfq, supplier=None, prospective=None, minutes_ago=0):
	sq = frappe.new_doc("Supplier Quotation")
	sq.name = name
	sq.supplier = supplier
	sq.ub_prospective_supplier = prospective
	sq.company = frappe.db.get_value("Company", {}, "name")
	sq.transaction_date = frappe.utils.nowdate()
	sq.docstatus = 0
	sq.creation = sq.modified = add_to_date(now_datetime(), minutes=-minutes_ago)
	sq.db_insert()
	item = frappe.get_doc({
		"doctype": "Supplier Quotation Item",
		"parent": name,
		"parenttype": "Supplier Quotation",
		"parentfield": "items",
		"item_name": "UB test line",
		"qty": 1,
		"request_for_quotation": rfq,
	})
	item.name = frappe.generate_hash(length=12)
	item.db_insert()
	return sq


class TestRFQTokens(IntegrationTestCase):
	def test_existing_token_is_reused(self):
		rfq = make_rfq("_UB-TEST-RFQ-TOK-1")
		row = make_rfq_row(rfq.name, supplier="_UB Test Supplier", token="fixedtoken123")
		self.assertEqual(get_or_create_rfq_token(rfq.name, "_UB Test Supplier"), "fixedtoken123")
		self.assertEqual(ensure_row_token(frappe._dict(name=row.name, ub_rfq_token=None)), "fixedtoken123")

	def test_token_created_once(self):
		rfq = make_rfq("_UB-TEST-RFQ-TOK-2")
		make_rfq_row(rfq.name, prospective="_UB Test Prospect")
		first = get_or_create_rfq_token(rfq.name, "_UB Test Prospect")
		self.assertTrue(first)
		self.assertEqual(get_or_create_rfq_token(rfq.name, "_UB Test Prospect"), first)

	def test_uninvited_party_is_refused(self):
		rfq = make_rfq("_UB-TEST-RFQ-TOK-3")
		with self.assertRaises(frappe.PermissionError):
			get_or_create_rfq_token(rfq.name, "_UB Somebody Else")

	def test_row_with_supplier_is_registered(self):
		self.assertTrue(is_prospective_row(frappe._dict(ub_prospective_supplier="P", supplier=None)))
		self.assertFalse(is_prospective_row(frappe._dict(ub_prospective_supplier="P", supplier="S")))


class TestQuotationRevisions(IntegrationTestCase):
	def test_new_version_supersedes_older_ones(self):
		rfq = make_rfq("_UB-TEST-RFQ-REV-1")
		make_sq("_UB-TEST-SQ-A1", rfq.name, supplier="_UB Sup A", minutes_ago=30)
		make_sq("_UB-TEST-SQ-A2", rfq.name, supplier="_UB Sup A", minutes_ago=20)
		make_sq("_UB-TEST-SQ-B1", rfq.name, supplier="_UB Sup B", minutes_ago=25)
		make_sq("_UB-TEST-SQ-A3", rfq.name, supplier="_UB Sup A", minutes_ago=10)

		flagged = supersede_older_quotations("_UB-TEST-SQ-A3", rfq.name, supplier="_UB Sup A")
		self.assertEqual(set(flagged), {"_UB-TEST-SQ-A1", "_UB-TEST-SQ-A2"})
		self.assertEqual(frappe.db.get_value("Supplier Quotation", "_UB-TEST-SQ-A3", "ub_revised"), 0)
		self.assertEqual(frappe.db.get_value("Supplier Quotation", "_UB-TEST-SQ-B1", "ub_revised"), 0)

		from universal_buying.ub_sourcing.comparison import live_quotations

		self.assertEqual(set(live_quotations(rfq.name)), {"_UB-TEST-SQ-A3", "_UB-TEST-SQ-B1"})

	def test_older_version_never_supersedes_newer(self):
		rfq = make_rfq("_UB-TEST-RFQ-REV-2")
		make_sq("_UB-TEST-SQ-P1", rfq.name, prospective="_UB Prospect", minutes_ago=5)
		make_sq("_UB-TEST-SQ-P2", rfq.name, prospective="_UB Prospect", minutes_ago=1)
		self.assertEqual(supersede_older_quotations("_UB-TEST-SQ-P1", rfq.name, prospective_supplier="_UB Prospect"), [])
		self.assertEqual(frappe.db.get_value("Supplier Quotation", "_UB-TEST-SQ-P2", "ub_revised"), 0)

	def test_mark_for_revision_while_bidding_open(self):
		rfq = make_rfq("_UB-TEST-RFQ-REV-3")
		make_sq("_UB-TEST-SQ-R1", rfq.name, supplier="_UB Sup R")
		with self.assertRaises(frappe.ValidationError):
			mark_for_revision("_UB-TEST-SQ-R1", "  ")
		self.assertTrue(mark_for_revision("_UB-TEST-SQ-R1", "Please re-check the rate")["ok"])
		vals = frappe.db.get_value("Supplier Quotation", "_UB-TEST-SQ-R1",
			["ub_revision_requested", "ub_revision_reason"], as_dict=True)
		self.assertEqual(vals.ub_revision_requested, 1)
		self.assertEqual(vals.ub_revision_reason, "Please re-check the rate")
		with self.assertRaises(frappe.ValidationError):
			mark_for_revision("_UB-TEST-SQ-R1", "again")

	def test_mark_for_revision_blocked_when_bidding_closed(self):
		rfq = make_rfq("_UB-TEST-RFQ-REV-4", workflow_state="Pending Final Approval")
		make_sq("_UB-TEST-SQ-R2", rfq.name, supplier="_UB Sup R")
		with self.assertRaises(frappe.ValidationError):
			mark_for_revision("_UB-TEST-SQ-R2", "late request")

	def test_superseded_quotation_cannot_be_marked(self):
		rfq = make_rfq("_UB-TEST-RFQ-REV-5")
		make_sq("_UB-TEST-SQ-S1", rfq.name, supplier="_UB Sup S")
		frappe.db.set_value("Supplier Quotation", "_UB-TEST-SQ-S1", "ub_revised", 1)
		with self.assertRaises(frappe.ValidationError):
			mark_for_revision("_UB-TEST-SQ-S1", "reason")
