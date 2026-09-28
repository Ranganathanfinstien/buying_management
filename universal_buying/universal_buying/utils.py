"""Helpers shared by every module. Keep this file free of module-specific logic."""

from contextlib import contextmanager

import frappe
from frappe import _
from frappe.model.naming import make_autoname

from universal_buying.universal_buying.settings import apply_mode, get_setting

# Purchase Order origin (BRD v2 design rule 3). Fields are created by ub_ordering/install.py.
ORIGIN_DOCTYPE_FIELD = "ub_origin_doctype"
ORIGIN_NAME_FIELD = "ub_origin_name"
ORIGINS = ("Auto PO Run", "Auto PO Exception", "Supplier Quotation", "Material Request", "Manual")

SUPPLIER_ENABLED_STATE = "Enabled"


def set_po_origin(po, origin_doctype, origin_name=None):
	"""Stamp where a Purchase Order came from. Call before insert."""
	po.set(ORIGIN_DOCTYPE_FIELD, origin_doctype)
	po.set(ORIGIN_NAME_FIELD, origin_name)


def get_po_origin(po):
	return po.get(ORIGIN_DOCTYPE_FIELD) or "Manual"


def supplier_is_enabled(supplier):
	if not supplier or not frappe.db.exists("Supplier", supplier):
		return False
	if frappe.db.get_value("Supplier", supplier, "disabled"):
		return False
	if not frappe.get_meta("Supplier").has_field("workflow_state"):
		return True
	state = frappe.db.get_value("Supplier", supplier, "workflow_state")
	return (not state) or state == SUPPLIER_ENABLED_STATE


def assert_supplier_enabled(supplier, context=None):
	"""V-5.1 / V-5.2: RFQ and PO only to Enabled suppliers (mode from settings)."""
	if supplier_is_enabled(supplier):
		return
	apply_mode(
		get_setting("block_unapproved_supplier"),
		_("Supplier {0} is not approved (status must be {1}){2}.").format(
			frappe.bold(supplier), SUPPLIER_ENABLED_STATE, f" - {context}" if context else ""
		),
		title=_("Supplier Not Approved"),
	)


def autoname_with_company(pattern, company):
	"""Expand {abbr} in a naming pattern and return the next name."""
	abbr = frappe.get_cached_value("Company", company, "abbr") if company else ""
	return make_autoname(pattern.replace("{abbr}", abbr or "X"))


def notify_users(users, subject, message, reference_doctype=None, reference_name=None):
	"""Email + desk notification to a list of users (silently skips users without email)."""
	users = [u for u in dict.fromkeys(users or []) if u and u not in ("Administrator", "Guest")]
	if not users:
		return
	emails = [e for e in (frappe.db.get_value("User", u, "email") for u in users) if e]
	if emails:
		frappe.sendmail(recipients=emails, subject=subject, message=message,
			reference_doctype=reference_doctype, reference_name=reference_name, now=False)
	for u in users:
		frappe.get_doc({
			"doctype": "Notification Log", "for_user": u, "type": "Alert", "subject": subject,
			"email_content": message, "document_type": reference_doctype, "document_name": reference_name,
		}).insert(ignore_permissions=True)


def users_with_role(role):
	return [r.parent for r in frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, fields=["parent"])
		if frappe.db.get_value("User", r.parent, "enabled")]


@contextmanager
def as_system_user():
	"""Run a system side effect as Administrator after the caller has authorised the user.

	ERPNext v16 checks the session user's own rights deep inside validate (Item read in get_item_details,
	Account read in get_party_account) even when the document has ignore_permissions. Portal users and
	inspectors never hold those rights, so only the side-effect save runs elevated; the session user is
	restored afterwards (owner / modified_by of that save become Administrator).
	"""
	user = frappe.session.user
	frappe.session.user = "Administrator"
	try:
		yield
	finally:
		frappe.session.user = user
