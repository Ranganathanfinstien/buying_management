"""Supplier portal row-level scoping (AC-21.1).

A supplier-portal user is a user with the ``Supplier`` role and none of the internal roles, linked to
one or more Suppliers through the standard ``Supplier.portal_users`` (Portal User) table. Such a user
sees only its own RFQs, quotations, POs, receipts, invoices and the portal logs; procurement documents
are read-only for them. Internal users are unaffected (the hooks return "" / None).
"""

import frappe

SUPPLIER_ROLE = "Supplier"

# A user holding any of these is internal staff even if they also hold Supplier.
INTERNAL_ROLES = {
	"System Manager", "Purchase Manager", "Purchase User", "Purchase Master Manager", "Accounts Manager",
	"Accounts User", "Stock Manager", "Stock User", "Quality Manager", "Auditor", "Sourcing User",
	"Sourcing Manager", "Finance Manager",
}


def get_user_suppliers(user=None):
	user = user or frappe.session.user
	if not user or user == "Guest":
		return []
	return frappe.get_all("Portal User", filters={"user": user, "parenttype": "Supplier"}, pluck="parent")


def is_supplier_portal_user(user=None):
	user = user or frappe.session.user
	if not user or user in ("Guest", "Administrator"):
		return False
	roles = set(frappe.get_roles(user))
	return SUPPLIER_ROLE in roles and roles.isdisjoint(INTERNAL_ROLES)


def supplier_portal_users(supplier):
	return frappe.get_all("Portal User", filters={"parent": supplier, "parenttype": "Supplier"}, pluck="user")


def _in(suppliers):
	return ", ".join(frappe.db.escape(s) for s in suppliers)


def _query(user, condition_fn):
	user = user or frappe.session.user
	if not is_supplier_portal_user(user):
		return ""
	suppliers = get_user_suppliers(user)
	if not suppliers:
		return "1=0"
	return condition_fn(_in(suppliers))


# ---- permission_query_conditions ------------------------------------------------------
def purchase_order_query(user=None):
	return _query(user, lambda s: f"`tabPurchase Order`.`supplier` in ({s})")


def supplier_quotation_query(user=None):
	return _query(user, lambda s: f"`tabSupplier Quotation`.`supplier` in ({s})")


def purchase_receipt_query(user=None):
	return _query(user, lambda s: f"`tabPurchase Receipt`.`supplier` in ({s})")


def purchase_invoice_query(user=None):
	return _query(user, lambda s: f"`tabPurchase Invoice`.`supplier` in ({s})")


def request_for_quotation_query(user=None):
	return _query(user, lambda s: (
		"`tabRequest for Quotation`.`name` in (select parent from `tabRequest for Quotation Supplier` "
		f"where supplier in ({s}))"
	))


def po_acknowledgement_query(user=None):
	return _query(user, lambda s: f"`tabPO Acknowledgement`.`supplier` in ({s})")


def po_material_status_query(user=None):
	return _query(user, lambda s: f"`tabPO Material Status`.`supplier` in ({s})")


def po_shipment_query(user=None):
	return _query(user, lambda s: f"`tabPO Shipment`.`supplier` in ({s})")


# ---- has_permission -------------------------------------------------------------------
def _belongs(doc, suppliers):
	if doc.doctype == "Request for Quotation":
		return any(r.supplier in suppliers for r in (doc.get("suppliers") or []))
	return doc.get("supplier") in suppliers


def procurement_read_only(doc, ptype=None, user=None, **kwargs):
	"""Own records, read / print only, for supplier-portal users.

	Frappe treats any falsy return as a denial, so internal users get True (standard rules apply).
	"""
	user = user or frappe.session.user
	if not is_supplier_portal_user(user):
		return True
	if ptype not in ("read", "print", "email", None):
		return False
	if isinstance(doc, str):
		return True
	return bool(_belongs(doc, get_user_suppliers(user)))
