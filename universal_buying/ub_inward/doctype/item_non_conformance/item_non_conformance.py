# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt

"""Item Non Conformance (BRD v2 6.25).

Dispositions map to standard documents only (separate Scrap Note and Material Transfer Note doctypes are
not ported):

| Disposition          | Output                                                                     |
|----------------------|----------------------------------------------------------------------------|
| Scrap                | Stock Entry "Material Transfer" to the company scrap warehouse when one      |
|                      | exists (setting scrap_warehouse_name, default "Scrap"), else "Material Issue" |
| Return to Supplier   | Purchase Return (Purchase Receipt, is_return) against the receipt            |
| Transfer             | Stock Entry "Material Transfer" to the chosen target warehouse               |
| Rework               | Stock Entry "Material Transfer" rejected -> accepted warehouse               |
| Accept On Deviation  | Stock Entry "Material Transfer" rejected -> accepted warehouse               |

Every output is valued at the receipt rate and linked back to the INC
(Stock Entry.ub_item_non_conformance / INC.purchase_return). Outputs are created as drafts for review.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from universal_buying.ub_inward.utils import get_company_warehouse
from universal_buying.universal_buying.settings import get_setting

TRANSFER_TO_ACCEPTED = ("Rework", "Accept On Deviation")


class ItemNonConformance(Document):
	def validate(self):
		if self.reference_type == "Purchase Receipt" and self.reference_name:
			pr = frappe.db.get_value(
				"Purchase Receipt", self.reference_name, ["supplier", "company"], as_dict=True
			)
			if pr:
				self.supplier = pr.supplier
				if frappe.get_meta("Purchase Receipt").has_field("ub_supplier_invoice_no"):
					self.supplier_invoice_no = frappe.db.get_value(
						"Purchase Receipt", self.reference_name, "ub_supplier_invoice_no"
					)
				if pr.company != self.company:
					frappe.throw(
						_("Purchase Receipt {0} belongs to another company.").format(self.reference_name)
					)
		if flt(self.rejected_qty) <= 0:
			frappe.throw(_("Rejected Qty must be greater than zero."))
		self.amount = flt(self.rate) * flt(self.rejected_qty)
		if self.docstatus == 0:
			self.status = "Draft"

	def before_submit(self):
		if not self.disposition:
			frappe.throw(_("Disposition is mandatory."), title=_("Missing Disposition"))
		if not self.attachment:
			frappe.throw(_("Attachment is mandatory."), title=_("Missing Attachment"))
		if self.disposition == "Transfer" and not self.target_warehouse:
			frappe.throw(_("Target Warehouse is required for a Transfer disposition."))
		self.status = "Open"

	def on_cancel(self):
		self.db_set("status", "Cancelled")


# ---------------------------------------------------------------------------
# builders (return unsaved documents, so they can be tested without stock)
# ---------------------------------------------------------------------------

ROW_FIELDS = [
	"name",
	"item_code",
	"warehouse",
	"rejected_warehouse",
	"base_net_rate",
	"base_rate",
	"conversion_factor",
	"batch_no",
	"stock_uom",
	"project",
	"cost_center",
]


def get_receipt_row(inc):
	"""The receipt row the INC is about (purchase_receipt_item, else item + batch)."""
	if inc.get("purchase_receipt_item"):
		row = frappe.db.get_value(
			"Purchase Receipt Item", inc.purchase_receipt_item, ROW_FIELDS, as_dict=True
		)
		if row:
			return row
	filters = {"parent": inc.reference_name, "item_code": inc.item_code}
	if inc.get("batch_no"):
		filters["batch_no"] = inc.batch_no
	row = frappe.db.get_value("Purchase Receipt Item", filters, ROW_FIELDS, as_dict=True)
	if not row:
		row = frappe.db.get_value(
			"Purchase Receipt Item",
			{"parent": inc.reference_name, "item_code": inc.item_code},
			ROW_FIELDS,
			as_dict=True,
		)
	if not row:
		frappe.throw(
			_("Item {0} not found in Purchase Receipt {1}.").format(inc.item_code, inc.reference_name)
		)
	return row


def receipt_rate(inc, row):
	"""Receipt rate per stock UOM in company currency."""
	if flt(inc.get("rate")):
		return flt(inc.rate)
	return flt(row.get("base_net_rate") or row.get("base_rate")) / (flt(row.get("conversion_factor")) or 1)


def stock_entry_plan(inc, row):
	"""(stock_entry_type, source_warehouse, target_warehouse) for a stock disposition."""
	source = inc.get("rejected_warehouse") or row.get("rejected_warehouse") or row.get("warehouse")
	disposition = inc.get("disposition")
	if disposition == "Scrap":
		scrap_name = get_setting("scrap_warehouse_name", company=inc.get("company"), default="Scrap")
		scrap = get_company_warehouse(inc.get("company"), scrap_name)
		if scrap and scrap != source:
			return "Material Transfer", source, scrap
		return "Material Issue", source, None
	if disposition == "Transfer":
		if not inc.get("target_warehouse"):
			frappe.throw(_("Target Warehouse is required for a Transfer disposition."))
		return "Material Transfer", source, inc.target_warehouse
	if disposition in TRANSFER_TO_ACCEPTED:
		target = inc.get("target_warehouse") or row.get("warehouse")
		if not target or target == source:
			frappe.throw(_("Set a Target Warehouse different from the rejected warehouse."))
		return "Material Transfer", source, target
	frappe.throw(_("Disposition {0} does not create a Stock Entry.").format(disposition or "-"))


def build_stock_entry(inc, row=None):
	row = row or get_receipt_row(inc)
	entry_type, source, target = stock_entry_plan(inc, row)
	rate = receipt_rate(inc, row)
	stock_uom = row.get("stock_uom") or frappe.get_cached_value("Item", inc.item_code, "stock_uom")

	se = frappe.new_doc("Stock Entry")
	se.company = inc.company
	se.stock_entry_type = entry_type
	se.purpose = entry_type
	se.ub_item_non_conformance = inc.name
	se.remarks = _("Item Non Conformance {0}: {1}").format(inc.name, inc.disposition)
	se.append(
		"items",
		{
			"item_code": inc.item_code,
			"qty": flt(inc.rejected_qty),
			"transfer_qty": flt(inc.rejected_qty),
			"uom": stock_uom,
			"stock_uom": stock_uom,
			"conversion_factor": 1,
			"s_warehouse": source,
			"t_warehouse": target,
			"batch_no": inc.get("batch_no"),
			"use_serial_batch_fields": 1 if inc.get("batch_no") else 0,
			"basic_rate": rate,
			"allow_zero_valuation_rate": 1 if not rate else 0,
			"project": inc.get("project") or row.get("project"),
			"cost_center": row.get("cost_center"),
		},
	)
	return se


def build_purchase_return(inc, row=None):
	"""Return of this item's rejected qty (or accepted qty when the stock was accepted) against the receipt."""
	from universal_buying.ub_inward.api import make_purchase_return

	row = row or get_receipt_row(inc)
	from_rejected = bool(row.get("rejected_warehouse")) and (
		not inc.get("rejected_warehouse") or inc.rejected_warehouse == row.get("rejected_warehouse")
	)
	ret = make_purchase_return(inc.reference_name, return_against_rejected_qty=1 if from_rejected else 0)
	keep = [d for d in ret.get("items") if d.get("purchase_receipt_item") == row.name]
	if not keep:
		frappe.throw(_("Nothing left to return for {0} on {1}.").format(inc.item_code, inc.reference_name))
	ret.set("items", keep)
	for d in ret.get("items"):
		cf = flt(d.get("conversion_factor")) or 1
		qty = -abs(flt(inc.rejected_qty)) / cf
		if abs(qty) > abs(flt(d.qty)):
			qty = flt(d.qty)
		d.qty = qty
		d.received_qty = qty
		d.stock_qty = qty * cf
		d.rejected_qty = 0
	ret.run_method("calculate_taxes_and_totals")
	return ret


# ---------------------------------------------------------------------------
# whitelisted actions
# ---------------------------------------------------------------------------


def _get_submitted_inc(name):
	inc = frappe.get_doc("Item Non Conformance", name)
	inc.check_permission("submit")
	if inc.docstatus != 1:
		frappe.throw(_("Submit the Item Non Conformance first."))
	if (
		inc.reference_type == "Purchase Receipt"
		and frappe.db.get_value("Purchase Receipt", inc.reference_name, "docstatus") != 1
	):
		frappe.throw(_("Purchase Receipt {0} must be submitted first.").format(inc.reference_name))
	return inc


def _alive(doctype, name):
	return bool(name) and frappe.db.get_value(doctype, name, "docstatus") in (0, 1)


@frappe.whitelist()
def make_stock_entry(name):
	inc = _get_submitted_inc(name)
	if inc.disposition == "Return to Supplier":
		frappe.throw(_("Use Create > Purchase Return for this disposition."))
	if _alive("Stock Entry", inc.stock_entry):
		return inc.stock_entry
	se = build_stock_entry(inc)
	se.insert()
	inc.db_set({"stock_entry": se.name, "status": "Completed"})
	return se.name


@frappe.whitelist()
def make_purchase_return(name):
	inc = _get_submitted_inc(name)
	if inc.disposition != "Return to Supplier":
		frappe.throw(_("Disposition must be Return to Supplier."))
	if _alive("Purchase Receipt", inc.purchase_return):
		return inc.purchase_return
	ret = build_purchase_return(inc)
	ret.insert()
	inc.db_set({"purchase_return": ret.name, "status": "Completed"})
	return ret.name
