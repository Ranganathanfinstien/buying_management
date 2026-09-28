"""Generate Frappe v16 DocType folders (json + py + __init__ [+ js]) from a compact spec.

Usage from another script:

	import sys; sys.path.insert(0, "/home/finstein-emp/frappe-v16/apps/universal_buying/tools")
	from make_doctype import make_doctype, F

	make_doctype(
		module="UB Planning",                  # module name as in modules.txt
		name="Item Price Request",
		fields=[
			F("company", "Link", "Company", options="Company", reqd=1),
			F("items", "Table", "Items", options="Item Price Request Detail", reqd=1),
		],
		autoname="naming_series:", naming_series="IPR-.YYYY.-.#####",
		is_submittable=1,
		permissions=[perm("Purchase User", submit=1), perm("Purchase Manager", submit=1, cancel=1, amend=1)],
		js=True,                               # also write an empty <name>.js
		controller_body=None,                  # optional python class body (tab indented)
	)

Rules:
- Existing .py / .js files are never overwritten (only the .json is rewritten), so
  hand-written controllers survive re-generation.
- Field order = list order. Use F(..., "Section Break") / "Column Break" / "Tab Break" as needed.
"""

import json
import os
import re

APP_PKG = "/home/finstein-emp/frappe-v16/apps/universal_buying/universal_buying"
NOW = "2026-09-26 12:00:00.000000"


def scrub(txt):
	return re.sub(r"[^a-z0-9_]", "_", txt.strip().lower().replace(" ", "_").replace("-", "_"))


def F(fieldname, fieldtype, label=None, **kw):
	d = {"fieldname": fieldname, "fieldtype": fieldtype}
	if label is not None:
		d["label"] = label
	d.update(kw)
	return d


def perm(role, read=1, write=1, create=1, delete=0, submit=0, cancel=0, amend=0, report=1, export=1, print_=1, email=1, share=1):
	return {
		"role": role, "read": read, "write": write, "create": create, "delete": delete,
		"submit": submit, "cancel": cancel, "amend": amend, "report": report, "export": export,
		"print": print_, "email": email, "share": share,
	}


def make_doctype(module, name, fields, istable=0, issingle=0, is_submittable=0, autoname=None,
		naming_series=None, title_field=None, permissions=None, js=False, controller_body=None,
		track_changes=1, sort_field="creation", sort_order="DESC", search_fields=None,
		quick_entry=0, extra=None, list_js=False):
	module_dir = os.path.join(APP_PKG, scrub(module), "doctype")
	os.makedirs(module_dir, exist_ok=True)
	init = os.path.join(module_dir, "__init__.py")
	if not os.path.exists(init):
		open(init, "w").close()
	dt_dir = os.path.join(module_dir, scrub(name))
	os.makedirs(dt_dir, exist_ok=True)
	open(os.path.join(dt_dir, "__init__.py"), "a").close()

	fields = [dict(f) for f in fields]
	if naming_series and not any(f["fieldname"] == "naming_series" for f in fields):
		fields.insert(0, F("naming_series", "Select", "Series", options=naming_series, default=naming_series.split("\n")[0], reqd=1, hidden=0, no_copy=1, print_hide=1))
		autoname = autoname or "naming_series:"
	if is_submittable and not any(f["fieldname"] == "amended_from" for f in fields):
		fields.append(F("amended_from", "Link", "Amended From", options=name, read_only=1, no_copy=1, print_hide=1, search_index=1))

	if permissions is None:
		permissions = [] if istable else [perm("System Manager", delete=1, submit=is_submittable, cancel=is_submittable, amend=is_submittable)]
	if issingle:
		for p in permissions:
			for k in ("submit", "cancel", "amend", "create", "delete", "report", "export"):
				p.pop(k, None)

	doc = {
		"actions": [],
		"allow_rename": 0,
		"creation": NOW,
		"doctype": "DocType",
		"engine": "InnoDB",
		"field_order": [f["fieldname"] for f in fields],
		"fields": fields,
		"index_web_pages_for_search": 0,
		"istable": istable,
		"issingle": issingle,
		"is_submittable": is_submittable,
		"links": [],
		"modified": NOW,
		"modified_by": "Administrator",
		"module": module,
		"name": name,
		"owner": "Administrator",
		"permissions": permissions,
		"sort_field": sort_field,
		"sort_order": sort_order,
		"states": [],
		"track_changes": 0 if istable else track_changes,
		"quick_entry": quick_entry,
		"row_format": "Dynamic",
		"rows_threshold_for_grid_search": 20,
	}
	if autoname:
		doc["autoname"] = autoname
		if autoname.startswith("naming_series"):
			doc["naming_rule"] = 'By "Naming Series" field'
		elif autoname.startswith("field:"):
			doc["naming_rule"] = "By fieldname"
		elif autoname.startswith("format:"):
			doc["naming_rule"] = "Expression"
		elif autoname == "hash":
			doc["naming_rule"] = "Random"
		elif autoname == "autoincrement":
			doc["naming_rule"] = "Autoincrement"
	if title_field:
		doc["title_field"] = title_field
		doc["show_title_field_in_link"] = 0
	if search_fields:
		doc["search_fields"] = search_fields
	if extra:
		doc.update(extra)

	with open(os.path.join(dt_dir, scrub(name) + ".json"), "w") as f:
		json.dump(doc, f, indent=1, sort_keys=True)

	cls = name.replace(" ", "").replace("-", "")
	py = os.path.join(dt_dir, scrub(name) + ".py")
	if not os.path.exists(py):
		body = controller_body or "\tpass\n"
		with open(py, "w") as f:
			f.write(
				"# Copyright (c) 2026, Finstein and contributors\n# For license information, please see license.txt\n\n"
				"import frappe\nfrom frappe.model.document import Document\n\n\n"
				f"class {cls}(Document):\n{body}"
			)
	if js:
		jsf = os.path.join(dt_dir, scrub(name) + ".js")
		if not os.path.exists(jsf):
			with open(jsf, "w") as f:
				f.write(f'// Copyright (c) 2026, Finstein and contributors\n\nfrappe.ui.form.on("{name}", {{\n\trefresh(frm) {{}},\n}});\n')
	if list_js:
		lj = os.path.join(dt_dir, scrub(name) + "_list.js")
		if not os.path.exists(lj):
			with open(lj, "w") as f:
				f.write(f'frappe.listview_settings["{name}"] = {{}};\n')
	return dt_dir
