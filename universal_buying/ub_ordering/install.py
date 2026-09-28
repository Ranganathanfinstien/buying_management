"""UB Ordering install data: Purchase Order custom fields, property setters and the PO Amendment workflow.

Merged by ``universal_buying.setup.install``. Every custom fieldname starts with ``ub_``.
"""

import frappe

ROLES = []

_PO = "Purchase Order"
_POI = "Purchase Order Item"

CUSTOM_FIELDS = {
	_PO: [
		# ---- header (BRD 6.17) ----
		{"fieldname": "ub_po_type", "label": "PO Type", "fieldtype": "Link", "options": "PO Type",
		 "insert_after": "company", "in_standard_filter": 1, "allow_on_submit": 0,
		 "description": "Blank = default PO Type (set on save)."},
		{"fieldname": "ub_is_import", "label": "Import", "fieldtype": "Check", "insert_after": "ub_po_type",
		 "read_only": 1, "description": "Set from the supplier address country. Imports carry no GST template."},

		# ---- Buying Control tab ----
		{"fieldname": "ub_control_tab", "label": "Buying Control", "fieldtype": "Tab Break", "insert_after": "terms"},
		{"fieldname": "ub_origin_section", "label": "Origin and Approval", "fieldtype": "Section Break",
		 "insert_after": "ub_control_tab"},
		{"fieldname": "ub_origin_doctype", "label": "Origin", "fieldtype": "Link", "options": "DocType",
		 "insert_after": "ub_origin_section", "read_only": 1, "no_copy": 1, "in_standard_filter": 1},
		{"fieldname": "ub_origin_name", "label": "Origin Document", "fieldtype": "Dynamic Link",
		 "options": "ub_origin_doctype", "insert_after": "ub_origin_doctype", "read_only": 1, "no_copy": 1},
		{"fieldname": "ub_origin_col", "fieldtype": "Column Break", "insert_after": "ub_origin_name"},
		{"fieldname": "ub_approval_status", "label": "Approval Status", "fieldtype": "Select",
		 "options": "Draft\nPending\nApproved\nRejected", "default": "Draft", "insert_after": "ub_origin_col",
		 "read_only": 1, "no_copy": 1, "in_standard_filter": 1, "in_list_view": 0, "search_index": 1},
		{"fieldname": "ub_approval_step", "label": "Current Approval Step", "fieldtype": "Int",
		 "insert_after": "ub_approval_status", "read_only": 1, "no_copy": 1},
		{"fieldname": "ub_approval_roles", "label": "Pending With (Roles)", "fieldtype": "Small Text",
		 "insert_after": "ub_approval_step", "read_only": 1, "no_copy": 1},
		{"fieldname": "ub_approval_history_section", "label": "Approval History", "fieldtype": "Section Break",
		 "insert_after": "ub_approval_roles", "collapsible": 1},
		{"fieldname": "ub_approval_history", "label": "Approval History", "fieldtype": "Table",
		 "options": "UB PO Approval Log", "insert_after": "ub_approval_history_section", "read_only": 1,
		 "no_copy": 1, "allow_on_submit": 1},

		# ---- supplier portal (BRD 6.21) ----
		{"fieldname": "ub_portal_section", "label": "Supplier Portal", "fieldtype": "Section Break",
		 "insert_after": "ub_approval_history"},
		{"fieldname": "ub_portal_status", "label": "Portal Status", "fieldtype": "Select",
		 "options": "\nPending Acceptance\nAccepted\nPartially Dispatched\nDispatched", "insert_after": "ub_portal_section",
		 "read_only": 1, "no_copy": 1, "allow_on_submit": 1, "in_standard_filter": 1},
		{"fieldname": "ub_confirmed_delivery_date", "label": "Confirmed Delivery Date", "fieldtype": "Date",
		 "insert_after": "ub_portal_status", "read_only": 1, "no_copy": 1, "allow_on_submit": 1},
		{"fieldname": "ub_portal_col", "fieldtype": "Column Break", "insert_after": "ub_confirmed_delivery_date"},
		{"fieldname": "ub_material_status", "label": "Material Status", "fieldtype": "Select",
		 "options": "\nIn Production\nPartial\nReady to Dispatch\nDispatched\nDelayed", "insert_after": "ub_portal_col",
		 "read_only": 1, "no_copy": 1, "allow_on_submit": 1},
		{"fieldname": "ub_expected_dispatch_date", "label": "Expected Dispatch Date", "fieldtype": "Date",
		 "insert_after": "ub_material_status", "read_only": 1, "no_copy": 1, "allow_on_submit": 1},
		{"fieldname": "ub_uploads_section", "label": "Supplier Uploads", "fieldtype": "Section Break",
		 "insert_after": "ub_expected_dispatch_date", "collapsible": 1},
		{"fieldname": "ub_invoice_uploads", "label": "Supplier Invoices", "fieldtype": "Table",
		 "options": "Portal PO Invoice", "insert_after": "ub_uploads_section", "no_copy": 1, "allow_on_submit": 1},
		{"fieldname": "ub_qc_attachments", "label": "QC Attachments", "fieldtype": "Table",
		 "options": "Portal PO QC Attachment", "insert_after": "ub_invoice_uploads", "no_copy": 1, "allow_on_submit": 1},

		# ---- integration channel (BRD 6.19) ----
		{"fieldname": "ub_integration_section", "label": "Supplier Confirmation", "fieldtype": "Section Break",
		 "insert_after": "ub_qc_attachments", "collapsible": 1},
		{"fieldname": "ub_channel", "label": "Supplier Channel", "fieldtype": "Link", "options": "Supplier Channel",
		 "insert_after": "ub_integration_section", "no_copy": 1, "allow_on_submit": 1},
		{"fieldname": "ub_channel_status", "label": "Channel Status", "fieldtype": "Data",
		 "insert_after": "ub_channel", "read_only": 1, "no_copy": 1, "allow_on_submit": 1},
		{"fieldname": "ub_channel_reference", "label": "Supplier Order No", "fieldtype": "Data",
		 "insert_after": "ub_channel_status", "read_only": 1, "no_copy": 1, "allow_on_submit": 1},
		{"fieldname": "ub_confirmations", "label": "PO Confirmation", "fieldtype": "Table", "options": "PO Confirmation",
		 "insert_after": "ub_channel_reference", "read_only": 1, "no_copy": 1, "allow_on_submit": 1},
	],
	_POI: [
		{"fieldname": "ub_required_by", "label": "Required By (Demand)", "fieldtype": "Date",
		 "insert_after": "schedule_date", "description": "Date the demand needs the material (from planning)."},
		{"fieldname": "ub_supplier_delivery_date", "label": "Supplier Delivery Date", "fieldtype": "Date",
		 "insert_after": "expected_delivery_date", "allow_on_submit": 1},
		{"fieldname": "ub_skip_moq", "label": "Skip MOQ", "fieldtype": "Check", "insert_after": "ub_required_by",
		 "read_only": 1, "description": "Set only by Auto PO Exception."},
		{"fieldname": "ub_compliance_section", "label": "Compliance", "fieldtype": "Section Break",
		 "insert_after": "manufacturer_part_no", "collapsible": 1},
		{"fieldname": "ub_revision_no", "label": "Revision No", "fieldtype": "Data",
		 "insert_after": "ub_compliance_section", "fetch_from": "item_code.ub_revision_no", "read_only": 1},
		{"fieldname": "ub_ppap_level", "label": "PPAP Level", "fieldtype": "Select", "options": "\nL1\nL2\nL3\nL4\nL5",
		 "insert_after": "ub_revision_no", "fetch_from": "item_code.ub_ppap_level", "read_only": 1},
		{"fieldname": "ub_test_certificate_required", "label": "Test Certificate Required", "fieldtype": "Check",
		 "insert_after": "ub_ppap_level", "fetch_from": "item_code.ub_test_certificate_required", "read_only": 1},
		{"fieldname": "ub_compliance_col", "fieldtype": "Column Break", "insert_after": "ub_test_certificate_required"},
		{"fieldname": "ub_coc_required", "label": "CoC Required", "fieldtype": "Check",
		 "insert_after": "ub_compliance_col", "fetch_from": "item_code.ub_coc_required", "read_only": 1},
		{"fieldname": "ub_fai_required", "label": "FAI Required", "fieldtype": "Check",
		 "insert_after": "ub_coc_required", "fetch_from": "item_code.ub_fai_required", "read_only": 1},
		{"fieldname": "ub_rohs", "label": "RoHS", "fieldtype": "Check",
		 "insert_after": "ub_fai_required", "fetch_from": "item_code.ub_rohs", "read_only": 1},
		{"fieldname": "ub_reach", "label": "REACH", "fieldtype": "Check",
		 "insert_after": "ub_rohs", "fetch_from": "item_code.ub_reach", "read_only": 1},
	],
}

PROPERTY_SETTERS = [
	# Lines without an item code are allowed when the PO Type says item_required = 0
	# (services / 2-Way). The rule is enforced in CustomPurchaseOrder.validate_line_items().
	{"doctype": _POI, "fieldname": "item_code", "property": "reqd", "value": "0", "property_type": "Check"},
]

AMENDMENT_WORKFLOW = "UB PO Amendment"
AMENDMENT_STATES = [
	# state, docstatus, allow_edit
	("Draft", "0", "Purchase User"),
	("Pending Approval", "0", "Purchase Manager"),
	("Approved", "1", "Purchase Manager"),
	("Rejected", "0", "Purchase Manager"),
]
AMENDMENT_TRANSITIONS = [
	# state, action, next_state, allowed role
	("Draft", "Submit for Approval", "Pending Approval", "Purchase User"),
	("Draft", "Submit for Approval", "Pending Approval", "Purchase Manager"),
	("Pending Approval", "Approve", "Approved", "Purchase Manager"),
	("Pending Approval", "Reject", "Rejected", "Purchase Manager"),
	("Rejected", "Revise", "Draft", "Purchase User"),
	("Rejected", "Revise", "Draft", "Purchase Manager"),
]
_STATE_STYLE = {"Draft": "", "Pending Approval": "Warning", "Approved": "Success", "Rejected": "Danger"}


def setup():
	_ensure_amendment_workflow()


def _ensure_amendment_workflow():
	if not frappe.db.exists("DocType", "PO Amendment"):
		return
	for state, _ds, _role in AMENDMENT_STATES:
		if not frappe.db.exists("Workflow State", state):
			frappe.get_doc({"doctype": "Workflow State", "workflow_state_name": state,
				"style": _STATE_STYLE.get(state, "")}).insert(ignore_permissions=True)
	for action in {t[1] for t in AMENDMENT_TRANSITIONS}:
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": action}).insert(
				ignore_permissions=True)
	if frappe.db.exists("Workflow", AMENDMENT_WORKFLOW):
		return
	roles_ok = all(frappe.db.exists("Role", r) for r in ("Purchase User", "Purchase Manager"))
	if not roles_ok:
		return
	wf = frappe.get_doc({
		"doctype": "Workflow",
		"workflow_name": AMENDMENT_WORKFLOW,
		"document_type": "PO Amendment",
		"workflow_state_field": "workflow_state",
		"is_active": 1,
		"send_email_alert": 0,
		"states": [{"state": s, "doc_status": ds, "allow_edit": role} for s, ds, role in AMENDMENT_STATES],
		"transitions": [{"state": s, "action": a, "next_state": n, "allowed": r, "allow_self_approval": 1}
			for s, a, n, r in AMENDMENT_TRANSITIONS],
	})
	wf.insert(ignore_permissions=True)
