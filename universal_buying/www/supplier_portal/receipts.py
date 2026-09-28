import frappe

from universal_buying.ub_ordering.portal_pages import fmt_date, list_docs, prepare

no_cache = 1


def get_context(context):
	suppliers = prepare(context, "receipts", "Goods Receipts")
	if not suppliers:
		return
	context.receipts = list_docs(context, "Purchase Receipt", suppliers,
		["name", "posting_date", "status", "supplier_delivery_note", "total_qty", "per_billed"],
		extra_filters={"docstatus": 1, "is_return": 0}, search_field="supplier_delivery_note",
		order_by="posting_date desc, name desc")
	for r in context.receipts:
		r.date_fmt = fmt_date(r.posting_date)
		r.pos = ", ".join(sorted(set(frappe.get_all("Purchase Receipt Item",
			filters={"parent": r.name, "purchase_order": ["is", "set"]}, pluck="purchase_order"))))
		agg = frappe.db.sql("""select sum(received_qty), sum(rejected_qty) from `tabPurchase Receipt Item`
			where parent = %s""", r.name)[0]
		r.received_qty, r.rejected_qty = agg[0] or 0, agg[1] or 0
