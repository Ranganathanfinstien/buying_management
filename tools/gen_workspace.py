"""Generate the desk Workspace, Workspace Sidebar and Desktop Icon for Universal Buying (Frappe v16)."""

import glob
import json
import os

PKG = "/home/finstein-emp/frappe-v16/apps/universal_buying/universal_buying"
NOW = "2026-09-26 12:00:00.000000"

SECTIONS = [
	("Setup", "settings", [
		("Buying Control Settings", "DocType"), ("PO Type", "DocType"),
	]),
	("Supplier", "users", [
		("Prospective Supplier", "DocType"), ("Supplier Onboarding", "DocType"), ("Supplier", "DocType"),
		("Supplier Audit Log", "DocType"), ("Supplier Profile Change Request", "DocType"),
		("Supplier Line Card", "DocType"), ("Supplier Onboarding Question Bank", "DocType"),
		("Supplier Audit Checklist", "DocType"),
	]),
	("Item and Price", "tag", [
		("Item", "DocType"), ("Item Manufacturer", "DocType"), ("Item Price Request", "DocType"),
		("Item Price", "DocType"), ("Item Classification", "DocType"),
	]),
	("Planning", "calendar", [
		("Sales Order", "DocType"), ("Requirement Log", "DocType"), ("Requirement Rebuild", "DocType"),
		("Auto PO Run", "DocType"), ("Auto PO Exception", "DocType"), ("Material Request", "DocType"),
	]),
	("Sourcing", "search", [
		("Request for Quotation", "DocType"), ("Supplier Quotation", "DocType"),
	]),
	("Ordering", "file-text", [
		("Purchase Order", "DocType"), ("PO Amendment", "DocType"), ("PO Acknowledgement", "DocType"),
		("PO Material Status", "DocType"), ("PO Shipment", "DocType"), ("Supplier Channel", "DocType"),
	]),
	("Inward", "truck", [
		("Gate Entry", "DocType"), ("Purchase Receipt", "DocType"), ("Quality Inspection", "DocType"),
		("Item Non Conformance", "DocType"), ("Inward Discrepancy", "DocType"), ("Landed Cost Voucher", "DocType"),
	]),
	("Finance", "wallet", [
		("Purchase Invoice", "DocType"), ("Payment Indent", "DocType"), ("Payment Request", "DocType"),
		("Payment Entry", "DocType"),
	]),
]


def app_reports():
	out = []
	for path in sorted(glob.glob(os.path.join(PKG, "ub_*", "report", "*", "*.json"))):
		d = json.load(open(path))
		if d.get("doctype") == "Report":
			out.append((d["name"], d.get("ref_doctype"), d.get("report_type")))
	return out


def exists(name, kind):
	return True  # all names above are standard ERPNext or this app's doctypes


def build():
	reports = app_reports()

	# ---- Workspace ----
	links, content = [], []
	for title, _icon, items in SECTIONS + [("Reports", "chart", [(r[0], "Report") for r in reports])]:
		links.append({"hidden": 0, "is_query_report": 0, "label": title, "link_count": len(items), "onboard": 0, "type": "Card Break"})
		for label, kind in items:
			row = {"hidden": 0, "is_query_report": 1 if kind == "Report" else 0, "label": label, "link_count": 0,
				"link_to": label, "link_type": kind, "onboard": 0, "type": "Link"}
			if kind == "Report":
				row["report_ref_doctype"] = next((r[1] for r in reports if r[0] == label), None)
			links.append(row)
		content.append({"id": title.lower().replace(" ", "_")[:10], "type": "card", "data": {"card_name": title, "col": 4}})
	content.insert(0, {"id": "ub_header", "type": "header", "data": {"text": "<span class=\"h4\"><b>Universal Buying</b></span>", "col": 12}})
	shortcuts = [
		{"label": "Auto PO Run", "link_to": "Auto PO Run", "type": "DocType", "color": "Grey", "doc_view": ""},
		{"label": "Auto PO Exception", "link_to": "Auto PO Exception", "type": "DocType", "color": "Grey", "doc_view": ""},
		{"label": "Request for Quotation", "link_to": "Request for Quotation", "type": "DocType", "color": "Grey", "doc_view": ""},
		{"label": "Purchase Order", "link_to": "Purchase Order", "type": "DocType", "color": "Grey", "doc_view": ""},
		{"label": "Purchase Receipt", "link_to": "Purchase Receipt", "type": "DocType", "color": "Grey", "doc_view": ""},
		{"label": "Buying Control Settings", "link_to": "Buying Control Settings", "type": "DocType", "color": "Grey", "doc_view": ""},
	]
	for i, s in enumerate(shortcuts):
		content.insert(1 + i, {"id": f"sc{i}", "type": "shortcut", "data": {"shortcut_name": s["label"], "col": 4}})
	ws = {
		"app": "universal_buying", "charts": [], "content": json.dumps(content), "creation": NOW, "custom_blocks": [],
		"docstatus": 0, "doctype": "Workspace", "for_user": "", "hide_custom": 0, "icon": "buying", "idx": 0,
		"is_hidden": 0, "label": "Universal Buying", "links": links, "modified": NOW, "modified_by": "Administrator",
		"module": "Universal Buying", "name": "Universal Buying", "number_cards": [], "owner": "Administrator",
		"parent_page": "", "public": 1, "quick_lists": [], "restrict_to_domain": "", "roles": [], "sequence_id": 6.0,
		"shortcuts": shortcuts, "title": "Universal Buying", "type": "Workspace",
	}
	d = os.path.join(PKG, "universal_buying", "workspace", "universal_buying")
	os.makedirs(d, exist_ok=True)
	json.dump(ws, open(os.path.join(d, "universal_buying.json"), "w"), indent=1, sort_keys=True)

	# ---- Workspace Sidebar ----
	items = [{"child": 0, "collapsible": 1, "icon": "home", "indent": 0, "keep_closed": 0, "label": "Home",
		"link_to": "Universal Buying", "link_type": "Workspace", "show_arrow": 0, "type": "Link"}]
	for title, icon, links_ in SECTIONS + [("Reports", "chart", [(r[0], "Report") for r in reports])]:
		items.append({"child": 0, "collapsible": 1, "icon": icon, "indent": 1, "keep_closed": 1 if title in ("Setup", "Reports") else 0,
			"label": title, "link_type": "DocType", "show_arrow": 0, "type": "Section Break"})
		for label, kind in links_:
			items.append({"child": 1, "collapsible": 1, "indent": 0, "keep_closed": 0, "label": label, "link_to": label,
				"link_type": kind, "show_arrow": 0, "type": "Link"})
	for i, it in enumerate(items, 1):
		it.update({"doctype": "Workspace Sidebar Item", "idx": i, "parent": "Universal Buying", "parentfield": "items",
			"parenttype": "Workspace Sidebar", "name": f"ubsb{i:03d}", "creation": NOW, "modified": NOW,
			"modified_by": "Administrator", "owner": "Administrator", "docstatus": 0})
	sb = {"app": "universal_buying", "creation": NOW, "docstatus": 0, "doctype": "Workspace Sidebar", "header_icon": "buying",
		"idx": 0, "items": items, "modified": NOW, "modified_by": "Administrator", "module": "Universal Buying",
		"name": "Universal Buying", "owner": "Administrator", "standard": 1, "title": "Universal Buying"}
	d = os.path.join(PKG, "workspace_sidebar")
	os.makedirs(d, exist_ok=True)
	json.dump(sb, open(os.path.join(d, "universal_buying.json"), "w"), indent=1, sort_keys=True)

	# ---- Desktop Icon ----
	icon = {"app": "universal_buying", "creation": NOW, "docstatus": 0, "doctype": "Desktop Icon", "hidden": 0, "icon": "buying",
		"icon_type": "Link", "idx": 1, "label": "Universal Buying", "link_to": "Universal Buying", "link_type": "Workspace Sidebar",
		"modified": NOW, "modified_by": "Administrator", "name": "Universal Buying", "owner": "Administrator",
		"parent_icon": "", "restrict_removal": 0, "roles": [], "standard": 1}
	d = os.path.join(PKG, "desktop_icon")
	os.makedirs(d, exist_ok=True)
	json.dump(icon, open(os.path.join(d, "universal_buying.json"), "w"), indent=1, sort_keys=True)
	print("reports", len(reports), "sidebar items", len(items))


build()
