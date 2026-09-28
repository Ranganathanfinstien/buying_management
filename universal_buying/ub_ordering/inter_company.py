"""A-17.3: mirror Sales Order in the supplying company when a PO to an internal supplier is submitted.

Minimal inter-company Sales Order creation on top of the standard
ERPNext mapper ``erpnext.buying.doctype.purchase_order.purchase_order.make_inter_company_sales_order``.
Client-specific fields (project_, cost_centre_, from_item mapping, job work flags) are dropped.

The Sales Order is saved as a Draft in the other company (its owner reviews and submits it).
Any problem (no represents_company, no internal customer, price list not valid for inter company)
is reported as a warning and never blocks the PO submit.
"""

import frappe
from frappe import _

from universal_buying.universal_buying.settings import get_setting


def make_inter_company_sales_order(po):
	if po.docstatus != 1 or not po.get("is_internal_supplier") or po.get("inter_company_order_reference"):
		return None
	if po.status in ("Closed", "On Hold"):
		return None
	if not get_setting("inter_company_auto_so", company=po.company):
		return None
	if not frappe.db.get_value("Supplier", po.supplier, "represents_company"):
		frappe.msgprint(_("Inter-company Sales Order not created: Supplier {0} has no Represents Company.").format(
			frappe.bold(po.supplier)), indicator="orange", alert=True)
		return None

	from erpnext.buying.doctype.purchase_order.purchase_order import make_inter_company_sales_order as _make

	frappe.db.savepoint("ub_ic_so")
	try:
		so = _make(po.name)
		so.delivery_date = so.delivery_date or po.schedule_date
		for row, po_row in zip(so.items, po.items):
			row.delivery_date = row.delivery_date or po_row.schedule_date or po.schedule_date
		so.po_no = po.name
		so.po_date = po.transaction_date
		so.flags.ignore_permissions = True
		so.insert(ignore_mandatory=True)
	except Exception as e:
		frappe.db.rollback(save_point="ub_ic_so")
		frappe.local.message_log = []
		frappe.log_error(title=f"Inter-company Sales Order for {po.name}")
		frappe.msgprint(_("Inter-company Sales Order was not created: {0}").format(frappe.utils.strip_html(str(e))),
			title=_("Inter Company"), indicator="orange")
		return None

	po.db_set("inter_company_order_reference", so.name, update_modified=False)
	frappe.msgprint(_("Inter-company Sales Order {0} created as Draft in {1}.").format(
		frappe.bold(so.name), so.company), indicator="green", alert=True)
	return so.name
