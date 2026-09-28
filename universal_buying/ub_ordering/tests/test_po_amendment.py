"""PO Amendment: V-20.1 rate cap, V-20.2 received qty, A-20.1 / AC-20.1 totals include tax."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from universal_buying.ub_ordering.tests import helpers


class TestPOAmendment(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = helpers.get_company()
		cls.has_tax = bool(helpers.tax_account(cls.company))
		cls.po = helpers.make_submitted_po(qty=10, rate=100, tax_rate=18)

	def amendment(self, **row):
		po = frappe.get_doc("Purchase Order", self.po.name)
		line = po.items[0]
		values = {"po_item": line.name, "revised_qty": line.qty, "revised_rate": line.rate}
		values.update(row)
		return frappe.get_doc({"doctype": "PO Amendment", "purchase_order": po.name, "reason": "test", "items": [values]})

	def cap(self, percent=5):
		return patch("universal_buying.ub_ordering.doctype.po_amendment.po_amendment.get_setting",
			side_effect=helpers.settings({"amendment_rate_cap_percent": percent}))

	def test_rate_increase_above_cap_needs_price(self):
		doc = self.amendment(revised_rate=110)
		with self.cap(5), patch("universal_buying.ub_ordering.doctype.po_amendment.po_amendment.get_valid_price", return_value=None):
			self.assertRaises(frappe.ValidationError, doc.insert, ignore_permissions=True)

	def test_rate_increase_supported_by_item_price(self):
		doc = self.amendment(revised_rate=110)
		price = frappe._dict(name="IP-1", price_list_rate=112, currency=self.po.currency, uom="Nos")
		with self.cap(5), patch("universal_buying.ub_ordering.doctype.po_amendment.po_amendment.get_valid_price", return_value=price):
			doc.insert(ignore_permissions=True)
		self.assertEqual(flt(doc.items[0].revised_amount), flt(doc.items[0].revised_qty) * 110)

	def test_rate_increase_within_cap(self):
		doc = self.amendment(revised_rate=104)
		with self.cap(5):
			doc.insert(ignore_permissions=True)

	def test_qty_below_received_blocked(self):
		line = frappe.get_doc("Purchase Order", self.po.name).items[0]
		frappe.db.set_value("Purchase Order Item", line.name, "received_qty", 6)
		try:
			doc = self.amendment(revised_qty=5)
			with self.cap():
				self.assertRaises(frappe.ValidationError, doc.insert, ignore_permissions=True)
		finally:
			frappe.db.set_value("Purchase Order Item", line.name, "received_qty", 0)

	def test_negative_qty_blocked(self):
		doc = self.amendment(revised_qty=-1)
		with self.cap():
			self.assertRaises(frappe.ValidationError, doc.insert, ignore_permissions=True)

	def test_apply_recalculates_taxes(self):
		"""AC-20.1: the grand total after amendment includes taxes (source bug: grand_total = net_total)."""
		doc = self.amendment(revised_qty=12)
		with self.cap():
			doc.insert(ignore_permissions=True)
			doc.apply_to_po()
		po = frappe.get_doc("Purchase Order", self.po.name)
		self.assertEqual(flt(po.items[0].qty), 12)
		self.assertEqual(flt(po.net_total), 1200)
		if self.has_tax:
			self.assertEqual(flt(po.total_taxes_and_charges), 216)
			self.assertEqual(flt(po.grand_total), 1416)
			self.assertGreater(flt(po.grand_total), flt(po.net_total))
		self.assertEqual(flt(frappe.db.get_value("PO Amendment", doc.name, "revised_grand_total")), flt(po.grand_total))
		self.assertEqual(frappe.db.get_value("PO Amendment", doc.name, "applied"), 1)
