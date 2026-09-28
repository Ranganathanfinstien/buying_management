"""One installer for the whole app. Runs on after_install and after_migrate; every step is idempotent.

Each module package may ship an ``install.py`` with any of:

	ROLES = ["Sourcing User", ...]                       # roles to create (desk access)
	CUSTOM_FIELDS = {"Purchase Order": [{...}, ...]}      # passed to create_custom_fields
	PROPERTY_SETTERS = [{"doctype": ..., "fieldname": ..., "property": ..., "value": ..., "property_type": ...}]
	def setup(): ...                                     # records, workflows, defaults (must be idempotent)

Rule: every custom fieldname starts with ``ub_`` so it can never clash with ERPNext or other apps.
"""

import importlib

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

MODULES = [
	"universal_buying.universal_buying",
	"universal_buying.ub_supplier",
	"universal_buying.ub_planning",
	"universal_buying.ub_sourcing",
	"universal_buying.ub_ordering",
	"universal_buying.ub_inward",
	"universal_buying.ub_finance",
]


def _load(module):
	try:
		return importlib.import_module(module + ".install")
	except ModuleNotFoundError as e:
		if e.name == module + ".install":
			return None
		raise


def after_install():
	run()


def after_migrate():
	run()


def run():
	mods = [m for m in (_load(p) for p in MODULES) if m]

	roles = []
	for m in mods:
		roles += list(getattr(m, "ROLES", []) or [])
	for role in dict.fromkeys(roles):
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)

	merged = {}
	for m in mods:
		for dt, fields in (getattr(m, "CUSTOM_FIELDS", {}) or {}).items():
			merged.setdefault(dt, []).extend(fields)
	for dt, fields in merged.items():
		for f in fields:
			if not f["fieldname"].startswith("ub_"):
				frappe.throw(f"Custom field {dt}.{f['fieldname']} must start with ub_")
	if merged:
		create_custom_fields(merged, ignore_validate=True, update=True)

	for m in mods:
		for ps in getattr(m, "PROPERTY_SETTERS", []) or []:
			make_property_setter(
				ps["doctype"], ps.get("fieldname"), ps["property"], ps["value"],
				ps.get("property_type", "Data"), for_doctype=not ps.get("fieldname"), validate_fields_for_doctype=False,
			)

	for m in mods:
		fn = getattr(m, "setup", None)
		if fn:
			fn()

	frappe.db.commit()
	frappe.clear_cache()
