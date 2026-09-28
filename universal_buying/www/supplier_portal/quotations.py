import frappe

from universal_buying.ub_ordering.portal_pages import fmt_date, list_docs, prepare

no_cache = 1


def get_context(context):
	suppliers = prepare(context, "quotations", "Quotations")
	if not suppliers:
		return
	fields = ["name", "transaction_date", "valid_till", "status", "grand_total", "currency", "docstatus"]
	if frappe.get_meta("Supplier Quotation").has_field("ub_revised"):
		fields.append("ub_revised")
	context.quotations = list_docs(context, "Supplier Quotation", suppliers, fields,
		extra_filters={"docstatus": ["<", 2]}, order_by="transaction_date desc, name desc")
	for r in context.quotations:
		r.date_fmt = fmt_date(r.transaction_date)
		r.valid_fmt = fmt_date(r.valid_till)
		r.total_fmt = frappe.utils.fmt_money(r.grand_total, currency=r.currency)
		r.rfqs = ", ".join(sorted(set(frappe.get_all("Supplier Quotation Item",
			filters={"parent": r.name, "request_for_quotation": ["is", "set"]}, pluck="request_for_quotation"))))
