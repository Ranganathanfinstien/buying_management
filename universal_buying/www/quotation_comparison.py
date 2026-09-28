"""Quotation Comparison page (/quotation-comparison?rfq=...). Logic: universal_buying.ub_sourcing.comparison."""

from urllib.parse import quote

import frappe

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		target = "/quotation-comparison?rfq=" + quote(frappe.form_dict.get("rfq") or "")
		frappe.local.flags.redirect_location = "/login?redirect-to=" + quote(target, safe="")
		raise frappe.Redirect

	from universal_buying.ub_sourcing.comparison import build_context

	context.no_cache = 1
	build_context(context)
	return context
