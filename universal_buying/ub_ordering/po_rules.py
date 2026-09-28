"""Purchase Order rules (BRD 6.17, V-17.1 .. V-17.6) as plain functions so they can be tested alone.

Called from ``universal_buying.ub_ordering.overrides.purchase_order.CustomPurchaseOrder``.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt
from frappe.utils.nestedset import get_descendants_of

from universal_buying.ub_ordering.pricing import expected_rate
from universal_buying.universal_buying.settings import get_list, get_setting, has_any_role

# Users holding one of these roles are never limited to consumables (fallback when the
# optional setting ``consumables_exempt_roles`` does not exist).
DEFAULT_CONSUMABLES_EXEMPT_ROLES = ["Purchase User", "Purchase Manager", "System Manager"]

IN_STATE_KEYS = ("in state", "in-state", "instate", "intra state", "intra-state", "intrastate", "within state")
OUT_STATE_KEYS = ("out state", "out-state", "outstate", "out of state", "inter state", "inter-state", "interstate")


# --------------------------------------------------------------------------------------
# Discount / margin reset 
# --------------------------------------------------------------------------------------
def reset_discount_and_margin(po):
	"""The PO carries the negotiated rate only: no discount or margin on lines."""
	for row in po.get("items") or []:
		row.margin_type = ""
		row.margin_rate_or_amount = 0
		row.rate_with_margin = 0
		row.base_rate_with_margin = 0
		row.discount_percentage = 0
		row.discount_amount = 0
		row.distributed_discount_amount = 0
		row.price_list_rate = row.rate
		row.base_price_list_rate = row.base_rate


# --------------------------------------------------------------------------------------
# Import flag and tax template (V-17.1)
# --------------------------------------------------------------------------------------
def _address_info(address):
	if not address:
		return None
	fields = ["state", "country"]
	if frappe.get_meta("Address").has_field("gst_state"):
		fields.append("gst_state")
	row = frappe.db.get_value("Address", address, fields, as_dict=True)
	if not row:
		return None
	state = (row.get("gst_state") or row.state or "").strip().lower()
	return frappe._dict(state=state, country=row.country)


def supplier_address_of(po):
	return po.get("supplier_address") or frappe.db.get_value("Supplier", po.supplier, "supplier_primary_address")


def company_address_of(po):
	addr = po.get("billing_address") or po.get("shipping_address")
	if addr:
		return addr
	try:
		from erpnext.setup.doctype.company.company import get_default_company_address

		return get_default_company_address(po.company)
	except Exception:
		return None


def is_import(po):
	"""Supplier address country (or Supplier.country) differs from the company country."""
	company_country = frappe.get_cached_value("Company", po.company, "country") if po.company else None
	if not company_country or not po.get("supplier"):
		return 0
	info = _address_info(supplier_address_of(po))
	country = (info and info.country) or frappe.db.get_value("Supplier", po.supplier, "country")
	return 1 if country and country != company_country else 0


def template_scope(template):
	"""'in' / 'out' / None from a Purchase Taxes and Charges Template's title or tax category."""
	if not template:
		return None
	row = frappe.db.get_value("Purchase Taxes and Charges Template", template, ["title", "tax_category"], as_dict=True)
	if not row:
		return None
	text = " ".join([row.title or "", row.tax_category or "", template]).lower()
	if any(k in text for k in OUT_STATE_KEYS):
		return "out"
	if any(k in text for k in IN_STATE_KEYS):
		return "in"
	return None


def scoped_templates(company):
	"""{'in': name, 'out': name} for the company's enabled In State / Out State templates."""
	out = {}
	rows = frappe.get_all(
		"Purchase Taxes and Charges Template",
		filters={"company": company, "disabled": 0},
		fields=["name", "is_default"],
		order_by="is_default desc, creation desc",
	)
	for r in rows:
		scope = template_scope(r.name)
		if scope and scope not in out:
			out[scope] = r.name
	return out


def expected_scope(po):
	"""'in' when supplier and company addresses share a state, 'out' when they differ, None if unknown."""
	sup = _address_info(supplier_address_of(po))
	com = _address_info(company_address_of(po))
	if not sup or not com or not sup.state or not com.state:
		return None
	return "in" if sup.state == com.state else "out"


def _load_taxes(po, template):
	from erpnext.controllers.accounts_controller import get_taxes_and_charges

	po.taxes_and_charges = template
	po.set("taxes", [])
	for tax in get_taxes_and_charges("Purchase Taxes and Charges Template", template) or []:
		po.append("taxes", tax)


def apply_tax_rules(po):
	"""Set the import flag, clear GST templates on imports, pick / validate In State vs Out State.

	Skipped silently when the company has no In State / Out State templates (generic companies).
	Returns True when taxes were changed (caller recalculates totals).
	"""
	po.ub_is_import = is_import(po)
	current_scope = template_scope(po.get("taxes_and_charges"))

	if po.ub_is_import:
		if current_scope:
			po.taxes_and_charges = None
			po.set("taxes", [])
			return True
		return False

	if po.get("is_internal_supplier"):
		return False

	templates = scoped_templates(po.company)
	if not templates:
		return False
	scope = expected_scope(po)
	if not scope:
		return False

	if not po.get("taxes_and_charges"):
		if templates.get(scope) and not po.get("taxes"):
			_load_taxes(po, templates[scope])
			return True
		return False

	if current_scope and current_scope != scope:
		frappe.throw(
			_("Tax template {0} does not match the addresses: supplier and company are in {1}. Select {2}.").format(
				frappe.bold(po.taxes_and_charges),
				_("the same state") if scope == "in" else _("different states"),
				frappe.bold(templates.get(scope) or (_("an In State template") if scope == "in" else _("an Out State template"))),
			),
			title=_("Tax and Address Mismatch"),
		)
	return False


@frappe.whitelist()
def get_tax_template_for_po(company, supplier=None, supplier_address=None, billing_address=None, shipping_address=None):
	"""Client helper: which template the addresses call for (None when not applicable)."""
	frappe.has_permission("Purchase Order", "read", throw=True)
	po = frappe._dict(company=company, supplier=supplier, supplier_address=supplier_address,
		billing_address=billing_address, shipping_address=shipping_address)
	if not company or not supplier:
		return {"template": None}
	if is_import(po):
		return {"template": None, "is_import": 1}
	templates = scoped_templates(company)
	scope = expected_scope(po) if templates else None
	return {"template": templates.get(scope) if scope else None, "is_import": 0, "scope": scope}


# --------------------------------------------------------------------------------------
# Line validations
# --------------------------------------------------------------------------------------
def validate_negative_taxes(po):
	"""V-17.6: a PO has no return concept, so negative tax rates/amounts are never valid."""
	for tax in po.get("taxes") or []:
		if tax.charge_type == "Actual":
			if flt(tax.tax_amount) < 0:
				frappe.throw(_("Row #{0}: Tax amount cannot be negative on a Purchase Order. "
					"Use Add/Deduct Tax = Deduct with a positive amount.").format(tax.idx))
		elif flt(tax.rate) < 0:
			frappe.throw(_("Row #{0}: Tax rate cannot be negative on a Purchase Order. "
				"Use Add/Deduct Tax = Deduct with a positive rate.").format(tax.idx))


def validate_uom_conversion(po):
	"""V-17.3: purchase UOM different from stock UOM needs a conversion on the Item."""
	missing = []
	for row in po.get("items") or []:
		if not row.item_code or not row.uom:
			continue
		stock_uom = frappe.get_cached_value("Item", row.item_code, "stock_uom")
		if not stock_uom or row.uom == stock_uom:
			continue
		if not frappe.db.exists("UOM Conversion Detail", {"parent": row.item_code, "parenttype": "Item", "uom": row.uom}):
			missing.append(_("Row {0}: Item {1} - UOM {2} has no conversion (stock UOM {3})").format(
				row.idx, frappe.bold(row.item_code), frappe.bold(row.uom), stock_uom))
	if missing:
		frappe.throw("<br>".join(missing), title=_("UOM Conversion Missing in Item Master"))


def _consumable_groups():
	groups = set()
	for g in get_list("consumable_item_groups"):
		groups.add(g)
		groups.update(get_descendants_of("Item Group", g) or [])
	return groups


def validate_consumables_role(po, user=None):
	"""V-17.4: users in consumables_only_roles may only order consumable item groups."""
	limited = get_list("consumables_only_roles")
	if not limited or not has_any_role(limited, user):
		return
	exempt = get_list("consumables_exempt_roles") or DEFAULT_CONSUMABLES_EXEMPT_ROLES
	if has_any_role(exempt, user):
		return
	allowed = _consumable_groups()
	bad = []
	for row in po.get("items") or []:
		if not row.item_code:
			continue
		group = row.get("item_group") or frappe.get_cached_value("Item", row.item_code, "item_group")
		if group not in allowed:
			bad.append("{0} ({1})".format(row.item_code, group))
	if bad:
		frappe.throw(
			_("Your role may order only consumable item groups ({0}). Not allowed: {1}").format(
				", ".join(sorted(get_list("consumable_item_groups"))) or "-", ", ".join(bad)),
			title=_("Consumables Only"),
		)


def validate_addresses(po):
	"""V-17.1: supplier, billing and shipping addresses are required (checked on send / submit)."""
	missing = [po.meta.get_label(f) for f in ("supplier_address", "billing_address", "shipping_address") if not po.get(f)]
	if missing:
		frappe.throw(_("Please set {0} on the Purchase Order.").format(", ".join(missing)), title=_("Address Required"))


def sync_skip_moq(po):
	"""V-17.2: only Auto PO Exception may set the skip-MOQ flag."""
	if po.get("ub_origin_doctype") == "Auto PO Exception":
		return
	for row in po.get("items") or []:
		if row.get("ub_skip_moq"):
			row.ub_skip_moq = 0


def validate_moq(po):
	"""V-17.2: ordered stock qty per item >= Item.min_order_qty, lines flagged ub_skip_moq exempt."""
	qty_by_item = {}
	for row in po.get("items") or []:
		if not row.item_code or row.get("ub_skip_moq"):
			continue
		qty_by_item[row.item_code] = qty_by_item.get(row.item_code, 0) + flt(row.stock_qty)
	if not qty_by_item:
		return
	moq = dict(frappe.get_all("Item", filters={"name": ["in", list(qty_by_item)]}, fields=["name", "min_order_qty"], as_list=1))
	for item_code, qty in qty_by_item.items():
		if flt(qty) < flt(moq.get(item_code)):
			frappe.throw(_("Item {0}: Ordered qty {1} cannot be less than minimum order qty {2} (defined in Item).").format(
				item_code, qty, flt(moq.get(item_code))), title=_("Minimum Order Qty"))


# --------------------------------------------------------------------------------------
# Price control (BRD 6.17: Strict / Warn / Free)
# --------------------------------------------------------------------------------------
def enforce_price_control(po):
	"""Return True when rates were corrected (caller recalculates totals)."""
	mode = get_setting("price_control_mode", company=po.company) or "Strict"
	if mode == "Free" or po.get("is_internal_supplier"):
		return False

	changed = False
	corrected, missing, zero, warned = [], [], [], []
	for row in po.get("items") or []:
		if not row.item_code or row.get("is_free_item"):
			continue
		rate, source = expected_rate(po, row)
		if rate is None:
			missing.append(row)
			continue
		if flt(rate) <= 0:
			zero.append(row)
			continue
		precision = row.precision("rate") or 2
		if abs(flt(row.rate, precision) - flt(rate, precision)) <= 0.5 / (10 ** cint(precision)):
			continue
		if mode == "Strict":
			corrected.append((row, flt(row.rate), rate, source))
			row.rate = flt(rate, precision)
			row.price_list_rate = row.rate
			changed = True
		else:
			warned.append((row, rate, source))

	if mode == "Strict":
		if missing or zero:
			lines = [_("Row {0}: {1} - no valid Item Price or Supplier Quotation").format(r.idx, r.item_code) for r in missing]
			lines += [_("Row {0}: {1} - valid price is zero").format(r.idx, r.item_code) for r in zero]
			frappe.throw(
				"<br>".join(lines) + "<br><br>" + _("Price control is Strict: create or renew the Item Price (Item Price Request) before saving."),
				title=_("Price Not Available"),
			)
		if corrected:
			frappe.msgprint(
				"<br>".join(_("Row {0}: {1} rate {2} reset to {3} ({4})").format(
					r.idx, r.item_code, old, new, src) for r, old, new, src in corrected),
				title=_("Rates Locked to Valid Price"), indicator="blue",
			)
	elif mode == "Warn":
		lines = [_("Row {0}: {1} rate {2} differs from {3} ({4})").format(r.idx, r.item_code, r.rate, rate, src)
			for r, rate, src in warned]
		lines += [_("Row {0}: {1} has no valid price").format(r.idx, r.item_code) for r in missing + zero]
		if lines:
			frappe.msgprint("<br>".join(lines), title=_("Price Check"), indicator="orange")
	return changed


# --------------------------------------------------------------------------------------
# Origin
# --------------------------------------------------------------------------------------
def set_default_origin(po):
	"""Origin from mapping when the creator did not stamp one (blank means Manual)."""
	if po.get("ub_origin_doctype"):
		return
	for field, doctype in (("supplier_quotation", "Supplier Quotation"), ("material_request", "Material Request")):
		refs = {r.get(field) for r in po.get("items") or [] if r.get(field)}
		if refs:
			po.ub_origin_doctype = doctype
			po.ub_origin_name = next(iter(refs)) if len(refs) == 1 else None
			return
