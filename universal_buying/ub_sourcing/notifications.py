"""RFQ emails: supplier invitations (A-13.1) and workflow state mails (A-13.4).

Fixes from the source app:
* workflow mails are keyed on the states of the workflow that is actually built (tiers from settings,
  Correction Required, Rejected, Awarded) instead of hard-coded state names that never matched;
* re-sending a portal link re-uses the supplier row's existing token, so earlier links keep working.
"""

import frappe
from frappe import _
from frappe.utils import escape_html, get_url

from universal_buying.ub_sourcing.workflow import (
	STATE_AWARDED,
	STATE_CORRECTION,
	STATE_REJECTED,
	get_tiers,
)

RFQ = "Request for Quotation"
RFQ_SUPPLIER = "Request for Quotation Supplier"


def supplier_portal_url():
	"""Landing page for registered (logged-in) suppliers. The supplier portal itself is owned by
	ub_ordering (www/supplier_portal); the login page redirects there after sign-in."""
	return get_url("/supplier_portal")


def comparison_url(rfq_name):
	return get_url(f"/quotation-comparison?rfq={rfq_name}")


# ---------------------------------------------------------------------------
# tokens
# ---------------------------------------------------------------------------


def ensure_row_token(row):
	"""Return the row's token, creating one only when the row has none (never regenerates)."""
	token = row.get("ub_rfq_token") or frappe.db.get_value(RFQ_SUPPLIER, row.name, "ub_rfq_token")
	if not token:
		token = frappe.generate_hash(length=32)
		frappe.db.set_value(RFQ_SUPPLIER, row.name, "ub_rfq_token", token, update_modified=False)
	row.ub_rfq_token = token
	return token


def is_prospective_row(row):
	"""Prospective until Supplier Onboarding links a Supplier (it then fills ``supplier`` and keeps the
	prospective link for traceability)."""
	return bool(row.get("ub_prospective_supplier")) and not row.get("supplier")


def _row_display_name(row):
	if is_prospective_row(row):
		ps = frappe.db.get_value(
			"Prospective Supplier", row.ub_prospective_supplier, ["supplier_name", "contact_person"], as_dict=True
		) or frappe._dict()
		return row.supplier_name or ps.contact_person or ps.supplier_name or row.ub_prospective_supplier
	return row.supplier_name or row.supplier


def _resolve_email(row):
	email = row.get("email_id")
	if not email and row.get("ub_prospective_supplier"):
		email = frappe.db.get_value("Prospective Supplier", row.ub_prospective_supplier, "email")
	if not email and row.get("contact"):
		email = frappe.db.get_value("Contact", row.contact, "email_id")
	if not email and row.get("supplier"):
		# row without a picked contact (RFQ made outside the desk form): the supplier's primary contact,
		# the supplier email, else its first portal user (who logs in to quote)
		sup = frappe.db.get_value("Supplier", row.supplier, ["supplier_primary_contact", "email_id"], as_dict=True) or {}
		if sup.get("supplier_primary_contact"):
			email = frappe.db.get_value("Contact", sup.supplier_primary_contact, "email_id")
		email = email or sup.get("email_id") or frappe.db.get_value(
			"Portal User", {"parent": row.supplier, "parenttype": "Supplier"}, "user", order_by="idx asc")
	return email


def _items_table(rfq):
	rows = "".join(
		"<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
			item.idx,
			escape_html(item.item_name or item.get("ub_item_description") or item.item_code or ""),
			item.qty,
			escape_html(item.uom or ""),
		)
		for item in rfq.items
	)
	return (
		"<table border='1' cellpadding='4' cellspacing='0' style='border-collapse:collapse;width:100%'>"
		"<tr><th>#</th><th>Item / Description</th><th>Qty</th><th>UOM</th></tr>" + rows + "</table>"
	)


def _deadline_line(rfq):
	from universal_buying.ub_sourcing.bidding import format_bid_deadline

	fmt = format_bid_deadline(rfq.get("ub_bid_deadline"))
	return f"<br><strong>{_('Bid Deadline')}:</strong> {fmt}" if fmt else ""


# ---------------------------------------------------------------------------
# A-13.1 supplier invitations
# ---------------------------------------------------------------------------


def send_prospective_links(rfq, only_unsent=True):
	"""One-time token link to every prospective supplier row. Existing tokens are re-used."""
	results = []
	for row in rfq.suppliers:
		if not is_prospective_row(row):
			continue
		if only_unsent and row.get("email_sent"):
			continue
		display_name = _row_display_name(row)
		email = _resolve_email(row)
		if not email:
			results.append({"status": "failed", "display_name": display_name, "is_prospective": True,
				"error": _("No email address found")})
			continue
		try:
			token = ensure_row_token(row)
			link = get_url(f"/rfq-portal?token={token}")
			message = _(
				"<p>Dear {supplier_name},</p>"
				"<p>We would like to invite you to submit a quotation for the following items/services.</p>"
				"<p><strong>RFQ No:</strong> {rfq}<br><strong>Date:</strong> {date}{deadline}</p>"
				"{items}{msg}"
				"<p>Please use the button below to open the quotation portal and enter your rates.</p>"
				'<p style="text-align:center;margin:24px 0;"><a href="{link}" style="background:#1a73e8;color:#fff;'
				'padding:12px 28px;border-radius:5px;text-decoration:none;font-size:15px;">Submit Your Quotation</a></p>'
				'<p style="color:#888;font-size:12px;">This link is unique to you. Keep it: you can use it to revise '
				"your quotation until the bid deadline.</p><p>Regards,<br>{company}</p>"
			).format(
				supplier_name=escape_html(display_name),
				rfq=rfq.name,
				date=frappe.format(rfq.transaction_date, {"fieldtype": "Date"}),
				deadline=_deadline_line(rfq),
				items=_items_table(rfq),
				msg=f"<p>{rfq.message_for_supplier}</p>" if rfq.message_for_supplier else "",
				link=link,
				company=escape_html(rfq.company),
			)
			frappe.sendmail(recipients=[email], subject=_("Request for Quotation - {0}").format(rfq.name),
				message=message, reference_doctype=RFQ, reference_name=rfq.name, now=False)
			frappe.db.set_value(RFQ_SUPPLIER, row.name, {"email_sent": 1, "email_id": email}, update_modified=False)
			row.email_sent = 1
			row.email_id = email
			results.append({"status": "sent", "display_name": display_name, "is_prospective": True,
				"email": email, "portal_link": link})
		except Exception:
			frappe.log_error(title="RFQ Portal Link Error", message=frappe.get_traceback())
			results.append({"status": "failed", "display_name": display_name, "is_prospective": True,
				"error": _("Unknown error - check Error Log")})
	return results


def send_registered_supplier_emails(rfq, only_unsent=True):
	"""'New RFQ available in the Supplier Portal' to registered suppliers (portal login, no token)."""
	results = []
	schedule_dates = [d.schedule_date for d in rfq.items if d.schedule_date]
	required_date = min(schedule_dates) if schedule_dates else rfq.transaction_date
	for row in rfq.suppliers:
		if is_prospective_row(row) or not row.get("supplier"):
			continue
		if only_unsent and row.get("email_sent"):
			continue
		display_name = _row_display_name(row)
		email = _resolve_email(row)
		if not email:
			results.append({"status": "failed", "display_name": display_name, "is_prospective": False,
				"error": _("No email address found")})
			continue
		try:
			message = _(
				"<p>Dear {supplier_name},</p>"
				"<p>A new Request for Quotation is available for you in the Supplier Portal.</p>"
				"<p><strong>RFQ No:</strong> {rfq}<br><strong>Required Date:</strong> {required}{deadline}</p>"
				"{items}"
				"<p>Please log in to the portal, review the RFQ and submit your best quotation.</p>"
				'<p style="text-align:center;margin:24px 0;"><a href="{link}" style="background:#1a73e8;color:#fff;'
				'padding:12px 28px;border-radius:5px;text-decoration:none;font-size:15px;">Log in to Supplier Portal</a></p>'
				"<p>Best regards,<br>{company}</p>"
			).format(
				supplier_name=escape_html(display_name),
				rfq=rfq.name,
				required=frappe.format(required_date, {"fieldtype": "Date"}) if required_date else "",
				deadline=_deadline_line(rfq),
				items=_items_table(rfq),
				link=supplier_portal_url(),
				company=escape_html(rfq.company),
			)
			frappe.sendmail(recipients=[email], subject=_("New Request for Quotation - {0}").format(rfq.name),
				message=message, reference_doctype=RFQ, reference_name=rfq.name, now=False)
			frappe.db.set_value(RFQ_SUPPLIER, row.name, {"email_sent": 1, "email_id": email}, update_modified=False)
			row.email_sent = 1
			row.email_id = email
			results.append({"status": "sent", "display_name": display_name, "is_prospective": False, "email": email})
		except Exception:
			frappe.log_error(title="RFQ Supplier Email Error", message=frappe.get_traceback())
			results.append({"status": "failed", "display_name": display_name, "is_prospective": False,
				"error": _("Unknown error - check Error Log")})
	return results


def invite_suppliers(rfq, only_unsent=True):
	"""A-13.1 at Open. Replaces ERPNext's standard supplier email."""
	return send_prospective_links(rfq, only_unsent) + send_registered_supplier_emails(rfq, only_unsent)


# ---------------------------------------------------------------------------
# A-13.4 workflow state mails
# ---------------------------------------------------------------------------


def _user_email(user):
	if not user or user in ("Administrator", "Guest"):
		return None
	return frappe.db.get_value("User", {"name": user, "enabled": 1}, "email") or None


def _role_emails(roles):
	from universal_buying.universal_buying.utils import users_with_role

	actor = frappe.session.user
	emails, seen = [], set()
	for role in roles:
		for user in users_with_role(role):
			if user in (actor, "Administrator"):
				continue
			email = _user_email(user)
			if email and email.lower() not in seen:
				seen.add(email.lower())
				emails.append(email)
	return emails


def _send(doc, recipients, subject, message):
	recipients = [e for e in recipients if e]
	if not recipients:
		return False
	from universal_buying.ub_sourcing.bidding import safe_sendmail

	return safe_sendmail(recipients=recipients, subject=subject, message=message,
		reference_doctype=doc.doctype, reference_name=doc.name)


def _body(doc, title, intro, accent="#2c3e50", button=None):
	actor = frappe.db.get_value("User", frappe.session.user, "full_name") if frappe.session.user else None
	btn = ""
	if button:
		btn = (f'<p style="margin:20px 0;"><a href="{button[1]}" style="background:{accent};color:#fff;'
			f'padding:10px 22px;border-radius:5px;text-decoration:none;">{button[0]}</a></p>')
	return (
		f'<div style="font-family:Arial,sans-serif;font-size:14px;color:#333;">'
		f'<h3 style="color:{accent};margin:0 0 12px;">{escape_html(title)}</h3>'
		f"<p>{intro}</p>"
		f"<p><strong>{_('RFQ')}:</strong> {doc.name}<br><strong>{_('Company')}:</strong> {escape_html(doc.company)}"
		f"<br><strong>{_('State')}:</strong> {escape_html(doc.get('workflow_state') or '')}"
		+ (f"<br><strong>{_('Action by')}:</strong> {escape_html(actor)}" if actor else "")
		+ f"</p>{btn}"
		f'<p><a href="{get_url(f"/app/request-for-quotation/{doc.name}")}">{_("Open the RFQ")}</a></p></div>'
	)


def notify_state_change(doc, old_state, new_state):
	"""Mail for every state of the built workflow. Open is handled by invite_suppliers()."""
	if not new_state or old_state == new_state or doc.flags.get("ub_skip_state_mail"):
		return
	tiers = dict((st, role) for role, st in get_tiers())
	if new_state in tiers:
		recipients = _role_emails([tiers[new_state]])
		_send(
			doc, recipients,
			_("[{0}] RFQ approval pending - {1}").format(doc.name, new_state),
			_body(doc, _("Approval pending: {0}").format(new_state),
				_("Request for Quotation <b>{0}</b> is waiting for your decision. Review the quotation "
				  "comparison and approve, reject or send it back for correction.").format(doc.name),
				button=(_("Open Quotation Comparison"), comparison_url(doc.name))),
		)
	elif new_state == STATE_CORRECTION:
		_send(doc, [_user_email(doc.owner)], _("[{0}] RFQ sent back for correction").format(doc.name),
			_body(doc, _("Sent back for correction"),
				_("Your Request for Quotation <b>{0}</b> was sent back for correction. See the timeline for the "
				  "reason, make the changes and resubmit.").format(doc.name)))
	elif new_state == STATE_REJECTED:
		_send(doc, [_user_email(doc.owner)], _("[{0}] RFQ rejected").format(doc.name),
			_body(doc, _("RFQ rejected"), _("Your Request for Quotation <b>{0}</b> was rejected.").format(doc.name),
				accent="#c0392b"))
	elif new_state == STATE_AWARDED:
		_send(doc, [_user_email(doc.owner)], _("[{0}] RFQ awarded").format(doc.name),
			_body(doc, _("RFQ awarded"),
				_("Request for Quotation <b>{0}</b> was awarded to quotation <b>{1}</b>. Create the Purchase Order "
				  "from the approved Supplier Quotation.").format(doc.name, doc.get("ub_awarded_quotation") or ""),
				accent="#27ae60"))
