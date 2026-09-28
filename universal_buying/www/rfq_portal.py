"""RFQ Portal page (/rfq-portal?token=...). All logic and endpoints: universal_buying.ub_sourcing.portal."""

import frappe
from frappe import _

no_cache = 1
allow_guest = True


def get_context(context):
	from universal_buying.ub_sourcing.portal import build_context

	context.no_cache = 1
	try:
		build_context(context)
	except frappe.PermissionError:
		context.error = _("This link is invalid or has expired.")
	except Exception:
		frappe.log_error(title="RFQ Portal Error", message=frappe.get_traceback())
		context.error = _("Something went wrong. Please contact the company.")
	return context
