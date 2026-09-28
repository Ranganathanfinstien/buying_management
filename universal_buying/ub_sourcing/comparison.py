"""Quotation Comparison and Award (BRD v2 6.15). Page: www/quotation-comparison.html.

* One column per LIVE quotation (not cancelled, not superseded by a newer version).
* Items and rates, landed total (lowest highlighted), lead time, MOQ / SPQ, payment terms, technical
  specs, supplier approval status, current approved Item Price and the difference against it.
* V-15.1 award only in the final approval state, by ``award_role`` (setting).
* A-15.1 award approves + submits the winner, rejects the others, sets the RFQ to Awarded, emails the
  purchase team. A-15.2 prospective winner -> Supplier Onboarding (ub_supplier contract).
"""

import frappe
from frappe import _
from frappe.model.workflow import apply_workflow
from frappe.utils import escape_html, flt, get_url, now_datetime

from universal_buying.ub_sourcing.workflow import (
	ACTION_APPROVE,
	ACTION_AWARD,
	ACTION_REJECT,
	STATE_APPROVED,
	STATE_AWARDED,
	STATE_DRAFT,
	STATE_REJECTED,
	get_award_role,
	get_final_state,
	get_tiers,
)

RFQ = "Request for Quotation"
SQ = "Supplier Quotation"

VIEW_ROLES = {"Purchase User", "Purchase Manager", "System Manager"}


def viewer_roles():
	return VIEW_ROLES | {get_award_role()} | {role for role, _st in get_tiers()}


def recommender_roles():
	return {"Purchase Manager", "System Manager"} | {role for role, _st in get_tiers()}


def _assert_can_view():
	if frappe.session.user == "Guest":
		frappe.throw(_("Please log in to view the quotation comparison."), frappe.PermissionError)
	if not set(frappe.get_roles()) & viewer_roles():
		frappe.throw(_("You do not have permission to view this page."), frappe.PermissionError)


def live_quotations(rfq_name):
	"""Names of the live quotations of an RFQ, in submission order."""
	return frappe.db.sql(
		"""
		SELECT DISTINCT sq.name FROM `tabSupplier Quotation` sq
		JOIN `tabSupplier Quotation Item` sqi ON sqi.parent = sq.name
		WHERE sqi.request_for_quotation = %s AND sq.docstatus < 2 AND IFNULL(sq.ub_revised, 0) = 0
		ORDER BY sq.creation, sq.name
		""",
		(rfq_name,),
		pluck=True,
	)


def _supplier_status(sq):
	if sq.supplier:
		from universal_buying.universal_buying.utils import supplier_is_enabled

		state = frappe.db.get_value("Supplier", sq.supplier, "workflow_state") if frappe.get_meta(
			"Supplier").has_field("workflow_state") else None
		return {"label": state or (_("Enabled") if supplier_is_enabled(sq.supplier) else _("Not approved")),
			"ok": supplier_is_enabled(sq.supplier)}
	if sq.get("ub_prospective_supplier"):
		status = frappe.db.get_value("Prospective Supplier", sq.ub_prospective_supplier, "status") if frappe.db.exists(
			"DocType", "Prospective Supplier") and frappe.get_meta("Prospective Supplier").has_field("status") else None
		return {"label": _("Prospective") + (f" ({status})" if status else ""), "ok": False}
	return {"label": "-", "ok": False}


def _current_price(item_code, company, uom, cache):
	"""Winning buying Item Price (ub_planning contract), tolerant to that module being absent."""
	if not item_code:
		return None
	key = (item_code, uom)
	if key in cache:
		return cache[key]
	price = None
	try:
		from universal_buying.ub_planning.api import get_current_item_price

		price = get_current_item_price(item_code, company=company, uom=uom)
	except ImportError:
		price = None
	except Exception:
		frappe.log_error(title="Quotation comparison: current price lookup failed", message=frappe.get_traceback())
		price = None
	if price:
		price = frappe._dict(price)
		company_currency = frappe.get_cached_value("Company", company, "default_currency")
		rate = flt(price.get("price_list_rate"))
		if price.get("currency") and price.currency != company_currency:
			from erpnext.setup.utils import get_exchange_rate

			rate = rate * flt(get_exchange_rate(price.currency, company_currency) or 0)
		price.base_rate = rate
	cache[key] = price
	return price


def build_context(context):
	rfq_name = frappe.form_dict.get("rfq")
	if not rfq_name:
		frappe.throw(_("RFQ not specified."), frappe.PermissionError)
	_assert_can_view()
	rfq = frappe.get_doc(RFQ, rfq_name)
	rfq.check_permission("read")

	roles = set(frappe.get_roles())
	award_role = get_award_role()
	final_state = get_final_state()
	wf_state = rfq.get("workflow_state") or ""
	base = {
		"rfq": rfq,
		"rfq_name": rfq.name,
		"title": _("Quotation Comparison - {0}").format(rfq.name),
		"workflow_state": wf_state,
		"final_state": final_state,
		"award_role": award_role,
		"can_award": award_role in roles and wf_state == final_state and rfq.docstatus == 1,
		"can_recommend": bool(roles & recommender_roles()) and wf_state not in (STATE_AWARDED, STATE_REJECTED),
		"awarded_quotation": rfq.get("ub_awarded_quotation") or "",
		"award_remarks": rfq.get("ub_award_remarks") or "",
		"awarded_by": rfq.get("ub_awarded_by") or "",
		"awarded_on": frappe.format(rfq.get("ub_awarded_on"), {"fieldtype": "Datetime"}) if rfq.get("ub_awarded_on") else "",
		"company_currency": frappe.get_cached_value("Company", rfq.company, "default_currency"),
		"no_cache": 1,
	}
	context.update(base)

	names = live_quotations(rfq.name)
	if not names:
		context.no_quotations = True
		return
	quotes = [frappe.get_doc(SQ, n) for n in names]

	rfq_items = [frappe._dict({
		"name": it.name,
		"idx": it.idx,
		"item_code": it.item_code or "",
		"description": it.item_name or it.get("ub_item_description") or it.description or "",
		"qty": it.qty,
		"uom": it.uom or "",
	}) for it in rfq.items]

	price_cache = {}
	cells = {}  # {sq: {rfq_item: {...}}}
	for sq in quotes:
		m = cells.setdefault(sq.name, {})
		for d in sq.items:
			if not d.request_for_quotation_item:
				continue
			current = _current_price(d.item_code, rfq.company, d.uom, price_cache)
			diff = None
			if current and flt(current.base_rate):
				diff = flt(d.base_rate) - flt(current.base_rate)
			m[d.request_for_quotation_item] = frappe._dict({
				"qty": d.qty, "uom": d.uom, "rate": d.base_rate, "amount": d.base_amount,
				"remarks": d.get("ub_remarks") or "", "moq": d.get("ub_moq"), "spq": d.get("ub_spq"),
				"lead_time_days": d.get("lead_time_days"),
				"current_rate": current.base_rate if current else None,
				"current_supplier": current.get("supplier") if current else None,
				"diff": diff,
				"diff_pct": (diff / flt(current.base_rate) * 100) if diff is not None else None,
				"has_tax_template": bool(d.item_tax_template),
			})

	terms_params, terms_map, tech_params, tech_map = [], {}, [], {}
	for sq in quotes:
		for pt in sq.get("ub_payment_terms") or []:
			terms_map.setdefault(sq.name, {})[pt.term] = pt.percentage
			if pt.term and pt.term not in terms_params:
				terms_params.append(pt.term)
		for ts in sq.get("ub_technical_spec") or []:
			tech_map.setdefault(sq.name, {})[ts.parameter] = ts.value
			if ts.parameter and ts.parameter not in tech_params:
				tech_params.append(ts.parameter)

	lowest_total = min(flt(sq.base_grand_total) for sq in quotes)
	context.update({
		"quotes": quotes,
		"rfq_items": rfq_items,
		"cells": cells,
		"terms_params": terms_params,
		"terms_map": terms_map,
		"tech_params": tech_params,
		"tech_map": tech_map,
		"lowest_total": lowest_total,
		"supplier_status": {sq.name: _supplier_status(sq) for sq in quotes},
		"chat_rows": _chat_rows(rfq.name, quotes),
		"has_current_prices": any(c.current_rate for m in cells.values() for c in m.values()),
	})


def _chat_rows(rfq_name, quotes):
	"""{supplier quotation: RFQ supplier row} - the discussion thread shown under each column."""
	from universal_buying.ub_sourcing.chat import row_for_quotation

	out = {}
	for sq in quotes:
		row = row_for_quotation(sq.name, rfq_name)
		out[sq.name] = row.name if row else ""
	return out


# ---------------------------------------------------------------------------
# actions
# ---------------------------------------------------------------------------


@frappe.whitelist()
def save_hod_recommendation(sq_name, remarks):
	if not set(frappe.get_roles()) & recommender_roles():
		frappe.throw(_("You are not permitted to record a recommendation."), frappe.PermissionError)
	rfq_name = frappe.db.get_value("Supplier Quotation Item",
		{"parent": sq_name, "request_for_quotation": ["is", "set"]}, "request_for_quotation")
	if rfq_name and frappe.db.get_value(RFQ, rfq_name, "workflow_state") in (STATE_AWARDED, STATE_REJECTED):
		frappe.throw(_("The RFQ is already decided."))
	remarks = (remarks or "").strip()
	frappe.db.set_value(SQ, sq_name, "ub_hod_remarks", remarks)
	frappe.get_doc(SQ, sq_name).add_comment("Comment", _("Recommendation: {0}").format(escape_html(remarks)))
	return {"status": "ok"}


def _assert_award_allowed(rfq):
	award_role = get_award_role()
	if award_role not in frappe.get_roles():
		frappe.throw(_("Only users with the {0} role can decide this comparison.").format(award_role),
			frappe.PermissionError)
	final_state = get_final_state()
	if rfq.docstatus != 1 or rfq.get("workflow_state") != final_state:
		frappe.throw(
			_("The RFQ must be in the final approval state ({0}) to be decided. Current state: {1}").format(
				final_state, rfq.get("workflow_state") or "-"),
			title=_("Not in final approval"),
		)


@frappe.whitelist()
def award_quotation(rfq_name, sq_name, remarks=None):
	"""A-15.1: approve + submit the winner, reject the rest, RFQ -> Awarded, notify purchase team."""
	rfq = frappe.get_doc(RFQ, rfq_name)
	_assert_award_allowed(rfq)
	if not sq_name:
		frappe.throw(_("Please select a Supplier Quotation first."))
	live = live_quotations(rfq_name)
	if sq_name not in live:
		frappe.throw(_("{0} is not a live quotation of {1}.").format(sq_name, rfq_name))

	winner = frappe.get_doc(SQ, sq_name)
	if winner.supplier:
		from universal_buying.universal_buying.utils import assert_supplier_enabled

		assert_supplier_enabled(winner.supplier, _("award"))

	rfq.db_set({
		"ub_awarded_quotation": sq_name,
		"ub_award_remarks": remarks or "",
		"ub_awarded_by": frappe.session.user,
		"ub_awarded_on": now_datetime(),
	}, update_modified=False)

	if winner.get("workflow_state") != STATE_APPROVED:
		winner.flags.ignore_permissions = True
		winner.flags.ignore_mandatory = True
		apply_workflow(winner, ACTION_APPROVE)

	rejected = _reject_quotations(rfq_name, exclude=sq_name)

	rfq.reload()
	rfq.flags.ignore_permissions = True
	apply_workflow(rfq, ACTION_AWARD)

	warnings = []
	try:
		_notify_purchase_team(rfq_name, sq_name, "Awarded", remarks)
	except Exception:
		frappe.log_error(title="Quotation award: notification failed", message=frappe.get_traceback())
		warnings.append(_("The purchase team could not be emailed."))

	onboarding = None
	if winner.get("ub_prospective_supplier") and not winner.supplier:
		onboarding = _start_onboarding(winner.ub_prospective_supplier)
		if not onboarding:
			warnings.append(_("Supplier onboarding for {0} could not be started. Check the Error Log.").format(
				winner.ub_prospective_supplier))

	return {"status": "awarded", "sq_approved": sq_name, "sq_rejected": rejected, "onboarding": onboarding,
		"warning": " ".join(warnings) or None}


@frappe.whitelist()
def reject_rfq(rfq_name, remarks=None):
	"""Award role rejects the whole comparison in the final state (comment kept on the timeline)."""
	rfq = frappe.get_doc(RFQ, rfq_name)
	_assert_award_allowed(rfq)
	remarks = (remarks or "").strip()
	if not remarks:
		frappe.throw(_("Please give a reason for rejecting."))
	rfq.db_set({
		"ub_award_remarks": remarks,
		"ub_awarded_by": frappe.session.user,
		"ub_awarded_on": now_datetime(),
	}, update_modified=False)
	rfq.add_comment("Comment", _("Rejected from the quotation comparison: {0}").format(escape_html(remarks)))
	rfq.reload()
	rfq.flags.ignore_permissions = True
	apply_workflow(rfq, ACTION_REJECT)
	rejected = _reject_quotations(rfq_name)
	try:
		_notify_purchase_team(rfq_name, None, "Rejected", remarks)
	except Exception:
		frappe.log_error(title="Quotation reject: notification failed", message=frappe.get_traceback())
	return {"status": "rejected", "sq_rejected": rejected}


def _reject_quotations(rfq_name, exclude=None):
	"""Every draft quotation of the RFQ (superseded versions included) goes to Rejected."""
	names = frappe.db.sql(
		"""
		SELECT DISTINCT sq.name FROM `tabSupplier Quotation` sq
		JOIN `tabSupplier Quotation Item` sqi ON sqi.parent = sq.name
		WHERE sqi.request_for_quotation = %s AND sq.docstatus = 0 AND sq.name != %s
		""",
		(rfq_name, exclude or ""),
		pluck=True,
	)
	done = []
	for name in names:
		doc = frappe.get_doc(SQ, name)
		if (doc.get("workflow_state") or STATE_DRAFT) != STATE_DRAFT:
			continue
		doc.flags.ignore_permissions = True
		doc.flags.ignore_mandatory = True
		apply_workflow(doc, ACTION_REJECT)
		done.append(name)
	return done


def _start_onboarding(prospective_supplier):
	"""A-15.2 via the ub_supplier contract (imported lazily; worker A implements it)."""
	try:
		from universal_buying.ub_supplier.api import create_onboarding_from_prospective
	except ImportError:
		frappe.log_error(title="Quotation award: ub_supplier.api missing",
			message="create_onboarding_from_prospective is not available")
		return None
	try:
		return create_onboarding_from_prospective(prospective_supplier, send_email=1)
	except Exception:
		frappe.log_error(title="Quotation award: onboarding failed", message=frappe.get_traceback())
		return None


def _notify_purchase_team(rfq_name, sq_name, decision, remarks):
	from universal_buying.universal_buying.utils import notify_users, users_with_role

	# the RFQ owner gets the workflow state mail (notifications.notify_state_change)
	users = set(users_with_role("Purchase Manager")) | set(users_with_role("Purchase User"))
	color = "#276749" if decision == "Awarded" else "#822727"
	sq_line = f"<tr><td style='padding:4px 16px 4px 0;color:#718096;'>{_('Awarded Quotation')}</td><td><b>{sq_name}</b></td></tr>" if sq_name else ""
	message = (
		f"<p>{_('Quotation comparison for')} <b>{rfq_name}</b>: "
		f"<b style='color:{color};'>{_(decision)}</b>.</p>"
		f"<table style='border-collapse:collapse;font-size:13px;'>{sq_line}"
		f"<tr><td style='padding:4px 16px 4px 0;color:#718096;'>{_('Remarks')}</td><td>{escape_html(remarks or '-')}</td></tr>"
		"</table>"
		+ (f"<p>{_('Create the Purchase Order from the approved Supplier Quotation (Create > Purchase Order).')}</p>"
		   if sq_name else "")
		+ f"<p><a href='{get_url(f'/app/request-for-quotation/{rfq_name}')}'>{_('Open RFQ')}</a></p>"
	)
	notify_users(list(users), _("[{0}] Quotation Comparison - {1}").format(decision, rfq_name), message, RFQ, rfq_name)
