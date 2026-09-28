"""UB Inward install data: roles, custom fields on standard doctypes, default discrepancy types."""

import frappe

ROLES = ["IQC User", "Security User", "Quality Manager"]

CUSTOM_FIELDS = {
	"Purchase Receipt": [
		{
			"fieldname": "ub_inward_section",
			"fieldtype": "Section Break",
			"label": "Inward Details",
			"insert_after": "supplier_delivery_note",
			"collapsible": 0,
		},
		{
			"fieldname": "ub_supplier_invoice_no",
			"fieldtype": "Data",
			"label": "Supplier Invoice No",
			"insert_after": "ub_inward_section",
			"in_standard_filter": 1,
			"search_index": 1,
		},
		{
			"fieldname": "ub_supplier_invoice_date",
			"fieldtype": "Date",
			"label": "Supplier Invoice Date",
			"insert_after": "ub_supplier_invoice_no",
		},
		{
			"fieldname": "ub_gate_entry",
			"fieldtype": "Link",
			"label": "Gate Entry",
			"options": "Gate Entry",
			"insert_after": "ub_supplier_invoice_date",
			"search_index": 1,
			"depends_on": "eval:!doc.is_return",
		},
		{"fieldname": "ub_inward_col", "fieldtype": "Column Break", "insert_after": "ub_gate_entry"},
		{
			"fieldname": "ub_is_import",
			"fieldtype": "Check",
			"label": "Is Import",
			"insert_after": "ub_inward_col",
			"description": "Set from the Purchase Order or the supplier address country.",
		},
		{
			"fieldname": "ub_boe_no",
			"fieldtype": "Data",
			"label": "Bill of Entry No",
			"insert_after": "ub_is_import",
			"search_index": 1,
			"depends_on": "eval:doc.ub_is_import || doc.ub_is_bonded",
		},
		{
			"fieldname": "ub_boe_date",
			"fieldtype": "Date",
			"label": "Bill of Entry Date",
			"insert_after": "ub_boe_no",
			"depends_on": "eval:doc.ub_is_import || doc.ub_is_bonded",
		},
		{"fieldname": "ub_inward_col_2", "fieldtype": "Column Break", "insert_after": "ub_boe_date"},
		{
			"fieldname": "ub_is_bonded",
			"fieldtype": "Check",
			"label": "Bonded Goods",
			"insert_after": "ub_inward_col_2",
			"description": "Bonded route (only when enabled in Buying Control Settings): no gate entry, no IQC, bonded warehouse.",
		},
		{
			"fieldname": "ub_green_card",
			"fieldtype": "Check",
			"label": "Green Card Supplier",
			"read_only": 1,
			"insert_after": "ub_is_bonded",
			"no_copy": 1,
		},
		{
			"fieldname": "ub_iqc_complete",
			"fieldtype": "Check",
			"label": "IQC Complete",
			"read_only": 1,
			"insert_after": "ub_green_card",
			"no_copy": 1,
			"allow_on_submit": 1,
		},
		{
			"fieldname": "ub_inward_discrepancy",
			"fieldtype": "Link",
			"label": "Inward Discrepancy",
			"options": "Inward Discrepancy",
			"read_only": 1,
			"insert_after": "ub_iqc_complete",
			"no_copy": 1,
			"allow_on_submit": 1,
		},
	],
	"Purchase Receipt Item": [
		{
			"fieldname": "ub_manufacturer_batch_no",
			"fieldtype": "Data",
			"label": "Manufacturer Batch No",
			"insert_after": "manufacturer_part_no",
			"in_list_view": 0,
		},
		{
			"fieldname": "ub_manufacturing_date",
			"fieldtype": "Date",
			"label": "Manufacturing Date",
			"insert_after": "ub_manufacturer_batch_no",
		},
	],
	"Batch": [
		{
			"fieldname": "ub_manufacturer_batch_no",
			"fieldtype": "Data",
			"label": "Manufacturer Batch No",
			"insert_after": "manufacturing_date",
			"read_only": 1,
			"search_index": 1,
		},
		{
			"fieldname": "ub_manufacturer_part_no",
			"fieldtype": "Data",
			"label": "Manufacturer Part No",
			"insert_after": "ub_manufacturer_batch_no",
			"read_only": 1,
		},
	],
	"Quality Inspection": [
		{
			"fieldname": "ub_iqc_section",
			"fieldtype": "Section Break",
			"label": "Incoming Inspection",
			"insert_after": "description",
		},
		{
			"fieldname": "ub_sample_taken",
			"fieldtype": "Float",
			"label": "Sample Taken",
			"insert_after": "ub_iqc_section",
			"description": "Must be at least the sample size (V-24.2), except green card suppliers when allowed.",
		},
		{
			"fieldname": "ub_batch_qty",
			"fieldtype": "Float",
			"label": "Lot Qty",
			"read_only": 1,
			"insert_after": "ub_sample_taken",
		},
		{"fieldname": "ub_iqc_col", "fieldtype": "Column Break", "insert_after": "ub_batch_qty"},
		{
			"fieldname": "ub_received_manufacturer",
			"fieldtype": "Link",
			"label": "Received Manufacturer",
			"options": "Manufacturer",
			"insert_after": "ub_iqc_col",
		},
		{
			"fieldname": "ub_received_manufacturer_part_no",
			"fieldtype": "Data",
			"label": "Received Manufacturer Part No",
			"insert_after": "ub_received_manufacturer",
		},
		{
			"fieldname": "ub_alternate_mpn",
			"fieldtype": "Check",
			"label": "Alternate MPN",
			"insert_after": "ub_received_manufacturer_part_no",
			"description": "Tick when the received MPN is not an approved Item Manufacturer (V-24.1).",
		},
		{
			"fieldname": "ub_item_non_conformance",
			"fieldtype": "Link",
			"label": "Item Non Conformance",
			"options": "Item Non Conformance",
			"read_only": 1,
			"no_copy": 1,
			"allow_on_submit": 1,
			"insert_after": "ub_alternate_mpn",
		},
	],
	"Quality Inspection Template": [
		{
			"fieldname": "ub_sampling_section",
			"fieldtype": "Section Break",
			"label": "Sampling Plan",
			"insert_after": "item_quality_inspection_parameter",
		},
		{
			"fieldname": "ub_sampling_bands",
			"fieldtype": "Table",
			"label": "Sampling Bands",
			"options": "UB QI Sampling Band",
			"insert_after": "ub_sampling_section",
			"description": "Sample size by inward lot quantity. Used for incoming inspections.",
		},
	],
	"Stock Entry": [
		{
			"fieldname": "ub_item_non_conformance",
			"fieldtype": "Link",
			"label": "Item Non Conformance",
			"options": "Item Non Conformance",
			"read_only": 1,
			"no_copy": 1,
			"insert_after": "stock_entry_type",
			"search_index": 1,
		},
	],
	"Landed Cost Voucher": [
		{
			"fieldname": "ub_boe_no",
			"fieldtype": "Data",
			"label": "Bill of Entry No",
			"insert_after": "company",
		},
		{
			"fieldname": "ub_fetch_receipts",
			"fieldtype": "Button",
			"label": "Get Receipts for Bill of Entry",
			"insert_after": "ub_boe_no",
			"depends_on": "eval:doc.docstatus==0 && doc.ub_boe_no",
		},
		{
			"fieldname": "ub_expected_total",
			"fieldtype": "Currency",
			"label": "Expected Charges Total",
			"options": "Company:company:default_currency",
			"insert_after": "total_taxes_and_charges",
			"description": "Optional. When set, Total Taxes and Charges must match it.",
		},
	],
}

PROPERTY_SETTERS = []

DEFAULT_DISCREPANCY_TYPES = [
	("Short Supply", "Received quantity is less than the invoice quantity."),
	("Excess Supply", "Received quantity is more than the invoice quantity."),
	("Wrong Item", "Item received does not match the order."),
	("Damaged", "Goods or packing received damaged."),
	("Rate Difference", "Invoice rate differs from the order rate."),
	("Documents Missing", "Invoice, packing list or certificates missing."),
]


def setup():
	if not frappe.db.exists("DocType", "Inward Discrepancy Type"):
		return
	for name, description in DEFAULT_DISCREPANCY_TYPES:
		if not frappe.db.exists("Inward Discrepancy Type", name):
			frappe.get_doc(
				{"doctype": "Inward Discrepancy Type", "discrepancy_type": name, "description": description}
			).insert(ignore_permissions=True)
