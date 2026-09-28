"""RFQ Portal (BRD v2 6.14): token / guest quoting and Supplier Quotation creation.

The page lives at ``www/rfq-portal.html`` (context from ``www/rfq_portal.py``); every endpoint is here.

Tax rules (india_compliance is NOT a dependency):
* HSN/SAC is asked for and validated only when the "GST HSN Code" doctype exists (and Supplier
  Quotation Item has ``gst_hsn_code``).
* A tax template is required on every priced line only when the company has Item Tax Templates;
  otherwise it may stay blank.
* Taxes on the quotation: India Compliance's GST details when that app is installed, else the company's
  default Purchase Taxes and Charges Template plus a row for every account used by the chosen Item Tax
  Templates. The live preview and the submit use exactly the same builder.

A-14.2: a new submission supersedes the party's earlier live quotations (``ub_revised``).
A-14.3: e-mail confirmation + one-time code (``otp_minutes``) to view an earlier submission.
"""

import json
import secrets

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, escape_html, flt, nowdate

from universal_buying.ub_sourcing.bidding import assert_bid_open, get_bid_state
from universal_buying.ub_sourcing.notifications import is_prospective_row
from universal_buying.universal_buying.settings import get_setting
from universal_buying.universal_buying.utils import as_system_user

RFQ = "Request for Quotation"
RFQ_SUPPLIER = "Request for Quotation Supplier"
SQ = "Supplier Quotation"
HSN_DOCTYPE = "GST HSN Code"

_ROW_FIELDS = ["name", "parent", "supplier", "supplier_name", "email_id", "ub_prospective_supplier", "ub_rfq_token"]


# ---------------------------------------------------------------------------
# lookups
# ---------------------------------------------------------------------------


def get_row_by_token(token, throw=True):
	"""The RFQ supplier row a token belongs to (None / PermissionError when unknown)."""
	token = (token or "").strip()
	row = None
	if token:
		row = frappe.db.get_value(RFQ_SUPPLIER, {"ub_rfq_token": token, "parenttype": RFQ}, _ROW_FIELDS, as_dict=True)
	if not row and throw:
		frappe.throw(_("This link is invalid or has expired."), frappe.PermissionError)
	return row


def get_active_rfq(row):
	rfq = frappe.get_doc(RFQ, row.parent)
	if rfq.docstatus == 2:
		frappe.throw(_("This Request for Quotation is no longer active."))
	return rfq


def hsn_enabled():
	return bool(frappe.db.exists("DocType", HSN_DOCTYPE)) and frappe.get_meta("Supplier Quotation Item").has_field(
		"gst_hsn_code"
	)


def tax_options(company):
	filters = {"company": company}
	if frappe.get_meta("Item Tax Template").has_field("disabled"):
		filters["disabled"] = 0
	return frappe.get_all("Item Tax Template", filters=filters, pluck="name", order_by="name")


def tax_required(company):
	return bool(tax_options(company))


def _ps_details(prospective_supplier):
	"""Prospective Supplier fields that exist on this site (worker A owns the doctype)."""
	if not prospective_supplier or not frappe.db.exists("DocType", "Prospective Supplier"):
		return frappe._dict()
	meta = frappe.get_meta("Prospective Supplier")
	wanted = ["supplier_name", "contact_person", "email", "address_line1", "address_line2", "city", "state",
		"country", "pincode", "gstin", "gst_category"]
	fields = [f for f in wanted if meta.has_field(f)]
	return frappe.db.get_value("Prospective Supplier", prospective_supplier, fields, as_dict=True) or frappe._dict()


def party_quotations(rfq_name, supplier=None, prospective_supplier=None):
	"""All non-cancelled quotations of one party on an RFQ, oldest first."""
	if prospective_supplier:
		field, value = "ub_prospective_supplier", prospective_supplier
	elif supplier:
		field, value = "supplier", supplier
	else:
		return []
	return frappe.db.sql(
		f"""
		SELECT sq.name, sq.creation, sq.docstatus, sq.ub_portal_revision, sq.ub_revised,
		       sq.ub_revision_requested, sq.ub_revision_reason, sq.workflow_state
		FROM `tabSupplier Quotation` sq
		WHERE sq.`{field}` = %s AND sq.docstatus < 2
		  AND EXISTS (SELECT 1 FROM `tabSupplier Quotation Item` sqi
		              WHERE sqi.parent = sq.name AND sqi.request_for_quotation = %s)
		ORDER BY sq.creation ASC, sq.name ASC
		""",
		(value, rfq_name),
		as_dict=True,
	)


def _hsn_label(code):
	if not code or not hsn_enabled():
		return ""
	desc = frappe.db.get_value(HSN_DOCTYPE, code, "description") or ""
	return f"{code} - {desc}" if desc else code


def _item_defaults(item, company):
	"""Default HSN / tax template for an RFQ line (from the Item master when there is an item code)."""
	hsn, tax = "", ""
	if item.item_code:
		if hsn_enabled() and frappe.get_meta("Item").has_field("gst_hsn_code"):
			hsn = frappe.db.get_value("Item", item.item_code, "gst_hsn_code") or ""
		tax = frappe.db.get_value(
			"Item Tax", {"parent": item.item_code, "parenttype": "Item"}, "item_tax_template", order_by="idx asc"
		) or ""
		if tax and frappe.db.get_value("Item Tax Template", tax, "company") != company:
			tax = ""
	return hsn, tax


# ---------------------------------------------------------------------------
# page context (www/rfq_portal.py)
# ---------------------------------------------------------------------------


def build_context(context):
	token = frappe.form_dict.get("token")
	if not token:
		context.error = _("No token provided. Please use the link from your email.")
		return
	row = get_row_by_token(token, throw=False)
	if not row:
		context.error = _("This link is invalid or has already been used.")
		return
	rfq = frappe.get_doc(RFQ, row.parent)
	if rfq.docstatus == 2:
		context.error = _("This Request for Quotation is no longer active.")
		return

	is_prospective = is_prospective_row(row)
	revisions = party_quotations(rfq.name, supplier=None if is_prospective else row.supplier,
		prospective_supplier=row.ub_prospective_supplier if is_prospective else None)
	if is_prospective:
		ps = _ps_details(row.ub_prospective_supplier)
		display_name = ps.get("contact_person") or ps.get("supplier_name") or row.supplier_name
	else:
		display_name = row.supplier_name or row.supplier

	items = []
	for item in rfq.items:
		hsn, tax = _item_defaults(item, rfq.company)
		items.append(frappe._dict({
			"idx": item.idx,
			"item_code": item.item_code or "",
			"item_name": item.item_name or item.get("ub_item_description") or "",
			"description": frappe.utils.strip_html(item.description or item.get("ub_item_description") or ""),
			"qty": item.qty,
			"uom": item.uom or "",
			"schedule_date": frappe.format(item.schedule_date, {"fieldtype": "Date"}) if item.schedule_date else "",
			"gst_hsn_code": hsn,
			"hsn_label": _hsn_label(hsn),
			"item_tax_template": tax,
		}))

	bid_state = get_bid_state(rfq)
	options = tax_options(rfq.company)
	revision_request = next((r for r in reversed(revisions) if r.ub_revision_requested and not r.ub_revised), None)
	context.update({
		"title": _("Request for Quotation {0}").format(rfq.name),
		"token": token,
		"rfq_name": rfq.name,
		"company": rfq.company,
		"transaction_date": frappe.format(rfq.transaction_date, {"fieldtype": "Date"}),
		"message_for_supplier": rfq.message_for_supplier or "",
		"terms": rfq.terms or "",
		"incoterm": rfq.get("incoterm") or "",
		"supplier_name": display_name,
		"is_prospective": is_prospective,
		"items": items,
		"existing_revisions": revisions,
		"next_revision": len(revisions),
		"revision_request": revision_request,
		"tax_options_json": frappe.as_json(options),
		"tax_required": bool(options),
		"hsn_enabled": hsn_enabled(),
		"closed": bid_state.closed,
		"closed_message": bid_state.message,
		"bid_state": bid_state.state,
		"bid_state_label": bid_state.label,
		"bid_deadline_fmt": bid_state.deadline_fmt,
		"currency": _quote_currency(rfq, row),
		"no_cache": 1,
	})


def _quote_currency(rfq, row):
	company_currency = frappe.get_cached_value("Company", rfq.company, "default_currency") or "INR"
	if row.get("supplier"):
		return frappe.db.get_value("Supplier", row.supplier, "default_currency") or company_currency
	return company_currency


# ---------------------------------------------------------------------------
# validation (V-14.2)
# ---------------------------------------------------------------------------


def validate_quote_items(item_map, company=None):
	"""Structured errors for a quote payload ({idx: {rate, hsn, item_tax_template, offered_qty}}).

	* a priced line (rate > 0) needs a quantity above 0                  -> qty / invalid
	* a priced line needs an HSN/SAC when HSN is enabled                 -> hsn / empty
	* a priced line needs a tax template when the company has any        -> tax / empty
	* any value given must exist (tax templates: of the RFQ company)     -> not_found
	Un-priced lines with nothing entered are skipped.
	"""
	check_hsn = hsn_enabled()
	valid_tax_list = tax_options(company) if company else None
	need_tax = bool(valid_tax_list) if company else True

	to_check, hsn_vals, tax_vals = [], set(), set()
	for idx, data in (item_map or {}).items():
		hsn = (data.get("hsn") or "").strip() if check_hsn else ""
		tax = (data.get("item_tax_template") or "").strip()
		qty = data.get("offered_qty")
		quoted = flt(data.get("rate")) > 0
		if not quoted and not hsn and not tax:
			continue
		to_check.append((cint(idx), hsn, tax, qty, quoted))
		if hsn:
			hsn_vals.add(hsn)
		if tax:
			tax_vals.add(tax)

	valid_hsn = set(frappe.get_all(HSN_DOCTYPE, filters={"name": ["in", list(hsn_vals)]}, pluck="name")) if hsn_vals else set()
	if valid_tax_list is not None:
		valid_tax = set(valid_tax_list) & tax_vals
	else:
		valid_tax = set(frappe.get_all("Item Tax Template", filters={"name": ["in", list(tax_vals)]}, pluck="name")) if tax_vals else set()

	errors = []
	for idx, hsn, tax, qty, quoted in to_check:
		if quoted and qty is not None and flt(qty) <= 0:
			errors.append({"idx": idx, "field": "qty", "type": "invalid", "value": qty})
		if check_hsn:
			if hsn:
				if hsn not in valid_hsn:
					errors.append({"idx": idx, "field": "hsn", "type": "not_found", "value": hsn})
			elif quoted:
				errors.append({"idx": idx, "field": "hsn", "type": "empty", "value": ""})
		if tax:
			if tax not in valid_tax:
				errors.append({"idx": idx, "field": "tax", "type": "not_found", "value": tax})
		elif quoted and need_tax:
			errors.append({"idx": idx, "field": "tax", "type": "empty", "value": ""})

	order = {"qty": 0, "hsn": 1, "tax": 2}
	errors.sort(key=lambda e: (e["idx"], order.get(e["field"], 9)))
	return errors


def format_quote_error(e):
	label = _("Item #{0}").format(e["idx"])
	if e["field"] == "qty":
		return _("{0}: Offered Qty must be greater than 0.").format(label)
	field = _("HSN/SAC") if e["field"] == "hsn" else _("Tax")
	if e["type"] == "not_found":
		return _("{0}: {1} '{2}' does not exist. Please contact the company.").format(
			label, field, escape_html(str(e["value"])))
	return _("{0}: {1} is required. Please select one from the list.").format(label, field)


def validate_quote_payload(item_map, company):
	if not any(flt(v.get("rate")) > 0 for v in (item_map or {}).values()):
		frappe.throw(_("Enter a rate for at least one item before submitting."))
	errors = validate_quote_items(item_map, company)
	if errors:
		frappe.throw(
			_("Please fix the following before submitting:") + "<br>&bull; "
			+ "<br>&bull; ".join(format_quote_error(e) for e in errors),
			title=_("Quotation validation"),
		)


def _offered_qty_or_none(payload):
	raw = payload.get("offered_qty")
	if raw in (None, ""):
		return None
	return flt(raw)


def _item_map(items, with_details=False):
	out = {}
	for i in items or []:
		entry = {
			"rate": flt(i.get("rate")),
			"hsn": (i.get("hsn") or "").strip(),
			"item_tax_template": (i.get("item_tax_template") or "").strip(),
			"offered_qty": _offered_qty_or_none(i),
		}
		if with_details:
			entry.update({
				"remarks": (i.get("remarks") or "").strip(),
				"moq": flt(i.get("moq")),
				"spq": flt(i.get("spq")),
			})
		out[str(cint(i.get("idx")))] = entry
	return out


# ---------------------------------------------------------------------------
# quotation builders (shared by preview and submit)
# ---------------------------------------------------------------------------


def apply_quote_items(sq, rfq, item_map):
	"""One Supplier Quotation Item per RFQ line."""
	for item in rfq.items:
		p = item_map.get(str(item.idx), {})
		rate = flt(p.get("rate"))
		offered_qty = flt(p.get("offered_qty"))
		if offered_qty <= 0:
			offered_qty = flt(item.qty)
		row = sq.append("items", {
			"item_code": item.item_code or None,
			"item_name": item.item_name or (item.get("ub_item_description") or "")[:140],
			"description": item.description or item.get("ub_item_description") or "",
			"ub_item_description": item.get("ub_item_description"),
			"qty": offered_qty,
			"ub_rfq_qty": flt(item.qty),
			"uom": item.uom or "Nos",
			"stock_uom": item.stock_uom or item.uom or "Nos",
			"conversion_factor": item.conversion_factor or 1,
			"rate": rate,
			"amount": rate * offered_qty,
			"warehouse": item.warehouse,
			"material_request": item.material_request,
			"material_request_item": item.material_request_item,
			"project": item.project_name,
			"request_for_quotation": rfq.name,
			"request_for_quotation_item": item.name,
			"ub_remarks": p.get("remarks") or "",
			"ub_moq": flt(p.get("moq")),
			"ub_spq": flt(p.get("spq")),
		})
		if item.get("schedule_date") and row.meta.has_field("expected_delivery_date"):
			row.expected_delivery_date = item.schedule_date


def _company_billing(company):
	from frappe.contacts.doctype.address.address import get_default_address

	address = get_default_address("Company", company) if company else None
	gstin = ""
	if address and frappe.get_meta("Address").has_field("gstin"):
		gstin = (frappe.db.get_value("Address", address, "gstin") or "").strip()
	if not gstin and frappe.get_meta("Company").has_field("gstin"):
		gstin = (frappe.db.get_value("Company", company, "gstin") or "").strip()
	return address, gstin


def _supplier_address(row, ps, create=False):
	"""Existing (or, for a prospective supplier on submit, newly created) address + GST info."""
	address_meta = frappe.get_meta("Address")
	has_gst = address_meta.has_field("gstin")
	prospective = is_prospective_row(row)
	link_doctype, link_name = ("Prospective Supplier", row.ub_prospective_supplier) if prospective else (
		"Supplier", row.supplier)
	existing = frappe.db.sql(
		"""
		SELECT a.name FROM `tabAddress` a JOIN `tabDynamic Link` dl ON dl.parent = a.name AND dl.parenttype = 'Address'
		WHERE dl.link_doctype = %s AND dl.link_name = %s
		ORDER BY a.is_primary_address DESC, a.creation ASC LIMIT 1
		""",
		(link_doctype, link_name),
		as_dict=True,
	)
	info = frappe._dict(address=None, gstin=ps.get("gstin") or "", gst_category=ps.get("gst_category") or "")
	if existing:
		info.address = existing[0].name
		if has_gst and not prospective:
			vals = frappe.db.get_value("Address", info.address, ["gstin", "gst_category"], as_dict=True) or {}
			info.gstin = vals.get("gstin") or ""
			info.gst_category = vals.get("gst_category") or ""
		return info
	if create and prospective and ps.get("address_line1"):
		addr = frappe.new_doc("Address")
		addr.address_title = ps.get("supplier_name") or row.ub_prospective_supplier
		addr.address_type = "Billing"
		addr.address_line1 = ps.get("address_line1")
		addr.address_line2 = ps.get("address_line2") or ""
		addr.city = ps.get("city") or "-"
		addr.state = ps.get("state") or ""
		addr.country = ps.get("country") or frappe.db.get_default("country") or "India"
		addr.pincode = ps.get("pincode") or ""
		if has_gst:
			addr.gstin = ps.get("gstin") or ""
			if address_meta.has_field("gst_category"):
				addr.gst_category = ps.get("gst_category") or "Unregistered"
		addr.is_primary_address = 1
		addr.append("links", {"link_doctype": "Prospective Supplier", "link_name": row.ub_prospective_supplier})
		addr.flags.ignore_mandatory = True
		addr.flags.ignore_permissions = True
		addr.insert()
		info.address = addr.name
	return info


def _india_compliance_installed():
	return "india_compliance" in frappe.get_installed_apps()


def apply_quote_taxes(sq, rfq, item_map, party, company_billing, company_gstin, tax_included=None):
	"""HSN / tax template per line, then the tax rows. ``party`` = _supplier_address() info."""
	from erpnext.controllers.accounts_controller import get_default_taxes_and_charges
	from erpnext.stock.get_item_details import get_item_tax_map

	check_hsn = hsn_enabled()
	allowed_tax = set(tax_options(rfq.company))
	for sq_item, rfq_item in zip(sq.items, rfq.items, strict=False):
		choice = item_map.get(str(rfq_item.idx), {})
		hsn = choice.get("hsn")
		if check_hsn and hsn and frappe.db.exists(HSN_DOCTYPE, hsn):
			sq_item.gst_hsn_code = hsn
		tax = choice.get("item_tax_template")
		if tax and tax in allowed_tax:
			sq_item.item_tax_template = tax

	inclusive = tax_included == "Included"
	taxes = []
	if _india_compliance_installed() and company_gstin:
		try:
			from india_compliance.gst_india.overrides.transaction import get_gst_details

			details = get_gst_details(frappe._dict({
				"supplier": sq.supplier or None,
				"supplier_address": party.address,
				"supplier_gstin": party.gstin or "",
				"gst_category": party.gst_category or "Unregistered",
				"company_gstin": company_gstin,
				"billing_address": company_billing,
				"is_reverse_charge": 0,
				"tax_category": "",
				"place_of_supply": "",
			}), SQ, rfq.company, update_place_of_supply=True)
			if details.get("place_of_supply") and sq.meta.has_field("place_of_supply"):
				sq.place_of_supply = details["place_of_supply"]
			if details.get("taxes_and_charges"):
				sq.taxes_and_charges = details["taxes_and_charges"]
				taxes = details.get("taxes") or []
		except Exception:
			frappe.log_error(title="RFQ portal: GST details failed", message=frappe.get_traceback())
			frappe.throw(_("Tax could not be applied to this quotation. Please try again or contact procurement."),
				title=_("Tax calculation failed"))
	else:
		default = get_default_taxes_and_charges("Purchase Taxes and Charges Template", company=rfq.company) or {}
		if default.get("taxes_and_charges"):
			sq.taxes_and_charges = default["taxes_and_charges"]
			taxes = default.get("taxes") or []

	for t in taxes:
		row = sq.append("taxes", t)
		if row.charge_type != "Actual":
			row.included_in_print_rate = 1 if inclusive else 0

	# every account the chosen item tax templates use needs a tax row, or the template has no effect
	existing = {t.account_head for t in sq.taxes}
	for sq_item in sq.items:
		if not sq_item.item_tax_template:
			continue
		sq_item.item_tax_rate = get_item_tax_map(doc=sq, tax_template=sq_item.item_tax_template, as_json=True)
		for account in json.loads(sq_item.item_tax_rate or "{}"):
			if account in existing:
				continue
			existing.add(account)
			sq.append("taxes", {
				"charge_type": "On Net Total",
				"account_head": account,
				"description": account,
				"rate": 0,
				"category": "Total",
				"add_deduct_tax": "Add",
				"set_by_item_tax_template": 1,
				"included_in_print_rate": 1 if inclusive else 0,
			})
	sq.flags.portal_zero_gst_untemplated = True


def _tax_row_label(tax_row):
	import re

	label = (tax_row.get("description") or tax_row.get("account_head") or "").strip()
	return re.sub(r"\s*@\s*[\d.]+\s*%?\s*$", "", label) or label


def _new_quotation(rfq, row, ps, party, company_billing, company_gstin):
	from erpnext.setup.utils import get_exchange_rate

	sq = frappe.new_doc(SQ)
	sq.company = rfq.company
	sq.transaction_date = nowdate()
	if row.ub_prospective_supplier:
		sq.ub_prospective_supplier = row.ub_prospective_supplier
	if is_prospective_row(row):
		sq.supplier_name = ps.get("supplier_name") or row.supplier_name or row.ub_prospective_supplier
	else:
		sq.supplier = row.supplier
		sq.supplier_name = row.supplier_name or row.supplier
	sq.ub_po_type = rfq.get("ub_po_type")
	company_currency = frappe.get_cached_value("Company", rfq.company, "default_currency") or "INR"
	sq.currency = _quote_currency(rfq, row)
	sq.conversion_rate = 1.0 if sq.currency == company_currency else (
		flt(get_exchange_rate(sq.currency, company_currency, sq.transaction_date)) or 1.0)
	sq.buying_price_list = frappe.db.get_single_value("Buying Settings", "buying_price_list") or "Standard Buying"
	plc = frappe.db.get_value("Price List", sq.buying_price_list, "currency") or company_currency
	sq.price_list_currency = plc
	sq.plc_conversion_rate = 1.0 if plc == company_currency else (
		flt(get_exchange_rate(plc, company_currency, sq.transaction_date)) or 1.0)
	if party.address:
		sq.supplier_address = party.address
	if party.gstin and sq.meta.has_field("supplier_gstin"):
		sq.supplier_gstin = party.gstin
	if party.gst_category and sq.meta.has_field("gst_category"):
		sq.gst_category = party.gst_category
	if company_billing:
		sq.billing_address = company_billing
	if company_gstin and sq.meta.has_field("company_gstin"):
		sq.company_gstin = company_gstin
	if rfq.get("incoterm"):
		sq.incoterm = rfq.incoterm
		sq.named_place = rfq.get("named_place")
	return sq


def _authorise(token=None, rfq_name=None):
	"""(row, rfq) for a token, or for the logged-in supplier's row on ``rfq_name``."""
	if token:
		row = get_row_by_token(token)
	else:
		from universal_buying.ub_sourcing.api import get_user_suppliers

		suppliers = get_user_suppliers()
		if not rfq_name or not suppliers:
			frappe.throw(_("You do not have access to this Request for Quotation."), frappe.PermissionError)
		row = frappe.db.get_value(RFQ_SUPPLIER, {"parent": rfq_name, "parenttype": RFQ, "supplier": ["in", suppliers]},
			_ROW_FIELDS, as_dict=True)
		if not row:
			frappe.throw(_("You do not have access to this Request for Quotation."), frappe.PermissionError)
	return row, get_active_rfq(row)


# ---------------------------------------------------------------------------
# endpoints
# ---------------------------------------------------------------------------


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=600, seconds=60 * 60)
def search_hsn_codes(txt=None, limit=20):
	"""Type-ahead over GST HSN Code (only when that doctype exists)."""
	if not hsn_enabled():
		return []
	txt = (txt or "").strip()
	limit = min(cint(limit) or 20, 50)
	if not txt:
		return frappe.get_all(HSN_DOCTYPE, fields=["name as code", "description"], order_by="name", limit=limit)
	return frappe.db.sql(
		f"""SELECT name AS code, description FROM `tab{HSN_DOCTYPE}`
		WHERE name LIKE %(like)s OR description LIKE %(like)s
		ORDER BY (name LIKE %(prefix)s) DESC, name ASC LIMIT %(limit)s""",
		{"like": f"%{txt}%", "prefix": f"{txt}%", "limit": limit},
		as_dict=True,
	)


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=600, seconds=60 * 60)
def preview_quote_taxes(items, token=None, rfq_name=None, tax_included=None):
	"""Totals for a quote that is NOT submitted yet, built with the submit builders (never inserted)."""
	items = json.loads(items or "[]") if isinstance(items, str) else items
	row, rfq = _authorise(token, rfq_name)
	item_map = _item_map(items)
	ps = _ps_details(row.ub_prospective_supplier) if is_prospective_row(row) else frappe._dict()
	party = _supplier_address(row, ps, create=False)
	company_billing, company_gstin = _company_billing(rfq.company)
	sq = _new_quotation(rfq, row, ps, party, company_billing, company_gstin)
	try:
		apply_quote_items(sq, rfq, item_map)
		apply_quote_taxes(sq, rfq, item_map, party, company_billing, company_gstin, tax_included)
		sq.calculate_taxes_and_totals()
	except Exception:
		frappe.log_error(title="RFQ portal tax preview failed", message=frappe.get_traceback())
		frappe.clear_last_message()
		return {"error": _("Could not calculate tax right now.")}
	return {
		"currency": sq.currency,
		"net_total": flt(sq.net_total),
		"taxes": [
			{"label": _tax_row_label(t), "rate": flt(t.rate), "amount": flt(t.tax_amount)}
			for t in (sq.taxes or []) if flt(t.tax_amount)
		],
		"total_taxes": flt(sq.total_taxes_and_charges),
		"grand_total": flt(sq.grand_total),
		"rounded_total": flt(sq.rounded_total),
		"untaxed_lines": sorted(
			rfq_item.idx for sq_item, rfq_item in zip(sq.items, rfq.items, strict=False)
			if flt(sq_item.rate) > 0 and not sq_item.item_tax_template
		),
	}


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=30, seconds=60 * 60)
def submit_portal_quotation(token, items, notes=None, lead_time_days=None, valid_till=None,
		quotation_number=None, freight_insurance=None, freight_insurance_desc=None,
		packing_forwarding=None, packing_forwarding_desc=None, installation=None, installation_desc=None,
		tax_included=None, payment_terms=None, technical_spec=None, quotation_attachment=None):
	"""A-14.1: create a draft Supplier Quotation from the portal (guest by token, or a logged-in supplier
	using the token from universal_buying.ub_sourcing.api.get_or_create_rfq_token)."""
	items = json.loads(items or "[]") if isinstance(items, str) else (items or [])
	payment_terms = json.loads(payment_terms or "[]") if isinstance(payment_terms, str) else (payment_terms or [])
	technical_spec = json.loads(technical_spec or "[]") if isinstance(technical_spec, str) else (technical_spec or [])

	row, rfq = _authorise(token)
	assert_bid_open(rfq)
	item_map = _item_map(items, with_details=True)
	validate_quote_payload(item_map, rfq.company)
	return create_portal_quotation(row, rfq, item_map, frappe._dict(
		notes=notes, lead_time_days=lead_time_days, valid_till=valid_till, quotation_number=quotation_number,
		freight_insurance=freight_insurance, freight_insurance_desc=freight_insurance_desc,
		packing_forwarding=packing_forwarding, packing_forwarding_desc=packing_forwarding_desc,
		installation=installation, installation_desc=installation_desc, tax_included=tax_included,
		payment_terms=payment_terms, technical_spec=technical_spec, quotation_attachment=quotation_attachment,
	))


def create_portal_quotation(row, rfq, item_map, data):
	"""Build + insert the Supplier Quotation, supersede older versions, confirm by e-mail."""
	from universal_buying.ub_sourcing.overrides.supplier_quotation import supersede_older_quotations

	is_prospective = is_prospective_row(row)
	previous = party_quotations(rfq.name, supplier=None if is_prospective else row.supplier,
		prospective_supplier=row.ub_prospective_supplier if is_prospective else None)
	revision = len(previous)

	ps = _ps_details(row.ub_prospective_supplier) if is_prospective else frappe._dict()
	party = _supplier_address(row, ps, create=True)
	company_billing, company_gstin = _company_billing(rfq.company)
	sq = _new_quotation(rfq, row, ps, party, company_billing, company_gstin)

	# terms: the buyer's RFQ terms win; the supplier's notes only when the RFQ has none
	if rfq.get("tc_name") or rfq.get("terms"):
		sq.tc_name = rfq.get("tc_name")
		sq.terms = rfq.get("terms") or ""
	else:
		sq.terms = escape_html(data.notes or "")

	sq.ub_portal_revision = revision
	if frappe.session.user and frappe.session.user != "Guest":
		sq.ub_raised_by = frappe.session.user
	if cint(data.lead_time_days) > 0:
		sq.ub_lead_time_days = cint(data.lead_time_days)
	if data.valid_till:
		sq.valid_till = data.valid_till
	if data.quotation_number:
		sq.quotation_number = (data.quotation_number or "")[:140]
	for field, desc in (("freight_insurance", "freight_insurance_desc"), ("packing_forwarding", "packing_forwarding_desc"),
			("installation", "installation_desc")):
		if data.get(field) in ("Included", "Excluded"):
			sq.set(f"ub_{field}", data.get(field))
			sq.set(f"ub_{desc}", data.get(desc) or "")

	apply_quote_items(sq, rfq, item_map)
	for pt in data.payment_terms or []:
		term = (pt.get("term") or "").strip()
		if term:
			sq.append("ub_payment_terms", {"term": term[:140], "percentage": flt(pt.get("percentage"))})
	for ts in data.technical_spec or []:
		param = (ts.get("parameter") or "").strip()
		if param:
			sq.append("ub_technical_spec", {"parameter": param[:140], "value": (ts.get("value") or "").strip()[:140]})
	apply_quote_taxes(sq, rfq, item_map, party, company_billing, company_gstin, data.tax_included)

	sq.flags.ignore_permissions = True
	sq.flags.ignore_mandatory = True
	# authorised by _authorise(); ERPNext v16 get_item_details checks Item read, which portal users lack
	with as_system_user():
		sq.insert()

	if data.quotation_attachment:
		_attach_file(sq, data.quotation_attachment)

	supersede_older_quotations(sq.name, rfq.name, supplier=None if is_prospective else row.supplier,
		prospective_supplier=row.ub_prospective_supplier if is_prospective else None)
	_confirm_to_supplier(row, ps, rfq, sq, revision)
	return {"sq_name": sq.name, "revision": revision}


def _attach_file(sq, file_url):
	"""Link a file the current uploader owns and that is still unattached (never hijack another file)."""
	name = frappe.db.get_value("File", {"file_url": file_url, "owner": frappe.session.user,
		"attached_to_doctype": ["is", "not set"]}, "name")
	if not name:
		return
	frappe.db.set_value("File", name, {"attached_to_doctype": SQ, "attached_to_name": sq.name,
		"attached_to_field": "ub_quotation_attachment"})
	frappe.db.set_value(SQ, sq.name, "ub_quotation_attachment", file_url, update_modified=False)


def _confirm_to_supplier(row, ps, rfq, sq, revision):
	email = row.email_id or ps.get("email")
	if not email:
		return
	from universal_buying.ub_sourcing.bidding import safe_sendmail

	name = ps.get("contact_person") or ps.get("supplier_name") or row.supplier_name or row.supplier or _("Sir/Madam")
	line = (_("We confirm receipt of your quotation against <strong>{0}</strong>.").format(rfq.name) if revision == 0
		else _("We confirm receipt of <strong>Version {0}</strong> of your quotation against <strong>{1}</strong>.").format(
			revision, rfq.name))
	safe_sendmail(
		recipients=[email],
		subject=(_("Quotation Received - {0}").format(rfq.name) if revision == 0
			else _("Version {0} Received - {1}").format(revision, rfq.name)),
		message=_("<p>Dear {0},</p><p>{1}</p><p><strong>Reference:</strong> {2}<br><strong>Date:</strong> {3}</p>"
			"<p>You can view it later from your RFQ link with a one-time code.</p><p>Thank you,<br>{4}</p>").format(
			escape_html(name), line, sq.name, frappe.utils.formatdate(nowdate()), escape_html(rfq.company)),
		reference_doctype=SQ,
		reference_name=sq.name,
	)


# ---------------------------------------------------------------------------
# A-14.3 one-time code to view an earlier submission
# ---------------------------------------------------------------------------


def _otp_key(token, sq_name):
	return f"ub_sq_view_otp:{token}:{sq_name}"


def _assert_owns_quotation(row, sq_name):
	field, value = ("ub_prospective_supplier", row.ub_prospective_supplier) if is_prospective_row(row) else (
		"supplier", row.supplier)
	if not value or frappe.db.get_value(SQ, sq_name, field) != value:
		frappe.throw(_("Access denied."), frappe.PermissionError)
	if not frappe.db.exists("Supplier Quotation Item", {"parent": sq_name, "request_for_quotation": row.parent}):
		frappe.throw(_("Access denied."), frappe.PermissionError)


def otp_minutes():
	return max(cint(get_setting("otp_minutes", default=10)), 1)


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=10, seconds=60 * 60)
def send_sq_view_otp(token, sq_name):
	row = get_row_by_token(token)
	_assert_owns_quotation(row, sq_name)
	email = row.email_id or (_ps_details(row.ub_prospective_supplier).get("email") if is_prospective_row(row) else None)
	if not email:
		frappe.throw(_("No email address found. Please contact the procurement team."))
	otp = f"{secrets.randbelow(900000) + 100000}"
	minutes = otp_minutes()
	frappe.cache.set_value(_otp_key(token, sq_name), otp, expires_in_sec=minutes * 60)
	frappe.sendmail(
		recipients=[email],
		subject=_("Code to view your quotation {0}").format(sq_name),
		message=_(
			"<p>Dear Supplier,</p><p>You asked to view your quotation <strong>{0}</strong>.</p>"
			'<p style="font-size:32px;font-weight:700;letter-spacing:8px;color:#1a73e8;text-align:center;">{1}</p>'
			"<p>The code is valid for <strong>{2} minutes</strong>. Do not share it.</p>"
		).format(sq_name, otp, minutes),
		now=True,
	)
	parts = email.split("@")
	masked = (parts[0][:2] + "***@" + parts[1]) if len(parts) == 2 else "***"
	return {"success": True, "masked_email": masked, "minutes": minutes}


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=20, seconds=60 * 60)
def verify_otp_and_get_sq(token, sq_name, otp):
	row = get_row_by_token(token)
	_assert_owns_quotation(row, sq_name)
	key = _otp_key(token, sq_name)
	stored = frappe.cache.get_value(key)
	if not stored:
		frappe.throw(_("The code has expired. Please request a new one."))
	if str(stored) != str(otp).strip():
		frappe.throw(_("Incorrect code. Please try again."))
	frappe.cache.delete_value(key)

	sq = frappe.get_doc(SQ, sq_name)
	return {
		"name": sq.name,
		"supplier_name": sq.supplier_name,
		"transaction_date": frappe.format(sq.transaction_date, {"fieldtype": "Date"}),
		"revision": sq.ub_portal_revision,
		"revised": sq.ub_revised,
		"currency": sq.currency,
		"net_total": flt(sq.net_total),
		"total_taxes": flt(sq.total_taxes_and_charges),
		"grand_total": flt(sq.grand_total),
		"terms": frappe.utils.strip_html(sq.terms or ""),
		"valid_till": frappe.format(sq.valid_till, {"fieldtype": "Date"}) if sq.valid_till else "",
		"lead_time_days": sq.ub_lead_time_days,
		"items": [{
			"idx": i.idx, "item_name": i.item_name or i.get("ub_item_description") or "", "qty": i.qty,
			"uom": i.uom or "", "rate": i.rate, "amount": i.amount, "remarks": i.get("ub_remarks") or "",
			"moq": i.get("ub_moq"), "spq": i.get("ub_spq"),
		} for i in sq.items],
		"payment_terms": [{"term": p.term, "percentage": p.percentage} for p in sq.get("ub_payment_terms") or []],
		"technical_spec": [{"parameter": t.parameter, "value": t.value} for t in sq.get("ub_technical_spec") or []],
	}


# ---------------------------------------------------------------------------
# Excel download / upload
# ---------------------------------------------------------------------------

_XL_HEADERS = ["#", "Description", "Qty", "Offered Qty", "UOM", "HSN/SAC", "Tax", "Rate", "MOQ", "SPQ", "Remarks"]


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=60, seconds=60 * 60)
def download_rfq_excel(token):
	"""Pre-filled .xlsx of the RFQ. #, Description, Qty and UOM are locked; the supplier edits the rest."""
	import math
	from io import BytesIO

	import openpyxl
	from openpyxl.styles import Alignment, Border, Font, PatternFill, Protection, Side
	from openpyxl.utils import get_column_letter
	from openpyxl.worksheet.datavalidation import DataValidation

	row = get_row_by_token(token)
	rfq = get_active_rfq(row)
	assert_bid_open(rfq)
	check_hsn = hsn_enabled()
	headers = [h for h in _XL_HEADERS if check_hsn or h != "HSN/SAC"]
	taxes = tax_options(rfq.company)

	wb = openpyxl.Workbook()
	ws = wb.active
	ws.title = "Quotation"
	lists = wb.create_sheet("Lists")
	for i, t in enumerate(taxes, start=1):
		lists.cell(row=i, column=1, value=t)
	lists.sheet_state = "hidden"

	thin = Side(style="thin", color="D0D7DE")
	border = Border(left=thin, right=thin, top=thin, bottom=thin)
	ws["A1"] = f"Request for Quotation - {rfq.name}"
	ws["A1"].font = Font(size=14, bold=True, color="1A73E8")
	ws["A2"] = "Company: {}    Date: {}    Supplier: {}".format(
		rfq.company, frappe.format(rfq.transaction_date, {"fieldtype": "Date"}), row.supplier_name or "")
	ws["A3"] = "Fill in the white columns and upload this file back on the portal. Do not change the # column."
	ws["A3"].font = Font(size=9, italic=True, color="888888")

	widths = {"#": 6, "Description": 60, "Qty": 10, "Offered Qty": 12, "UOM": 10, "HSN/SAC": 16, "Tax": 26,
		"Rate": 14, "MOQ": 10, "SPQ": 10, "Remarks": 30}
	hdr_row = 5
	for c, h in enumerate(headers, start=1):
		cell = ws.cell(row=hdr_row, column=c, value=h)
		cell.font = Font(bold=True, color="FFFFFF")
		cell.fill = PatternFill("solid", fgColor="1A73E8")
		cell.border = border
		cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
		ws.column_dimensions[get_column_letter(c)].width = widths[h]
	locked = {"#", "Description", "Qty", "UOM"}
	col = {h: i for i, h in enumerate(headers, start=1)}

	r = hdr_row + 1
	for item in rfq.items:
		hsn, tax = _item_defaults(item, rfq.company)
		desc = item.item_name or item.get("ub_item_description") or item.item_code or ""
		values = {"#": item.idx, "Description": desc, "Qty": item.qty, "Offered Qty": item.qty, "UOM": item.uom or "",
			"HSN/SAC": hsn, "Tax": tax, "Rate": 0, "MOQ": None, "SPQ": None, "Remarks": ""}
		for h in headers:
			cell = ws.cell(row=r, column=col[h], value=values[h])
			cell.border = border
			if h == "Description":
				cell.alignment = Alignment(wrap_text=True, vertical="top")
			if h not in locked:
				cell.protection = Protection(locked=False)
		ws.row_dimensions[r].height = min(15 * max(1, math.ceil(len(desc) / 58)), 320)
		r += 1
	last = r - 1
	if last > hdr_row and taxes:
		dv = DataValidation(type="list", formula1=f"=Lists!$A$1:$A${len(taxes)}", allow_blank=True)
		dv.error = "Please pick a tax from the list."
		ws.add_data_validation(dv)
		letter = get_column_letter(col["Tax"])
		dv.add(f"{letter}{hdr_row + 1}:{letter}{last}")
	ws.freeze_panes = f"A{hdr_row + 1}"

	out = BytesIO()
	wb.save(out)
	frappe.response["filename"] = f"RFQ-{rfq.name}.xlsx"
	frappe.response["filecontent"] = out.getvalue()
	frappe.response["type"] = "binary"


def parse_rfq_excel(rfq, content):
	"""Rows of the uploaded workbook matched to RFQ lines by #, each with per-field status
	(hsn_status / tax_status: ok | empty | not_found; rate_status: ok | empty). Never rejects."""
	from io import BytesIO

	import openpyxl

	try:
		wb = openpyxl.load_workbook(BytesIO(content), data_only=False)
	except Exception:
		frappe.throw(_("Could not read the file. Please upload the .xlsx you downloaded from this portal."))
	ws = wb["Quotation"] if "Quotation" in wb.sheetnames else wb.active

	header_row = next((rr for rr in range(1, 15) if str(ws.cell(row=rr, column=1).value or "").strip() == "#"), None)
	if not header_row:
		frappe.throw(_("This does not look like the RFQ template. Please use the downloaded file."))
	col_map = {}
	for c in range(1, 25):
		h = str(ws.cell(row=header_row, column=c).value or "").strip()
		if h:
			col_map[h] = c

	def val(rr, name):
		c = col_map.get(name)
		return ws.cell(row=rr, column=c).value if c else None

	check_hsn = hsn_enabled()
	allowed_tax = set(tax_options(rfq.company))
	valid_idx = {str(it.idx) for it in rfq.items}
	items, rr, blanks = [], header_row + 1, 0
	while blanks < 5 and rr < header_row + 5000:
		idx_val = ws.cell(row=rr, column=1).value
		if idx_val in (None, ""):
			blanks += 1
			rr += 1
			continue
		blanks = 0
		try:
			idx = str(int(float(idx_val)))
		except (TypeError, ValueError):
			idx = str(idx_val).strip()
		if idx not in valid_idx:
			rr += 1
			continue
		hsn = str(val(rr, "HSN/SAC") or "").strip() if check_hsn else ""
		tax = str(val(rr, "Tax") or "").strip()
		rate = flt(val(rr, "Rate"))
		oq = val(rr, "Offered Qty")
		offered_qty = flt(oq) if oq not in (None, "") else None
		if not check_hsn:
			hsn_status, hsn_label = "ok", ""
		elif not hsn:
			hsn_status, hsn_label = "empty", ""
		elif frappe.db.exists(HSN_DOCTYPE, hsn):
			hsn_status, hsn_label = "ok", _hsn_label(hsn)
		else:
			hsn_status, hsn_label = "not_found", ""
		tax_status = "empty" if not tax else ("ok" if tax in allowed_tax else "not_found")
		items.append({
			"idx": int(idx), "rate": rate, "rate_status": "ok" if rate > 0 else "empty",
			"hsn": hsn, "hsn_label": hsn_label, "hsn_status": hsn_status,
			"item_tax_template": tax, "tax_status": tax_status,
			"remarks": str(val(rr, "Remarks") or "").strip(), "offered_qty": offered_qty,
			"moq": flt(val(rr, "MOQ")), "spq": flt(val(rr, "SPQ")),
		})
		rr += 1
	return items


def _uploaded_content():
	upload = frappe.request.files.get("file") if frappe.request else None
	if not upload:
		frappe.throw(_("No file was uploaded."))
	content = upload.read()
	if len(content) > 5 * 1024 * 1024:
		frappe.throw(_("The file is too large."))
	return content


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=30, seconds=60 * 60)
def upload_rfq_excel(token):
	"""Token portal upload: reject when a filled HSN/SAC or Tax does not exist; nothing is saved."""
	row = get_row_by_token(token)
	rfq = get_active_rfq(row)
	assert_bid_open(rfq)
	items = parse_rfq_excel(rfq, _uploaded_content())
	errors = []
	for it in items:
		if it["hsn_status"] == "not_found":
			errors.append(_("Row {0}: HSN/SAC '{1}' does not exist.").format(it["idx"], escape_html(it["hsn"])))
		if it["tax_status"] == "not_found":
			errors.append(_("Row {0}: Tax '{1}' is not available.").format(it["idx"], escape_html(it["item_tax_template"])))
	if errors:
		frappe.throw(_("Could not upload. Please fix these rows and try again:") + "<br>&bull; " + "<br>&bull; ".join(errors),
			title=_("Invalid values"))
	return {"items": items}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=30, seconds=60 * 60)
def upload_rfq_excel_review(token):
	"""Supplier-app upload: never rejects; returns items plus a summary of what still needs fixing."""
	row = get_row_by_token(token)
	rfq = get_active_rfq(row)
	assert_bid_open(rfq)
	items = parse_rfq_excel(rfq, _uploaded_content())
	return {
		"items": items,
		"summary": {
			"total": len(items),
			"rate_missing": [it["idx"] for it in items if it["rate_status"] != "ok"],
			"hsn_missing": [it["idx"] for it in items if it["hsn_status"] == "empty"],
			"hsn_invalid": [it["idx"] for it in items if it["hsn_status"] == "not_found"],
			"tax_missing": [it["idx"] for it in items if it["tax_status"] == "empty"],
			"tax_invalid": [it["idx"] for it in items if it["tax_status"] == "not_found"],
		},
	}
