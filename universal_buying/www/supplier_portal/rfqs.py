import frappe

from universal_buying.ub_ordering.portal_pages import fmt_date, paginate, prepare

no_cache = 1


def get_context(context):
	suppliers = prepare(context, "rfqs", "RFQs")
	if not suppliers:
		return
	has_deadline = frappe.get_meta("Request for Quotation").has_field("ub_bid_deadline")
	deadline = "rfq.ub_bid_deadline" if has_deadline else "null"
	q = (frappe.form_dict.get("q") or "").strip()
	params = {"sup": tuple(suppliers), "q": f"%{q}%"}
	where = """rfq.docstatus = 1 and rs.supplier in %(sup)s""" + (" and rfq.name like %(q)s" if q else "")
	total = frappe.db.sql(f"""select count(distinct rfq.name) from `tabRequest for Quotation` rfq
		join `tabRequest for Quotation Supplier` rs on rs.parent = rfq.name and rs.parenttype = 'Request for Quotation'
		where {where}""", params)[0][0]
	page_length, start = paginate(context, total)
	params.update(start=start, page_length=page_length)
	context.rfqs = frappe.db.sql(f"""select rfq.name, rfq.transaction_date, rfq.schedule_date, rfq.status,
			{deadline} as deadline, max(rs.quote_status) as quote_status, rfq.company
		from `tabRequest for Quotation` rfq
		join `tabRequest for Quotation Supplier` rs on rs.parent = rfq.name and rs.parenttype = 'Request for Quotation'
		where {where}
		group by rfq.name order by rfq.transaction_date desc, rfq.name desc
		limit %(start)s, %(page_length)s""", params, as_dict=True)
	now = frappe.utils.now_datetime()
	for r in context.rfqs:
		r.date_fmt = fmt_date(r.transaction_date)
		r.required_fmt = fmt_date(r.schedule_date)
		r.deadline_fmt = frappe.format(r.deadline, {"fieldtype": "Datetime"}) if r.deadline else ""
		r.open = r.status not in ("Cancelled",) and (not r.deadline or frappe.utils.get_datetime(r.deadline) > now)
		r.item_count = frappe.db.count("Request for Quotation Item", {"parent": r.name})
