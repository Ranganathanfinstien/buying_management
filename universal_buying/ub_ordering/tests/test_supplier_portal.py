"""Supplier portal after the PO (6.21): acknowledgement, material status rules, shipment over-shipping, scoping."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from universal_buying.ub_ordering import permissions, portal
from universal_buying.ub_ordering.tests import helpers

NO_MAIL = patch("universal_buying.ub_ordering.portal.notify_users")


def ack(po, days=5, notes=None):
	return frappe.get_doc({"doctype": "PO Acknowledgement", "purchase_order": po,
		"confirmed_delivery_date": add_days(today(), days), "notes": notes}).insert(ignore_permissions=True)


def status(po, value, remarks="r"):
	return frappe.get_doc({"doctype": "PO Material Status", "purchase_order": po, "status": value,
		"remarks": remarks}).insert(ignore_permissions=True)


def ship(po, qty, submit=True):
	line = frappe.get_doc("Purchase Order", po).items[0]
	doc = frappe.get_doc({"doctype": "PO Shipment", "purchase_order": po, "shipment_date": today(),
		"items": [{"po_item": line.name, "shipped_qty": qty}]})
	doc.insert(ignore_permissions=True)
	if submit:
		doc.submit()
	return doc


class TestSupplierPortalFlow(IntegrationTestCase):
	def setUp(self):
		self.mail = NO_MAIL.start()
		self.po = helpers.make_submitted_po(qty=10, rate=100, tax_rate=0).name

	def tearDown(self):
		NO_MAIL.stop()
		frappe.set_user("Administrator")

	def test_submit_sets_pending_acceptance(self):
		self.assertEqual(frappe.db.get_value("Purchase Order", self.po, "ub_portal_status"), "Pending Acceptance")

	def test_acknowledgement_latest_wins_and_append_only(self):
		first = ack(self.po, 5)
		self.assertEqual(first.event_type, "Acknowledged")
		self.assertEqual(frappe.db.get_value("Purchase Order", self.po, "ub_portal_status"), "Accepted")
		second = ack(self.po, 9)
		self.assertEqual(second.event_type, "Revised")
		self.assertEqual(str(frappe.db.get_value("Purchase Order", self.po, "ub_confirmed_delivery_date")), add_days(today(), 9))
		first.notes = "edited"
		self.assertRaises(frappe.ValidationError, first.save, ignore_permissions=True)

	def test_material_status_needs_acceptance(self):
		self.assertRaises(frappe.ValidationError, status, self.po, "In Production")

	def test_material_status_rules(self):
		ack(self.po)
		self.assertRaises(frappe.ValidationError, status, self.po, "In Production", remarks="")
		status(self.po, "In Production")
		self.assertRaises(frappe.ValidationError, status, self.po, "In Production")  # same status twice
		status(self.po, "Ready to Dispatch")
		self.assertRaises(frappe.ValidationError, status, self.po, "Partial")  # backwards
		status(self.po, "Delayed")
		status(self.po, "Ready to Dispatch")  # resuming at the reached level is allowed
		self.assertEqual(frappe.db.get_value("Purchase Order", self.po, "ub_material_status"), "Ready to Dispatch")

	def test_dispatched_needs_invoice_and_shipment(self):
		ack(self.po)
		self.assertRaises(frappe.ValidationError, status, self.po, "Dispatched")
		ship(self.po, 10)
		self.assertRaises(frappe.ValidationError, status, self.po, "Dispatched")  # still no invoice
		portal._append_po_child(self.po, "Portal PO Invoice", "ub_invoice_uploads",
			{"bill_no": "INV-1", "attachment": "/private/files/x.pdf"})
		status(self.po, "Dispatched")
		self.assertRaises(frappe.ValidationError, status, self.po, "Delayed")  # nothing after dispatch

	def test_shipment_over_shipping_and_portal_status(self):
		ack(self.po)
		ship(self.po, 4)
		self.assertEqual(frappe.db.get_value("Purchase Order", self.po, "ub_portal_status"), "Partially Dispatched")
		self.assertRaises(frappe.ValidationError, ship, self.po, 7)  # only 6 remain
		last = ship(self.po, 6)
		self.assertEqual(last.shipment_status, "Fully Shipped")
		self.assertEqual(frappe.db.get_value("Purchase Order", self.po, "ub_portal_status"), "Dispatched")
		last.cancel()
		self.assertEqual(frappe.db.get_value("Purchase Order", self.po, "ub_portal_status"), "Partially Dispatched")


class TestPortalScoping(IntegrationTestCase):
	def test_supplier_user_sees_only_own_documents(self):
		supplier = helpers.make_supplier()
		user = helpers.make_user("ub-portal-supplier@example.com", ["Supplier"])
		frappe.db.set_value("User", user, "user_type", "Website User")
		if not frappe.db.exists("Portal User", {"parent": supplier, "user": user}):
			sup = frappe.get_doc("Supplier", supplier)
			sup.append("portal_users", {"user": user})
			sup.flags.ignore_permissions = True
			sup.save()
		self.assertTrue(permissions.is_supplier_portal_user(user))
		cond = permissions.purchase_order_query(user)
		self.assertIn(frappe.db.escape(supplier), cond)
		self.assertEqual(permissions.purchase_order_query("Administrator"), "")
		own = frappe._dict(doctype="Purchase Order", supplier=supplier)
		other = frappe._dict(doctype="Purchase Order", supplier="Someone Else")
		self.assertTrue(permissions.procurement_read_only(own, "read", user))
		self.assertFalse(permissions.procurement_read_only(other, "read", user))
		self.assertFalse(permissions.procurement_read_only(own, "write", user))
		self.assertTrue(permissions.procurement_read_only(other, "write", "Administrator"))
