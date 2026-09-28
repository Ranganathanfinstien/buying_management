"""UB Supplier install data: roles, Supplier custom fields, the "UB Supplier Approval" workflow and master seeds.

Everything here is idempotent (runs on after_install and every after_migrate via setup/install.py).
"""

import json
import os

import frappe

from universal_buying.ub_supplier.utils import APPROVAL_WORKFLOW, ROUTE_DIRECT, ROUTE_FINANCE, ROUTE_FULL

ROLES = ["Quality Manager", "Finance Manager", "Purchase Master Manager"]

CUSTOM_FIELDS = {
	"Supplier": [
		{
			"fieldname": "ub_approval_route", "label": "Approval Route", "fieldtype": "Select",
			"options": f"\n{ROUTE_FULL}\n{ROUTE_FINANCE}\n{ROUTE_DIRECT}", "insert_after": "supplier_group",
			"read_only": 1, "no_copy": 1, "hidden": 1,
			"description": "Set from the supplier group and Buying Control Settings; decides the approval chain.",
		},
		{
			"fieldname": "ub_incoterm", "label": "Incoterms", "fieldtype": "Link", "options": "Incoterm",
			"insert_after": "payment_terms", "description": "Required before the supplier is sent for approval.",
		},
		{"fieldname": "ub_pan", "label": "PAN", "fieldtype": "Data", "insert_after": "tax_id", "length": 10},
		# --- Buying tab ---
		{"fieldname": "ub_buying_tab", "label": "Buying", "fieldtype": "Tab Break", "insert_after": "customer_numbers"},
		{"fieldname": "ub_buying_section", "label": "Buying Controls", "fieldtype": "Section Break", "insert_after": "ub_buying_tab"},
		{
			"fieldname": "ub_green_card", "label": "Green Card (Trusted Supplier)", "fieldtype": "Check", "default": "0",
			"insert_after": "ub_buying_section", "description": "Receipts from this supplier may skip incoming inspection.",
		},
		{
			"fieldname": "ub_moq_per_line", "label": "MOQ Applies per Line", "fieldtype": "Check", "default": "0",
			"insert_after": "ub_green_card", "description": "Round order quantities up to MOQ instead of SPQ.",
		},
		{"fieldname": "ub_buying_col", "fieldtype": "Column Break", "insert_after": "ub_moq_per_line"},
		{
			"fieldname": "ub_onboarding", "label": "Supplier Onboarding", "fieldtype": "Link",
			"options": "Supplier Onboarding", "insert_after": "ub_buying_col", "read_only": 1, "no_copy": 1,
		},
		{"fieldname": "ub_msme_section", "label": "MSME", "fieldtype": "Section Break", "insert_after": "ub_onboarding"},
		{"fieldname": "ub_msme", "label": "MSME Registered", "fieldtype": "Check", "default": "0", "insert_after": "ub_msme_section"},
		{
			"fieldname": "ub_msme_category", "label": "MSME Category", "fieldtype": "Select",
			"options": "\nMicro\nSmall\nMedium", "insert_after": "ub_msme", "depends_on": "ub_msme",
		},
		{"fieldname": "ub_msme_col", "fieldtype": "Column Break", "insert_after": "ub_msme_category"},
		{
			"fieldname": "ub_msme_certificate", "label": "MSME Certificate", "fieldtype": "Attach",
			"insert_after": "ub_msme_col", "depends_on": "ub_msme",
		},
		{
			"fieldname": "ub_msme_expiry", "label": "MSME Certificate Expiry", "fieldtype": "Date",
			"insert_after": "ub_msme_certificate", "depends_on": "ub_msme",
		},
		{
			"fieldname": "ub_bank_section", "label": "Bank Details", "fieldtype": "Section Break",
			"insert_after": "ub_msme_expiry", "collapsible": 1,
			"description": "Typing the bank details here creates the supplier Bank Account on save.",
		},
		{"fieldname": "ub_bank", "label": "Bank", "fieldtype": "Link", "options": "Bank", "insert_after": "ub_bank_section"},
		{"fieldname": "ub_bank_account_no", "label": "Bank Account No", "fieldtype": "Data", "insert_after": "ub_bank"},
		{"fieldname": "ub_bank_col", "fieldtype": "Column Break", "insert_after": "ub_bank_account_no"},
		{"fieldname": "ub_bank_ifsc", "label": "IFSC / Branch Code", "fieldtype": "Data", "insert_after": "ub_bank_col"},
		{"fieldname": "ub_vault_section", "label": "Document Vault", "fieldtype": "Section Break", "insert_after": "ub_bank_ifsc"},
		{
			"fieldname": "ub_document_vault", "label": "Documents", "fieldtype": "Table",
			"options": "Supplier Document", "insert_after": "ub_vault_section",
		},
	],
}

PROPERTY_SETTERS = []

STATE_STYLE = {
	"Draft": "Danger",
	"Pending Purchase Approval": "Warning",
	"Pending Quality Approval": "Warning",
	"Pending Finance Approval": "Warning",
	"Enabled": "Success",
	"Rejected": "Inverse",
}
ACTIONS = ["Send for Approval", "Approve", "Reject", "Send Back"]

WORKFLOW_STATES = [
	("Draft", ["Purchase User", "Purchase Manager", "Purchase Master Manager", "System Manager"]),
	("Pending Purchase Approval", ["Purchase Manager", "System Manager"]),
	("Pending Quality Approval", ["Quality Manager", "System Manager"]),
	("Pending Finance Approval", ["Finance Manager", "System Manager"]),
	("Enabled", ["Purchase Manager", "Purchase Master Manager", "System Manager"]),
	("Rejected", ["Purchase User", "Purchase Manager", "System Manager"]),
]
# (state, action, next_state, role, condition) - BRD 6.5
WORKFLOW_TRANSITIONS = [
	("Draft", "Send for Approval", "Pending Purchase Approval", "Purchase User", f'doc.ub_approval_route == "{ROUTE_FULL}"'),
	("Draft", "Send for Approval", "Pending Finance Approval", "Purchase User", f'doc.ub_approval_route == "{ROUTE_FINANCE}"'),
	("Draft", "Approve", "Enabled", "Purchase User", f'doc.ub_approval_route not in ("{ROUTE_FULL}", "{ROUTE_FINANCE}")'),
	("Pending Purchase Approval", "Approve", "Pending Quality Approval", "Purchase Manager", None),
	("Pending Purchase Approval", "Reject", "Rejected", "Purchase Manager", None),
	("Pending Quality Approval", "Approve", "Pending Finance Approval", "Quality Manager", None),
	("Pending Quality Approval", "Reject", "Rejected", "Quality Manager", None),
	("Pending Finance Approval", "Approve", "Enabled", "Finance Manager", None),
	("Pending Finance Approval", "Reject", "Rejected", "Finance Manager", None),
	("Rejected", "Send Back", "Draft", "Purchase User", None),
]

GRANDFATHER_MARKER = "ub_supplier_wf_grandfathered"

DOCUMENT_TYPES = [
	("insurance_certificate", "Insurance Certificate", "Insurance", 0, 12, 0, 10),
	("bank_guarantee_lou", "Bank Guarantee / LoU", "Financial", 0, 12, 0, 20),
	("import_export_licence", "Export / Import Licence (IEC)", "Statutory", 0, 0, 0, 30),
	("msme_udyam", "MSME / Udyam Certificate", "Statutory", 0, 0, 0, 40),
	("pan_card", "PAN Card", "Statutory", 1, 0, 0, 50),
	("gst_registration", "GST Registration Certificate", "Statutory", 1, 0, 0, 60),
	("vendor_qualification", "Vendor Qualification Report", "Quality", 1, 0, 0, 70),
	("quality_certifications", "Quality Certifications (ISO / IATF / AS9100)", "Quality", 1, 36, 0, 80),
	("nda_msa", "NDA / MSA", "Legal", 0, 0, 0, 90),
	("customs_boe", "Customs / BOE Documents", "Customs", 0, 0, 0, 100),
	("other", "Other (Free Upload)", "Other", 0, 0, 1, 110),
]


def setup():
	make_workflow_masters()
	make_workflow()
	ensure_workflow_permissions()
	expose_workflow_state_field()
	grandfather_existing_suppliers()
	seed_document_types()
	seed_question_bank()
	seed_audit_checklist()


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------


def make_workflow_masters():
	for state, style in STATE_STYLE.items():
		if not frappe.db.exists("Workflow State", state):
			frappe.get_doc({"doctype": "Workflow State", "workflow_state_name": state, "style": style}).insert(ignore_permissions=True)
	for action in ACTIONS:
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": action}).insert(ignore_permissions=True)


def make_workflow():
	"""Create the workflow once. An existing one is left untouched so site changes survive migrate."""
	if frappe.db.exists("Workflow", APPROVAL_WORKFLOW):
		return
	for role in {r for _s, roles in WORKFLOW_STATES for r in roles}:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)
	wf = frappe.new_doc("Workflow")
	wf.workflow_name = APPROVAL_WORKFLOW
	wf.document_type = "Supplier"
	wf.workflow_state_field = "workflow_state"
	wf.is_active = 1
	wf.override_status = 0
	wf.send_email_alert = 0
	for state, roles in WORKFLOW_STATES:
		for role in roles:
			wf.append("states", {"state": state, "doc_status": "0", "allow_edit": role})
	for state, action, next_state, role, condition in WORKFLOW_TRANSITIONS:
		wf.append("transitions", {
			"state": state, "action": action, "next_state": next_state, "allowed": role,
			"allow_self_approval": 1, "condition": condition,
		})
	wf.insert(ignore_permissions=True)


def ensure_workflow_permissions():
	"""Every role that acts on the workflow needs read + write on Supplier (apply_workflow saves the
	document). Standard ERPNext gives Purchase User, Quality Manager and Finance Manager no write right,
	so the shipped chain could not be executed. Only missing rights are added (Custom DocPerm)."""
	from frappe.permissions import add_permission, update_permission_property

	if not frappe.db.exists("Workflow", APPROVAL_WORKFLOW):
		return
	roles = set(frappe.get_all("Workflow Transition", filters={"parent": APPROVAL_WORKFLOW}, pluck="allowed"))
	changed = False
	for role in sorted(r for r in roles if r and frappe.db.exists("Role", r)):
		table = "Custom DocPerm" if frappe.db.exists("Custom DocPerm", {"parent": "Supplier"}) else "DocPerm"
		row = frappe.db.get_value(table, {"parent": "Supplier", "role": role, "permlevel": 0, "if_owner": 0},
			["read", "write"], as_dict=True)
		if row and row.read and row.write:
			continue
		if not frappe.db.get_value("Custom DocPerm", {"parent": "Supplier", "role": role, "permlevel": 0, "if_owner": 0}):
			add_permission("Supplier", role, 0, "read")
		for ptype in ("read", "write"):
			update_permission_property("Supplier", role, 0, ptype, 1, validate=False)
		changed = True
	if changed:
		frappe.clear_cache(doctype="Supplier")


def expose_workflow_state_field():
	"""Frappe creates Supplier.workflow_state hidden; show it read-only as the approval status."""
	name = frappe.db.get_value("Custom Field", {"dt": "Supplier", "fieldname": "workflow_state"}, "name")
	if not name or not frappe.db.get_value("Custom Field", name, "hidden"):
		return
	frappe.db.set_value("Custom Field", name, {
		"hidden": 0, "read_only": 1, "label": "Approval Status", "in_standard_filter": 1,
		"in_list_view": 1, "insert_after": "supplier_name",
	})
	frappe.clear_cache(doctype="Supplier")


def grandfather_existing_suppliers():
	"""AC-5.1: suppliers that existed before the workflow are set to Enabled, once."""
	if frappe.db.get_default(GRANDFATHER_MARKER):
		return
	if not frappe.db.exists("Workflow", APPROVAL_WORKFLOW) or not frappe.db.has_column("Supplier", "workflow_state"):
		return
	cutoff = frappe.db.get_value("Workflow", APPROVAL_WORKFLOW, "creation")
	frappe.db.sql(
		"""update `tabSupplier` set workflow_state = 'Enabled'
		where ifnull(workflow_state, '') in ('', 'Draft') and creation <= %s""",
		cutoff,
	)
	if frappe.db.has_column("Supplier", "ub_approval_route"):
		from universal_buying.ub_supplier.supplier import recompute_approval_routes

		recompute_approval_routes()
	frappe.db.set_default(GRANDFATHER_MARKER, "1")


# ---------------------------------------------------------------------------
# Master seeds
# ---------------------------------------------------------------------------


def _data(fname):
	path = os.path.join(os.path.dirname(__file__), "data", fname)
	with open(path, encoding="utf-8") as f:
		return json.load(f)


def seed_document_types():
	if not frappe.db.exists("DocType", "Supplier Document Type"):
		return
	for key, label, category, required, renewal, custom_label, order in DOCUMENT_TYPES:
		if frappe.db.exists("Supplier Document Type", key):
			continue
		frappe.get_doc({
			"doctype": "Supplier Document Type", "document_key": key, "label": label, "category": category,
			"is_required": required, "renewal_months": renewal, "allow_custom_label": custom_label,
			"is_active": 1, "sort_order": order,
		}).insert(ignore_permissions=True)


def seed_question_bank():
	"""Insert the default bank when missing, refill it when empty; never overwrite site edits."""
	if not frappe.db.exists("DocType", "Supplier Onboarding Question Bank"):
		return
	data = _data("question_bank.json")
	name = data["question_bank_name"]
	if frappe.db.exists("Supplier Onboarding Question Bank", name):
		doc = frappe.get_doc("Supplier Onboarding Question Bank", name)
		if doc.questions:
			return
		doc.extend("questions", data["questions"])
		doc.save(ignore_permissions=True)
		return
	if frappe.db.count("Supplier Onboarding Question Bank"):
		return
	frappe.get_doc(dict(data, doctype="Supplier Onboarding Question Bank")).insert(ignore_permissions=True)


def seed_audit_checklist():
	if not frappe.db.exists("DocType", "Supplier Audit Checklist") or frappe.db.count("Supplier Audit Checklist"):
		return
	data = _data("audit_checklist.json")
	frappe.get_doc(dict(data, doctype="Supplier Audit Checklist")).insert(ignore_permissions=True)
