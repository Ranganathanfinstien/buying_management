"""Single read path for every configurable rule (BRD v2 section 7).

Usage:
	from universal_buying.universal_buying.settings import get_setting, get_list, apply_mode

	days = get_setting("planning_buffer_days", company=doc.company)       # int, company override aware
	groups = get_list("consumable_item_groups")                           # ["Consumable", ...]
	apply_mode(get_setting("iqc_gate"), _("Inspection missing"))          # Off / Warn / Block
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

SETTINGS_DOCTYPE = "Buying Control Settings"

# child tables of type Table MultiSelect -> the link field inside the child row
_LIST_FIELDS = {
	"UB Item Group Link": "item_group",
	"UB Role Link": "role",
	"UB Supplier Group Link": "supplier_group",
}


def get_settings():
	return frappe.get_cached_doc(SETTINGS_DOCTYPE)


def _cast(fieldname, value):
	df = frappe.get_meta(SETTINGS_DOCTYPE).get_field(fieldname)
	if not df or value is None:
		return value
	if df.fieldtype in ("Int", "Check"):
		return cint(value)
	if df.fieldtype in ("Float", "Currency", "Percent"):
		return flt(value)
	return value


def get_setting(fieldname, company=None, default=None):
	"""Return a setting value. A Company Override row (company + fieldname) wins when company is given."""
	doc = get_settings()
	if company:
		for row in doc.get("company_overrides") or []:
			if row.company == company and row.setting_field == fieldname:
				return _cast(fieldname, row.value)
	value = doc.get(fieldname)
	if value is None or value == "":
		return default if default is not None else _cast(fieldname, value)
	return _cast(fieldname, value)


def get_list(fieldname):
	"""Values of a Table MultiSelect setting, e.g. get_list('batch_exempt_groups') -> ['Charges', 'Stencil']."""
	doc = get_settings()
	df = frappe.get_meta(SETTINGS_DOCTYPE).get_field(fieldname)
	key = _LIST_FIELDS.get(df.options) if df else None
	return [row.get(key) for row in (doc.get(fieldname) or []) if key and row.get(key)]


def get_lines(fieldname):
	"""Small Text setting split into non-empty stripped lines."""
	return [line.strip() for line in (get_setting(fieldname) or "").splitlines() if line.strip()]


def apply_mode(mode, message, title=None):
	"""Enforce an Off / Warn / Block setting. Returns True when the rule fired."""
	if not mode or mode == "Off":
		return False
	if mode == "Block":
		frappe.throw(message, title=title or _("Not Allowed"))
	frappe.msgprint(message, title=title or _("Warning"), indicator="orange")
	return True


def has_any_role(roles, user=None):
	if not roles:
		return False
	return bool(set(roles) & set(frappe.get_roles(user)))


def abc_threshold(item_class):
	"""MOQ fraction (0-1) for an ABC class; unknown class uses the default class."""
	cls = (item_class or get_setting("abc_default_class") or "C").upper()
	if cls not in ("A", "B", "C"):
		cls = get_setting("abc_default_class") or "C"
	return flt(get_setting(f"abc_threshold_{cls.lower()}")) / 100.0
