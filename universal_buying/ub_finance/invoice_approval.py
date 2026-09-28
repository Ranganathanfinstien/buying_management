"""Optional Purchase Invoice approval (BRD v2 A-27.2).

When Buying Control Settings ``invoice_approval_enabled`` is on, the workflow
"UB Purchase Invoice Approval" is created (or re-activated):

	Draft --Send for Approval (maker)--> Pending Approval --Approve (approver)--> Approved (submitted)
	                                                    \\--Reject (approver)--> Rejected --Send for Approval--> Pending Approval
	Approved --Cancel (approver)--> Cancelled

When the setting is switched off the workflow is de-activated (not deleted, so the
state history on existing invoices stays readable).

Roles default to Accounts User (maker) / Accounts Manager (approver) and can be
changed with the optional settings ``invoice_maker_role`` / ``invoice_approver_role``.

Notifications (on_change): Pending Approval -> every approver; Approved / Rejected -> invoice owner.
Based on the earlier purchase_invoice_workflow_mail.py with the state names fixed to
match this workflow (the source mailed on Director / CFO / CEO states that do not exist here).
"""

import frappe
from frappe import _

from universal_buying.universal_buying.settings import get_setting
from universal_buying.universal_buying.utils import notify_users, users_with_role

WORKFLOW_NAME = "UB Purchase Invoice Approval"
DOCTYPE = "Purchase Invoice"

STATE_DRAFT = "Draft"
STATE_PENDING = "Pending Approval"
STATE_APPROVED = "Approved"
STATE_REJECTED = "Rejected"
STATE_CANCELLED = "Cancelled"

ACTION_SEND = "Send for Approval"
ACTION_APPROVE = "Approve"
ACTION_REJECT = "Reject"
ACTION_CANCEL = "Cancel"

_STATE_STYLE = {
	STATE_DRAFT: "",
	STATE_PENDING: "Warning",
	STATE_APPROVED: "Success",
	STATE_REJECTED: "Danger",
	STATE_CANCELLED: "Inverse",
}


def _roles():
	maker = get_setting("invoice_maker_role", default="Accounts User") or "Accounts User"
	approver = get_setting("invoice_approver_role", default="Accounts Manager") or "Accounts Manager"
	return maker, approver


def is_enabled():
	return bool(get_setting("invoice_approval_enabled", default=0))


def sync_invoice_approval_workflow(settings=None):
	"""Create / update / de-activate the workflow to match the setting. Idempotent.

	Registered in UB_ON_SETTINGS_UPDATE and called from install.setup()."""
	if not frappe.db.exists("DocType", "Buying Control Settings"):
		return
	enabled = bool(settings.get("invoice_approval_enabled")) if settings is not None else is_enabled()

	exists = frappe.db.exists("Workflow", WORKFLOW_NAME)
	if not enabled:
		if exists and frappe.db.get_value("Workflow", WORKFLOW_NAME, "is_active"):
			frappe.db.set_value("Workflow", WORKFLOW_NAME, "is_active", 0)
			frappe.clear_cache(doctype=DOCTYPE)
		return

	maker, approver = _roles()
	for role in (maker, approver):
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)

	for state, style in _STATE_STYLE.items():
		if not frappe.db.exists("Workflow State", state):
			frappe.get_doc({"doctype": "Workflow State", "workflow_state_name": state, "style": style}).insert(
				ignore_permissions=True
			)
	for action in (ACTION_SEND, ACTION_APPROVE, ACTION_REJECT, ACTION_CANCEL):
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": action}).insert(
				ignore_permissions=True
			)

	wf = frappe.get_doc("Workflow", WORKFLOW_NAME) if exists else frappe.new_doc("Workflow")
	wf.workflow_name = WORKFLOW_NAME
	wf.document_type = DOCTYPE
	wf.workflow_state_field = "workflow_state"
	wf.is_active = 1
	wf.override_status = 0
	wf.send_email_alert = 0
	wf.set("states", [
		{"state": STATE_DRAFT, "doc_status": "0", "allow_edit": maker},
		{"state": STATE_PENDING, "doc_status": "0", "allow_edit": approver},
		{"state": STATE_REJECTED, "doc_status": "0", "allow_edit": maker},
		{"state": STATE_APPROVED, "doc_status": "1", "allow_edit": approver},
		{"state": STATE_CANCELLED, "doc_status": "2", "allow_edit": approver},
	])
	wf.set("transitions", [
		{"state": STATE_DRAFT, "action": ACTION_SEND, "next_state": STATE_PENDING, "allowed": maker, "allow_self_approval": 1},
		{"state": STATE_PENDING, "action": ACTION_APPROVE, "next_state": STATE_APPROVED, "allowed": approver, "allow_self_approval": 0},
		{"state": STATE_PENDING, "action": ACTION_REJECT, "next_state": STATE_REJECTED, "allowed": approver, "allow_self_approval": 1},
		{"state": STATE_REJECTED, "action": ACTION_SEND, "next_state": STATE_PENDING, "allowed": maker, "allow_self_approval": 1},
		{"state": STATE_APPROVED, "action": ACTION_CANCEL, "next_state": STATE_CANCELLED, "allowed": approver, "allow_self_approval": 1},
	])
	wf.flags.ignore_permissions = True
	wf.save() if exists else wf.insert()
	frappe.clear_cache(doctype=DOCTYPE)


def notify_on_state_change(doc, method=None):
	"""Purchase Invoice on_change: mail when the approval state changes."""
	new_state = doc.get("workflow_state")
	if not new_state or not frappe.db.get_value("Workflow", WORKFLOW_NAME, "is_active"):
		return
	prev = doc.get_doc_before_save()
	if prev is None or prev.get("workflow_state") == new_state:
		return

	_maker, approver = _roles()
	label = f"{doc.name} ({doc.get('supplier_name') or doc.get('supplier')})"
	amount = frappe.utils.fmt_money(doc.get("grand_total"), currency=doc.get("currency"))
	actor = frappe.utils.get_fullname(frappe.session.user)

	if new_state == STATE_PENDING:
		users = [u for u in users_with_role(approver) if u != frappe.session.user]
		subject = _("Purchase Invoice {0} is pending your approval").format(doc.name)
		message = _("Purchase Invoice <b>{0}</b> for {1} was sent for approval by {2}.").format(label, amount, actor)
	elif new_state in (STATE_APPROVED, STATE_REJECTED):
		users = [doc.owner]
		verb = _("approved") if new_state == STATE_APPROVED else _("rejected")
		subject = _("Purchase Invoice {0} {1}").format(doc.name, verb)
		message = _("Your Purchase Invoice <b>{0}</b> for {1} was {2} by {3}.").format(label, amount, verb, actor)
	else:
		return

	try:
		notify_users(users, subject, message, reference_doctype=doc.doctype, reference_name=doc.name)
	except Exception:
		frappe.log_error(title=f"UB invoice approval mail failed: {doc.name}")
