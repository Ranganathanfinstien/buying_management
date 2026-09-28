from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import flt, fmt_money

from universal_buying.ub_ordering import portal
from universal_buying.ub_ordering.doctype.po_material_status.po_material_status import ACCEPTED_STATES, RANK
from universal_buying.ub_ordering.portal_pages import clean_address, fmt_date, paginate, prepare

no_cache = 1

MATERIAL_STATUSES = list(RANK) + ["Delayed"]
PILL = {"Pending Acceptance": "orange", "Accepted": "blue", "Partially Dispatched": "blue", "Dispatched": "green"}


def get_context(context):
	suppliers = prepare(context, "purchase_orders", "Purchase Orders")
	if not suppliers:
		return
	context.pill = PILL
	name = frappe.form_dict.get("name")
	if name:
		_detail(context, name, suppliers)
	else:
		_list(context, suppliers)


def _list(context, suppliers):
	view = frappe.form_dict.get("view")
	filters = {"supplier": ["in", suppliers], "docstatus": 1}
	if view == "pending":
		filters["ub_portal_status"] = "Pending Acceptance"
	elif view == "open":
		filters["status"] = ["in", ["To Receive and Bill", "To Receive", "To Bill"]]
	q = (frappe.form_dict.get("q") or "").strip()
	if q:
		filters["name"] = ["like", f"%{q}%"]
	context.view = view
	page_length, start = paginate(context, frappe.db.count("Purchase Order", filters))
	context.orders = frappe.get_all("Purchase Order", filters=filters,
		fields=["name", "transaction_date", "schedule_date", "status", "ub_portal_status", "ub_material_status",
			"ub_confirmed_delivery_date", "grand_total", "currency", "per_received"],
		order_by="transaction_date desc, name desc", limit_start=start, limit_page_length=page_length)
	for o in context.orders:
		o.date_fmt = fmt_date(o.transaction_date)
		o.required_fmt = fmt_date(o.schedule_date)
		o.confirmed_fmt = fmt_date(o.ub_confirmed_delivery_date)
		o.total_fmt = fmt_money(flt(o.grand_total), currency=o.currency)


def _detail(context, name, suppliers):
	row = frappe.db.get_value("Purchase Order", name, ["supplier", "docstatus"], as_dict=True)
	if not row or row.supplier not in suppliers or row.docstatus != 1:
		frappe.throw(_("You do not have access to this Purchase Order."), frappe.PermissionError)
	po = frappe.get_doc("Purchase Order", name)
	context.po = po
	context.title = po.name
	context.addresses = {
		"billing": clean_address(po.get("billing_address_display")),
		"shipping": clean_address(po.get("shipping_address_display")),
		"supplier": clean_address(po.get("address_display")),
	}
	shipped = portal.shipped_map(name)
	context.lines = []
	for d in po.items:
		context.lines.append(frappe._dict(
			name=d.name, idx=d.idx, item_code=d.item_code, item_name=d.item_name, description=d.description,
			mpn=d.get("manufacturer_part_no"), uom=d.uom, qty=flt(d.qty), received=flt(d.received_qty),
			shipped=flt(shipped.get(d.name)), remaining=max(flt(d.qty) - flt(shipped.get(d.name)), 0),
			required_fmt=fmt_date(d.schedule_date), rate=fmt_money(d.rate, currency=po.currency),
			amount=fmt_money(d.amount, currency=po.currency),
		))
	context.taxes = [frappe._dict(description=t.description, amount=fmt_money(t.tax_amount, currency=po.currency))
		for t in po.get("taxes") or []]
	context.totals = frappe._dict(net=fmt_money(po.net_total, currency=po.currency),
		grand=fmt_money(po.grand_total, currency=po.currency))
	context.date_fmt = fmt_date(po.transaction_date)
	context.required_fmt = fmt_date(po.schedule_date)
	context.confirmed_fmt = fmt_date(po.get("ub_confirmed_delivery_date"))
	context.is_open = po.status not in ("Closed", "Completed")
	context.accepted = po.get("ub_portal_status") in ACCEPTED_STATES
	context.material_statuses = MATERIAL_STATUSES
	context.acks = frappe.get_all("PO Acknowledgement", filters={"purchase_order": name},
		fields=["event_type", "confirmed_delivery_date", "notes", "acknowledged_by", "acknowledged_on"],
		order_by="creation desc")
	context.material_log = frappe.get_all("PO Material Status", filters={"purchase_order": name},
		fields=["status", "expected_dispatch_date", "remarks", "created_by", "created_on"], order_by="creation desc")
	context.shipments = frappe.get_all("PO Shipment", filters={"purchase_order": name, "docstatus": ["<", 2]},
		fields=["name", "shipment_date", "mode_of_transport", "lr_awb_no", "shipment_status", "delivery_status",
			"total_shipped_qty", "docstatus"], order_by="creation desc")
	context.invoices = frappe.get_all("Portal PO Invoice", filters={"parent": name, "parenttype": "Purchase Order"},
		fields=["bill_no", "bill_date", "amount", "attachment", "uploaded_on"], order_by="idx")
	context.qc_files = frappe.get_all("Portal PO QC Attachment", filters={"parent": name, "parenttype": "Purchase Order"},
		fields=["title", "item_code", "attachment", "uploaded_on"], order_by="idx")
	for r in context.acks:
		r.date_fmt = fmt_date(r.confirmed_delivery_date)
	for r in context.material_log:
		r.date_fmt = fmt_date(r.expected_dispatch_date)
	for r in context.shipments:
		r.date_fmt = fmt_date(r.shipment_date)
	for r in context.invoices:
		r.date_fmt = fmt_date(r.bill_date)
	context.pdf_url = "/api/method/frappe.utils.print_format.download_pdf?doctype=Purchase%20Order&name=" + quote(name)
