"""Core install: shared roles, default PO Types and default Buying Control Settings values."""

import frappe

ROLES = [
	# approvers used by the default RFQ tiers and PO approval bands (BRD v2 section 8)
	"Department Head",
	"SCM Head",
	"Head of Operations",
	"CEO",
	"Purchase Executive",
	"Purchase Senior Manager",
	"Purchase HOD",
	"President SCM",
	"Managing Director",
	"Sourcing User",
	"Sourcing Manager",
	"Finance Manager",
]

CUSTOM_FIELDS = {}

DEFAULT_PO_TYPES = [
	{"po_type_name": "3-Way", "is_default": 1, "receipt_required": 1, "po_required_on_invoice": 1, "item_required": 1,
	 "invoice_tolerance_percent": 0, "description": "Stock items. Purchase Receipt required before invoice."},
	{"po_type_name": "2-Way", "is_default": 0, "receipt_required": 0, "po_required_on_invoice": 1, "item_required": 1,
	 "invoice_tolerance_percent": 0, "description": "Services and non-stock items. Invoice against PO without receipt."},
]

DEFAULT_RFQ_TIERS = [
	("Department Head", "Pending Dept Head Approval"),
	("SCM Head", "Pending SCM Head Approval"),
	("Head of Operations", "Pending Operations Head Approval"),
	("CEO", "Pending Final Approval"),
]

# Default value bands (base currency). Each band lists its approvers in step order.
DEFAULT_PO_BANDS = [
	(0, 500000, ["Purchase Executive"]),
	(500000, 10000000, ["Purchase Executive", "Purchase Senior Manager"]),
	(10000000, 20000000, ["Purchase Executive", "Purchase Senior Manager", "Purchase HOD"]),
	(20000000, 50000000, ["Purchase Executive", "Purchase Senior Manager", "Purchase HOD", "President SCM"]),
	(50000000, 0, ["Purchase Executive", "Purchase Senior Manager", "Purchase HOD", "President SCM", "Managing Director"]),
]


# (settings field, link key, default values, link doctype) - seeded once per field, as soon as the
# linked masters exist (Supplier / Item Groups are often created by the setup wizard after install).
DEFAULT_LIST_SEEDS = [
	("consumable_item_groups", "item_group", ["Consumable"], "Item Group"),
	("price_request_roles", "role", ["Sourcing User", "Sourcing Manager", "Purchase User", "Purchase Manager"], "Role"),
	("consumables_only_roles", "role", ["Stock User"], "Role"),
	("indent_approver_roles", "role", ["Purchase Manager"], "Role"),
	("approval_full_chain_groups", "supplier_group", ["Raw Material"], "Supplier Group"),
	("approval_finance_only_groups", "supplier_group", ["Services"], "Supplier Group"),
	("audit_required_groups", "supplier_group", ["Custom Built"], "Supplier Group"),
]
LIST_SEED_MARKER = "ub_settings_lists_seeded"


def setup():
	for row in DEFAULT_PO_TYPES:
		if not frappe.db.exists("PO Type", row["po_type_name"]):
			frappe.get_doc({"doctype": "PO Type", **row}).insert(ignore_permissions=True)

	settings = frappe.get_single("Buying Control Settings")
	changed = seed_list_defaults(settings)
	if not (settings.get("__ub_seeded") or frappe.db.get_default("ub_settings_seeded")):
		seed_defaults(settings)
		changed = True
		frappe.db.set_default("ub_settings_seeded", 1)
	if changed:
		settings.flags.ignore_permissions = True
		settings.flags.ignore_mandatory = True
		settings.save()
	disable_auto_item_price()


def disable_auto_item_price():
	"""BR-05 / BR-14: buying rates come from Item Price Request only. ERPNext's default "Auto insert Price
	List rate if missing" turns every PO / Supplier Quotation rate into a supplier-less buying Item Price,
	which then feeds Auto PO and Strict price control. Switched off once; an admin may turn it back on."""
	if frappe.db.get_default("ub_auto_item_price_disabled"):
		return
	frappe.db.set_single_value("Stock Settings", "auto_insert_price_list_rate_if_missing", 0)
	frappe.db.set_default("ub_auto_item_price_disabled", 1)


def seed_list_defaults(settings):
	"""Fill each default list once; a list whose masters do not exist yet is retried on the next migrate."""
	done = {f for f in (frappe.db.get_default(LIST_SEED_MARKER) or "").split(",") if f}
	changed = False
	for fieldname, key, values, doctype in DEFAULT_LIST_SEEDS:
		if fieldname in done:
			continue
		present = [v for v in values if frappe.db.exists(doctype, v)]
		if not present:
			continue
		existing = {r.get(key) for r in settings.get(fieldname) or []}
		for v in present:
			if v not in existing:
				settings.append(fieldname, {key: v})
				changed = True
		done.add(fieldname)
	frappe.db.set_default(LIST_SEED_MARKER, ",".join(sorted(done)))
	return changed


def seed_defaults(settings):
	meta = frappe.get_meta("Buying Control Settings")
	for df in meta.fields:
		if df.default and df.fieldtype not in ("Table", "Table MultiSelect") and settings.get(df.fieldname) in (None, ""):
			settings.set(df.fieldname, df.default)

	if not settings.rfq_approval_tiers:
		for role, state in DEFAULT_RFQ_TIERS:
			settings.append("rfq_approval_tiers", {"role": role, "state_name": state})
	if not settings.award_role:
		settings.award_role = "CEO"
	if not settings.po_approval_rules:
		for lo, hi, roles in DEFAULT_PO_BANDS:
			for step, role in enumerate(roles, 1):
				settings.append("po_approval_rules", {"from_amount": lo, "to_amount": hi, "step": step, "approver_role": role})
