"""Bid deadline / bid lock for RFQs (BRD v2 6.13 A-13.2, A-13.3, AC-13.1 and 6.14 V-14.1).

ONE function decides whether a supplier may still quote: ``get_bid_state``. Every quoting surface
(guest token portal, logged-in supplier portal, Excel round trip, desk "Mark for Revision") calls it,
so they can never disagree. States, in precedence order::

	cancelled         docstatus 2                              -> closed
	awarded           workflow "Awarded" / bid status Awarded  -> closed
	rejected          workflow "Rejected" / bid status Rejected-> closed
	under_evaluation  any approval state or Correction Required-> closed
	                  (Correction Required re-opens once the buyer extends the deadline)
	not_open          docstatus 0                              -> closed
	closed            deadline passed                          -> closed
	closing_soon      less than bid_reminder_hours left        -> open
	open                                                       -> open

The scheduler (every 15 minutes) only sends notifications and stamps the stored Bid Status; the lock
itself is computed at read time, so a stalled scheduler can never keep bidding open.
"""

import frappe
from frappe import _
from frappe.utils import add_days, add_to_date, cint, get_datetime, get_time, get_url, getdate, now_datetime, nowdate

from universal_buying.ub_sourcing.workflow import (
	STATE_AWARDED,
	STATE_CORRECTION,
	STATE_DRAFT,
	STATE_OPEN,
	STATE_REJECTED,
)
from universal_buying.universal_buying.settings import get_setting

RFQ = "Request for Quotation"

BID_OPEN = "Open"
BID_UNDER_EVALUATION = "Under Evaluation"
BID_CLOSED = "Closed"
BID_AWARDED = "Awarded"
BID_REJECTED = "Rejected"

_BID_STATE_LABELS = {
	"open": "Open",
	"closing_soon": "Closing Soon",
	"closed": "Closed",
	"under_evaluation": "Under Evaluation",
	"awarded": "Awarded",
	"rejected": "Rejected",
	"not_open": "Not Open",
	"cancelled": "Cancelled",
}

RFQ_BID_FIELDS = ["name", "company", "owner", "docstatus", "workflow_state", "ub_bid_deadline", "ub_bid_status"]


# ---------------------------------------------------------------------------
# settings
# ---------------------------------------------------------------------------


def reminder_seconds():
	return max(cint(get_setting("bid_reminder_hours", default=24)), 0) * 3600


def get_default_bid_deadline(base_date=None):
	"""AC-13.1: today (or ``base_date``) + bid_deadline_default_days at bid_deadline_default_time."""
	days = cint(get_setting("bid_deadline_default_days", default=7))
	at = get_setting("bid_deadline_default_time", default="17:00:00") or "17:00:00"
	day = getdate(add_days(base_date or nowdate(), days))
	t = get_time(at)
	return get_datetime(f"{day} {t.strftime('%H:%M:%S')}")


@frappe.whitelist()
def default_bid_deadline(base_date=None):
	return str(get_default_bid_deadline(base_date))


# ---------------------------------------------------------------------------
# state
# ---------------------------------------------------------------------------


def _tz_label():
	tz = frappe.utils.get_system_timezone() or ""
	return "IST" if tz == "Asia/Kolkata" else tz


def format_bid_deadline(deadline):
	"""'10/09/2026 17:00 IST' - supplier facing, time zone explicit for foreign suppliers."""
	if not deadline:
		return ""
	deadline = get_datetime(deadline)
	return "{} {}".format(frappe.utils.format_datetime(deadline, "dd/MM/yyyy HH:mm"), _tz_label()).strip()


def is_evaluation_state(wf):
	"""Every workflow state after Open that is neither Awarded nor Rejected (approval tiers,
	Correction Required and states kept from an older tier set)."""
	return bool(wf) and wf not in (STATE_DRAFT, STATE_OPEN, STATE_AWARDED, STATE_REJECTED)


def _reopened_for_correction(rfq, wf, deadline, now):
	"""A Correction Required RFQ whose deadline the buyer extended (bid status stamped Open)."""
	return (
		wf == STATE_CORRECTION
		and (rfq.get("ub_bid_status") or "") == BID_OPEN
		and deadline is not None
		and deadline > now
	)


def get_bid_state(rfq, now=None):
	"""Resolve the bidding state of an RFQ (doc or dict).

	Returns frappe._dict(state, label, closed, message, deadline, deadline_fmt, seconds_left).
	``closed`` is True whenever a supplier must NOT submit or revise a quotation.
	"""
	now = get_datetime(now) if now else now_datetime()
	deadline = rfq.get("ub_bid_deadline")
	deadline = get_datetime(deadline) if deadline else None
	deadline_fmt = format_bid_deadline(deadline)
	wf = rfq.get("workflow_state") or ""
	bid_status = rfq.get("ub_bid_status") or ""
	docstatus = cint(rfq.get("docstatus"))

	seconds_left = None
	if docstatus == 2:
		state, message = "cancelled", _("This Request for Quotation has been cancelled.")
	elif wf == STATE_AWARDED or bid_status == BID_AWARDED:
		state, message = "awarded", _(
			"This Request for Quotation has been awarded. New submissions are no longer accepted."
		)
	elif wf == STATE_REJECTED or bid_status == BID_REJECTED:
		state, message = "rejected", _(
			"This Request for Quotation was not awarded. New submissions are no longer accepted."
		)
	elif is_evaluation_state(wf) and not _reopened_for_correction(rfq, wf, deadline, now):
		state, message = "under_evaluation", _(
			"Quotations for this Request for Quotation are under evaluation. "
			"New submissions or revisions are not accepted at this stage."
		)
	elif docstatus == 0:
		state, message = "not_open", _("This Request for Quotation is not yet open for quotation.")
	elif deadline and deadline <= now:
		state, message = "closed", _("Bidding closed on {0}. New submissions are no longer accepted.").format(
			deadline_fmt
		)
	else:
		state, message = "open", ""
		if deadline:
			seconds_left = int((deadline - now).total_seconds())
			if seconds_left <= reminder_seconds():
				state = "closing_soon"

	return frappe._dict(
		state=state,
		label=_(_BID_STATE_LABELS[state]),
		closed=state not in ("open", "closing_soon"),
		message=message,
		deadline=deadline,
		deadline_fmt=deadline_fmt,
		seconds_left=seconds_left,
	)


def assert_bid_open(rfq):
	state = get_bid_state(rfq)
	if state.closed:
		frappe.throw(state.message, title=_("Bidding closed"))
	return state


def bid_status_for_workflow(wf):
	"""Stored Bid Status that goes with a workflow state (None = leave as is)."""
	if not wf:
		return None
	if wf == STATE_OPEN:
		return BID_OPEN
	if wf == STATE_AWARDED:
		return BID_AWARDED
	if wf == STATE_REJECTED:
		return BID_REJECTED
	if is_evaluation_state(wf):
		return BID_UNDER_EVALUATION
	return None


def sync_bid_status_with_workflow(doc):
	"""Re-stamp ub_bid_status on a workflow transition only (a plain save in the same state, e.g. a
	deadline extension that set it back to Open, must not undo it)."""
	before = doc.get_doc_before_save()
	if before is not None and (before.get("workflow_state") or "") == (doc.get("workflow_state") or ""):
		return
	status = bid_status_for_workflow(doc.get("workflow_state"))
	if status and doc.get("ub_bid_status") != status:
		doc.db_set("ub_bid_status", status, update_modified=False)


# ---------------------------------------------------------------------------
# scheduler (cron */15)
# ---------------------------------------------------------------------------


def process_bid_deadlines():
	now = now_datetime()
	send_deadline_reminders(now)
	close_expired_rfqs(now)


def quoted_parties(rfq_name):
	"""(suppliers, prospective suppliers) that have a live (not cancelled) quotation on the RFQ."""
	rows = frappe.db.sql(
		"""
		SELECT DISTINCT sq.supplier, sq.ub_prospective_supplier
		FROM `tabSupplier Quotation` sq
		JOIN `tabSupplier Quotation Item` sqi ON sqi.parent = sq.name
		WHERE sqi.request_for_quotation = %s AND sq.docstatus < 2
		""",
		(rfq_name,),
		as_dict=True,
	)
	return (
		{r.supplier for r in rows if r.supplier},
		{r.ub_prospective_supplier for r in rows if r.ub_prospective_supplier},
	)


def row_email(row):
	email = row.get("email_id")
	if not email and row.get("contact"):
		email = frappe.db.get_value("Contact", row.contact, "email_id")
	if not email and row.get("ub_prospective_supplier"):
		email = frappe.db.get_value("Prospective Supplier", row.ub_prospective_supplier, "email")
	return email


def safe_sendmail(**kwargs):
	"""Queue a mail without letting an SMTP / Email Account problem abort the business action."""
	try:
		kwargs.setdefault("now", False)
		frappe.sendmail(**kwargs)
		return True
	except Exception:
		frappe.log_error(title="RFQ bidding: mail not sent", message=frappe.get_traceback())
		frappe.clear_last_message()
		return False


def supplier_link(rfq_name, row):
	"""Where a supplier row quotes: the token link for everybody who has a token, otherwise the portal."""
	token = row.get("ub_rfq_token")
	if token:
		return get_url(f"/rfq-portal?token={token}")
	from universal_buying.ub_sourcing.notifications import supplier_portal_url

	return supplier_portal_url()


def send_deadline_reminders(now=None):
	now = get_datetime(now) if now else now_datetime()
	soon = add_to_date(now, seconds=reminder_seconds())
	rfqs = frappe.get_all(
		RFQ,
		filters={"docstatus": 1, "ub_bid_reminder_sent": 0, "ub_bid_deadline": ["between", [now, soon]]},
		fields=RFQ_BID_FIELDS,
	)
	for r in rfqs:
		state = get_bid_state(r, now=now)
		if not state.closed:
			_remind_unquoted_suppliers(r, state)
		frappe.db.set_value(RFQ, r.name, "ub_bid_reminder_sent", 1, update_modified=False)
		frappe.db.commit()


def _remind_unquoted_suppliers(r, state):
	doc = frappe.get_doc(RFQ, r.name)
	quoted, quoted_ps = quoted_parties(doc.name)
	for row in doc.suppliers:
		if row.supplier:
			if row.supplier in quoted:
				continue
		elif not row.get("ub_prospective_supplier") or row.ub_prospective_supplier in quoted_ps:
			continue
		email = row_email(row)
		if not email:
			continue
		safe_sendmail(
			recipients=[email],
			subject=_("Reminder: RFQ {0} closes on {1}").format(doc.name, state.deadline_fmt),
			message=_(
				"<p>Dear {0},</p>"
				"<p>Bidding for <strong>Request for Quotation {1}</strong> closes on "
				"<strong>{2}</strong>. We have not received your quotation yet.</p>"
				'<p><a href="{3}">Submit your quotation</a> before the deadline. '
				"Submissions are not accepted after it.</p>"
				"<p>Best regards,<br>{4}</p>"
			).format(
				frappe.utils.escape_html(row.supplier_name or row.supplier or row.ub_prospective_supplier or "Supplier"),
				doc.name,
				state.deadline_fmt,
				supplier_link(doc.name, row),
				doc.company,
			),
			reference_doctype=RFQ,
			reference_name=doc.name,
		)


def close_expired_rfqs(now=None):
	now = get_datetime(now) if now else now_datetime()
	rfqs = frappe.get_all(
		RFQ,
		filters={"docstatus": 1, "ub_bid_closed_notified": 0, "ub_bid_deadline": ["<", now]},
		fields=RFQ_BID_FIELDS,
	)
	for r in rfqs:
		state = get_bid_state(r, now=now)
		values = {"ub_bid_closed_notified": 1}
		# A stored "Open" means suppliers could bid right up to the deadline (a plain open RFQ, or a
		# Correction Required RFQ the buyer re-opened): stamp it Closed and tell the owner.
		if state.state == "closed" or (r.get("ub_bid_status") or "") == BID_OPEN:
			values["ub_bid_status"] = BID_CLOSED
			_notify_owner_closed(r, state)
		frappe.db.set_value(RFQ, r.name, values, update_modified=False)
		frappe.db.commit()


def _notify_owner_closed(r, state):
	quoted, quoted_ps = quoted_parties(r.name)
	count = len(quoted) + len(quoted_ps)
	if not r.owner or r.owner in ("Administrator", "Guest"):
		return
	email = frappe.db.get_value("User", r.owner, "email")
	if not email:
		return
	safe_sendmail(
		recipients=[email],
		subject=_("Bidding closed: RFQ {0} ({1} quotation(s) received)").format(r.name, count),
		message=_(
			"<p>Bidding for <strong>{0}</strong> closed on <strong>{1}</strong>.</p>"
			"<p><strong>{2}</strong> supplier(s) submitted a quotation. "
			'You can now <a href="{3}">compare the quotations</a> and send the RFQ for approval.</p>'
		).format(r.name, state.deadline_fmt, count, get_url(f"/quotation-comparison?rfq={r.name}")),
		reference_doctype=RFQ,
		reference_name=r.name,
	)


# ---------------------------------------------------------------------------
# A-13.3 Extend Deadline
# ---------------------------------------------------------------------------


def extension_roles():
	role = get_setting("deadline_extension_role", default="Purchase Manager") or "Purchase Manager"
	return {role, "System Manager"}


@frappe.whitelist()
def extend_bid_deadline(rfq_name, new_deadline, reason=None):
	"""Purchase Manager moves the deadline forward: history row, bidding re-opens, suppliers are
	emailed. Tokens are NOT regenerated, so every link already sent keeps working."""
	if not set(frappe.get_roles()) & extension_roles():
		frappe.throw(_("Only a Purchase Manager can extend the bid deadline."), frappe.PermissionError)
	doc = frappe.get_doc(RFQ, rfq_name)
	doc.check_permission("write")

	reason = (reason or "").strip()
	if not reason:
		frappe.throw(_("Please give a reason for the extension. Suppliers are told about it."))
	if doc.docstatus != 1:
		frappe.throw(_("Only a submitted RFQ can have its bid deadline extended."))
	state = get_bid_state(doc)
	if state.state in ("awarded", "rejected", "cancelled"):
		frappe.throw(
			_("The bid deadline cannot be extended while the RFQ is {0}.").format(state.label.lower()),
			title=_("Extension not allowed"),
		)
	# Pending approval: the comparison the approvers look at must not change. Correction Required is
	# the one evaluation state the buyer owns again, so extending there re-opens bidding.
	if state.state == "under_evaluation" and doc.workflow_state != STATE_CORRECTION:
		frappe.throw(
			_(
				"The bid deadline cannot be extended while the RFQ is pending approval. "
				"Ask the approver to send it back for correction first."
			),
			title=_("Extension not allowed"),
		)

	new_dt = get_datetime(new_deadline)
	old_dt = get_datetime(doc.ub_bid_deadline) if doc.ub_bid_deadline else None
	if new_dt <= now_datetime():
		frappe.throw(_("The new bid deadline must be in the future."))
	if old_dt and new_dt <= old_dt:
		frappe.throw(
			_("The new bid deadline must be later than the current one ({0}).").format(
				frappe.format(old_dt, {"fieldtype": "Datetime"})
			)
		)

	doc.append(
		"ub_deadline_history",
		{
			"old_deadline": old_dt,
			"new_deadline": new_dt,
			"reason": reason,
			"extended_by": frappe.session.user,
			"extended_on": now_datetime(),
		},
	)
	doc.ub_bid_deadline = new_dt
	doc.ub_bid_status = BID_OPEN
	doc.ub_bid_reminder_sent = 0
	doc.ub_bid_closed_notified = 0
	doc.flags.ignore_validate_update_after_submit = True
	doc.flags.ub_skip_state_mail = True
	doc.save(ignore_permissions=True)
	doc.add_comment(
		"Comment",
		_("Bid deadline extended from {0} to {1}: {2}").format(
			frappe.format(old_dt, {"fieldtype": "Datetime"}) if old_dt else _("none"),
			frappe.format(new_dt, {"fieldtype": "Datetime"}),
			frappe.utils.escape_html(reason),
		),
	)

	notified, mail_failed = _notify_suppliers_of_extension(doc, old_dt, new_dt, reason)
	return {
		"new_deadline": str(new_dt),
		"new_deadline_fmt": format_bid_deadline(new_dt),
		"notified": notified,
		"mail_failed": mail_failed,
		"bid_state": get_bid_state(doc).state,
	}


def _notify_suppliers_of_extension(doc, old_dt, new_dt, reason):
	new_fmt = format_bid_deadline(new_dt)
	old_fmt = format_bid_deadline(old_dt) if old_dt else _("no deadline")
	sent, failed = [], []
	for row in doc.suppliers:
		email = row_email(row)
		if not email:
			continue
		ok = safe_sendmail(
			recipients=[email],
			subject=_("Bid deadline extended: RFQ {0} now closes on {1}").format(doc.name, new_fmt),
			message=_(
				"<p>Dear {0},</p>"
				"<p>The bid deadline for <strong>Request for Quotation {1}</strong> has been extended "
				"from {2} to <strong>{3}</strong>.</p>"
				"<p><strong>Reason:</strong> {4}</p>"
				'<p>You can <a href="{5}">submit or revise your quotation</a> until the new deadline.</p>'
				"<p>Best regards,<br>{6}</p>"
			).format(
				frappe.utils.escape_html(row.supplier_name or row.supplier or row.ub_prospective_supplier or "Supplier"),
				doc.name,
				old_fmt,
				new_fmt,
				frappe.utils.escape_html(reason),
				supplier_link(doc.name, row),
				doc.company,
			),
			reference_doctype=RFQ,
			reference_name=doc.name,
		)
		(sent if ok else failed).append(email)
	return sent, failed
