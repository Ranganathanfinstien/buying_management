"""RFQ and Supplier Quotation workflows built from Buying Control Settings (BRD v2 section 8.2).

RFQ ("UB RFQ Approval")::

	Draft --Submit--> Open (bidding) --Send for Approval--> tier 1 --Approve--> tier 2 ... tier n
	tier n (the final approval state, default "Pending Final Approval") --Award--> Awarded
	every tier --Reject--> Rejected
	every tier --Send Back for Correction--> Correction Required --Resubmit--> tier 1

The tiers are the rows of ``rfq_approval_tiers`` (role, state_name). "Award" is done by
``award_role`` from the Quotation Comparison page; its transition carries the condition
``doc.ub_awarded_quotation`` so the desk never shows an Award button without a winner.

Supplier Quotation ("UB Supplier Quotation Approval")::

	Draft --Approve--> Approved (submitted)   Draft --Reject--> Rejected (submitted)

Both are rebuilt whenever Buying Control Settings is saved (hooks UB_ON_SETTINGS_UPDATE) and
from install.setup().
"""

import frappe
from frappe import _

RFQ_DOCTYPE = "Request for Quotation"
SQ_DOCTYPE = "Supplier Quotation"
RFQ_WORKFLOW = "UB RFQ Approval"
SQ_WORKFLOW = "UB Supplier Quotation Approval"

STATE_DRAFT = "Draft"
STATE_OPEN = "Open"
STATE_CORRECTION = "Correction Required"
STATE_REJECTED = "Rejected"
STATE_AWARDED = "Awarded"
STATE_APPROVED = "Approved"
DEFAULT_FINAL_STATE = "Pending Final Approval"

ACTION_SUBMIT = "Submit"
ACTION_SEND = "Send for Approval"
ACTION_APPROVE = "Approve"
ACTION_REJECT = "Reject"
ACTION_SEND_BACK = "Send Back for Correction"
ACTION_RESUBMIT = "Resubmit"
ACTION_AWARD = "Award"

# actions that need a comment (timeline) before they are applied
COMMENT_ACTIONS = (ACTION_SEND_BACK, ACTION_RESUBMIT)

RESERVED_STATES = {STATE_DRAFT, STATE_OPEN, STATE_CORRECTION, STATE_REJECTED, STATE_AWARDED}

BUYER_ROLES = ("Purchase User", "Purchase Manager")
BUYER_MANAGER_ROLE = "Purchase Manager"

# Open -> tier 1 only once bidding has closed (deadline passed or stamped Closed by the scheduler).
SEND_CONDITION = (
	'doc.ub_bid_status == "Closed" or (doc.ub_bid_deadline and '
	"frappe.utils.get_datetime(doc.ub_bid_deadline) <= frappe.utils.now_datetime())"
)
AWARD_CONDITION = "doc.ub_awarded_quotation"

_STATE_STYLE = {
	STATE_DRAFT: "",
	STATE_OPEN: "Info",
	STATE_CORRECTION: "Warning",
	STATE_REJECTED: "Danger",
	STATE_AWARDED: "Success",
	STATE_APPROVED: "Success",
}


# ---------------------------------------------------------------------------
# settings readers
# ---------------------------------------------------------------------------


def _settings(settings=None):
	if settings is not None:
		return settings
	from universal_buying.universal_buying.settings import get_settings

	return get_settings()


def get_award_role(settings=None):
	s = _settings(settings)
	return (s.get("award_role") or "").strip() or "CEO"


def get_tiers(settings=None):
	"""[(role, state_name), ...] in approval order, cleaned and de-duplicated.

	Falls back to a single tier (award role, "Pending Final Approval") when the table is empty so the
	workflow is always usable.
	"""
	s = _settings(settings)
	tiers, seen = [], set()
	for row in s.get("rfq_approval_tiers") or []:
		role = (row.get("role") or "").strip()
		state = (row.get("state_name") or "").strip()
		if not role or not state or state in seen:
			continue
		if state in RESERVED_STATES:
			frappe.throw(
				_("RFQ approval tier state {0} is reserved. Use a name such as 'Pending ... Approval'.").format(
					frappe.bold(state)
				)
			)
		seen.add(state)
		tiers.append((role, state))
	if not tiers:
		tiers = [(get_award_role(s), DEFAULT_FINAL_STATE)]
	return tiers


def get_tier_states(settings=None):
	return [state for _role, state in get_tiers(settings)]


def get_final_state(settings=None):
	"""The final approval state: the state of the last tier (V-15.1 award only here)."""
	return get_tier_states(settings)[-1]


def get_tier_role(state, settings=None):
	for role, st in get_tiers(settings):
		if st == state:
			return role
	return None


# ---------------------------------------------------------------------------
# master records
# ---------------------------------------------------------------------------


def ensure_workflow_state(name, style=None):
	if not frappe.db.exists("Workflow State", name):
		frappe.get_doc(
			{"doctype": "Workflow State", "workflow_state_name": name, "style": style or ""}
		).insert(ignore_permissions=True)


def ensure_workflow_action(name):
	if not frappe.db.exists("Workflow Action Master", name):
		frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": name}).insert(
			ignore_permissions=True
		)


def _ensure_roles(roles):
	for role in roles:
		if role and not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)


# ---------------------------------------------------------------------------
# builders (pure: return dicts, easy to test)
# ---------------------------------------------------------------------------


def build_rfq_workflow_definition(settings=None, extra_states=None):
	"""Return {"states": [...], "transitions": [...]} for the RFQ workflow."""
	tiers = get_tiers(settings)
	award_role = get_award_role(settings)
	states, transitions = [], []

	def state(name, docstatus, allow_edit, **kw):
		states.append({"state": name, "doc_status": str(docstatus), "allow_edit": allow_edit, **kw})

	def trans(frm, action, to, allowed, condition=None, self_approval=1):
		transitions.append({
			"state": frm, "action": action, "next_state": to, "allowed": allowed,
			"allow_self_approval": self_approval, "condition": condition or None,
		})

	state(STATE_DRAFT, 0, "Purchase User")
	state(STATE_DRAFT, 0, BUYER_MANAGER_ROLE)
	state(STATE_OPEN, 1, BUYER_MANAGER_ROLE)
	for role, st in tiers:
		state(st, 1, role)
	state(STATE_CORRECTION, 1, BUYER_MANAGER_ROLE)
	state(STATE_REJECTED, 1, BUYER_MANAGER_ROLE)
	state(STATE_AWARDED, 1, award_role)

	for role in BUYER_ROLES:
		trans(STATE_DRAFT, ACTION_SUBMIT, STATE_OPEN, role)
	first_tier = tiers[0][1]
	for role in BUYER_ROLES:
		trans(STATE_OPEN, ACTION_SEND, first_tier, role, condition=SEND_CONDITION)
	trans(STATE_OPEN, ACTION_REJECT, STATE_REJECTED, BUYER_MANAGER_ROLE)

	for i, (role, st) in enumerate(tiers):
		if i + 1 < len(tiers):
			trans(st, ACTION_APPROVE, tiers[i + 1][1], role, self_approval=0)
		else:
			trans(st, ACTION_AWARD, STATE_AWARDED, award_role, condition=AWARD_CONDITION, self_approval=0)
		trans(st, ACTION_REJECT, STATE_REJECTED, role)
		trans(st, ACTION_SEND_BACK, STATE_CORRECTION, role)
	# the award role may also reject / send back in the final state even if it is not the tier role
	final_role, final_state = tiers[-1]
	if award_role != final_role:
		trans(final_state, ACTION_REJECT, STATE_REJECTED, award_role)
		trans(final_state, ACTION_SEND_BACK, STATE_CORRECTION, award_role)

	for role in BUYER_ROLES:
		trans(STATE_CORRECTION, ACTION_RESUBMIT, first_tier, role)

	# states that documents still sit in but which are no longer configured: keep them so those
	# documents stay valid, and let the buyer move them out.
	for st in extra_states or []:
		state(st, 1, BUYER_MANAGER_ROLE)
		trans(st, ACTION_SEND_BACK, STATE_CORRECTION, BUYER_MANAGER_ROLE)
		trans(st, ACTION_REJECT, STATE_REJECTED, BUYER_MANAGER_ROLE)

	return {"states": states, "transitions": transitions}


def build_sq_workflow_definition(settings=None):
	award_role = get_award_role(settings)
	states = [
		{"state": STATE_DRAFT, "doc_status": "0", "allow_edit": "Purchase User"},
		{"state": STATE_DRAFT, "doc_status": "0", "allow_edit": BUYER_MANAGER_ROLE},
		{"state": STATE_APPROVED, "doc_status": "1", "allow_edit": award_role,
		 "update_field": "ub_sq_status", "update_value": "Approved"},
		{"state": STATE_REJECTED, "doc_status": "1", "allow_edit": award_role,
		 "update_field": "ub_sq_status", "update_value": "Rejected"},
	]
	transitions = [
		{"state": STATE_DRAFT, "action": ACTION_APPROVE, "next_state": STATE_APPROVED, "allowed": award_role,
		 "allow_self_approval": 1},
		{"state": STATE_DRAFT, "action": ACTION_REJECT, "next_state": STATE_REJECTED, "allowed": award_role,
		 "allow_self_approval": 1},
	]
	return {"states": states, "transitions": transitions}


# ---------------------------------------------------------------------------
# (re)create
# ---------------------------------------------------------------------------


def _orphan_states(workflow_name, doctype, configured):
	"""States used by live documents that the new definition no longer has."""
	if not frappe.db.has_column(doctype, "workflow_state"):
		return []
	used = frappe.get_all(
		doctype, filters={"docstatus": 1, "workflow_state": ["is", "set"]}, pluck="workflow_state", distinct=True
	)
	return [s for s in used if s and s not in configured]


def _save_workflow(name, doctype, definition):
	for st in definition["states"]:
		ensure_workflow_state(st["state"], _STATE_STYLE.get(st["state"], "Warning"))
	for tr in definition["transitions"]:
		ensure_workflow_action(tr["action"])
	_ensure_roles({s["allow_edit"] for s in definition["states"]} | {t["allowed"] for t in definition["transitions"]})

	if frappe.db.exists("Workflow", name):
		wf = frappe.get_doc("Workflow", name)
		wf.set("states", [])
		wf.set("transitions", [])
	else:
		wf = frappe.new_doc("Workflow")
		wf.workflow_name = name
	wf.document_type = doctype
	wf.workflow_state_field = "workflow_state"
	wf.is_active = 1
	wf.override_status = 1
	wf.send_email_alert = 0
	for st in definition["states"]:
		wf.append("states", st)
	for tr in definition["transitions"]:
		wf.append("transitions", tr)
	wf.flags.ignore_permissions = True
	wf.save()
	frappe.cache.hdel("workflow", doctype)
	return wf


def rebuild_rfq_workflow(settings=None):
	"""(Re)create Workflow "UB RFQ Approval" on Request for Quotation from ``rfq_approval_tiers``."""
	definition = build_rfq_workflow_definition(settings)
	configured = {s["state"] for s in definition["states"]}
	orphans = _orphan_states(RFQ_WORKFLOW, RFQ_DOCTYPE, configured)
	if orphans:
		definition = build_rfq_workflow_definition(settings, extra_states=orphans)
	return _save_workflow(RFQ_WORKFLOW, RFQ_DOCTYPE, definition)


def rebuild_sq_workflow(settings=None):
	"""(Re)create Workflow "UB Supplier Quotation Approval" (award role approves / rejects)."""
	return _save_workflow(SQ_WORKFLOW, SQ_DOCTYPE, build_sq_workflow_definition(settings))


def _has_perm_row(doctype, role, ptypes):
	table = "Custom DocPerm" if frappe.db.exists("Custom DocPerm", {"parent": doctype}) else "DocPerm"
	row = frappe.db.get_value(table, {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0},
		list(ptypes), as_dict=True)
	return row and all(row.get(p) for p in ptypes)


def ensure_approver_permissions(settings=None):
	"""Approver roles (tiers + award role) need read/write on RFQ and Supplier Quotation to act on the
	workflow (apply_workflow checks read and saves the document); the award role also submits the
	winning quotation. Only missing rights are added (Custom DocPerm); existing rules are kept."""
	from frappe.permissions import add_permission, update_permission_property

	award_role = get_award_role(settings)
	wanted = {RFQ_DOCTYPE: {}, SQ_DOCTYPE: {}}
	# the buyer roles run Draft --Submit--> Open; standard ERPNext gives Purchase User no submit right
	for role in BUYER_ROLES:
		wanted[RFQ_DOCTYPE][role] = ("read", "write", "create", "submit", "print", "report")
	for role, _state in get_tiers(settings):
		wanted[RFQ_DOCTYPE][role] = ("read", "write", "print", "report")
		wanted[SQ_DOCTYPE][role] = ("read", "print", "report")
	wanted[RFQ_DOCTYPE][award_role] = ("read", "write", "print", "report")
	wanted[SQ_DOCTYPE][award_role] = ("read", "write", "submit", "print", "report")

	for doctype, roles in wanted.items():
		changed = False
		for role, ptypes in roles.items():
			if not role or not frappe.db.exists("Role", role) or _has_perm_row(doctype, role, ptypes):
				continue
			if not frappe.db.get_value("Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0}):
				add_permission(doctype, role, 0, "read")
			for ptype in ptypes:
				update_permission_property(doctype, role, 0, ptype, 1, validate=False)
			changed = True
		if changed:
			frappe.clear_cache(doctype=doctype)


def on_settings_update(settings=None, method=None):
	"""UB_ON_SETTINGS_UPDATE hook: Buying Control Settings saved -> rebuild both workflows."""
	rebuild_rfq_workflow(settings)
	rebuild_sq_workflow(settings)
	ensure_approver_permissions(settings)
