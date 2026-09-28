"""UB Finance install data: Purchase Invoice / Supplier custom fields and the optional invoice approval workflow."""

ROLES = []

CUSTOM_FIELDS = {
	"Purchase Invoice": [
		{"fieldname": "ub_is_import", "label": "Is Import", "fieldtype": "Check", "insert_after": "bill_date",
		 "read_only": 1, "description": "Set automatically: supplier address country differs from the company country."},
		{"fieldname": "ub_boe_no", "label": "Bill of Entry No", "fieldtype": "Data", "insert_after": "ub_is_import",
		 "depends_on": "eval:doc.ub_is_import", "description": "Used to fetch the exchange rate from the Purchase Receipt."},
		{"fieldname": "ub_boe_date", "label": "Bill of Entry Date", "fieldtype": "Date", "insert_after": "ub_boe_no",
		 "depends_on": "eval:doc.ub_is_import"},
		{"fieldname": "ub_override_section", "label": "PO Tolerance Override", "fieldtype": "Section Break",
		 "insert_after": "items", "collapsible": 1, "collapsible_depends_on": "eval:doc.ub_override_reason"},
		{"fieldname": "ub_override_reason", "label": "Override Reason (Invoice above PO + Tolerance)", "fieldtype": "Small Text",
		 "insert_after": "ub_override_section", "no_copy": 1,
		 "description": "Required only when the invoice total is above the Purchase Order total plus the PO Type tolerance."},
		{"fieldname": "ub_tds_opening_applied", "label": "TDS Opening Balance Applied", "fieldtype": "Check",
		 "insert_after": "apply_tds", "read_only": 1, "no_copy": 1, "print_hide": 1},
		{"fieldname": "ub_tds_opening_amount", "label": "TDS Applicable Amount (Opening Balance Mode)", "fieldtype": "Currency",
		 "insert_after": "ub_tds_opening_applied", "read_only": 1, "no_copy": 1, "print_hide": 1,
		 "options": "Company:company:default_currency", "depends_on": "eval:doc.ub_tds_opening_applied"},
	],
	"Supplier": [
		{"fieldname": "ub_tds_opening_section", "label": "TDS Opening Balance", "fieldtype": "Section Break",
		 "insert_after": "tax_withholding_group", "collapsible": 1,
		 "description": "Used only when 'TDS Opening Balance Mode' is on in Buying Control Settings."},
		{"fieldname": "ub_tax_withholding_details", "label": "Opening Balance Categories", "fieldtype": "Table",
		 "options": "UB Supplier TDS Category", "insert_after": "ub_tds_opening_section"},
		{"fieldname": "ub_tds_opening_balances", "label": "Opening Balance per Company", "fieldtype": "Table",
		 "options": "UB Supplier TDS Balance", "insert_after": "ub_tax_withholding_details"},
	],
}

PROPERTY_SETTERS = []


def setup():
	from universal_buying.ub_finance.invoice_approval import sync_invoice_approval_workflow

	sync_invoice_approval_workflow()
