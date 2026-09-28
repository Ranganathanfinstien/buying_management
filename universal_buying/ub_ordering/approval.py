"""Value-band Purchase Order approval for every PO (BRD v2 6.18 and 8.3).

Rules live in Buying Control Settings -> ``po_approval_rules`` (UB PO Approval Rule rows:
company, from_amount, to_amount, origin, step, approver_role). A row matches a PO when

* company is blank or equals the PO company,
* origin is blank or equals the PO origin (``get_po_origin``: Auto PO Run, Auto PO Exception,
  Supplier Quotation, Material Request, Manual),
* ``from_amount < base_grand_total <= to_amount`` (a 0 from_amount includes 0; a 0 to_amount means no limit).

The most specific rows win (company + origin > company > origin > generic); among equally specific
bands the narrowest one (highest from_amount) wins. The winning band's rows ordered by ``step`` are
the approval chain; several rows with the same step mean any of those roles may approve that step.

State lives on the PO: ``ub_approval_status`` (Draft / Pending / Approved / Rejected), ``ub_approval_step``,
``ub_approval_roles`` and the ``ub_approval_history`` table (UB PO Approval Log).

Changed from the earlier ``po_approval.py``: applies to all POs (not only Material Request based),
roles and bands come from settings, and there is no System Manager bypass (AC-18.1) - only a holder of
the step's role can approve or reject it.
"""

import frappe
from frappe import _
from frappe.utils import flt, fmt_money, get_url_to_form, now_datetime

from universal_buying.universal_buying.settings import get_setting, get_settings
from universal_buying.universal_buying.utils import get_po_origin, notify_users, users_with_role

DOCTYPE = "Purchase Order"
DRAFT, PENDING, APPROVED, REJECTED = "Draft", "Pending", "Approved", "Rejected"
_STATE_FIELDS = ("ub_approval_status", "ub_approval_step", "ub_approval_roles")


# ======================================================================================
# Rule matching
# ======================================================================================
def _in_band(amount, from_amount, to_amount):
	lo, hi = flt(from_amount), flt(to_amount)
	above_lo = amount > lo or (lo == 0 and amount >= 0)
	below_hi = hi == 0 or amount <= hi
	return above_lo and below_hi


def match_rules(rules, company, origin, amount):
	"""Pure matcher (unit tested). ``rules`` are dict-like rows. Returns [{"step", "roles"}] in order."""
	amount = flt(amount)
	matching = [
		r for r in rules or []
		if r.get("approver_role")
		and (not r.get("company") or r.get("company") == company)
		and (not r.get("origin") or r.get("origin") == origin)
		and _in_band(amount, r.get("from_amount"), r.get("to_amount"))
	]
	if not matching:
		return []

	def score(r):
		return (2 if r.get("company") else 0) + (1 if r.get("origin") else 0)

	best = max(score(r) for r in matching)
	matching = [r for r in matching if score(r) == best]

	def band(r):
		return (r.get("company") or "", r.get("origin") or "", flt(r.get("from_amount")), flt(r.get("to_amount")))

	bands = {}
	for r in matching:
		bands.setdefault(band(r), []).append(r)
	# narrowest band: highest lower bound, then lowest (non-zero) upper bound
	key = sorted(bands, key=lambda b: (-b[2], b[3] if b[3] else float("inf")))[0]

	steps = {}
	for r in bands[key]:
		step = int(r.get("step") or 1)
		roles = steps.setdefault(step, [])
		if r.get("approver_role") not in roles:
			roles.append(r.get("approver_role"))
	return [{"step": s, "roles": steps[s]} for s in sorted(steps)]


def is_enabled(po):
	return bool(get_setting("po_approval_enabled", company=po.get("company")))


def get_steps(po):
	rules = get_settings().get("po_approval_rules") or []
	return match_rules(rules, po.get("company"), get_po_origin(po), po.get("base_grand_total"))


# ======================================================================================
# Controller hooks (called from CustomPurchaseOrder)
# ======================================================================================
def _fingerprint(doc):
	lines = tuple(
		(d.get("item_code") or d.get("description") or "", flt(d.get("qty")), flt(d.get("rate")))
		for d in doc.get("items") or []
	)
	return (doc.get("supplier"), doc.get("company"), flt(doc.get("base_grand_total"), 2), lines)


def on_validate(po):
	"""Keep approval fields server-owned; reset a Pending / Approved PO when it is edited."""
	if po.flags.get("ub_approval_action"):
		return
	before = None if po.is_new() else po.get_doc_before_save()
	if not before:
		if po.docstatus == 0 and po.is_new():
			po.ub_approval_status = DRAFT
			po.ub_approval_step = 0
			po.ub_approval_roles = None
		return
	for f in _STATE_FIELDS:
		po.set(f, before.get(f))
	if before.get("ub_approval_status") in (PENDING, APPROVED) and po.docstatus == 0 and _fingerprint(before) != _fingerprint(po):
		po.ub_approval_status = DRAFT
		po.ub_approval_step = 0
		po.ub_approval_roles = None
		po.append("ub_approval_history", _log_row(0, None, "Reset", _("PO changed after it was sent for approval")))
		frappe.msgprint(_("The PO was changed, so its approval was reset. Send it for approval again."),
			indicator="orange", alert=True)


def check_before_submit(po):
	"""V-18.1: no submit until the approval is complete."""
	if not is_enabled(po) or po.get("ub_approval_status") == APPROVED:
		return
	if not get_steps(po):
		po.ub_approval_status = APPROVED
		po.append("ub_approval_history", _log_row(0, None, "Auto Approved", _("No approval rule matched")))
		return
	frappe.throw(
		_("Purchase Order {0} must be approved before it is submitted (approval status: {1}).").format(
			po.name, po.get("ub_approval_status") or DRAFT),
		title=_("Approval Pending"),
	)


# ======================================================================================
# Persistence helpers (no full save: approvers need not have write access to the PO)
# ======================================================================================
def _log_row(step, role, action, remarks=None):
	return {
		"step": step, "approver_role": role, "action": action, "user": frappe.session.user,
		"action_on": now_datetime(), "remarks": remarks,
	}


def _append_history(name, row):
	idx = frappe.db.sql(
		"""select coalesce(max(idx), 0) + 1 from `tabUB PO Approval Log`
		where parent = %s and parenttype = %s and parentfield = 'ub_approval_history'""",
		(name, DOCTYPE),
	)[0][0]
	child = frappe.get_doc({
		"doctype": "UB PO Approval Log", "parent": name, "parenttype": DOCTYPE,
		"parentfield": "ub_approval_history", "idx": idx, **row,
	})
	child.db_insert()


def _persist(doc, values, log):
	_append_history(doc.name, log)
	frappe.db.set_value(DOCTYPE, doc.name, values)
	for k, v in values.items():
		doc.set(k, v)


def _load(name):
	doc = frappe.get_doc(DOCTYPE, name)
	if doc.docstatus != 0:
		frappe.throw(_("Only a draft Purchase Order can go through approval."))
	return doc


def _current_step(doc):
	steps = get_steps(doc)
	current = next((s for s in steps if s["step"] == int(doc.get("ub_approval_step") or 0)), None)
	return steps, current


def _user_roles(user=None):
	"""Roles actually assigned to the user. frappe.get_roles() gives Administrator every role, which would
	let Administrator approve any band (AC-18.1), so for Administrator only the Has Role rows count."""
	user = user or frappe.session.user
	if user == "Administrator":
		return set(frappe.get_all("Has Role", filters={"parent": user, "parenttype": "User"}, pluck="role"))
	return set(frappe.get_roles(user))


def _require_step_role(current, user=None):
	"""AC-18.1: strictly the step role - System Manager / Administrator do not override."""
	roles = _user_roles(user)
	if not current or not roles.intersection(current["roles"]):
		frappe.throw(
			_("Only {0} can act on this approval step.").format(", ".join(current["roles"]) if current else "-"),
			frappe.PermissionError,
		)


# ======================================================================================
# Actions
# ======================================================================================
@frappe.whitelist()
def send_for_approval(name, remarks=None):
	from universal_buying.ub_ordering import po_rules
	from universal_buying.universal_buying.utils import assert_supplier_enabled

	doc = _load(name)
	doc.check_permission("write")
	if doc.get("ub_approval_status") not in (None, "", DRAFT, REJECTED):
		frappe.throw(_("The PO is already {0}.").format(doc.ub_approval_status))
	po_rules.validate_addresses(doc)
	assert_supplier_enabled(doc.supplier, _("Purchase Order {0}").format(doc.name))

	steps = get_steps(doc)
	if not steps:
		_persist(doc, {"ub_approval_status": APPROVED, "ub_approval_step": 0, "ub_approval_roles": None},
			_log_row(0, None, "Auto Approved", remarks or _("No approval rule matched")))
		return get_approval_state(name)

	first = steps[0]
	_persist(doc, {"ub_approval_status": PENDING, "ub_approval_step": first["step"],
		"ub_approval_roles": "\n".join(first["roles"])},
		_log_row(0, None, "Sent", remarks))
	_notify_approvers(doc, first)
	return get_approval_state(name)


@frappe.whitelist()
def approve(name, remarks=None):
	doc = _load(name)
	if doc.get("ub_approval_status") != PENDING:
		frappe.throw(_("The PO is not pending approval."))
	steps, current = _current_step(doc)
	if not current:
		frappe.throw(_("The approval rules changed after this PO was sent. Reject it and send it again."))
	_require_step_role(current)

	role = next(r for r in current["roles"] if r in _user_roles())
	later = [s for s in steps if s["step"] > current["step"]]
	if later:
		nxt = later[0]
		_persist(doc, {"ub_approval_status": PENDING, "ub_approval_step": nxt["step"],
			"ub_approval_roles": "\n".join(nxt["roles"])},
			_log_row(current["step"], role, "Approved", remarks))
		_notify_approvers(doc, nxt)
		return get_approval_state(name)

	_persist(doc, {"ub_approval_status": APPROVED, "ub_approval_step": 0, "ub_approval_roles": None},
		_log_row(current["step"], role, "Approved", remarks))
	_notify_owner(doc, _("Purchase Order {0} approved").format(doc.name),
		_("Purchase Order {0} received its final approval.").format(doc.name))

	if get_setting("submit_po_on_final_approval", company=doc.company):
		_auto_submit(name)
	return get_approval_state(name)


def _auto_submit(name):
	frappe.db.savepoint("ub_po_auto_submit")
	try:
		doc = frappe.get_doc(DOCTYPE, name)
		doc.flags.ignore_permissions = True
		doc.flags.ub_approval_action = True
		doc.submit()
	except Exception as e:
		frappe.db.rollback(save_point="ub_po_auto_submit")
		frappe.local.message_log = []
		frappe.log_error(title=f"PO auto submit failed: {name}")
		frappe.msgprint(
			_("The PO is approved but could not be submitted automatically: {0}. Please submit it manually.").format(
				frappe.utils.strip_html(str(e))),
			title=_("Submit Pending"), indicator="orange",
		)


@frappe.whitelist()
def reject(name, reason=None):
	reason = (reason or "").strip()
	if not reason:
		frappe.throw(_("A reason is required to reject the Purchase Order."))
	doc = _load(name)
	if doc.get("ub_approval_status") != PENDING:
		frappe.throw(_("The PO is not pending approval."))
	_steps, current = _current_step(doc)
	if not current:
		current = {"step": doc.get("ub_approval_step"), "roles": (doc.get("ub_approval_roles") or "").split("\n")}
	_require_step_role(current)
	role = next((r for r in current["roles"] if r in _user_roles()), None)
	_persist(doc, {"ub_approval_status": REJECTED, "ub_approval_step": 0, "ub_approval_roles": None},
		_log_row(current["step"], role, "Rejected", reason))
	doc.add_comment("Comment", _("Approval rejected by {0}: {1}").format(frappe.utils.get_fullname(), reason))
	_notify_owner(doc, _("Purchase Order {0} rejected").format(doc.name),
		_("Purchase Order {0} was rejected at step {1}. Reason: {2}").format(doc.name, current["step"], reason))
	return get_approval_state(name)


# ======================================================================================
# State (contract: get_approval_state(po_name) -> dict)
# ======================================================================================
def get_approval_state(po_name):
	doc = frappe.get_doc(DOCTYPE, po_name)
	enabled = is_enabled(doc)
	steps = get_steps(doc)
	status = doc.get("ub_approval_status") or DRAFT
	current_step = int(doc.get("ub_approval_step") or 0)

	history = [
		{"step": h.step, "role": h.approver_role, "action": h.action, "user": h.user, "on": h.action_on, "remarks": h.remarks}
		for h in doc.get("ub_approval_history") or []
	]
	# approvals since the last Sent / Reset / Rejected row belong to the current cycle
	cycle = []
	for h in history:
		if h["action"] in ("Sent", "Reset", "Rejected", "Auto Approved"):
			cycle = []
		elif h["action"] == "Approved":
			cycle.append(h)
	approved = {h["step"]: h for h in cycle}

	out_steps = []
	for s in steps:
		h = approved.get(s["step"])
		if status == APPROVED and not h and doc.docstatus != 0:
			st = APPROVED
		elif h:
			st = APPROVED
		elif status == PENDING and s["step"] == current_step:
			st = PENDING
		else:
			st = "Waiting"
		out_steps.append({"step": s["step"], "roles": s["roles"], "status": st,
			"by": h["user"] if h else None, "on": h["on"] if h else None})

	pending_roles = []
	if status == PENDING:
		pending_roles = next((s["roles"] for s in steps if s["step"] == current_step), None) or \
			[r for r in (doc.get("ub_approval_roles") or "").split("\n") if r]

	return {
		"name": doc.name,
		"enabled": enabled,
		"required": bool(enabled and steps),
		"status": status,
		"step": current_step,
		"total_steps": len(steps),
		"pending_roles": pending_roles,
		"steps": out_steps,
		"history": history,
		"origin": get_po_origin(doc),
		"base_grand_total": flt(doc.get("base_grand_total")),
		"docstatus": doc.docstatus,
	}


@frappe.whitelist()
def get_approval_context(name):
	"""State + what the current user may do (drives the form buttons)."""
	frappe.has_permission(DOCTYPE, "read", doc=name, throw=True)
	state = get_approval_state(name)
	roles = _user_roles()
	is_draft = state["docstatus"] == 0
	can_write = frappe.has_permission(DOCTYPE, "write", doc=name)
	state["can_send"] = bool(is_draft and state["enabled"] and can_write and state["status"] in (DRAFT, REJECTED))
	can_decide = bool(is_draft and state["status"] == PENDING and roles.intersection(state["pending_roles"]))
	state["can_approve"] = can_decide
	state["can_reject"] = can_decide
	return state


# ======================================================================================
# Notifications (A-18.1)
# ======================================================================================
def _po_summary(doc):
	return _("{0} - {1} - {2}").format(
		doc.name, doc.get("supplier_name") or doc.supplier,
		fmt_money(flt(doc.get("base_grand_total")), currency=frappe.get_cached_value("Company", doc.company, "default_currency")),
	)


def _notify_approvers(doc, step):
	try:
		users = []
		for role in step["roles"]:
			users += users_with_role(role)
		link = get_url_to_form(DOCTYPE, doc.name)
		notify_users(
			users,
			_("Approval required: Purchase Order {0}").format(doc.name),
			_("Purchase Order {0} is waiting for your approval (step {1}).<br><br><a href=\"{2}\">Open the Purchase Order</a>").format(
				_po_summary(doc), step["step"], link),
			DOCTYPE, doc.name,
		)
	except Exception:
		frappe.log_error(title=f"PO approval notification failed: {doc.name}")


def _notify_owner(doc, subject, message):
	try:
		notify_users([doc.owner], subject, message, DOCTYPE, doc.name)
	except Exception:
		frappe.log_error(title=f"PO approval notification failed: {doc.name}")
