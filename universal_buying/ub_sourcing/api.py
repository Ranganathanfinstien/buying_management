"""UB Sourcing public API (contracts used by other modules and by the desk scripts)."""

import frappe
from frappe import _
from frappe.utils import escape_html, now_datetime

from universal_buying.ub_sourcing.workflow import COMMENT_ACTIONS, STATE_CORRECTION

RFQ = "Request for Quotation"
RFQ_SUPPLIER = "Request for Quotation Supplier"


def get_user_suppliers(user=None):
	"""Suppliers the (portal) user is linked to through Supplier > Portal Users."""
	user = user or frappe.session.user
	if not user or user == "Guest":
		return []
	return frappe.get_all("Portal User", filters={"user": user, "parenttype": "Supplier"}, pluck="parent")


def get_or_create_rfq_token(rfq, supplier):
	"""Contract (BUILD_SPEC 6.3): token of the supplier's row on the RFQ, created once and then re-used.

	Used by the logged-in supplier portal (ub_ordering) to send a supplier to ``/rfq-portal?token=``.
	``supplier`` may be a Supplier or a Prospective Supplier name. Raises PermissionError when the
	party is not invited on the RFQ.
	"""
	row = frappe.db.get_value(RFQ_SUPPLIER, {"parent": rfq, "parenttype": RFQ, "supplier": supplier},
		["name", "ub_rfq_token"], as_dict=True)
	if not row:
		row = frappe.db.get_value(RFQ_SUPPLIER, {"parent": rfq, "parenttype": RFQ, "ub_prospective_supplier": supplier},
			["name", "ub_rfq_token"], as_dict=True)
	if not row:
		frappe.throw(_("{0} is not invited on Request for Quotation {1}.").format(supplier, rfq), frappe.PermissionError)
	if row.ub_rfq_token:
		return row.ub_rfq_token
	token = frappe.generate_hash(length=32)
	frappe.db.set_value(RFQ_SUPPLIER, row.name, "ub_rfq_token", token, update_modified=False)
	return token


@frappe.whitelist()
def get_my_rfq_token(rfq):
	"""Logged-in supplier: token for their own row (so the portal can link to /rfq-portal?token=)."""
	suppliers = get_user_suppliers()
	if not suppliers:
		frappe.throw(_("Your login is not linked to any supplier."), frappe.PermissionError)
	for supplier in suppliers:
		if frappe.db.exists(RFQ_SUPPLIER, {"parent": rfq, "parenttype": RFQ, "supplier": supplier}):
			return get_or_create_rfq_token(rfq, supplier)
	frappe.throw(_("You do not have access to this Request for Quotation."), frappe.PermissionError)


@frappe.whitelist()
def send_rfq_portal_links(rfq_name):
	"""Desk button "Send RFQ Portal Link": (re)send the invitation to every supplier row.

	Tokens that already exist are re-used, so earlier links keep working (source-app fix).
	"""
	from universal_buying.ub_sourcing.bidding import get_bid_state
	from universal_buying.ub_sourcing.notifications import invite_suppliers

	rfq = frappe.get_doc(RFQ, rfq_name)
	rfq.check_permission("write")
	if rfq.docstatus != 1:
		frappe.throw(_("Submit the Request for Quotation before sending portal links."))
	state = get_bid_state(rfq)
	if state.closed:
		frappe.throw(state.message, title=_("Bidding closed"))
	return invite_suppliers(rfq, only_unsent=False)


@frappe.whitelist()
def log_workflow_comment(reference_doctype, reference_name, action_type, workflow_state, comments):
	"""Mandatory comment for Send Back for Correction / Resubmit, stored on the RFQ timeline.

	Called by the workflow action dialog right before the transition is applied; the controller then
	checks that the comment exists (see UBRequestForQuotation._assert_workflow_comment).
	"""
	if reference_doctype != RFQ:
		frappe.throw(_("Unsupported document type."))
	if action_type not in COMMENT_ACTIONS:
		frappe.throw(_("No comment is needed for this action."))
	comments = (comments or "").strip()
	if not comments:
		frappe.throw(_("A comment is required to proceed with this workflow action."))

	doc = frappe.get_doc(reference_doctype, reference_name)
	doc.check_permission("read")
	label = _("Correction Reason") if action_type != "Resubmit" else _("Resubmit Notes")
	body = (
		f"<b>{escape_html(action_type)}</b> &mdash; {_('Workflow State')}: <i>{escape_html(workflow_state or '')}</i><br>"
		f"{label}: {escape_html(comments)}"
	)
	doc.add_comment("Comment", body)
	return {"ok": True}


def has_recent_workflow_comment(rfq_name, action_type, user=None, minutes=15):
	"""True when ``user`` logged the comment for ``action_type`` on the RFQ in the last ``minutes``."""
	since = frappe.utils.add_to_date(now_datetime(), minutes=-minutes)
	return bool(
		frappe.db.exists(
			"Comment",
			{
				"reference_doctype": RFQ,
				"reference_name": rfq_name,
				"comment_type": "Comment",
				"owner": user or frappe.session.user,
				"creation": [">=", since],
				"content": ["like", f"%{action_type}%"],
			},
		)
	)


# ---------------------------------------------------------------------------
# A-14.4 Mark for Revision
# ---------------------------------------------------------------------------

REVISION_ROLES = {"System Manager", "Purchase Manager", "Purchase User"}


def rfq_of_quotation(supplier_quotation):
	return frappe.db.get_value(
		"Supplier Quotation Item",
		{"parent": supplier_quotation, "request_for_quotation": ["is", "set"]},
		"request_for_quotation",
	)


@frappe.whitelist()
def mark_for_revision(supplier_quotation, reason):
	"""Buyer asks the supplier to revise a live quotation while bidding is open (reason mandatory)."""
	from universal_buying.ub_sourcing.bidding import RFQ_BID_FIELDS, get_bid_state

	if not set(frappe.get_roles()) & REVISION_ROLES:
		frappe.throw(_("You are not permitted to request a revision."), frappe.PermissionError)
	reason = (reason or "").strip()
	if not reason:
		frappe.throw(_("Please provide a reason for the revision."))

	row = frappe.db.get_value("Supplier Quotation", supplier_quotation,
		["docstatus", "ub_revision_requested", "ub_revised"], as_dict=True)
	if not row:
		frappe.throw(_("Supplier Quotation not found."))
	if row.docstatus == 2:
		frappe.throw(_("Cannot request a revision on a cancelled quotation."))
	if row.ub_revised:
		frappe.throw(
			_("This quotation has been superseded by a newer version from the supplier. "
			  "Request the revision on their current quotation instead."),
			title=_("Superseded quotation"),
		)
	if row.ub_revision_requested:
		frappe.throw(_("A revision has already been requested for this quotation."))

	rfq_name = rfq_of_quotation(supplier_quotation)
	if rfq_name:
		rfq = frappe.db.get_value(RFQ, rfq_name, RFQ_BID_FIELDS, as_dict=True)
		state = get_bid_state(rfq)
		if state.closed:
			frappe.throw(
				_("Bidding for {0} is {1}, so the supplier cannot submit a revised quotation. "
				  "Extend the bid deadline first.").format(rfq_name, state.label.lower()),
				title=_("Bidding closed"),
			)

	frappe.db.set_value("Supplier Quotation", supplier_quotation, {
		"ub_revision_requested": 1,
		"ub_revision_reason": reason,
		"ub_revision_requested_on": now_datetime(),
	}, update_modified=False)
	sq = frappe.get_doc("Supplier Quotation", supplier_quotation)
	sq.add_comment("Info", _("Revision requested by {0}: {1}").format(frappe.session.user, escape_html(reason)))
	_email_revision_request(sq, rfq_name, reason)
	return {"ok": True}


def _email_revision_request(sq, rfq_name, reason):
	"""Tell the supplier (token link when they have one)."""
	if not rfq_name:
		return
	from universal_buying.ub_sourcing.bidding import row_email, safe_sendmail, supplier_link

	filters = {"parent": rfq_name, "parenttype": RFQ}
	if sq.get("ub_prospective_supplier"):
		filters["ub_prospective_supplier"] = sq.ub_prospective_supplier
	elif sq.supplier:
		filters["supplier"] = sq.supplier
	else:
		return
	names = frappe.get_all(RFQ_SUPPLIER, filters=filters, pluck="name", limit=1)
	if not names:
		return
	row = frappe.get_doc(RFQ_SUPPLIER, names[0])
	email = row_email(row)
	if not email:
		return
	safe_sendmail(
		recipients=[email],
		subject=_("Revision requested: your quotation {0} for RFQ {1}").format(sq.name, rfq_name),
		message=_(
			"<p>Dear {0},</p><p>Please revise your quotation <strong>{1}</strong> for Request for Quotation "
			"<strong>{2}</strong>.</p><p><strong>Reason:</strong> {3}</p>"
			'<p><a href="{4}">Open the quotation portal</a> to submit a new version before the bid deadline.</p>'
		).format(escape_html(sq.supplier_name or "Supplier"), sq.name, rfq_name, escape_html(reason),
			supplier_link(rfq_name, row)),
		reference_doctype="Supplier Quotation",
		reference_name=sq.name,
	)


def assert_correction_comment(doc, old_state, new_state):
	"""Server side guard: Send Back for Correction and Resubmit need a comment on the timeline."""
	if frappe.flags.in_test and doc.flags.get("ub_skip_comment_check"):
		return
	if new_state == STATE_CORRECTION and old_state != STATE_CORRECTION:
		action = "Send Back for Correction"
	elif old_state == STATE_CORRECTION and new_state != STATE_CORRECTION:
		action = "Resubmit"
	else:
		return
	if not has_recent_workflow_comment(doc.name, action):
		frappe.throw(
			_("{0} needs a comment. Use the workflow action button so the reason is recorded.").format(_(action)),
			title=_("Comment required"),
		)
