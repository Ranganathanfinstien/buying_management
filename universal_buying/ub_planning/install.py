"""UB Planning install contributions (merged by universal_buying.setup.install)."""

ROLES = []

CUSTOM_FIELDS = {
	"Item": [
		{"fieldname": "ub_built_type", "label": "Built Type", "fieldtype": "Select", "options": "Standard\nCustom",
			"default": "Standard", "insert_after": "item_group", "in_standard_filter": 1},
		{"fieldname": "ub_revision_no", "label": "Revision No", "fieldtype": "Data", "insert_after": "ub_built_type"},
		{"fieldname": "ub_standard_packing_qty", "label": "Standard Packing Qty (SPQ)", "fieldtype": "Float",
			"insert_after": "min_order_qty", "non_negative": 1,
			"description": "Auto PO rounds order quantities up to a multiple of this (purchase UOM)."},
		{"fieldname": "ub_compliance_section", "label": "Supplier Compliance", "fieldtype": "Section Break",
			"insert_after": "quality_inspection_template", "collapsible": 1},
		{"fieldname": "ub_test_certificate_required", "label": "Test Certificate Required", "fieldtype": "Check",
			"insert_after": "ub_compliance_section"},
		{"fieldname": "ub_coc_required", "label": "CoC Required", "fieldtype": "Check",
			"insert_after": "ub_test_certificate_required"},
		{"fieldname": "ub_fai_required", "label": "FAI Required", "fieldtype": "Check", "insert_after": "ub_coc_required"},
		{"fieldname": "ub_compliance_col", "fieldtype": "Column Break", "insert_after": "ub_fai_required"},
		{"fieldname": "ub_rohs", "label": "RoHS", "fieldtype": "Check", "insert_after": "ub_compliance_col"},
		{"fieldname": "ub_reach", "label": "REACH", "fieldtype": "Check", "insert_after": "ub_rohs"},
		{"fieldname": "ub_ppap_level", "label": "PPAP Level", "fieldtype": "Select", "options": "\nL1\nL2\nL3\nL4\nL5",
			"insert_after": "ub_reach"},
	],
	"Item Manufacturer": [
		{"fieldname": "ub_disabled", "label": "Disabled", "fieldtype": "Check", "insert_after": "is_default",
			"in_list_view": 1, "in_standard_filter": 1,
			"description": "A disabled manufacturer / MPN is blocked on Purchase Orders and inspections."},
	],
	"Item Price": [
		{"fieldname": "ub_company", "label": "Company", "fieldtype": "Link", "options": "Company",
			"insert_after": "supplier", "in_standard_filter": 1},
		{"fieldname": "ub_item_manufacturer", "label": "MPN (Item Manufacturer)", "fieldtype": "Link",
			"options": "Item Manufacturer", "insert_after": "ub_company"},
		{"fieldname": "ub_manufacturer", "label": "Manufacturer", "fieldtype": "Link", "options": "Manufacturer",
			"insert_after": "ub_item_manufacturer", "fetch_from": "ub_item_manufacturer.manufacturer",
			"fetch_if_empty": 1},
	],
}

PROPERTY_SETTERS = []
