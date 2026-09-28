"""Quotation discussion: one thread per RFQ supplier row, internal notes hidden from the supplier."""

import frappe
from frappe.tests import IntegrationTestCase

from universal_buying.ub_sourcing import chat
from universal_buying.ub_sourcing.tests.test_tokens_and_revisions import make_rfq, make_rfq_row, make_sq


def _supplier(name):
	if not frappe.db.exists("Supplier", name):
		frappe.get_doc({"doctype": "Supplier", "supplier_name": name,
			"supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}, "name")}).insert(ignore_permissions=True)
	return name


class TestQuotationChat(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.rfq = make_rfq("UB-CHAT-RFQ-" + frappe.generate_hash(length=6)).name
		self.sup_a = _supplier("_UB Chat Supplier A")
		self.sup_b = _supplier("_UB Chat Supplier B")
		self.row_a = make_rfq_row(self.rfq, supplier=self.sup_a, token="tok-a-" + frappe.generate_hash(length=8))
		self.row_b = make_rfq_row(self.rfq, supplier=self.sup_b, token="tok-b-" + frappe.generate_hash(length=8))
		self.sq_a = make_sq("UB-CHAT-SQ-" + frappe.generate_hash(length=6), self.rfq, supplier=self.sup_a).name

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_quotation_maps_to_its_supplier_row(self):
		self.assertEqual(chat.row_for_quotation(self.sq_a).name, self.row_a.name)

	def test_buyer_message_and_supplier_reply_share_one_thread(self):
		chat.post_message(self.rfq, self.row_a.name, "Can you do 10 days lead time?")
		frappe.set_user("Guest")
		thread = chat.portal_post_message(self.row_a.ub_rfq_token, "Yes, 10 days confirmed.")
		self.assertEqual([m["sender_type"] for m in thread], ["Buyer", "Supplier"])
		frappe.set_user("Administrator")
		# the quotation form sees the same thread
		self.assertEqual(len(chat.get_thread_for_quotation(self.sq_a)["messages"]), 2)

	def test_internal_note_hidden_from_supplier(self):
		chat.post_message(self.rfq, self.row_a.name, "Price looks high, negotiate", is_internal=1)
		chat.post_message(self.rfq, self.row_a.name, "Please confirm your best price")
		staff = chat.get_threads(self.rfq)[self.row_a.name]["messages"]
		self.assertEqual(len(staff), 2)
		frappe.set_user("Guest")
		supplier_view = chat.portal_get_thread(self.row_a.ub_rfq_token)
		self.assertEqual([m["message"] for m in supplier_view], ["Please confirm your best price"])

	def test_suppliers_only_see_their_own_thread(self):
		chat.post_message(self.rfq, self.row_a.name, "Message for A only")
		frappe.set_user("Guest")
		self.assertEqual(chat.portal_get_thread(self.row_b.ub_rfq_token), [])

	def test_supplier_cannot_post_internal_note(self):
		frappe.set_user("Guest")
		chat.portal_post_message(self.row_a.ub_rfq_token, "hello")
		frappe.set_user("Administrator")
		self.assertFalse(frappe.db.get_value("Quotation Message", {"rfq_supplier_row": self.row_a.name}, "is_internal"))

	def test_bad_token_and_empty_message_refused(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			chat.portal_get_thread("no-such-token")
		with self.assertRaises(frappe.ValidationError):
			chat.portal_post_message(self.row_a.ub_rfq_token, "   ")

	def test_row_of_another_rfq_refused(self):
		other = make_rfq("UB-CHAT-RFQ-" + frappe.generate_hash(length=6)).name
		with self.assertRaises(frappe.ValidationError):
			chat.post_message(other, self.row_a.name, "wrong rfq")
