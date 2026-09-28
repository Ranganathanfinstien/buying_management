"""Whitelisted endpoints for the Jinja supplier portal (/supplier_portal/*).

Call as ``universal_buying.www.supplier_portal_api.<method>``. Every method resolves the supplier
from the session; nothing trusts a supplier id sent by the browser without checking it.
"""

import frappe
from frappe import _

# PO actions (BRD 6.21) - implemented in ub_ordering.portal, re-exported here for the portal pages
from universal_buying.ub_ordering.portal import (  # noqa: F401
	acknowledge_po,
	add_qc_attachment,
	create_shipment,
	get_po_lines_for_shipment,
	update_material_status,
	upload_invoice,
)
from universal_buying.ub_ordering.permissions import get_user_suppliers


def _assert_supplier(supplier):
	if not supplier or supplier not in get_user_suppliers():
		frappe.throw(_("You do not have access to this supplier."), frappe.PermissionError)
	return supplier


@frappe.whitelist()
def get_rfq_quote_link(rfq):
	"""Link to the RFQ quoting page (/rfq-portal?token=) for the logged-in supplier."""
	from universal_buying.ub_sourcing.api import get_or_create_rfq_token

	for supplier in get_user_suppliers():
		if frappe.db.exists("Request for Quotation Supplier", {"parent": rfq, "parenttype": "Request for Quotation",
				"supplier": supplier}):
			return "/rfq-portal?token=" + get_or_create_rfq_token(rfq, supplier)
	frappe.throw(_("You are not invited on this Request for Quotation."), frappe.PermissionError)


@frappe.whitelist()
def submit_profile_change(supplier, changes):
	from universal_buying.ub_supplier.api import submit_profile_change_request

	_assert_supplier(supplier)
	return submit_profile_change_request(supplier, changes=changes)


@frappe.whitelist()
def vault_upload(supplier, doc_key, file_url, expires_on=None, custom_label=None, row_name=None):
	from universal_buying.ub_supplier.api import upload_vault_document

	_assert_supplier(supplier)
	return upload_vault_document(supplier, doc_key, file_url, expires_on=expires_on or None,
		custom_label=custom_label or None, row_name=row_name or None)


@frappe.whitelist()
def vault_delete(supplier, doc_key, row_name=None):
	from universal_buying.ub_supplier.api import delete_vault_document

	_assert_supplier(supplier)
	return delete_vault_document(supplier, doc_key, row_name=row_name or None)
