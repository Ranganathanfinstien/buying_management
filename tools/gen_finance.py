"""Generate the UB Finance doctypes (worker F): TDS opening balance children and Payment Indent."""

import sys

sys.path.insert(0, "/home/finstein-emp/frappe-v16/apps/universal_buying/tools")
from make_doctype import F, make_doctype, perm

M = "UB Finance"

# ---- Supplier TDS opening balance (Supplier custom tables, BUILD_SPEC 6.1) ----------------
make_doctype(M, "UB Supplier TDS Category", [
	F("tax_withholding_category", "Link", "Tax Withholding Category", options="Tax Withholding Category", reqd=1, in_list_view=1),
	F("enabled", "Check", "Enabled", default="1", in_list_view=1,
		description="Apply the opening balance (tax only on the amount above the cumulative threshold) for this category."),
], istable=1)

make_doctype(M, "UB Supplier TDS Balance", [
	F("company", "Link", "Company", options="Company", reqd=1, in_list_view=1),
	F("existing_balance", "Currency", "Opening Balance", in_list_view=1, options="Company:company:default_currency",
		description="Amount already paid / credited to this supplier in the year before go-live."),
	F("updated_balance", "Currency", "Running Balance", in_list_view=1, read_only=1, options="Company:company:default_currency",
		description="Opening balance plus TDS-applicable amounts of invoices submitted in this system."),
], istable=1)

# ---- Payment Indent ----------------------------------------------------------------------
make_doctype(M, "Payment Indent PO", [
	F("purchase_order", "Link", "Purchase Order", options="Purchase Order", reqd=1, in_list_view=1),
	F("supplier", "Link", "Supplier", options="Supplier", fetch_from="purchase_order.supplier", read_only=1),
	F("transaction_date", "Date", "PO Date", fetch_from="purchase_order.transaction_date", read_only=1, in_list_view=1),
	F("currency", "Link", "Currency", options="Currency", fetch_from="purchase_order.currency", read_only=1),
	F("col_1", "Column Break"),
	F("grand_total", "Currency", "PO Value", options="currency", fetch_from="purchase_order.grand_total", read_only=1, in_list_view=1),
	F("advance_paid", "Currency", "Advance Paid", options="currency", fetch_from="purchase_order.advance_paid", read_only=1),
	F("allocated_amount", "Currency", "Requested Amount (Allocated)", options="currency", read_only=1, in_list_view=1, no_copy=1),
	F("payment_request", "Link", "Payment Request", options="Payment Request", read_only=1, allow_on_submit=1, no_copy=1, in_list_view=1),
], istable=1)

make_doctype(M, "Payment Indent Item", [
	F("purchase_order", "Link", "Purchase Order", options="Purchase Order", in_list_view=1, read_only=1),
	F("po_detail", "Data", "Purchase Order Item", hidden=1, read_only=1),
	F("item_code", "Link", "Item Code", options="Item", in_list_view=1, read_only=1),
	F("item_name", "Data", "Item Name", read_only=1),
	F("description", "Small Text", "Description", read_only=1),
	F("schedule_date", "Date", "Required By", read_only=1),
	F("col_1", "Column Break"),
	F("qty", "Float", "PO Qty", read_only=1, in_list_view=1),
	F("pending_qty", "Float", "Pending Qty (not received)", read_only=1),
	F("rate", "Currency", "Rate", options="currency", read_only=1, in_list_view=1),
	F("currency", "Link", "Currency", options="Currency", hidden=1, read_only=1),
	F("indent_qty", "Float", "Indent Qty", in_list_view=1, columns=1),
	F("value", "Currency", "Value", options="currency", read_only=1, in_list_view=1),
	F("planning_section", "Section Break", "MOQ / SPQ and Shortage"),
	F("min_order_qty", "Float", "MOQ", read_only=1),
	F("standard_packing_qty", "Float", "SPQ", read_only=1),
	F("col_2", "Column Break"),
	F("cur_month_shortage", "Float", "Current Month Shortage", read_only=1),
	F("cur_plus1_month_shortage", "Float", "Shortage (Current + 1 Month)", read_only=1),
	F("cur_plus3_month_shortage", "Float", "Shortage (Current + 3 Months)", read_only=1),
], istable=1)

make_doctype(M, "Payment Indent", [
	F("company", "Link", "Company", options="Company", reqd=1, in_standard_filter=1),
	F("supplier", "Link", "Supplier", options="Supplier", reqd=1, in_standard_filter=1, in_list_view=1),
	F("supplier_name", "Data", "Supplier Name", fetch_from="supplier.supplier_name", read_only=1),
	F("col_1", "Column Break"),
	F("posting_date", "Date", "Date", default="Today", reqd=1),
	F("currency", "Link", "Currency", options="Currency", read_only=1, description="Taken from the selected Purchase Orders."),
	F("status", "Select", "Status", options="Draft\nSubmitted\nPayment Requested\nCancelled", default="Draft", read_only=1, no_copy=1, in_list_view=1, in_standard_filter=1),
	F("po_section", "Section Break", "Purchase Orders"),
	F("purchase_orders", "Table", "Purchase Orders", options="Payment Indent PO", reqd=1),
	F("get_items", "Button", "Get Items from Purchase Orders"),
	F("items_section", "Section Break", "Lines"),
	F("items", "Table", "Items", options="Payment Indent Item"),
	F("total_value", "Currency", "Total Indent Value", options="currency", read_only=1),
	F("request_section", "Section Break", "Payment Request"),
	F("proforma_inv_no", "Data", "Proforma Invoice No"),
	F("proforma_inv_date", "Date", "Proforma Invoice Date"),
	F("proforma_inv_value", "Currency", "Proforma Invoice Value", options="currency"),
	F("col_2", "Column Break"),
	F("requested_amount", "Currency", "Requested Amount", options="currency", reqd=1, in_list_view=1),
	F("required_date", "Date", "Payment Required Date"),
	F("justification", "Small Text", "Justification"),
	F("documents", "Attach", "Documents"),
	F("approval_section", "Section Break", "Approval", collapsible=1),
	F("approval_required", "Check", "Approval Required", read_only=1, no_copy=1,
		description="Set when the requested amount is above the indent approval limit in Buying Control Settings."),
	F("approved_by", "Link", "Approved By", options="User", read_only=1, no_copy=1),
	F("col_3", "Column Break"),
	F("approved_on", "Datetime", "Approved On", read_only=1, no_copy=1),
], autoname="naming_series:", naming_series="PAY-IND-.YYYY.-.#####", is_submittable=1, title_field="supplier_name",
	search_fields="supplier,supplier_name",
	permissions=[
		perm("Purchase User"),
		perm("Purchase Manager", delete=1, submit=1, cancel=1, amend=1),
		perm("Accounts User", write=0, create=0),
		perm("Accounts Manager", submit=1, cancel=1, amend=1),
		perm("System Manager", delete=1, submit=1, cancel=1, amend=1),
	],
	js=True, list_js=True,
)
