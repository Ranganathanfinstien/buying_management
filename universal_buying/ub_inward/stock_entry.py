"""Stock Entry doc events for UB Inward.

Item Non Conformance rate rule: a Stock Entry raised from an Item
Non Conformance (``ub_item_non_conformance``) is valued at the receipt rate.

Only rows that bring stock in without a source warehouse get ``set_basic_rate_manually``; rows that move
stock out of a warehouse keep the ledger valuation (for a batch received on that receipt the ledger rate
already is the receipt rate), so the stock ledger and GL stay consistent.
"""

import frappe
from frappe.utils import flt


def enforce_inc_rate(doc, method=None):
	inc_name = doc.get("ub_item_non_conformance")
	if not inc_name or not frappe.db.exists("Item Non Conformance", inc_name):
		return

	inc = frappe.get_doc("Item Non Conformance", inc_name)
	if inc.reference_type != "Purchase Receipt" or not inc.reference_name:
		return

	from universal_buying.ub_inward.doctype.item_non_conformance.item_non_conformance import (
		get_receipt_row,
		receipt_rate,
	)

	rate = receipt_rate(inc, get_receipt_row(inc))
	for row in doc.get("items"):
		if row.item_code != inc.item_code:
			continue
		if inc.batch_no and row.get("batch_no") and row.batch_no != inc.batch_no:
			continue
		if row.get("s_warehouse"):
			continue
		qty = flt(row.get("transfer_qty")) or flt(row.qty) * (flt(row.get("conversion_factor")) or 1)
		row.basic_rate = rate
		row.basic_amount = flt(rate * qty, row.precision("basic_amount"))
		row.amount = flt(row.basic_amount + flt(row.get("additional_cost")), row.precision("amount"))
		row.valuation_rate = flt(row.amount / qty, row.precision("valuation_rate")) if qty else rate
		row.set_basic_rate_manually = 1
		row.allow_zero_valuation_rate = 1 if not rate else 0
