"""Auto PO rules: ABC threshold, SPQ carry-forward, MOQ top-up, exception classification, tolerance, buckets."""

from datetime import date
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from universal_buying.ub_planning import planning
from universal_buying.ub_planning.doctype.auto_po_exception.auto_po_exception import tolerance_percent

THRESHOLDS = {"A": 0.9, "B": 0.8, "C": 0.7}


def threshold(cls):
	return THRESHOLDS.get(cls, THRESHOLDS["C"])


def line(item_code="ITEM-1", shortage=10, moq=100, spq=1, item_class="A", supplier="SUP-1", rate=5.0,
		bucket=date(2026, 10, 1), moq_per_line=0, project=None):
	return frappe._dict(item_code=item_code, po_shortage=shortage, moq=moq, spq=spq, item_class=item_class,
		supplier=supplier, rate=rate, bucket=bucket, required_by=bucket, schedule_date=bucket,
		moq_per_line=moq_per_line, project=project, uom="Nos", currency="INR", price_list="Standard Buying")


def fake_setting(fieldname, company=None, default=None):
	return {"abc_default_class": "C"}.get(fieldname, default)


class TestThreshold(IntegrationTestCase):
	def test_class_a_needs_90_percent_of_moq(self):
		eligible, exceptions = planning.classify_lines([line(shortage=89, moq=100, item_class="A")], threshold)
		self.assertFalse(eligible)
		self.assertEqual(exceptions[0].exception_type, planning.MOQ_EXCEPTION)

		eligible, exceptions = planning.classify_lines([line(shortage=90, moq=100, item_class="A")], threshold)
		self.assertEqual(len(eligible), 1)
		self.assertFalse(exceptions)

	def test_threshold_uses_total_of_all_buckets(self):
		lines = [line(shortage=40, bucket=date(2026, 10, 1)), line(shortage=45, bucket=date(2026, 11, 1))]
		eligible, _exc = planning.classify_lines(lines, lambda c: 0.8)
		self.assertEqual(len(eligible), 2)

	def test_unknown_class_uses_default_class_not_dropped(self):
		"""Source bug: a class outside A/B/C was silently dropped (neither PO nor exception)."""
		with patch.object(planning, "get_setting", side_effect=fake_setting):
			eligible, exceptions = planning.classify_lines([line(shortage=75, moq=100, item_class="X")], threshold)
			self.assertEqual(len(eligible), 1)  # C = 70 %
			eligible, exceptions = planning.classify_lines([line(shortage=60, moq=100, item_class=None)], threshold)
			self.assertEqual(len(exceptions), 1)
			self.assertEqual(exceptions[0].item_class, "C")


class TestExceptionClassification(IntegrationTestCase):
	def test_no_supplier(self):
		_el, exc = planning.classify_lines([line(supplier=None, rate=None)], threshold)
		self.assertEqual(exc[0].exception_type, planning.NO_SUPPLIER)

	def test_no_price(self):
		_el, exc = planning.classify_lines([line(rate=None, shortage=500)], threshold)
		self.assertEqual([e.exception_type for e in exc], [planning.NO_PRICE])

	def test_one_row_per_item_with_total_shortage(self):
		lines = [line(shortage=10, bucket=date(2026, 10, 1)), line(shortage=15, bucket=date(2026, 11, 1))]
		_el, exc = planning.classify_lines(lines, threshold)
		self.assertEqual(len(exc), 1)
		self.assertEqual(exc[0].po_shortage, 25)
		self.assertEqual(exc[0].required_by, date(2026, 10, 1))

	def test_items_are_independent(self):
		lines = [line("A-1", shortage=100), line("B-1", shortage=1)]
		eligible, exc = planning.classify_lines(lines, threshold)
		self.assertEqual([x.item_code for x in eligible], ["A-1"])
		self.assertEqual([x.item_code for x in exc], ["B-1"])


class TestSpqAndMoq(IntegrationTestCase):
	def test_spq_rounding_carries_surplus_forward(self):
		lines = [
			line(shortage=30, spq=50, moq=1, bucket=date(2026, 10, 1)),
			line(shortage=15, spq=50, moq=1, bucket=date(2026, 11, 1)),
			line(shortage=40, spq=50, moq=1, bucket=date(2026, 12, 1)),
		]
		out = planning.apply_spq_carry_forward(lines)
		# 30 -> 50 (surplus 20); 15 covered by surplus (5 left); 40 - 5 = 35 -> 50
		self.assertEqual([x.qty for x in out], [50, 50])
		self.assertEqual([x.bucket for x in out], [date(2026, 10, 1), date(2026, 12, 1)])

	def test_moq_top_up_on_last_line(self):
		lines = planning.apply_spq_carry_forward([
			line(shortage=20, spq=10, moq=100, bucket=date(2026, 10, 1)),
			line(shortage=30, spq=10, moq=100, bucket=date(2026, 11, 1)),
		])
		planning.apply_moq_top_up(lines)
		self.assertEqual([x.qty for x in lines], [20, 80])
		self.assertEqual(sum(x.qty for x in lines), 100)

	def test_moq_top_up_rounds_to_spq(self):
		lines = planning.apply_spq_carry_forward([line(shortage=10, spq=30, moq=100)])
		planning.apply_moq_top_up(lines)
		self.assertEqual(lines[0].qty, 120)

	def test_moq_top_up_empty_list(self):
		"""Source bug: check_moq failed with an empty eligible list."""
		self.assertEqual(planning.apply_moq_top_up([]), [])
		self.assertEqual(planning.round_eligible([]), [])

	def test_moq_per_line_supplier(self):
		lines = [
			line(shortage=10, spq=5, moq=100, moq_per_line=1, bucket=date(2026, 10, 1)),
			line(shortage=150, spq=5, moq=100, moq_per_line=1, bucket=date(2026, 11, 1)),
		]
		out = planning.apply_spq_carry_forward(lines)
		# line 1: 10 -> 100 (surplus 90); line 2: 150 - 90 = 60 -> 100
		self.assertEqual([x.qty for x in out], [100, 100])

	def test_float_quantities(self):
		out = planning.apply_spq_carry_forward([line(shortage=0.3 * 3, spq=0.3, moq=0.1)])
		self.assertAlmostEqual(out[0].qty, 0.9)


class TestTolerance(IntegrationTestCase):
	def test_tolerance_percent(self):
		self.assertAlmostEqual(tolerance_percent(95, 100), 5.0)
		self.assertAlmostEqual(tolerance_percent(94, 100), 6.0)
		self.assertEqual(tolerance_percent(150, 100), 0.0)
		self.assertEqual(tolerance_percent(10, 0), 0.0)


class TestBuckets(IntegrationTestCase):
	def test_bucket_dates(self):
		d = date(2026, 10, 15)  # Thursday
		self.assertEqual(planning.bucket_date(d, "Month"), date(2026, 10, 1))
		self.assertEqual(planning.bucket_date(d, "Week"), date(2026, 10, 12))
		self.assertEqual(planning.bucket_date(d, "Exact Date"), d)

	def test_unreserved_po_allocation(self):
		lines = [
			frappe._dict(item_code="I", project=None, stock_qty=30),
			frappe._dict(item_code="I", project=None, stock_qty=30),
		]
		pool = {(None, "I"): 40}
		planning.allocate_unreserved_po(lines, pool)
		self.assertEqual([x.stock_qty for x in lines], [0, 20])
		self.assertEqual(pool[(None, "I")], 0)


class TestExceptionFollowUp(IntegrationTestCase):
	"""AC-12.2: a row with a filled Follow-up is not repeated on the next run."""

	def test_follow_up_rows_are_not_repeated(self):
		company = frappe.db.get_value("Company", {"is_group": 0}, "name", order_by="creation asc")
		item = "_UB-APE-ITEM"
		if not frappe.db.exists("Item", item):
			frappe.get_doc({"doctype": "Item", "item_code": "_UB-APE-ITEM", "item_name": "_UB-APE-ITEM",
				"stock_uom": "Nos", "item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
				"is_purchase_item": 1}).insert(ignore_permissions=True)
		fake = [line(item_code=item, shortage=1, moq=100)]

		rows = planning.compute_exception_rows(company, date(2026, 12, 31), lines=[frappe._dict(x) for x in fake])
		self.assertEqual([r.item_code for r in rows], [item])

		exc = frappe.get_doc({
			"doctype": "Auto PO Exception", "company": company, "to_date": date(2026, 12, 31),
			"items": [{"exception_type": planning.MOQ_EXCEPTION, "item_code": item, "po_shortage": 1, "moq": 100}],
		}).insert(ignore_permissions=True)
		exc.submit()
		# submitted without follow-up: still repeated
		rows = planning.compute_exception_rows(company, date(2026, 12, 31), lines=[frappe._dict(x) for x in fake])
		self.assertEqual([r.item_code for r in rows], [item])

		frappe.db.set_value("Auto PO Exception Detail", exc.items[0].name, "follow_up", "RFQ-0001")
		rows = planning.compute_exception_rows(company, date(2026, 12, 31), lines=[frappe._dict(x) for x in fake])
		self.assertEqual(rows, [])
