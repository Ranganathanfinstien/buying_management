import frappe
from frappe.utils import flt, today

from universal_buying.ub_ordering.portal_pages import fmt_date, prepare

no_cache = 1


def get_context(context):
	suppliers = prepare(context, "dashboard", "Supplier Portal")
	if not suppliers:
		return
	sup = {"sup": tuple(suppliers)}
	context.kpis = [
		{"label": "Open RFQs", "route": "/supplier_portal/rfqs", "value": frappe.db.sql(
			"""select count(distinct rfq.name) from `tabRequest for Quotation` rfq
			join `tabRequest for Quotation Supplier` rs on rs.parent = rfq.name and rs.parenttype = 'Request for Quotation'
			where rfq.docstatus = 1 and rfq.status != 'Cancelled' and rs.supplier in %(sup)s
			and ifnull(rs.quote_status, 'Pending') = 'Pending'""", sup)[0][0]},
		{"label": "POs to acknowledge", "route": "/supplier_portal/purchase_orders?view=pending", "value": frappe.db.count(
			"Purchase Order", {"supplier": ["in", suppliers], "docstatus": 1, "ub_portal_status": "Pending Acceptance"})},
		{"label": "Open POs", "route": "/supplier_portal/purchase_orders", "value": frappe.db.count(
			"Purchase Order", {"supplier": ["in", suppliers], "docstatus": 1,
				"status": ["in", ["To Receive and Bill", "To Receive", "To Bill"]]})},
		{"label": "Overdue PO lines", "route": "/supplier_portal/purchase_orders", "value": frappe.db.sql(
			"""select count(*) from `tabPurchase Order Item` poi join `tabPurchase Order` po on po.name = poi.parent
			where po.docstatus = 1 and po.status not in ('Closed', 'Completed') and po.supplier in %(sup)s
			and poi.qty > ifnull(poi.received_qty, 0)
			and coalesce(poi.ub_supplier_delivery_date, po.ub_confirmed_delivery_date, poi.schedule_date) < %(today)s""",
			dict(sup, today=today()))[0][0]},
		{"label": "Unpaid invoices", "route": "/supplier_portal/invoices", "value": frappe.db.count(
			"Purchase Invoice", {"supplier": ["in", suppliers], "docstatus": 1, "outstanding_amount": [">", 0]})},
	]
	context.recent_pos = frappe.get_all("Purchase Order",
		filters={"supplier": ["in", suppliers], "docstatus": 1},
		fields=["name", "transaction_date", "status", "ub_portal_status", "grand_total", "currency", "schedule_date"],
		order_by="transaction_date desc, name desc", limit_page_length=8)
	for po in context.recent_pos:
		po.date_fmt = fmt_date(po.transaction_date)
		po.total_fmt = frappe.utils.fmt_money(flt(po.grand_total), currency=po.currency)
