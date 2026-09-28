from frappe.utils import flt, fmt_money

from universal_buying.ub_ordering.portal_pages import fmt_date, list_docs, prepare

no_cache = 1


def get_context(context):
	suppliers = prepare(context, "invoices", "Invoices")
	if not suppliers:
		return
	context.invoices = list_docs(context, "Purchase Invoice", suppliers,
		["name", "posting_date", "bill_no", "bill_date", "due_date", "status", "grand_total", "outstanding_amount", "currency"],
		extra_filters={"docstatus": 1}, search_field="bill_no", order_by="posting_date desc, name desc")
	for r in context.invoices:
		r.date_fmt = fmt_date(r.posting_date)
		r.bill_date_fmt = fmt_date(r.bill_date)
		r.due_fmt = fmt_date(r.due_date)
		r.total_fmt = fmt_money(flt(r.grand_total), currency=r.currency)
		r.outstanding_fmt = fmt_money(flt(r.outstanding_amount), currency=r.currency)
