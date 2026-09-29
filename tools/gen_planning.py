"""Generate the UB Planning doctypes (worker B). Re-run freely: only .json files are rewritten."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_doctype import F, make_doctype, perm  # noqa: E402

M = "UB Planning"


def ro(fieldname, fieldtype, label, **kw):
	kw.setdefault("read_only", 1)
	return F(fieldname, fieldtype, label, **kw)


def readonly_perms(*roles):
	return [perm(r, write=0, create=0, delete=0, print_=1, email=0, share=0) for r in roles]


# ---------------------------------------------------------------- Requirement Log
make_doctype(
	module=M,
	name="Requirement Log",
	autoname="hash",
	fields=[
		ro("company", "Link", "Company", options="Company", in_list_view=1, in_standard_filter=1, search_index=1),
		ro("reservation_type", "Select", "Reservation Type", options="Stock\nPurchase Order\nWork Order\nShortage",
			in_list_view=1, in_standard_filter=1, search_index=1),
		ro("item_code", "Link", "Item Code", options="Item", in_list_view=1, in_standard_filter=1, search_index=1),
		ro("qty", "Float", "Qty (Stock UOM)", in_list_view=1),
		ro("stock_uom", "Link", "Stock UOM", options="UOM"),
		F("col_1", "Column Break"),
		ro("demand_type", "Select", "Demand Type", options="Sales Order\nWork Order\nSafety Stock", in_standard_filter=1),
		ro("project", "Link", "Project", options="Project", in_standard_filter=1, search_index=1),
		ro("cost_center", "Link", "Cost Center", options="Cost Center"),
		ro("delivery_date", "Date", "Delivery Date", in_list_view=1),
		ro("grouped_delivery_date", "Date", "Grouped Delivery Date (Month)", search_index=1),
		F("demand_section", "Section Break", "Demand"),
		ro("sales_order", "Link", "Sales Order", options="Sales Order", in_standard_filter=1),
		ro("sales_order_item", "Data", "Sales Order Item", search_index=1),
		ro("demand_work_order", "Link", "Demand Work Order", options="Work Order"),
		F("col_2", "Column Break"),
		ro("fg_item_code", "Link", "FG Item Code", options="Item"),
		ro("bom_no", "Link", "BOM (exploded from)", options="BOM"),
		ro("bom_item_type", "Select", "BOM Item Type", options="\nFinished Good\nSub Assembly\nComponent"),
		ro("level", "Int", "BOM Level"),
		F("supply_section", "Section Break", "Supply"),
		ro("warehouse", "Link", "Warehouse", options="Warehouse"),
		ro("purchase_order", "Link", "Purchase Order", options="Purchase Order"),
		ro("purchase_order_item", "Data", "Purchase Order Item", search_index=1),
		F("col_3", "Column Break"),
		ro("work_order", "Link", "Work Order (supply)", options="Work Order"),
		ro("rebuild_id", "Data", "Rebuild ID", search_index=1),
		ro("posting_datetime", "Datetime", "Rebuilt On"),
	],
	permissions=readonly_perms("System Manager", "Purchase Manager", "Purchase User", "Stock User", "Sourcing User",
		"Sourcing Manager"),
	track_changes=0,
	sort_field="creation",
	extra={"in_create": 1, "description": "Written by the nightly Requirement Engine. Do not edit."},
	list_js=True,
)

# ---------------------------------------------------------------- Requirement Rebuild (status per company)
make_doctype(
	module=M,
	name="Requirement Rebuild",
	autoname="hash",
	fields=[
		ro("company", "Link", "Company", options="Company", in_list_view=1, in_standard_filter=1),
		ro("status", "Select", "Status", options="Queued\nRunning\nCompleted\nFailed\nSkipped", in_list_view=1,
			in_standard_filter=1),
		ro("rebuild_id", "Data", "Rebuild ID"),
		ro("triggered_by", "Link", "Triggered By", options="User"),
		F("col_1", "Column Break"),
		ro("started_at", "Datetime", "Started At", in_list_view=1),
		ro("completed_at", "Datetime", "Completed At"),
		ro("row_count", "Int", "Rows Written", in_list_view=1),
		ro("shortage_rows", "Int", "Shortage Rows"),
		F("error_section", "Section Break", "Error", collapsible=1),
		ro("error_message", "Long Text", "Error Message"),
	],
	permissions=[
		perm("System Manager", write=0, delete=1),
		perm("Purchase Manager", write=0),
		perm("Purchase User", write=0, create=0),
	],
	track_changes=0,
	title_field="company",
	extra={"in_create": 1},
	list_js=True,
)

# ---------------------------------------------------------------- Item Classification
make_doctype(
	module=M,
	name="Item Classification",
	autoname="hash",
	fields=[
		ro("item_code", "Link", "Item Code", options="Item", in_list_view=1, in_standard_filter=1, search_index=1),
		ro("company", "Link", "Company", options="Company", in_list_view=1, in_standard_filter=1, search_index=1),
		ro("project", "Link", "Project", options="Project", in_list_view=1, in_standard_filter=1),
		F("col_1", "Column Break"),
		ro("item_class", "Select", "Class", options="A\nB\nC", in_list_view=1, in_standard_filter=1),
		ro("value", "Currency", "Consumption Value", options="Company:company:default_currency"),
		ro("cumulative_percent", "Percent", "Cumulative % Before Item"),
		ro("computed_on", "Datetime", "Computed On"),
	],
	permissions=readonly_perms("System Manager", "Purchase Manager", "Purchase User", "Sourcing User", "Sourcing Manager"),
	track_changes=0,
	extra={"in_create": 1},
)

# ---------------------------------------------------------------- Auto PO Run
make_doctype(
	module=M,
	name="Auto PO Run Item",
	istable=1,
	fields=[
		F("item_code", "Link", "Item Code", options="Item", reqd=1, in_list_view=1),
		F("item_name", "Data", "Item Name", fetch_from="item_code.item_name", read_only=1, in_list_view=1),
	],
)

make_doctype(
	module=M,
	name="Auto PO Run",
	naming_series="APO-.YYYY.-.#####",
	is_submittable=1,
	fields=[
		F("company", "Link", "Company", options="Company", reqd=1, in_list_view=1, in_standard_filter=1,
			remember_last_selected_value=1),
		F("project", "Link", "Project", options="Project", in_list_view=1, in_standard_filter=1,
			description="Only used when Buying Control Settings > Plan by Project is on. Leave empty to plan all projects."),
		F("to_date", "Date", "To Date", reqd=1, in_list_view=1),
		F("lead_time_order", "Check", "Lead-time Mode", default="0",
			description="Order date = required date minus the shortest Supplier Line Card lead time for the item's MPN."),
		F("col_1", "Column Break"),
		ro("status", "Select", "Status", options="Not Started\nQueued\nIn Progress\nCompleted\nCompleted with Errors\nFailed", default="Not Started",
			allow_on_submit=1, in_list_view=1, in_standard_filter=1, no_copy=1),
		ro("started_at", "Datetime", "Started At", allow_on_submit=1, no_copy=1),
		ro("completed_at", "Datetime", "Completed At", allow_on_submit=1, no_copy=1),
		F("filters_section", "Section Break", "Item Filter",
			description="Optional. When rows are added only these items are ordered (exceptions still cover every item)."),
		F("items_filter", "Table", "Items", options="Auto PO Run Item"),
		F("result_section", "Section Break", "Result"),
		ro("po_count", "Int", "Purchase Orders Created", allow_on_submit=1, no_copy=1),
		ro("purchase_orders", "Small Text", "Purchase Orders", allow_on_submit=1, no_copy=1),
		F("col_2", "Column Break"),
		ro("exception_count", "Int", "Exception Rows", allow_on_submit=1, no_copy=1),
		ro("auto_po_exception", "Link", "Auto PO Exception", options="Auto PO Exception", allow_on_submit=1, no_copy=1),
		F("error_section", "Section Break", "Error Log", collapsible=1),
		ro("error_message", "Long Text", "Error Message", allow_on_submit=1, no_copy=1),
	],
	permissions=[
		perm("System Manager", delete=1, submit=1, cancel=1, amend=1),
		perm("Purchase Manager", delete=1, submit=1, cancel=1, amend=1),
		perm("Purchase User", submit=1),
	],
	title_field="company",
	js=True,
	list_js=True,
)

# ---------------------------------------------------------------- Auto PO Exception
make_doctype(
	module=M,
	name="Auto PO Exception Detail",
	istable=1,
	fields=[
		ro("exception_type", "Select", "Exception Type", options="No Supplier\nNo Price\nMOQ Exception", in_list_view=1,
			columns=1),
		ro("item_code", "Link", "Item Code", options="Item", in_list_view=1, columns=2),
		ro("item_name", "Data", "Item Name"),
		ro("description", "Small Text", "Description"),
		ro("project", "Link", "Project", options="Project"),
		ro("item_class", "Data", "Class", in_list_view=1, columns=1),
		ro("po_shortage", "Float", "Shortage", in_list_view=1, columns=1),
		ro("uom", "Link", "UOM", options="UOM"),
		ro("required_by", "Date", "Required By"),
		F("col_1", "Column Break"),
		ro("moq", "Float", "MOQ", in_list_view=1, columns=1),
		ro("spq", "Float", "SPQ"),
		ro("default_supplier", "Link", "Default Supplier", options="Supplier", in_list_view=1, columns=1),
		ro("rate", "Float", "Rate"),
		ro("currency", "Link", "Currency", options="Currency"),
		ro("manufacturer", "Link", "Manufacturer", options="Manufacturer"),
		ro("mpn", "Data", "MPN"),
		F("follow_section", "Section Break", "Follow-up"),
		ro("status", "Data", "Status", allow_on_submit=1, in_list_view=1, columns=1),
		ro("item_price_request", "Link", "Item Price Request", options="Item Price Request", allow_on_submit=1),
		ro("purchase_order", "Link", "Purchase Order", options="Purchase Order", allow_on_submit=1),
		F("col_2", "Column Break"),
		F("follow_up", "Data", "Follow-up", allow_on_submit=1, in_list_view=1, columns=2,
			description="RFQ / PO name or note. Rows with a follow-up are not repeated on the next run."),
	],
)

make_doctype(
	module=M,
	name="Auto PO Exception",
	naming_series="APE-.YYYY.-.#####",
	is_submittable=1,
	fields=[
		F("company", "Link", "Company", options="Company", reqd=1, in_list_view=1, in_standard_filter=1),
		F("project", "Link", "Project", options="Project", in_list_view=1, in_standard_filter=1),
		F("col_1", "Column Break"),
		F("to_date", "Date", "To Date", reqd=1, in_list_view=1),
		F("lead_time_order", "Check", "Lead-time Mode", default="0"),
		ro("auto_po_reference", "Link", "Auto PO Run", options="Auto PO Run", in_standard_filter=1),
		F("items_section", "Section Break", "Exceptions"),
		F("items", "Table", "Exception Items", options="Auto PO Exception Detail", allow_on_submit=1),
	],
	permissions=[
		perm("System Manager", delete=1, submit=1, cancel=1, amend=1),
		perm("Purchase Manager", delete=1, submit=1, cancel=1, amend=1),
		perm("Purchase User", submit=1),
	],
	title_field="company",
	js=True,
)

# ---------------------------------------------------------------- Item Price Request
make_doctype(
	module=M,
	name="Item Price Request Detail",
	istable=1,
	fields=[
		F("item_code", "Link", "Item Code", options="Item", reqd=1, in_list_view=1, columns=2),
		F("item_name", "Data", "Item Name", fetch_from="item_code.item_name", read_only=1),
		F("item_description", "Small Text", "Description", fetch_from="item_code.description", read_only=1),
		F("uom", "Link", "UOM", options="UOM", reqd=1, in_list_view=1, columns=1),
		F("item_manufacturer", "Link", "MPN (Item Manufacturer)", options="Item Manufacturer", in_list_view=1, columns=2),
		F("manufacturer", "Link", "Manufacturer", options="Manufacturer", fetch_from="item_manufacturer.manufacturer",
			read_only=1),
		F("manufacturer_part_no", "Data", "Manufacturer Part No", fetch_from="item_manufacturer.manufacturer_part_no",
			read_only=1),
		F("project", "Link", "Project", options="Project"),
		F("col_1", "Column Break"),
		F("supplier", "Link", "Supplier", options="Supplier", in_list_view=1, columns=2),
		F("customer", "Link", "Customer", options="Customer"),
		F("price_list", "Link", "Price List", options="Price List", reqd=1),
		F("currency", "Link", "Currency", options="Currency", fetch_from="price_list.currency", read_only=1),
		F("rate", "Currency", "Rate", options="currency", reqd=1, in_list_view=1, columns=1),
		F("col_2", "Column Break"),
		F("moq", "Float", "MOQ"),
		F("spq", "Float", "SPQ"),
		F("lead_time_days", "Int", "Lead Time Days", reqd=1),
		F("valid_from", "Date", "Valid From", reqd=1, in_list_view=1, columns=1),
		F("valid_upto", "Date", "Valid Upto", reqd=1, in_list_view=1, columns=1),
		ro("item_price", "Link", "Item Price Created", options="Item Price", no_copy=1),
	],
)

make_doctype(
	module=M,
	name="Item Price Request",
	naming_series="IPR-.YYYY.-.#####",
	is_submittable=1,
	fields=[
		F("company", "Link", "Company", options="Company", reqd=1, in_list_view=1, in_standard_filter=1,
			remember_last_selected_value=1),
		F("col_1", "Column Break"),
		F("type", "Select", "Type", options="Buying\nSelling", default="Buying", reqd=1, in_list_view=1,
			in_standard_filter=1),
		F("items_section", "Section Break"),
		F("item_price_details", "Table", "Items", options="Item Price Request Detail", reqd=1),
		F("previous_section", "Section Break", "Previous Prices", collapsible=1),
		F("previous_prices", "HTML", "Previous Prices"),
	],
	permissions=[
		perm("System Manager", delete=1, submit=1, cancel=1, amend=1),
		perm("Purchase Manager", delete=1, submit=1, cancel=1, amend=1),
		perm("Purchase User", submit=1),
		perm("Sourcing Manager", delete=1, submit=1, cancel=1, amend=1),
		perm("Sourcing User", submit=1),
	],
	title_field="company",
	js=True,
)

print("UB Planning doctypes generated")
