"""Small helpers shared inside UB Inward."""

import frappe
from frappe import _
from frappe.utils import cint
from frappe.utils.nestedset import get_descendants_of

from universal_buying.universal_buying.settings import get_list, get_setting


def get_company_warehouse(company, warehouse_name):
	"""Leaf warehouse of a company by its warehouse_name (e.g. "Rejected Goods")."""
	if not (company and warehouse_name):
		return None
	return frappe.db.get_value(
		"Warehouse", {"warehouse_name": warehouse_name, "company": company, "is_group": 0}, "name"
	)


def get_rejected_warehouse(company, throw=True):
	name = get_setting("rejected_warehouse_name", company=company) or "Rejected Goods"
	warehouse = get_company_warehouse(company, name)
	if not warehouse and throw:
		frappe.throw(
			_(
				"Warehouse {0} is missing for company {1}. Create it or change 'Rejected Warehouse Name' in Buying Control Settings."
			).format(frappe.bold(name), frappe.bold(company)),
			title=_("Rejected Warehouse Missing"),
		)
	return warehouse


def get_bonded_warehouse(company, throw=True):
	name = get_setting("bonded_goods_warehouse_name", company=company) or "Bonded Goods"
	warehouse = get_company_warehouse(company, name)
	if not warehouse and throw:
		frappe.throw(
			_("Bonded warehouse {0} is missing for company {1}.").format(
				frappe.bold(name), frappe.bold(company)
			),
			title=_("Bonded Warehouse Missing"),
		)
	return warehouse


def row_item_code(row):
	"""Stock item of a receipt row (the earlier design kept template + variant; standard ERPNext stores the variant)."""
	return row.get("item_code")


def get_batch_exempt_groups():
	"""batch_exempt_groups from settings plus all their child groups (cached per request in frappe.flags)."""
	if frappe.flags.get("ub_batch_exempt_groups") is not None:
		return frappe.flags.ub_batch_exempt_groups
	groups = set()
	for group in get_list("batch_exempt_groups"):
		groups.add(group)
		try:
			groups.update(get_descendants_of("Item Group", group, ignore_permissions=True) or [])
		except Exception:
			pass
	frappe.flags.ub_batch_exempt_groups = groups
	return groups


def is_batch_exempt(item_code):
	group = frappe.get_cached_value("Item", item_code, "item_group")
	return bool(group and group in get_batch_exempt_groups())


def item_has_batch(item_code):
	return cint(frappe.get_cached_value("Item", item_code, "has_batch_no"))


def item_needs_inspection(item_code):
	return cint(frappe.get_cached_value("Item", item_code, "inspection_required_before_purchase"))


def item_built_type(item_code):
	"""Item.ub_built_type (owned by UB Planning). Missing field = Standard."""
	if not frappe.get_meta("Item").has_field("ub_built_type"):
		return "Standard"
	return (frappe.get_cached_value("Item", item_code, "ub_built_type") or "Standard").strip()


def supplier_is_green_card(supplier):
	if not supplier or not frappe.get_meta("Supplier").has_field("ub_green_card"):
		return False
	return bool(cint(frappe.db.get_value("Supplier", supplier, "ub_green_card")))


def green_card_skips_iqc(doc):
	"""True when this receipt's supplier is green card and the setting allows skipping IQC."""
	if not cint(get_setting("green_card_skips_iqc", company=doc.get("company"))):
		return False
	return bool(cint(doc.get("ub_green_card"))) or supplier_is_green_card(doc.get("supplier"))


def bonded_route_active(doc):
	return bool(cint(doc.get("ub_is_bonded"))) and bool(
		cint(get_setting("bonded_goods_enabled", company=doc.get("company")))
	)
