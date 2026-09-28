"""Shared context for the Jinja supplier portal pages (www/supplier_portal/*)."""

import re

import frappe
from frappe.utils import cint

from universal_buying.ub_ordering.permissions import get_user_suppliers

PORTAL_BASE = "/supplier_portal"
PAGE_SIZE = 20

# (key, label, route) - labels are translated in the template
PORTAL_MENU = [
	("dashboard", "Dashboard", PORTAL_BASE),
	("rfqs", "RFQs", PORTAL_BASE + "/rfqs"),
	("quotations", "Quotations", PORTAL_BASE + "/quotations"),
	("purchase_orders", "Purchase Orders", PORTAL_BASE + "/purchase_orders"),
	("shipments", "Shipments", PORTAL_BASE + "/shipments"),
	("receipts", "Goods Receipts", PORTAL_BASE + "/receipts"),
	("invoices", "Invoices", PORTAL_BASE + "/invoices"),
	("document_vault", "Document Vault", PORTAL_BASE + "/document_vault"),
	("profile", "Profile", PORTAL_BASE + "/profile"),
]


def prepare(context, active, title):
	"""Guard + base context for every portal page. Returns the user's supplier names ([] = not linked)."""
	context.no_cache = 1
	context.show_sidebar = False
	context.full_width = 1
	context.title = title
	if frappe.session.user == "Guest":
		frappe.redirect("/login?redirect-to=" + (
			getattr(getattr(frappe.local, "request", None), "path", None) or PORTAL_BASE))

	suppliers = get_user_suppliers()
	context.portal_menu = PORTAL_MENU
	context.active_page = active
	context.suppliers = suppliers
	context.not_linked = not suppliers
	context.supplier_names = {s: frappe.db.get_value("Supplier", s, "supplier_name") or s for s in suppliers}
	context.portal_fullname = frappe.utils.get_fullname(frappe.session.user)
	context.portal_email = frappe.session.user
	requested = frappe.form_dict.get("supplier")
	context.current_supplier = requested if requested in suppliers else (suppliers[0] if suppliers else None)
	return suppliers


def paginate(context, total):
	page = max(1, cint(frappe.form_dict.get("page") or 1))
	total_pages = max(1, (cint(total) + PAGE_SIZE - 1) // PAGE_SIZE)
	page = min(page, total_pages)
	context.page = page
	context.total_pages = total_pages
	context.total_records = cint(total)
	req = getattr(frappe.local, "request", None)
	context.list_path = (req.path if req else "") or ""
	context.q = (frappe.form_dict.get("q") or "").strip()
	return PAGE_SIZE, (page - 1) * PAGE_SIZE


def clean_address(html):
	if not html:
		return ""
	s = re.sub(r"<\s*br\s*/?\s*>", "\n", html, flags=re.IGNORECASE)
	s = re.sub(r"<[^>]+>", "", s)
	return "\n".join(ln.strip() for ln in s.splitlines() if ln.strip())


def fmt_date(value):
	return frappe.format(value, {"fieldtype": "Date"}) if value else ""


def list_docs(context, doctype, suppliers, fields, extra_filters=None, search_field="name", order_by="modified desc"):
	"""One page of a supplier's documents of ``doctype``."""
	filters = {"supplier": ["in", suppliers]}
	filters.update(extra_filters or {})
	q = (frappe.form_dict.get("q") or "").strip()
	or_filters = None
	if q:
		or_filters = {search_field: ["like", f"%{q}%"], "name": ["like", f"%{q}%"]}
	total = len(frappe.get_all(doctype, filters=filters, or_filters=or_filters, pluck="name")) if or_filters else \
		frappe.db.count(doctype, filters)
	page_length, start = paginate(context, total)
	return frappe.get_all(doctype, filters=filters, or_filters=or_filters, fields=fields, order_by=order_by,
		limit_start=start, limit_page_length=page_length)
