"""PAN / GSTIN validation (BRD V-2.2, V-2.3, V-2.4, V-3.2)."""

import frappe
from frappe.tests import IntegrationTestCase

from universal_buying.ub_supplier.tests.helpers import gstin_for, random_pan, unique
from universal_buying.ub_supplier.utils import is_valid_gstin, is_valid_pan, validate_gstin, validate_pan


def make_prospective(**kw):
	doc = frappe.get_doc({
		"doctype": "Prospective Supplier",
		"supplier_name": unique("_Test UB Prospect"),
		"email": f"{frappe.generate_hash(length=8)}@example.com",
		**kw,
	})
	return doc.insert(ignore_permissions=True)


class TestPartyIdentity(IntegrationTestCase):
	def test_pan_format(self):
		self.assertTrue(is_valid_pan("ABCDE1234F"))
		self.assertTrue(is_valid_pan(" abcde1234f "))
		for bad in ("ABCD1234F", "ABCDE12345", "1BCDE1234F", "ABCDE1234", "ABCDE-1234"):
			self.assertFalse(is_valid_pan(bad), bad)
		self.assertEqual(validate_pan("abcde1234f"), "ABCDE1234F")
		self.assertRaises(frappe.ValidationError, validate_pan, "ABC")

	def test_gstin_format_and_pan_match(self):
		self.assertTrue(is_valid_gstin("29ABCDE1234F1Z5"))
		self.assertFalse(is_valid_gstin("29ABCDE1234F1Z"))
		self.assertFalse(is_valid_gstin("29ABCDE1234F1X5"))
		self.assertEqual(validate_gstin("29abcde1234f1z5", "ABCDE1234F"), "29ABCDE1234F1Z5")
		with self.assertRaises(frappe.ValidationError) as ctx:
			validate_gstin("29ABCDE1234F1Z5", "ZZZZZ9999Z")
		self.assertIn("GSTIN does not match PAN", str(ctx.exception))

	def test_prospective_supplier_rejects_bad_pan_and_email(self):
		self.assertRaises(frappe.ValidationError, make_prospective, pan="BAD")
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "Prospective Supplier", "supplier_name": unique("_Test UB"), "email": "not-an-email"}).insert()

	def test_prospective_supplier_gstin_mismatch(self):
		pan = random_pan()
		self.assertRaises(frappe.ValidationError, make_prospective, pan=pan, gstin=gstin_for(random_pan()))
		ps = make_prospective(pan=pan.lower(), gstin=gstin_for(pan).lower())
		self.assertEqual(ps.pan, pan)
		self.assertEqual(ps.gstin, gstin_for(pan))

	def test_duplicate_gstin_blocked_across_prospective_and_supplier(self):
		pan = random_pan()
		gstin = gstin_for(pan)
		make_prospective(pan=pan, gstin=gstin)
		self.assertRaises(frappe.ValidationError, make_prospective, pan=pan, gstin=gstin)

		pan2 = random_pan()
		supplier = frappe.get_doc({
			"doctype": "Supplier", "supplier_name": unique("_Test UB Supplier"),
			"supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}, "name"),
			"tax_id": gstin_for(pan2),
		}).insert(ignore_permissions=True)
		self.assertTrue(supplier.name)
		self.assertRaises(frappe.ValidationError, make_prospective, pan=pan2, gstin=gstin_for(pan2))
