"""Landed Cost Voucher helpers: fetch receipts by Bill of Entry and check the expected total."""

import frappe
from frappe import _
from frappe.utils import flt


def validate_landed_cost_voucher(doc, method=None):
	"""Charges must equal the expected (BoE) total when one is given."""
	expected = flt(doc.get("ub_expected_total"))
	if not expected:
		return
	precision = doc.precision("total_taxes_and_charges") or 2
	if abs(flt(expected, precision) - flt(doc.total_taxes_and_charges, precision)) > 0.5 / (10**precision):
		frappe.throw(
			_("Total Taxes and Charges {0} does not match the Expected Charges Total {1}.").format(
				frappe.format(doc.total_taxes_and_charges, {"fieldtype": "Currency"}),
				frappe.format(expected, {"fieldtype": "Currency"}),
			),
			title=_("Landed Cost Mismatch"),
		)


def get_receipts_by_boe(company, boe_no):
	"""Submitted, non-return receipts of a company carrying this Bill of Entry number."""
	if not (company and boe_no):
		return []
	return frappe.get_all(
		"Purchase Receipt",
		filters={"company": company, "ub_boe_no": boe_no.strip(), "docstatus": 1, "is_return": 0},
		fields=["name", "supplier", "base_grand_total as grand_total", "posting_date"],
		order_by="posting_date asc, name asc",
	)
