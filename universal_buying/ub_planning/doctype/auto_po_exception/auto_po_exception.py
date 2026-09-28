# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt

"""Auto PO Exception (BRD v2 6.12).

Rows: No Supplier / No Price / MOQ Exception. Actions on the submitted document:

- Create Item Price Request - No Price rows, one draft request per row, row stamped (V-9.3: an open
  draft request for the item is linked instead of creating a second one).
- Create PO for MOQ items - MOQ rows whose (1 - shortage / MOQ) x 100 is at or below
  ``moq_tolerance_percent``; a draft PO at MOQ per supplier, origin "Auto PO Exception", lines flagged
  ``ub_skip_moq``. Rows above the tolerance are returned as refused.
- Follow-up (free text) - rows with a follow-up are not repeated on the next run (AC-12.2).

There is no Recommendation Note action (AC-12.1).
"""

from collections import OrderedDict

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, getdate, nowdate

from universal_buying.ub_planning import planning
from universal_buying.ub_planning.api import get_current_item_price
from universal_buying.ub_planning.po_builder import build_purchase_order
from universal_buying.universal_buying.settings import get_setting

ORIGIN = "Auto PO Exception"


class AutoPOException(Document):
	def validate(self):
		if self.project and not cint(get_setting("plan_by_project", company=self.company)):
			self.project = None

	def before_submit(self):
		if not self.items:
			frappe.throw(_("There are no exception rows to submit."))

	@frappe.whitelist()
	def get_exceptions(self):
		"""Fill the rows for a manually created exception (draft)."""
		if self.docstatus != 0:
			frappe.throw(_("Rows can only be refreshed on a draft."))
		if not self.to_date:
			frappe.throw(_("To Date is required."))
		from universal_buying.ub_planning.doctype.auto_po_run.auto_po_run import exception_child

		project = self.project if cint(get_setting("plan_by_project", company=self.company)) else None
		rows = planning.compute_exception_rows(self.company, self.to_date, project, cint(self.lead_time_order),
			exclude_doc=self.name if not self.is_new() else None)
		self.set("items", [exception_child(r) for r in rows])
		return len(rows)


def _check_submitted(doc):
	if doc.docstatus != 1:
		frappe.throw(_("Submit the Auto PO Exception first."))
	doc.check_permission("submit")


def tolerance_percent(shortage, moq):
	"""(1 - shortage / MOQ) x 100; 0 when shortage >= MOQ."""
	moq = flt(moq)
	if moq <= 0:
		return 0.0
	return max(0.0, (1 - flt(shortage) / moq) * 100.0)


@frappe.whitelist()
def create_item_price_requests(docname, rows):
	"""rows: [{row_name, supplier, rate, price_list, valid_from, valid_upto, lead_time_days, item_manufacturer,
	moq, spq}] - one draft Item Price Request per No Price row."""
	doc = frappe.get_doc("Auto PO Exception", docname)
	_check_submitted(doc)
	rows = frappe.parse_json(rows) if isinstance(rows, str) else rows
	by_name = {r.name: r for r in doc.items}
	created = []
	for data in rows or []:
		data = frappe._dict(data)
		row = by_name.get(data.row_name or data.name)
		if not row or row.exception_type != planning.NO_PRICE or row.item_price_request:
			continue
		open_ipr = get_open_price_request(row.item_code, doc.company)
		if not open_ipr:
			ipr = frappe.new_doc("Item Price Request")
			ipr.company = doc.company
			ipr.type = "Buying"
			uom = row.uom or frappe.db.get_value("Item", row.item_code, "stock_uom")
			ipr.append("item_price_details", {
				"item_code": row.item_code,
				"uom": uom,
				"supplier": data.supplier or row.default_supplier,
				"price_list": data.price_list,
				"rate": flt(data.rate),
				"moq": flt(data.moq) or flt(row.moq),
				"spq": flt(data.spq) or flt(row.spq),
				"valid_from": data.valid_from,
				"valid_upto": data.valid_upto,
				"lead_time_days": cint(data.lead_time_days),
				"item_manufacturer": data.item_manufacturer,
				"project": row.project,
			})
			ipr.insert()
			open_ipr = ipr.name
		frappe.db.set_value("Auto PO Exception Detail", row.name,
			{"item_price_request": open_ipr, "status": "Item Price Request Created"})
		created.append({"item_code": row.item_code, "item_price_request": open_ipr})
	return created


def get_open_price_request(item_code, company):
	res = frappe.db.sql(
		"""select ipr.name from `tabItem Price Request` ipr
		inner join `tabItem Price Request Detail` d on d.parent = ipr.name and d.parenttype = 'Item Price Request'
		where ipr.docstatus = 0 and ipr.type = 'Buying' and ipr.company = %s and d.item_code = %s
		order by ipr.creation desc limit 1""",
		(company, item_code),
	)
	return res[0][0] if res else None


@frappe.whitelist()
def make_purchase_order(docname, row_names=None):
	"""Draft POs at MOQ for MOQ Exception rows within moq_tolerance_percent."""
	doc = frappe.get_doc("Auto PO Exception", docname)
	_check_submitted(doc)
	row_names = frappe.parse_json(row_names) if isinstance(row_names, str) else row_names
	tolerance = flt(get_setting("moq_tolerance_percent", company=doc.company))
	today = getdate(nowdate())

	groups = OrderedDict()
	refused = []
	for row in doc.items:
		if row.exception_type != planning.MOQ_EXCEPTION or row.purchase_order or not row.default_supplier:
			continue
		if row_names and row.name not in row_names:
			continue
		gap = tolerance_percent(row.po_shortage, row.moq)
		if gap > tolerance + 1e-9:
			refused.append({"item_code": row.item_code, "tolerance_percent": flt(gap, 2), "moq": row.moq,
				"shortage": row.po_shortage})
			continue
		schedule_date = max(getdate(row.required_by or today), today)
		price = get_current_item_price(row.item_code, row.default_supplier, doc.company, schedule_date)
		if not price:
			refused.append({"item_code": row.item_code, "reason": _("No valid price"), "moq": row.moq,
				"shortage": row.po_shortage})
			continue
		groups.setdefault((row.default_supplier, price["currency"], price["price_list"]), []).append((row, price))

	created = []
	for (supplier, currency, price_list), pairs in groups.items():
		lines = []
		for row, price in pairs:
			lines.append({
				"item_code": row.item_code,
				"qty": flt(row.moq),
				"uom": row.uom,
				"rate": planning.price_rate_for_uom(row.item_code, price, row.uom),
				"schedule_date": max(getdate(row.required_by or today), today),
				"project": row.project or doc.project,
				"manufacturer": price.get("manufacturer") or row.manufacturer,
				"manufacturer_part_no": price.get("manufacturer_part_no") or row.mpn,
				"required_by": row.required_by,
				"supplier_delivery_date": row.required_by,
				"skip_moq": 1,
			})
		po = build_purchase_order(doc.company, supplier, lines, ORIGIN, doc.name, currency=currency,
			price_list=price_list, project=doc.project)
		for row, _price in pairs:
			frappe.db.set_value("Auto PO Exception Detail", row.name,
				{"purchase_order": po.name, "status": "Purchase Order Created"})
		created.append({"name": po.name, "supplier": supplier, "items": [r.item_code for r, _p in pairs]})
	return {"purchase_orders": created, "refused": refused, "tolerance": tolerance}
