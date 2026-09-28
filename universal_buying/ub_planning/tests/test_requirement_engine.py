"""Requirement Engine allocation on a tiny synthetic dataset, plus one end-to-end rebuild with real documents."""

from datetime import date
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, nowdate

from universal_buying.ub_planning import requirement_engine as re_mod
from universal_buying.ub_planning.requirement_engine import RequirementEngine


def fake_setting(fieldname, company=None, default=None):
	return {"include_open_production": 0, "include_safety_stock": 0}.get(fieldname, default)


class SyntheticEngine(RequirementEngine):
	"""Engine with in-memory data: FG = 2 x SUB + 1 x RM1 ; SUB = 3 x RM2."""

	def __init__(self, demand, stock=None, pos=None, sub_bom_qty=1.0):
		with patch.object(re_mod, "get_setting", side_effect=fake_setting), \
				patch.object(re_mod, "get_lines", return_value=[]):
			super().__init__("_Synthetic Co", rebuild_id="T1")
		self._demand = demand
		self._stock_data = stock or {}
		self._po_data = pos or {}
		self._sub_bom_qty = sub_bom_qty

	def load(self):
		self.stock = {k: [list(x) for x in v] for k, v in self._stock_data.items()}
		self.po_pool = {k: [list(x) for x in v] for k, v in self._po_data.items()}
		self.wo_pool = {}
		self.default_boms = {"FG": ("BOM-FG", 1.0), "SUB": ("BOM-SUB", 1.0)}
		self._bom_items = {
			"BOM-FG": (1.0, [
				frappe._dict(item_code="SUB", stock_qty=2, bom_no=None, do_not_explode=0),
				frappe._dict(item_code="RM1", stock_qty=1, bom_no=None, do_not_explode=0),
			]),
			"BOM-SUB": (self._sub_bom_qty, [frappe._dict(item_code="RM2", stock_qty=3, bom_no=None, do_not_explode=0)]),
		}

	def stock_uom(self, item_code):
		return "Nos"

	def get_sales_order_demand(self):
		rows = []
		for i, (item, qty, when) in enumerate(self._demand, 1):
			rows.append(frappe._dict(
				sales_order=f"SO-{i}", sales_order_item=f"SOI-{i}", item_code=item, qty=qty, delivery_date=when,
				project="P1", cost_center=None, bom_no=None, demand_type="Sales Order", demand_work_order=None,
				fg_item_code=item, level=0, parent_bom=None, bom_item_type="Finished Good",
			))
		return rows


def totals(rows, reservation_type):
	out = {}
	for r in rows:
		if r["reservation_type"] == reservation_type:
			out[r["item_code"]] = flt(out.get(r["item_code"], 0) + r["qty"], 6)
	return out


class TestEngineAllocation(IntegrationTestCase):
	def test_multi_level_explosion_without_supply(self):
		rows = SyntheticEngine([("FG", 10, date(2026, 11, 20))]).run()
		self.assertEqual(totals(rows, "Shortage"), {"RM2": 60, "RM1": 10})
		self.assertTrue(all(r["grouped_delivery_date"] == date(2026, 11, 1) for r in rows))
		self.assertTrue(all(r["project"] == "P1" and r["fg_item_code"] == "FG" for r in rows))

	def test_stock_and_po_cover_before_explosion(self):
		rows = SyntheticEngine(
			[("FG", 10, date(2026, 11, 20))],
			stock={"FG": [("WH-1", 4)], "RM2": [("WH-1", 10)]},
			pos={"SUB": [("PO-1", "POI-1", 5)]},
		).run()
		# FG: 4 from stock, 6 exploded -> SUB 12: 5 on PO, 7 exploded -> RM2 21: 10 stock, 11 short; RM1 6 short
		self.assertEqual(totals(rows, "Stock"), {"FG": 4, "RM2": 10})
		self.assertEqual(totals(rows, "Purchase Order"), {"SUB": 5})
		self.assertEqual(totals(rows, "Shortage"), {"RM2": 11, "RM1": 6})
		po_row = next(r for r in rows if r["reservation_type"] == "Purchase Order")
		self.assertEqual((po_row["purchase_order"], po_row["purchase_order_item"]), ("PO-1", "POI-1"))
		self.assertEqual(po_row["bom_no"], "BOM-FG")
		self.assertEqual(po_row["bom_item_type"], "Sub Assembly")

	def test_supply_goes_to_earliest_demand_and_is_consumed_once(self):
		rows = SyntheticEngine(
			[("RM1", 5, date(2026, 10, 5)), ("RM1", 5, date(2026, 12, 5))],
			stock={"RM1": [("WH-1", 3)]},
			pos={"RM1": [("PO-1", "POI-1", 4)]},
		).run()
		first = [r for r in rows if r["sales_order"] == "SO-1"]
		second = [r for r in rows if r["sales_order"] == "SO-2"]
		self.assertEqual(totals(first, "Stock"), {"RM1": 3})
		self.assertEqual(totals(first, "Purchase Order"), {"RM1": 2})
		self.assertEqual(totals(second, "Purchase Order"), {"RM1": 2})
		self.assertEqual(totals(second, "Shortage"), {"RM1": 3})

	def test_bom_quantity_is_respected(self):
		"""The earlier engine multiplied by BOM Item stock_qty and ignored BOM.quantity."""
		rows = SyntheticEngine([("SUB", 10, date(2026, 11, 1))], sub_bom_qty=2.0).run()
		self.assertEqual(totals(rows, "Shortage"), {"RM2": 15})


def _company():
	return frappe.db.get_value("Company", {"is_group": 0}, "name", order_by="creation asc")


def _make_item(code, company, is_purchase=1):
	if frappe.db.exists("Item", code):
		return code
	frappe.get_doc({
		"doctype": "Item",
		"item_code": code,
		"item_name": code,
		"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name") or "All Item Groups",
		"stock_uom": "Nos",
		"is_stock_item": 1,
		"is_purchase_item": is_purchase,
		"item_defaults": [{"company": company}],
	}).insert(ignore_permissions=True)
	return code


class TestEngineRebuild(IntegrationTestCase):
	def test_rebuild_writes_requirement_log(self):
		company = _company()
		warehouse = frappe.db.get_value("Warehouse", {"company": company, "is_group": 0}, "name")
		fg = _make_item("_UB-ENG-FG", company, is_purchase=0)
		rm = _make_item("_UB-ENG-RM", company)
		if not frappe.db.exists("BOM", {"item": fg, "company": company, "docstatus": 1, "is_default": 1}):
			bom = frappe.get_doc({
				"doctype": "BOM", "item": fg, "company": company, "quantity": 2,
				"items": [{"item_code": rm, "qty": 6, "rate": 1}],
			})
			bom.insert(ignore_permissions=True)
			bom.submit()
		customer = "_UB Engine Customer"
		if not frappe.db.exists("Customer", customer):
			frappe.get_doc({"doctype": "Customer", "customer_name": customer,
				"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
				"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name")}).insert(ignore_permissions=True)
		so = frappe.get_doc({
			"doctype": "Sales Order", "company": company, "customer": customer, "transaction_date": nowdate(),
			"delivery_date": add_days(nowdate(), 30), "order_type": "Sales",
			"items": [{"item_code": fg, "qty": 4, "rate": 100, "warehouse": warehouse,
				"delivery_date": add_days(nowdate(), 30)}],
		})
		so.insert(ignore_permissions=True)
		so.submit()

		with patch.object(re_mod, "get_setting", side_effect=fake_setting):
			rows = RequirementEngine(company).run()
		mine = [r for r in rows if r["sales_order"] == so.name]
		# BOM makes 2 FG from 6 RM -> 3 RM per FG -> 12 RM short (no stock / PO for the new item)
		self.assertEqual(totals(mine, "Shortage").get(rm), 12)

		re_mod.write_log(company, rows)
		logged = frappe.db.sql("""select sum(qty) from `tabRequirement Log`
			where sales_order = %s and item_code = %s and reservation_type = 'Shortage'""", (so.name, rm))[0][0]
		self.assertEqual(flt(logged), 12)
		frappe.db.rollback()
