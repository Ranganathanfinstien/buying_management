"""Supplier doc events (BRD 6.5). Registered through ub_supplier/hooks_contrib.py.

- ub_approval_route (Full / Finance / Direct) drives the "UB Supplier Approval" workflow conditions;
  it is recomputed on every save and whenever Buying Control Settings change.
- V-5.3: an active Bank Account is required before a supplier leaves Draft (setting require_bank_account).
  Bank details typed on the Supplier (ub_bank, ub_bank_account_no, ub_bank_ifsc) become a party
  Bank Account after save, so the rule never deadlocks a new supplier.
- PAN / GSTIN format and duplicate checks (GSTIN in the standard tax_id field).
- Document vault row status sync.
"""

import frappe
from frappe import _
from frappe.utils import cint

from universal_buying.ub_supplier.utils import (
	add_pan_comment,
	check_duplicate_gstin,
	check_duplicate_pan,
	clean_code,
	create_supplier_bank_account,
	get_approval_route,
	has_active_bank_account,
	validate_pan,
)
from universal_buying.universal_buying.settings import get_setting

DRAFT = "Draft"
REJECTED = "Rejected"


def validate(doc, method=None):
	doc.ub_approval_route = get_approval_route(doc.supplier_group)
	validate_identity(doc)
	validate_bank_before_approval(doc)
	from universal_buying.ub_supplier.api import sync_vault_rows

	sync_vault_rows(doc)
	if cint(doc.get("ub_msme")) == 0:
		for field in ("ub_msme_category", "ub_msme_certificate", "ub_msme_expiry"):
			if doc.meta.has_field(field):
				doc.set(field, None)


def validate_identity(doc):
	pan_field = "pan" if doc.meta.has_field("pan") else "ub_pan"
	if doc.meta.has_field(pan_field) and doc.get(pan_field):
		doc.set(pan_field, validate_pan(doc.get(pan_field)))
		check_duplicate_pan(doc, doc.get(pan_field))

	gstin = clean_code(doc.get("gstin") if doc.meta.has_field("gstin") else None) or clean_code(doc.tax_id)
	# tax_id may hold a foreign tax number: only GSTIN-shaped values are checked
	if len(gstin) == 15 and gstin[:2].isdigit():
		pan = clean_code(doc.get(pan_field)) if doc.meta.has_field(pan_field) else ""
		if pan and gstin[2:12] != pan:
			frappe.throw(_("GSTIN does not match PAN"), title=_("GSTIN / PAN Mismatch"))
		check_duplicate_gstin(doc, gstin)


def _bank_details_typed(doc):
	return bool(doc.get("ub_bank") and (doc.get("ub_bank_account_no") or "").strip())


def validate_bank_before_approval(doc):
	"""V-5.3 (bank account) and BRD 6.5 Incoterms*: checked when the supplier leaves Draft."""
	if not doc.meta.has_field("workflow_state"):
		return
	before = doc.get_doc_before_save()
	if not before:
		return
	old_state, new_state = before.get("workflow_state") or DRAFT, doc.get("workflow_state") or DRAFT
	if old_state != DRAFT or new_state in (DRAFT, REJECTED):
		return
	incoterm_field = "incoterm" if doc.meta.has_field("incoterm") else "ub_incoterm"
	if doc.meta.has_field(incoterm_field) and not doc.get(incoterm_field):
		frappe.throw(_("Set the Incoterms of supplier {0} before sending it for approval.").format(frappe.bold(doc.name)), title=_("Incoterms Required"))
	if not cint(get_setting("require_bank_account")):
		return
	if has_active_bank_account(doc.name) or _bank_details_typed(doc):
		return
	frappe.throw(
		_("Supplier {0} needs an active Bank Account before it can be sent for approval.").format(frappe.bold(doc.name)),
		title=_("Bank Account Required"),
	)


def after_insert(doc, method=None):
	add_pan_comment(doc)
	create_bank_account_from_fields(doc)


def on_update(doc, method=None):
	if not doc.flags.in_insert:
		create_bank_account_from_fields(doc)


def create_bank_account_from_fields(doc):
	if not _bank_details_typed(doc):
		return
	account_no = doc.ub_bank_account_no.strip()
	if frappe.db.exists("Bank Account", {"party_type": "Supplier", "party": doc.name, "bank_account_no": account_no}):
		return
	create_supplier_bank_account(
		doc.name, doc.ub_bank, account_no=account_no, branch_code=(doc.get("ub_bank_ifsc") or "").strip().upper() or None,
		is_default=0 if has_active_bank_account(doc.name) else 1,
	)


def recompute_approval_routes(settings=None):
	"""UB_ON_SETTINGS_UPDATE: suppliers not yet approved follow the new group lists."""
	if not frappe.get_meta("Supplier").has_field("ub_approval_route"):
		return
	filters = {}
	if frappe.get_meta("Supplier").has_field("workflow_state"):
		filters = {"workflow_state": ("in", ["", DRAFT, REJECTED])}
	cache = {}
	for row in frappe.get_all("Supplier", filters=filters, fields=["name", "supplier_group", "ub_approval_route"]):
		if row.supplier_group not in cache:
			cache[row.supplier_group] = get_approval_route(row.supplier_group)
		route = cache[row.supplier_group]
		if route != row.ub_approval_route:
			frappe.db.set_value("Supplier", row.name, "ub_approval_route", route, update_modified=False)
	# empty workflow_state (never saved since the workflow was installed)
	if filters:
		for row in frappe.get_all("Supplier", filters={"workflow_state": ("is", "not set")}, fields=["name", "supplier_group", "ub_approval_route"]):
			route = cache.get(row.supplier_group) or get_approval_route(row.supplier_group)
			if route != row.ub_approval_route:
				frappe.db.set_value("Supplier", row.name, "ub_approval_route", route, update_modified=False)
