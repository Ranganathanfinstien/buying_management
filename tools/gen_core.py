"""Generate the core (module "Universal Buying") doctypes: settings, PO Type and link children."""

import sys

sys.path.insert(0, "/home/finstein-emp/frappe-v16/apps/universal_buying/tools")
from make_doctype import F, make_doctype, perm

M = "Universal Buying"

# ---- link / child tables -----------------------------------------------------
make_doctype(M, "UB Item Group Link", [F("item_group", "Link", "Item Group", options="Item Group", reqd=1, in_list_view=1)], istable=1)
make_doctype(M, "UB Role Link", [F("role", "Link", "Role", options="Role", reqd=1, in_list_view=1)], istable=1)
make_doctype(M, "UB Supplier Group Link", [F("supplier_group", "Link", "Supplier Group", options="Supplier Group", reqd=1, in_list_view=1)], istable=1)
make_doctype(M, "UB RFQ Approval Tier", [
	F("role", "Link", "Approver Role", options="Role", reqd=1, in_list_view=1),
	F("state_name", "Data", "Workflow State", reqd=1, in_list_view=1, description="e.g. Pending Dept Head Approval"),
], istable=1)
make_doctype(M, "UB PO Approval Rule", [
	F("company", "Link", "Company", options="Company", in_list_view=1, description="Blank = all companies"),
	F("from_amount", "Currency", "From Amount (Base)", in_list_view=1, default="0"),
	F("to_amount", "Currency", "To Amount (Base)", in_list_view=1, description="0 = no upper limit"),
	F("origin", "Select", "PO Origin", in_list_view=1, options="\nAuto PO Run\nAuto PO Exception\nSupplier Quotation\nMaterial Request\nManual", description="Blank = all origins"),
	F("step", "Int", "Step", reqd=1, in_list_view=1, default="1"),
	F("approver_role", "Link", "Approver Role", options="Role", reqd=1, in_list_view=1),
], istable=1)
make_doctype(M, "UB Company Override", [
	F("company", "Link", "Company", options="Company", reqd=1, in_list_view=1),
	F("setting_field", "Data", "Setting Fieldname", reqd=1, in_list_view=1, description="Fieldname from Buying Control Settings"),
	F("value", "Data", "Value", reqd=1, in_list_view=1),
], istable=1)

# ---- Buying Control Settings (single) ----------------------------------------
fields = [
	F("planning_tab", "Tab Break", "Planning"),
	F("planning_section", "Section Break", "Requirement Engine and Auto PO Run"),
	F("requirement_engine_enabled", "Check", "Run Requirement Engine Nightly", default="1"),
	F("planning_buffer_days", "Int", "Planning Buffer Days", default="0", description="Required date is pulled earlier by this many days (e.g. 15)."),
	F("planning_bucket", "Select", "Shortage Bucket", options="Month\nWeek\nExact Date", default="Month"),
	F("planning_horizon_days", "Int", "Planning Horizon (Days)", default="365"),
	F("plan_by_project", "Check", "Plan by Project", default="1"),
	F("line_card_supplier_fallback", "Check", "Use Supplier Line Card when Item has no Default Supplier", default="1"),
	F("col_plan_1", "Column Break"),
	F("abc_threshold_a", "Percent", "Class A Threshold (% of MOQ)", default="90"),
	F("abc_threshold_b", "Percent", "Class B Threshold (% of MOQ)", default="80"),
	F("abc_threshold_c", "Percent", "Class C Threshold (% of MOQ)", default="70"),
	F("abc_default_class", "Select", "Default Class", options="A\nB\nC", default="C"),
	F("abc_scope", "Select", "Classify By", options="Project\nCompany", default="Project"),
	F("moq_tolerance_percent", "Percent", "MOQ Tolerance for Direct PO (%)", default="5", description="Auto PO Exception may order MOQ directly when (1 - shortage/MOQ) is within this %."),
	F("abc_classification_section", "Section Break", "ABC Classification (weekly job)"),
	F("abc_lookback_months", "Int", "Consumption Lookback (Months)", default="6"),
	F("col_abc", "Column Break"),
	F("abc_pareto_a_percent", "Percent", "Class A up to Cumulative Value (%)", default="70"),
	F("abc_pareto_b_percent", "Percent", "Class B up to Cumulative Value (%)", default="90"),
	F("demand_section", "Section Break", "Demand and Supply Filters"),
	F("excluded_order_types", "Small Text", "Excluded Sales Order Types", default="Maintenance", description="One Sales Order order_type per line."),
	F("excluded_warehouse_names", "Small Text", "Excluded Warehouse Names", default="Rejected Goods\nE-WIP\nJob Work\nSales Return\nService", description="Warehouse names (without company suffix), one per line, not counted as available stock."),
	F("col_plan_2", "Column Break"),
	F("include_open_production", "Check", "Count Open Work Orders as Supply", default="0"),
	F("include_safety_stock", "Check", "Add Item Safety Stock to Demand", default="0"),
	F("purge_draft_auto_po_days", "Int", "Delete Draft Auto POs Older Than (Days)", default="0", description="0 = never delete."),
	F("consumables_section", "Section Break", "Consumables Auto PO"),
	F("consumables_auto_po_enabled", "Check", "Create POs from Consumable Material Requests Daily", default="0"),
	F("consumables_project", "Link", "Consumables Project", options="Project"),
	F("col_cons", "Column Break"),
	F("consumable_item_groups", "Table MultiSelect", "Consumable Item Groups", options="UB Item Group Link"),

	F("supplier_tab", "Tab Break", "Supplier"),
	F("supplier_section", "Section Break", "Supplier Approval and Onboarding"),
	F("block_unapproved_supplier", "Select", "RFQ / PO to Supplier not Enabled", options="Off\nWarn\nBlock", default="Block"),
	F("require_bank_account", "Check", "Supplier needs a Bank Account before Approval", default="1"),
	F("onboarding_questionnaire", "Check", "Use Onboarding Questionnaire (Risk / Evaluation)", default="1"),
	F("rpn_mitigation_threshold", "Int", "RPN Needing Mitigation Plan", default="27"),
	F("default_onboarding_supplier_group", "Link", "Default Supplier Group for Onboarding", options="Supplier Group"),
	F("audit_nc_procedure", "Link", "Quality Procedure for Audit Non Conformance", options="Quality Procedure"),
	F("col_sup", "Column Break"),
	F("approval_full_chain_groups", "Table MultiSelect", "Groups: Purchase → Quality → Finance Approval", options="UB Supplier Group Link"),
	F("approval_finance_only_groups", "Table MultiSelect", "Groups: Finance Approval Only", options="UB Supplier Group Link"),
	F("audit_required_groups", "Table MultiSelect", "Groups Needing Supplier Audit Log", options="UB Supplier Group Link"),
	F("price_section", "Section Break", "Price Control"),
	F("price_control_mode", "Select", "PO Rate Control", options="Strict\nWarn\nFree", default="Strict"),
	F("col_price", "Column Break"),
	F("price_request_roles", "Table MultiSelect", "Roles Allowed to Raise Item Price Request", options="UB Role Link"),

	F("rfq_tab", "Tab Break", "RFQ"),
	F("rfq_section", "Section Break", "Bidding"),
	F("bid_deadline_default_days", "Int", "Default Bid Deadline (Days)", default="7"),
	F("bid_deadline_default_time", "Time", "Default Bid Deadline Time", default="17:00:00"),
	F("bid_reminder_hours", "Int", "Reminder Before Deadline (Hours)", default="24"),
	F("otp_minutes", "Int", "Quotation View Code Validity (Minutes)", default="10"),
	F("col_rfq", "Column Break"),
	F("award_role", "Link", "Role that Awards Quotations", options="Role"),
	F("deadline_extension_role", "Link", "Role that Extends Bid Deadlines", options="Role", default="Purchase Manager"),
	F("rfq_approval_section", "Section Break", "RFQ Approval Tiers", description="Evaluated in row order after bidding closes. The RFQ workflow is rebuilt from this table on save."),
	F("rfq_approval_tiers", "Table", "RFQ Approval Tiers", options="UB RFQ Approval Tier"),

	F("po_tab", "Tab Break", "Purchase Order"),
	F("po_section", "Section Break", "Purchase Order"),
	F("po_naming_series", "Data", "PO Naming Pattern", default="PUR-.{abbr}.-.YYYY.-.#####", description="{abbr} is replaced by the company abbreviation."),
	F("inter_company_auto_so", "Check", "Create Sales Order in Other Company for Internal Supplier POs", default="1"),
	F("amendment_rate_cap_percent", "Percent", "PO Amendment Rate Increase Cap (%)", default="5"),
	F("col_po", "Column Break"),
	F("consumables_only_roles", "Table MultiSelect", "Roles Limited to Consumable Item Groups", options="UB Role Link"),
	F("consumables_exempt_roles", "Table MultiSelect", "Roles Never Limited to Consumables", options="UB Role Link"),
	F("po_approval_section", "Section Break", "PO Approval"),
	F("po_approval_enabled", "Check", "PO Approval Enabled", default="1"),
	F("submit_po_on_final_approval", "Check", "Submit PO on Final Approval", default="1"),
	F("po_approval_rules", "Table", "PO Approval Rules", options="UB PO Approval Rule", description="Rows with the same company, amount band and origin form one approval chain, run in Step order."),

	F("inward_tab", "Tab Break", "Inward"),
	F("inward_section", "Section Break", "Receiving and Quality"),
	F("gate_entry_required", "Check", "Gate Entry Required on Purchase Receipt", default="1"),
	F("gate_entry_lookback_days", "Int", "Gate Entry Pick List Lookback (Days)", default="90"),
	F("iqc_gate", "Select", "Block Receipt Submit without Quality Inspection", options="Off\nWarn\nBlock", default="Block"),
	F("green_card_skips_iqc", "Check", "Green Card Suppliers Skip Inspection", default="1"),
	F("min_remaining_shelf_life_percent", "Percent", "Minimum Remaining Shelf Life at Receipt (%)", default="75"),
	F("col_inward", "Column Break"),
	F("batch_exempt_groups", "Table MultiSelect", "Item Groups Exempt from Batch", options="UB Item Group Link"),
	F("boe_fiscal_year_check", "Check", "Bill of Entry Date Must Be in Fiscal Year", default="1"),
	F("rejected_warehouse_name", "Data", "Rejected Warehouse Name", default="Rejected Goods"),
	F("background_submit_rows", "Int", "Submit Receipts / Invoices in Background Above (Rows)", default="100"),
	F("auto_create_inc", "Check", "Create Item Non Conformance on Rejected Inspection", default="1"),
	F("scrap_warehouse_name", "Data", "Scrap Warehouse Name", default="Scrap"),
	F("use_boe_exchange_rate", "Check", "Import Receipts Use Exchange Rate of BoE Date", default="1"),
	F("invoice_no_edit_roles", "Table MultiSelect", "Roles Allowed to Edit Supplier Invoice No after Submit", options="UB Role Link"),
	F("bonded_section", "Section Break", "Bonded Goods"),
	F("bonded_goods_enabled", "Check", "Bonded Goods Route Enabled", default="0"),
	F("bonded_goods_warehouse_name", "Data", "Bonded Goods Warehouse Name", default="Bonded Goods"),

	F("finance_tab", "Tab Break", "Finance"),
	F("finance_section", "Section Break", "Invoice and Payment"),
	F("tds_opening_balance_mode", "Check", "Use Supplier TDS Opening Balance", default="0"),
	F("invoice_approval_enabled", "Check", "Purchase Invoice Approval Enabled", default="0"),
	F("invoice_account_currency_check", "Select", "Credit Account Currency Must Match Invoice", options="Off\nWarn\nBlock", default="Block"),
	F("invoice_maker_role", "Link", "Invoice Approval: Maker Role", options="Role", default="Accounts User"),
	F("invoice_approver_role", "Link", "Invoice Approval: Approver Role", options="Role", default="Accounts Manager"),
	F("col_fin", "Column Break"),
	F("indent_cap_percent", "Percent", "Payment Indent Cap (% of Value)", default="110"),
	F("indent_approval_limit_inr", "Currency", "Payment Indent Approval Limit (INR)", default="500000"),
	F("indent_approval_limit_fx", "Currency", "Payment Indent Approval Limit (Foreign Currency)", default="5000"),
	F("indent_approver_roles", "Table MultiSelect", "Payment Indent Approver Roles", options="UB Role Link"),

	F("override_tab", "Tab Break", "Company Overrides"),
	F("company_overrides", "Table", "Company Overrides", options="UB Company Override"),
]
make_doctype(M, "Buying Control Settings", fields, issingle=1,
	permissions=[perm("System Manager"), perm("Purchase Manager"), perm("Purchase User", write=0)],
	js=True)

# ---- PO Type ------------------------------------------------------------------
make_doctype(M, "PO Type", [
	F("po_type_name", "Data", "PO Type Name", reqd=1, unique=1, in_list_view=1),
	F("is_default", "Check", "Default", in_list_view=1),
	F("receipt_required", "Check", "Purchase Receipt Required (3-Way)", default="1", in_list_view=1),
	F("po_required_on_invoice", "Check", "Purchase Order Required on Invoice", default="1"),
	F("col_1", "Column Break"),
	F("item_required", "Check", "Item Code Required on Lines", default="1"),
	F("invoice_tolerance_percent", "Percent", "Invoice Over PO Tolerance (%)", default="0"),
	F("description", "Small Text", "Description"),
], autoname="field:po_type_name", quick_entry=0,
	permissions=[perm("System Manager", delete=1), perm("Purchase Manager", delete=1), perm("Purchase User", write=0, create=0), perm("Accounts User", write=0, create=0)])

print("core doctypes generated")
