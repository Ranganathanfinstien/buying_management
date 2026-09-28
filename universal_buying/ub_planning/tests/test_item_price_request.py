"""Item Price Request: V-9.1, V-9.2, V-9.3 and the A-9.1 submit effects; get_current_item_price contract."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, nowdate

from universal_buying.ub_planning.api import get_current_item_price


def _company():
	return frappe.db.get_value("Company", {"is_group": 0}, "name", order_by="creation asc")


def _buying_price_list(company):
	currency = frappe.get_cached_value("Company", company, "default_currency")
	name = frappe.db.get_value("Price List", {"buying": 1, "enabled": 1, "currency": currency}, "name")
	if not name:
		name = frappe.get_doc({"doctype": "Price List", "price_list_name": "_UB Buying", "buying": 1,
			"currency": currency, "enabled": 1}).insert(ignore_permissions=True).name
	return name


def _supplier(name):
	if not frappe.db.exists("Supplier", name):
		frappe.get_doc({"doctype": "Supplier", "supplier_name": name,
			"supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}, "name")}).insert(
			ignore_permissions=True)
	if frappe.get_meta("Supplier").has_field("workflow_state"):
		frappe.db.set_value("Supplier", name, "workflow_state", "Enabled")
	return name


def _item(code, company, with_default=True):
	if not frappe.db.exists("Item", code):
		frappe.get_doc({
			"doctype": "Item", "item_code": code, "item_name": code, "stock_uom": "Nos", "is_stock_item": 1,
			"is_purchase_item": 1,
			"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name") or "All Item Groups",
			"item_defaults": [{"company": company}] if with_default else [],
		}).insert(ignore_permissions=True)
	if not with_default:
		# ERPNext v16 adds an Item Default for the default company on insert; remove it for this case.
		frappe.db.delete("Item Default", {"parent": code, "parenttype": "Item", "company": company})
	return code


def _mpn(item_code, mpn):
	manufacturer = "_UB Test Manufacturer"
	if not frappe.db.exists("Manufacturer", manufacturer):
		frappe.get_doc({"doctype": "Manufacturer", "short_name": manufacturer}).insert(ignore_permissions=True)
	name = frappe.db.get_value("Item Manufacturer", {"item_code": item_code, "manufacturer_part_no": mpn}, "name")
	if not name:
		name = frappe.get_doc({"doctype": "Item Manufacturer", "item_code": item_code, "manufacturer": manufacturer,
			"manufacturer_part_no": mpn}).insert(ignore_permissions=True).name
	return name


def _request(company, item_code, supplier, rate=10, item_manufacturer=None, valid_from=None, lead=7, moq=100, spq=25):
	return frappe.get_doc({
		"doctype": "Item Price Request",
		"company": company,
		"type": "Buying",
		"item_price_details": [{
			"item_code": item_code, "uom": "Nos", "supplier": supplier, "price_list": _buying_price_list(company),
			"rate": rate, "moq": moq, "spq": spq, "lead_time_days": lead,
			"valid_from": valid_from or nowdate(), "valid_upto": add_days(nowdate(), 365),
			"item_manufacturer": item_manufacturer,
		}],
	})


class TestItemPriceRequest(IntegrationTestCase):
	def setUp(self):
		self.company = _company()
		self.supplier = _supplier("_UB IPR Supplier")

	def test_item_default_required(self):
		item = _item("_UB-IPR-NODEF", self.company, with_default=False)
		with self.assertRaises(frappe.ValidationError):
			_request(self.company, item, self.supplier).insert()

	def test_lead_time_and_dates(self):
		item = _item("_UB-IPR-V92", self.company)
		with self.assertRaises(frappe.ValidationError):
			_request(self.company, item, self.supplier, lead=0).insert()
		doc = _request(self.company, item, self.supplier)
		doc.item_price_details[0].valid_upto = add_days(nowdate(), -1)
		with self.assertRaises(frappe.ValidationError):
			doc.insert()

	def test_single_open_request_per_item(self):
		item = _item("_UB-IPR-V93", self.company)
		first = _request(self.company, item, self.supplier).insert()
		with self.assertRaises(frappe.ValidationError):
			_request(self.company, item, self.supplier).insert()
		first.submit()
		# once the earlier request is submitted a new one is allowed (changed rule)
		_request(self.company, item, self.supplier, rate=12, valid_from=add_days(nowdate(), 1)).insert()

	def test_submit_sets_approved_source(self):
		item = _item("_UB-IPR-A91", self.company)
		old_supplier = _supplier("_UB IPR Old Supplier")
		old_price = frappe.get_doc({
			"doctype": "Item Price", "item_code": item, "price_list": _buying_price_list(self.company),
			"supplier": old_supplier, "price_list_rate": 99, "valid_from": add_days(nowdate(), -30), "uom": "Nos",
		}).insert(ignore_permissions=True)
		im = _mpn(item, "_UB-MPN-A91")

		doc = _request(self.company, item, self.supplier, rate=10, item_manufacturer=im).insert()
		doc.submit()

		row = doc.item_price_details[0]
		self.assertTrue(row.item_price)
		price = frappe.get_doc("Item Price", row.item_price)
		self.assertEqual(price.supplier, self.supplier)
		self.assertEqual(flt(price.price_list_rate), 10)
		self.assertEqual(price.ub_company, self.company)
		self.assertEqual(price.ub_item_manufacturer, im)

		# previous buying price ended the day before
		self.assertEqual(str(frappe.db.get_value("Item Price", old_price.name, "valid_upto")),
			str(add_days(nowdate(), -1)))

		item_doc = frappe.get_doc("Item", item)
		self.assertEqual(flt(item_doc.min_order_qty), 100)
		self.assertEqual(flt(item_doc.ub_standard_packing_qty), 25)
		self.assertEqual(item_doc.default_manufacturer_part_no, "_UB-MPN-A91")
		self.assertEqual(frappe.db.get_value("Item Default", {"parent": item, "company": self.company},
			"default_supplier"), self.supplier)
		self.assertEqual(frappe.db.get_value("Item Manufacturer", im, "is_default"), 1)

		current = get_current_item_price(item, company=self.company)
		self.assertEqual(current["name"], row.item_price)
		self.assertEqual(current["manufacturer_part_no"], "_UB-MPN-A91")
		self.assertIsNone(get_current_item_price(item, old_supplier, self.company))

	def test_disabled_mpn_rejected(self):
		item = _item("_UB-IPR-DIS", self.company)
		im = _mpn(item, "_UB-MPN-DIS")
		frappe.db.set_value("Item Manufacturer", im, "ub_disabled", 1)
		with self.assertRaises(frappe.ValidationError):
			_request(self.company, item, self.supplier, item_manufacturer=im).insert()
