"""Purchase Receipt rules (BRD v2 6.22, 6.23). Called from the controller override in overrides/purchase_receipt.py.

Every function takes the receipt document and is safe to call for returns (they return early).
"""

import frappe
from frappe import _
from frappe.utils import cint, date_diff, flt, getdate

from universal_buying.ub_inward.utils import (
	bonded_route_active,
	get_bonded_warehouse,
	supplier_is_green_card,
)
from universal_buying.universal_buying.settings import get_setting

# ---------------------------------------------------------------------------
# header defaults
# ---------------------------------------------------------------------------


def set_receipt_flags(doc):
	"""Green card flag from the supplier and the import flag."""
	doc.ub_green_card = 1 if supplier_is_green_card(doc.get("supplier")) else 0
	if doc.get("is_return"):
		return

	po_names = list({r.purchase_order for r in doc.get("items") if r.get("purchase_order")})
	if po_names and frappe.get_meta("Purchase Order").has_field("ub_is_import"):
		if frappe.get_all("Purchase Order", filters={"name": ("in", po_names), "ub_is_import": 1}, limit=1):
			doc.ub_is_import = 1
			return

	if doc.get("supplier_address"):
		country = frappe.db.get_value("Address", doc.supplier_address, "country")
		company_country = frappe.get_cached_value("Company", doc.company, "country")
		if country and company_country:
			doc.ub_is_import = 1 if country != company_country else 0


# ---------------------------------------------------------------------------
# V-23.1 rows only from a Purchase Order
# ---------------------------------------------------------------------------


def validate_rows_from_po(doc):
	if doc.get("is_return") or doc.is_internal_transfer():
		return
	bad = [r for r in doc.get("items") if not (r.get("purchase_order") and r.get("purchase_order_item"))]
	if bad:
		frappe.throw(
			_(
				"Rows {0}: a Purchase Receipt row must come from a Purchase Order line. Use Get Items From > Purchase Order."
			).format(", ".join(f"#{r.idx} {r.item_code or ''}" for r in bad)),
			title=_("Purchase Order Required"),
		)


# ---------------------------------------------------------------------------
# V-23.2 over-receipt checked at save
# ---------------------------------------------------------------------------


def get_already_received(po_item_names, exclude_receipt=None):
	"""{po_item: net received qty} from submitted receipts (returns reduce it), excluding one receipt."""
	if not po_item_names:
		return {}
	rows = frappe.db.sql(
		"""
		select pri.purchase_order_item,
			sum(case when pr.is_return = 1 then pri.qty else pri.received_qty end) as qty
		from `tabPurchase Receipt Item` pri
		inner join `tabPurchase Receipt` pr on pr.name = pri.parent
		where pri.purchase_order_item in %(items)s and pr.docstatus = 1 and pr.name != %(exclude)s
		group by pri.purchase_order_item
		""",
		{"items": tuple(po_item_names), "exclude": exclude_receipt or ""},
		as_dict=True,
	)
	return {r.purchase_order_item: flt(r.qty) for r in rows}


def validate_over_receipt(doc):
	"""Sum this receipt's rows per PO line and compare with PO qty + allowance (Stock Settings / Item)."""
	if doc.get("is_return"):
		return
	from erpnext.controllers.status_updater import get_allowance_for

	groups = {}
	for row in doc.get("items"):
		if row.get("purchase_order_item"):
			groups.setdefault(row.purchase_order_item, []).append(row)
	if not groups:
		return

	po_rows = {
		r.name: r
		for r in frappe.get_all(
			"Purchase Order Item",
			filters={"name": ("in", list(groups))},
			fields=["name", "parent", "item_code", "qty"],
		)
	}
	received = get_already_received(list(groups), doc.name)
	bypass_role = frappe.get_single_value("Stock Settings", "role_allowed_to_over_deliver_receive")
	can_bypass = bool(bypass_role and bypass_role in frappe.get_roles())

	item_allowance, global_qty, global_amount = {}, None, None
	for po_item, rows in groups.items():
		po_row = po_rows.get(po_item)
		if not po_row or flt(po_row.qty) <= 0:
			continue
		allowance, item_allowance, global_qty, global_amount = get_allowance_for(
			po_row.item_code, item_allowance, global_qty, global_amount, "qty"
		)
		max_qty = flt(po_row.qty) * (100 + flt(allowance)) / 100
		already = flt(received.get(po_item))
		this_doc = sum(flt(r.received_qty) or (flt(r.qty) + flt(r.rejected_qty)) for r in rows)
		if already + this_doc <= max_qty + 0.0001:
			continue

		row_label = ", ".join(f"#{r.idx}" for r in rows)
		message = _(
			"Row(s) {0}: over-receipt for {1} against {2}. Ordered {3}, already received {4}, this receipt {5}, allowed {6} (allowance {7}%)."
		).format(
			row_label,
			frappe.bold(po_row.item_code),
			po_row.parent,
			flt(po_row.qty),
			flt(already),
			flt(this_doc),
			flt(max_qty, 3),
			flt(allowance),
		)
		if can_bypass:
			frappe.msgprint(message, indicator="orange", alert=True)
		else:
			frappe.throw(message, title=_("Over Receipt"))


# ---------------------------------------------------------------------------
# V-22.1 gate entry
# ---------------------------------------------------------------------------


def get_gate_entry(name):
	return frappe.db.get_value(
		"Gate Entry",
		name,
		["docstatus", "entry_type", "company", "entry_date", "party_type", "party"],
		as_dict=True,
	)


def validate_gate_entry(doc):
	if doc.get("is_return") or bonded_route_active(doc):
		return
	required = cint(get_setting("gate_entry_required", company=doc.company))
	if not doc.get("ub_gate_entry"):
		if required:
			frappe.throw(
				_("Gate Entry is required for this Purchase Receipt."), title=_("Gate Entry Required")
			)
		return

	ge = get_gate_entry(doc.ub_gate_entry)
	if not ge:
		frappe.throw(_("Gate Entry {0} not found.").format(doc.ub_gate_entry))
	if cint(ge.docstatus) != 1:
		frappe.throw(_("Gate Entry {0} must be submitted.").format(frappe.bold(doc.ub_gate_entry)))
	if ge.entry_type != "In":
		frappe.throw(_("Gate Entry {0} is not an inward entry.").format(frappe.bold(doc.ub_gate_entry)))
	if ge.company and ge.company != doc.company:
		frappe.throw(
			_("Gate Entry {0} belongs to company {1}.").format(frappe.bold(doc.ub_gate_entry), ge.company)
		)

	lookback = cint(get_setting("gate_entry_lookback_days", company=doc.company))
	if lookback and ge.entry_date and date_diff(getdate(doc.posting_date), getdate(ge.entry_date)) > lookback:
		frappe.throw(
			_("Gate Entry {0} is older than {1} days.").format(frappe.bold(doc.ub_gate_entry), lookback),
			title=_("Gate Entry Too Old"),
		)
	if ge.party_type == "Supplier" and ge.party and doc.get("supplier") and ge.party != doc.supplier:
		frappe.msgprint(
			_("Gate Entry {0} was made for supplier {1}.").format(doc.ub_gate_entry, frappe.bold(ge.party)),
			indicator="orange",
			alert=True,
		)


# ---------------------------------------------------------------------------
# bonded goods route (optional)
# ---------------------------------------------------------------------------


def apply_bonded_route(doc):
	if doc.get("is_return"):
		return
	enabled = cint(get_setting("bonded_goods_enabled", company=doc.company))
	if cint(doc.get("ub_is_bonded")) and not enabled:
		frappe.throw(_("The bonded goods route is disabled in Buying Control Settings."))
	if not enabled:
		return

	bonded = get_bonded_warehouse(doc.company, throw=cint(doc.get("ub_is_bonded")))
	if cint(doc.get("ub_is_bonded")):
		doc.set_warehouse = bonded
		doc.rejected_warehouse = None
		for row in doc.get("items"):
			row.warehouse = bonded
			row.rejected_warehouse = None
	elif bonded:
		for row in doc.get("items"):
			if bonded in (row.get("warehouse"), row.get("rejected_warehouse")):
				frappe.throw(
					_("Row #{0}: bonded warehouse {1} is only allowed on a bonded goods receipt.").format(
						row.idx, bonded
					)
				)


# ---------------------------------------------------------------------------
# Bill of Entry (V-23.6) and exchange rate on BoE date
# ---------------------------------------------------------------------------


def apply_boe_exchange_rate(doc):
	"""Import receipts are valued at the customs exchange rate of the BoE date."""
	if doc.get("is_return") or doc.docstatus != 0 or not doc.get("ub_boe_date"):
		return
	if not cint(get_setting("use_boe_exchange_rate", company=doc.company, default=1)):
		return
	company_currency = frappe.get_cached_value("Company", doc.company, "default_currency")
	if not doc.get("currency") or doc.currency == company_currency:
		return
	from erpnext.setup.utils import get_exchange_rate

	rate = get_exchange_rate(doc.currency, company_currency, doc.ub_boe_date, args="for_buying")
	if flt(rate) > 0:
		doc.conversion_rate = rate
		if doc.get("price_list_currency") == doc.currency:
			doc.plc_conversion_rate = rate
	else:
		frappe.msgprint(
			_("No exchange rate {0} to {1} on {2}; keeping {3}.").format(
				doc.currency, company_currency, doc.ub_boe_date, doc.conversion_rate
			),
			indicator="orange",
			alert=True,
		)


def validate_boe(doc):
	if doc.get("is_return") or not cint(doc.get("ub_is_import")):
		return
	if not cint(get_setting("boe_fiscal_year_check", company=doc.company)):
		return
	if not doc.get("ub_boe_date"):
		frappe.throw(_("Bill of Entry Date is required for an import receipt."), title=_("Bill of Entry"))

	from erpnext.accounts.utils import get_fiscal_year

	posting_fy = get_fiscal_year(doc.posting_date, company=doc.company, as_dict=True, raise_on_missing=False)
	boe_fy = get_fiscal_year(doc.ub_boe_date, company=doc.company, as_dict=True, raise_on_missing=False)
	if not boe_fy or not posting_fy or boe_fy.get("name") != posting_fy.get("name"):
		frappe.throw(
			_("Bill of Entry Date {0} must be inside the fiscal year of the posting date.").format(
				frappe.format(doc.ub_boe_date, "Date")
			),
			title=_("Bill of Entry"),
		)


# ---------------------------------------------------------------------------
# Manufacturing shortage notice (informational)
# ---------------------------------------------------------------------------


def get_shortage_for_items(item_codes, company):
	"""{item_code: shortage qty} via UB Planning (optional; empty when the module is missing)."""
	item_codes = [c for c in dict.fromkeys(item_codes or []) if c]
	if not item_codes or not company:
		return {}
	try:
		from universal_buying.ub_planning.api import get_shortage_map
	except ImportError:
		return {}
	try:
		data = get_shortage_map(item_codes, company) or {}
	except Exception:
		frappe.log_error(title="UB Inward: shortage lookup failed")
		return {}

	out = {}
	for item_code, value in data.items():
		if isinstance(value, dict):
			value = value.get("shortage_qty", value.get("shortage", value.get("qty")))
		if flt(value) > 0:
			out[item_code] = flt(value)
	return out


def shortage_message(shortage):
	rows = "".join(
		f"<tr><td>{frappe.utils.escape_html(item)}</td><td style='text-align:right'>{flt(qty)}</td></tr>"
		for item, qty in sorted(shortage.items())
	)
	return (
		"<p>{0}</p><table class='table table-bordered table-condensed'><thead><tr><th>{1}</th>"
		"<th style='text-align:right'>{2}</th></tr></thead><tbody>{3}</tbody></table>"
	).format(
		_("These items are short for current manufacturing demand. Please receive them first."),
		_("Item"),
		_("Shortage Qty"),
		rows,
	)


def notify_manufacturing_shortage(doc):
	if doc.get("is_return") or not doc.is_new():
		return
	shortage = get_shortage_for_items([r.item_code for r in doc.get("items")], doc.company)
	if shortage:
		frappe.msgprint(shortage_message(shortage), title=_("Manufacturing Shortage"), indicator="orange")
