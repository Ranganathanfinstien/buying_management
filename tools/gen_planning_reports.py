"""Write the UB Planning Script Report JSON stubs (worker B). py/js are hand written."""

import json
import os

BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "universal_buying", "ub_planning", "report")
NOW = "2026-09-26 12:00:00.000000"
ROLES = ["System Manager", "Purchase Manager", "Purchase User", "Sourcing User", "Sourcing Manager"]
REPORTS = [
	("Manufacturing Shortage Summary", "Requirement Log"),
	("PO Shortage Summary", "Requirement Log"),
	("Project Shortage Summary", "Requirement Log"),
	("Auto PO Exception", "Auto PO Exception"),
	("Excess PO", "Purchase Order"),
]

for name, ref in REPORTS:
	folder = os.path.join(BASE, name.lower().replace(" ", "_"))
	os.makedirs(folder, exist_ok=True)
	open(os.path.join(folder, "__init__.py"), "a").close()
	doc = {
		"add_total_row": 0,
		"creation": NOW,
		"disabled": 0,
		"docstatus": 0,
		"doctype": "Report",
		"idx": 0,
		"is_standard": "Yes",
		"modified": NOW,
		"modified_by": "Administrator",
		"module": "UB Planning",
		"name": name,
		"owner": "Administrator",
		"prepared_report": 0,
		"ref_doctype": ref,
		"report_name": name,
		"report_type": "Script Report",
		"roles": [{"role": r} for r in ROLES],
	}
	with open(os.path.join(folder, name.lower().replace(" ", "_") + ".json"), "w") as f:
		json.dump(doc, f, indent=1, sort_keys=True)
print("reports written")
