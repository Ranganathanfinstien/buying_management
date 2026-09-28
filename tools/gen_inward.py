"""Generate the UB Inward doctypes (BRD v2 sections 6.22 - 6.26)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_doctype import F, make_doctype, perm

M = "UB Inward"

STOCK_ROLES = [
	perm("System Manager", delete=1, submit=1, cancel=1, amend=1),
	perm("Stock Manager", delete=1, submit=1, cancel=1, amend=1),
	perm("Stock User", submit=1),
]

# ---- Gate Entry (6.22) -------------------------------------------------------
make_doctype(
	M,
	"Gate Entry",
	[
		F("company", "Link", "Company", options="Company", reqd=1, in_standard_filter=1),
		F(
			"entry_type",
			"Select",
			"Entry Type",
			options="In\nOut",
			default="In",
			reqd=1,
			in_list_view=1,
			in_standard_filter=1,
		),
		F("entry_date", "Datetime", "Entry Date", default="Now", reqd=1, in_list_view=1),
		F("col_1", "Column Break"),
		F(
			"party_type",
			"Select",
			"Party Type",
			options="Supplier\nCustomer\nEmployee",
			default="Supplier",
			reqd=1,
		),
		F(
			"party",
			"Dynamic Link",
			"Party",
			options="party_type",
			reqd=1,
			in_list_view=1,
			in_standard_filter=1,
		),
		F("party_name", "Data", "Party Name", read_only=1),
		F("invoice_section", "Section Break", "Documents"),
		F(
			"invoice_numbers",
			"Small Text",
			"Invoice / DC Numbers",
			description="One supplier invoice or delivery challan number per line.",
		),
		F("col_2", "Column Break"),
		F("no_of_invoices", "Int", "Number of Invoices / DC", default="1"),
		F("no_of_boxes", "Int", "Number of Boxes"),
		F("vehicle_section", "Section Break", "Vehicle"),
		F("vehicle_no", "Data", "Vehicle / Docket Number"),
		F("transporter_name", "Data", "Transporter Name"),
		F("col_3", "Column Break"),
		F("lr_no", "Data", "LR / AWB Number"),
		F("handover_section", "Section Break", "Handover"),
		F("employee", "Link", "Handover Employee", options="Employee"),
		F("employee_name", "Data", "Employee Name", fetch_from="employee.employee_name", read_only=1),
		F("col_4", "Column Break"),
		F(
			"external_party",
			"Data",
			"External Person",
			description="Driver / courier person handing over or receiving the goods.",
		),
		F("outward_section", "Section Break", "Outward Reference", depends_on="eval:doc.entry_type=='Out'"),
		F(
			"document_type",
			"Select",
			"Document Type",
			options="\nDelivery Note\nSales Invoice\nStock Entry\nPurchase Receipt",
		),
		F("col_5", "Column Break"),
		F("document_number", "Dynamic Link", "Document Number", options="document_type"),
		F("remarks_section", "Section Break"),
		F("remarks", "Small Text", "Remarks"),
	],
	is_submittable=1,
	title_field="party",
	search_fields="party,entry_type,vehicle_no",
	permissions=[*STOCK_ROLES, perm("Security User", submit=1)],
	js=True,
)

# ---- Inward Discrepancy (6.26) -----------------------------------------------
make_doctype(
	M,
	"Inward Discrepancy Type",
	[
		F("discrepancy_type", "Data", "Discrepancy Type", reqd=1, unique=1, in_list_view=1),
		F("description", "Small Text", "Description"),
	],
	autoname="field:discrepancy_type",
	permissions=[
		perm("System Manager", delete=1),
		perm("Stock Manager", delete=1),
		perm("Purchase Manager"),
		perm("Stock User", write=0, create=0),
		perm("Purchase User", write=0, create=0),
	],
	quick_entry=1,
)

make_doctype(
	M,
	"Inward Discrepancy Item",
	[
		F("item_code", "Link", "Item Code", options="Item", reqd=1, in_list_view=1),
		F("item_name", "Data", "Item Name", fetch_from="item_code.item_name", read_only=1),
		F("invoice_qty", "Float", "Invoice Qty", in_list_view=1),
		F("received_qty", "Float", "Received Qty", in_list_view=1),
		F("rate", "Currency", "Rate", in_list_view=1),
		F("col_1", "Column Break"),
		F("discrepancy_type", "Link", "Discrepancy Type", options="Inward Discrepancy Type", in_list_view=1),
		F(
			"status",
			"Select",
			"Status",
			options="Open\nClosed",
			default="Open",
			in_list_view=1,
			allow_on_submit=1,
		),
		F("remarks", "Small Text", "Remarks", allow_on_submit=1),
		F("purchase_receipt_item", "Data", "Purchase Receipt Item", hidden=1, read_only=1),
	],
	istable=1,
)

make_doctype(
	M,
	"Inward Discrepancy",
	[
		F("company", "Link", "Company", options="Company", reqd=1),
		F("date", "Date", "Date", default="Today", reqd=1),
		F(
			"purchase_receipt",
			"Link",
			"Purchase Receipt",
			options="Purchase Receipt",
			reqd=1,
			in_list_view=1,
			in_standard_filter=1,
		),
		F("col_1", "Column Break"),
		F("supplier", "Link", "Supplier", options="Supplier", reqd=1, in_list_view=1, in_standard_filter=1),
		F("supplier_invoice_no", "Data", "Supplier Invoice No"),
		F("project", "Link", "Project", options="Project"),
		F(
			"status",
			"Select",
			"Status",
			options="Draft\nOpen\nClosed\nCancelled",
			default="Draft",
			read_only=1,
			in_list_view=1,
			in_standard_filter=1,
			no_copy=1,
		),
		F("items_section", "Section Break", "Items"),
		F("items", "Table", "Items", options="Inward Discrepancy Item", reqd=1),
		F("comments_section", "Section Break", "Comments"),
		F("iqc_remarks", "Small Text", "Stores / IQC Remarks"),
		F("col_2", "Column Break"),
		F(
			"buyer_comments",
			"Small Text",
			"Buyer Comments",
			description="Required before submit (V-26.1).",
			allow_on_submit=1,
		),
	],
	naming_series="ID-.YYYY.-.#####",
	is_submittable=1,
	title_field="supplier",
	permissions=STOCK_ROLES
	+ [
		perm("Purchase User", submit=1),
		perm("Purchase Manager", submit=1, cancel=1, amend=1),
		perm("IQC User", submit=1),
		perm("Quality Manager", submit=1, cancel=1, amend=1),
	],
	js=True,
	list_js=True,
)

# ---- Item Non Conformance (6.25) ---------------------------------------------
make_doctype(
	M,
	"Item Non Conformance",
	[
		F("company", "Link", "Company", options="Company", reqd=1),
		F("date", "Date", "Date", default="Today", reqd=1),
		F(
			"inspection_type",
			"Select",
			"Inspection Type",
			options="Incoming\nIn Process",
			default="Incoming",
			reqd=1,
		),
		F(
			"reference_type",
			"Select",
			"Reference Type",
			options="Purchase Receipt",
			default="Purchase Receipt",
			reqd=1,
		),
		F(
			"reference_name",
			"Dynamic Link",
			"Reference Name",
			options="reference_type",
			reqd=1,
			in_list_view=1,
			in_standard_filter=1,
		),
		F("quality_inspection", "Link", "Quality Inspection", options="Quality Inspection", read_only=1),
		F("col_1", "Column Break"),
		F("supplier", "Link", "Supplier", options="Supplier", read_only=1, in_standard_filter=1),
		F("supplier_invoice_no", "Data", "Supplier Invoice No", read_only=1),
		F("project", "Link", "Project", options="Project"),
		F(
			"status",
			"Select",
			"Status",
			options="Draft\nOpen\nCompleted\nCancelled",
			default="Draft",
			read_only=1,
			no_copy=1,
			in_list_view=1,
			in_standard_filter=1,
		),
		F("item_section", "Section Break", "Item"),
		F("item_code", "Link", "Item Code", options="Item", reqd=1, in_list_view=1, in_standard_filter=1),
		F("item_name", "Data", "Item Name", fetch_from="item_code.item_name", read_only=1),
		F("batch_no", "Link", "Batch", options="Batch"),
		F("purchase_receipt_item", "Data", "Purchase Receipt Item", hidden=1, read_only=1),
		F("col_2", "Column Break"),
		F("rejected_qty", "Float", "Rejected Qty (Stock UOM)", reqd=1),
		F(
			"rate",
			"Currency",
			"Receipt Rate (Company Currency)",
			read_only=1,
			description="Valued at the receipt rate.",
		),
		F("amount", "Currency", "Amount", read_only=1),
		F("rejected_warehouse", "Link", "Rejected Warehouse", options="Warehouse"),
		F("disposition_section", "Section Break", "Disposition"),
		F(
			"disposition",
			"Select",
			"Disposition",
			options="\nAccept On Deviation\nScrap\nReturn to Supplier\nTransfer\nRework",
		),
		F(
			"target_warehouse",
			"Link",
			"Target Warehouse",
			options="Warehouse",
			depends_on="eval:in_list(['Transfer','Rework','Accept On Deviation'], doc.disposition)",
			description="Transfer: required. Rework / Accept On Deviation: blank = accepted warehouse of the receipt row.",
		),
		F("supplier_capa_required", "Check", "Supplier CAPA Required"),
		F("col_3", "Column Break"),
		F("attachment", "Attach", "Attachment", description="Mandatory before submit."),
		F("remarks", "Small Text", "Remarks"),
		F("output_section", "Section Break", "Output Documents"),
		F(
			"stock_entry",
			"Link",
			"Stock Entry",
			options="Stock Entry",
			read_only=1,
			no_copy=1,
			allow_on_submit=1,
		),
		F("col_4", "Column Break"),
		F(
			"purchase_return",
			"Link",
			"Purchase Return",
			options="Purchase Receipt",
			read_only=1,
			no_copy=1,
			allow_on_submit=1,
		),
	],
	naming_series="INC-.YYYY.-.#####",
	is_submittable=1,
	title_field="item_code",
	permissions=STOCK_ROLES
	+ [
		perm("IQC User", submit=1),
		perm("Quality Manager", delete=1, submit=1, cancel=1, amend=1),
		perm("Purchase User", write=0, create=0),
	],
	js=True,
	list_js=True,
)

# ---- Sampling band child table for Quality Inspection Template (6.24) --------
make_doctype(
	M,
	"UB QI Sampling Band",
	[
		F("qty_from", "Float", "Lot Qty From", in_list_view=1, reqd=1),
		F("qty_to", "Float", "Lot Qty To", in_list_view=1, description="0 = no upper limit"),
		F("sample_qty", "Float", "Sample Qty", in_list_view=1, reqd=1),
	],
	istable=1,
)

print("UB Inward doctypes generated")
