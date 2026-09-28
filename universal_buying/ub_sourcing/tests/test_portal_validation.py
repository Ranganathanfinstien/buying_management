"""RFQ portal quote validation (V-14.2) without india_compliance."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from universal_buying.ub_sourcing import portal

TAX = "_Test UB Tax Template"


def line(rate=0, qty=None, tax="", hsn=""):
	return {"rate": rate, "offered_qty": qty, "item_tax_template": tax, "hsn": hsn}


class TestPortalValidation(IntegrationTestCase):
	def errors(self, item_map, templates=(TAX,), hsn=False):
		with patch.object(portal, "tax_options", return_value=list(templates)), patch.object(
			portal, "hsn_enabled", return_value=hsn
		):
			return portal.validate_quote_items(item_map, company="_Test Company")

	def test_unpriced_empty_lines_are_skipped(self):
		self.assertEqual(self.errors({"1": line(), "2": line()}), [])

	def test_priced_line_needs_tax_when_company_has_templates(self):
		errs = self.errors({"1": line(rate=10, qty=2)})
		self.assertEqual([(e["idx"], e["field"], e["type"]) for e in errs], [(1, "tax", "empty")])
		self.assertEqual(self.errors({"1": line(rate=10, qty=2, tax=TAX)}), [])

	def test_tax_optional_when_company_has_no_templates(self):
		self.assertEqual(self.errors({"1": line(rate=10, qty=2)}, templates=()), [])

	def test_unknown_or_foreign_tax_template(self):
		errs = self.errors({"1": line(rate=10, qty=2, tax="Other Company Template")})
		self.assertEqual([(e["field"], e["type"]) for e in errs], [("tax", "not_found")])

	def test_quantity_must_be_positive_on_priced_lines(self):
		errs = self.errors({"3": line(rate=5, qty=0, tax=TAX)})
		self.assertEqual([(e["idx"], e["field"], e["type"]) for e in errs], [(3, "qty", "invalid")])
		# blank offered qty falls back to the RFQ quantity
		self.assertEqual(self.errors({"3": line(rate=5, qty=None, tax=TAX)}), [])

	def test_hsn_ignored_without_gst_hsn_master(self):
		self.assertEqual(self.errors({"1": line(rate=10, qty=1, tax=TAX, hsn="")}, hsn=False), [])

	def test_hsn_required_when_master_exists(self):
		with patch.object(frappe, "get_all", return_value=[]):
			errs = self.errors({"1": line(rate=10, qty=1, tax=TAX)}, hsn=True)
		self.assertIn(("hsn", "empty"), [(e["field"], e["type"]) for e in errs])

	def test_payload_needs_at_least_one_rate(self):
		with patch.object(portal, "tax_options", return_value=[TAX]), patch.object(portal, "hsn_enabled", return_value=False):
			with self.assertRaises(frappe.ValidationError):
				portal.validate_quote_payload({"1": line(rate=0)}, "_Test Company")
			with self.assertRaises(frappe.ValidationError):
				portal.validate_quote_payload({"1": line(rate=10, qty=1)}, "_Test Company")
			portal.validate_quote_payload({"1": line(rate=10, qty=1, tax=TAX)}, "_Test Company")

	def test_error_messages_are_readable(self):
		msg = portal.format_quote_error({"idx": 2, "field": "tax", "type": "empty", "value": ""})
		self.assertIn("#2", msg)
		msg = portal.format_quote_error({"idx": 4, "field": "hsn", "type": "not_found", "value": "<b>x</b>"})
		self.assertNotIn("<b>", msg)

	def test_item_map_parsing(self):
		m = portal._item_map([{"idx": "1", "rate": "12.5", "offered_qty": "", "moq": "10", "remarks": " x "}], with_details=True)
		self.assertEqual(m["1"]["rate"], 12.5)
		self.assertIsNone(m["1"]["offered_qty"])
		self.assertEqual(m["1"]["moq"], 10)
		self.assertEqual(m["1"]["remarks"], "x")
