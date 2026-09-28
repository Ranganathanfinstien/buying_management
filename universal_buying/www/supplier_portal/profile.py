import frappe

from universal_buying.ub_ordering.portal_pages import prepare

no_cache = 1


def get_context(context):
	suppliers = prepare(context, "profile", "Profile")
	if not suppliers:
		return
	context.profile = context.pending = None
	try:
		from universal_buying.ub_supplier.api import get_pending_profile_change, get_supplier_profile
	except ImportError:
		context.unavailable = True
		return
	context.profile = get_supplier_profile(context.current_supplier)
	context.pending = get_pending_profile_change(context.current_supplier)
	context.countries = frappe.get_all("Country", pluck="name", order_by="name")
