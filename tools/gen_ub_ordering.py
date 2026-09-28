"""Generate the UB Ordering doctypes (BRD v2 sections 6.17 - 6.21, 8.3, 8.4)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_doctype import F, make_doctype, perm

M = "UB Ordering"

PORTAL_READ = perm("Supplier", write=0, create=0, delete=0, report=0, export=0, email=0, share=0)

# ---- child tables on Purchase Order ------------------------------------------------
make_doctype(M, "UB PO Approval Log", [
	F("step", "Int", "Step", in_list_view=1, read_only=1),
	F("approver_role", "Link", "Role", options="Role", in_list_view=1, read_only=1),
	F("action", "Select", "Action", options="Sent\nApproved\nRejected\nReset\nAuto Approved", in_list_view=1, read_only=1),
	F("user", "Link", "User", options="User", in_list_view=1, read_only=1),
	F("action_on", "Datetime", "On", in_list_view=1, read_only=1),
	F("remarks", "Small Text", "Remarks", in_list_view=1, read_only=1),
], istable=1)

make_doctype(M, "Portal PO Invoice", [
	F("bill_no", "Data", "Supplier Invoice No", reqd=1, in_list_view=1),
	F("bill_date", "Date", "Supplier Invoice Date", in_list_view=1),
	F("amount", "Currency", "Invoice Amount", in_list_view=1),
	F("attachment", "Attach", "Attachment", reqd=1, in_list_view=1),
	F("uploaded_on", "Datetime", "Uploaded On", read_only=1),
	F("uploaded_by", "Link", "Uploaded By", options="User", read_only=1),
], istable=1)

make_doctype(M, "Portal PO QC Attachment", [
	F("po_item", "Data", "PO Line", read_only=1),
	F("item_code", "Link", "Item Code", options="Item", in_list_view=1),
	F("item_name", "Data", "Item Name"),
	F("title", "Data", "Title", in_list_view=1),
	F("attachment", "Attach", "Attachment", reqd=1, in_list_view=1),
	F("uploaded_on", "Datetime", "Uploaded On", read_only=1, in_list_view=1),
	F("uploaded_by", "Link", "Uploaded By", options="User", read_only=1),
], istable=1)

make_doctype(M, "PO Confirmation", [
	F("channel", "Link", "Channel", options="Supplier Channel", in_list_view=1),
	F("event", "Select", "Event", options="Sent\nStatus\nAmendment\nCancellation", in_list_view=1),
	F("po_item", "Data", "PO Line"),
	F("line_no", "Int", "Line No"),
	F("item_code", "Link", "Item Code", options="Item", in_list_view=1),
	F("manufacturer_part_no", "Data", "MPN"),
	F("col_req", "Column Break"),
	F("requested_qty", "Float", "Requested Qty", in_list_view=1),
	F("requested_date", "Date", "Requested Date"),
	F("requested_rate", "Currency", "Requested Rate", options="currency"),
	F("col_conf", "Column Break"),
	F("confirmed_qty", "Float", "Confirmed Qty", in_list_view=1),
	F("confirmed_date", "Date", "Confirmed Date", in_list_view=1),
	F("confirmed_rate", "Currency", "Confirmed Rate"),
	F("shipped_qty", "Float", "Shipped Qty"),
	F("sec_status", "Section Break"),
	F("status", "Data", "Status", in_list_view=1),
	F("reference", "Data", "Supplier Reference"),
	F("updated_on", "Datetime", "Updated On"),
	F("message", "Small Text", "Message"),
], istable=1)

# ---- PO Amendment -------------------------------------------------------------------
make_doctype(M, "PO Amendment Item", [
	F("po_item", "Data", "PO Line", read_only=1, description="Blank for a split (new) line"),
	F("item_code", "Link", "Item Code", options="Item", in_list_view=1, columns=2),
	F("item_name", "Data", "Item Name", read_only=1),
	F("uom", "Link", "UOM", options="UOM", read_only=1),
	F("conversion_factor", "Float", "Conversion Factor", read_only=1, hidden=1),
	F("received_qty", "Float", "Received Qty", read_only=1),
	F("split", "Check", "Split (New Line)", in_list_view=1, columns=1),
	F("col_old", "Column Break"),
	F("original_qty", "Float", "Old Qty", read_only=1, in_list_view=1, columns=1),
	F("original_rate", "Currency", "Old Rate", read_only=1, in_list_view=1, columns=1, options="currency"),
	F("original_schedule_date", "Date", "Old Required By", read_only=1),
	F("original_amount", "Currency", "Old Amount", read_only=1, options="currency"),
	F("col_new", "Column Break"),
	F("revised_qty", "Float", "New Qty", in_list_view=1, columns=1),
	F("revised_rate", "Currency", "New Rate", in_list_view=1, columns=1, options="currency"),
	F("revised_schedule_date", "Date", "New Required By", in_list_view=1, columns=1),
	F("revised_amount", "Currency", "New Amount", read_only=1, options="currency"),
	F("sec_just", "Section Break"),
	F("justification", "Small Text", "Justification", in_list_view=1, columns=2),
], istable=1)

make_doctype(M, "PO Amendment", [
	F("purchase_order", "Link", "Purchase Order", options="Purchase Order", reqd=1, in_list_view=1, in_standard_filter=1),
	F("supplier", "Link", "Supplier", options="Supplier", fetch_from="purchase_order.supplier", read_only=1, in_list_view=1, in_standard_filter=1),
	F("company", "Link", "Company", options="Company", fetch_from="purchase_order.company", read_only=1),
	F("currency", "Link", "Currency", options="Currency", fetch_from="purchase_order.currency", read_only=1),
	F("col_1", "Column Break"),
	F("amendment_date", "Date", "Date", default="Today", reqd=1),
	F("workflow_state", "Link", "Workflow State", options="Workflow State", read_only=1, allow_on_submit=1, no_copy=1, in_list_view=1),
	F("applied", "Check", "Applied to PO", read_only=1, no_copy=1, allow_on_submit=1),
	F("applied_on", "Datetime", "Applied On", read_only=1, no_copy=1, allow_on_submit=1),
	F("sec_reason", "Section Break"),
	F("reason", "Small Text", "Reason", reqd=1),
	F("sec_items", "Section Break", "Lines"),
	F("items", "Table", "Lines", options="PO Amendment Item", reqd=1),
	F("sec_totals", "Section Break", "Totals"),
	F("original_total", "Currency", "Old Net Total", options="currency", read_only=1),
	F("revised_total", "Currency", "New Net Total", options="currency", read_only=1),
	F("col_t", "Column Break"),
	F("original_grand_total", "Currency", "Old Grand Total (with taxes)", options="currency", read_only=1),
	F("revised_grand_total", "Currency", "New Grand Total (with taxes)", options="currency", read_only=1, no_copy=1, allow_on_submit=1,
		description="Set from the Purchase Order after the amendment is applied (taxes recalculated)."),
], naming_series="POA-.YYYY.-.#####", is_submittable=1, title_field="purchase_order", js=True,
	search_fields="purchase_order,supplier",
	permissions=[
		perm("Purchase User", submit=0),
		perm("Purchase Manager", submit=1, cancel=1, amend=1, delete=1),
		perm("System Manager", submit=1, cancel=1, amend=1, delete=1),
	])

# ---- Supplier portal logs ----------------------------------------------------------
make_doctype(M, "PO Acknowledgement", [
	F("purchase_order", "Link", "Purchase Order", options="Purchase Order", reqd=1, in_list_view=1, in_standard_filter=1, search_index=1),
	F("supplier", "Link", "Supplier", options="Supplier", read_only=1, in_list_view=1, in_standard_filter=1),
	F("col_main", "Column Break"),
	F("event_type", "Select", "Event", options="Acknowledged\nRevised", read_only=1, in_list_view=1),
	F("confirmed_delivery_date", "Date", "Confirmed Delivery Date", reqd=1, in_list_view=1),
	F("sec_details", "Section Break"),
	F("notes", "Small Text", "Notes"),
	F("col_stamp", "Column Break"),
	F("acknowledged_by", "Link", "Acknowledged By", options="User", read_only=1),
	F("acknowledged_on", "Datetime", "Acknowledged On", read_only=1),
], naming_series="PO-ACK-.YYYY.-.#####", title_field="purchase_order", sort_field="creation",
	permissions=[
		perm("Purchase User", write=0, create=0),
		perm("Purchase Manager", write=0),
		perm("System Manager", write=0, delete=1),
		PORTAL_READ,
	])

make_doctype(M, "PO Material Status", [
	F("purchase_order", "Link", "Purchase Order", options="Purchase Order", reqd=1, in_list_view=1, in_standard_filter=1, search_index=1),
	F("supplier", "Link", "Supplier", options="Supplier", read_only=1, in_list_view=1, in_standard_filter=1),
	F("col_main", "Column Break"),
	F("status", "Select", "Status", options="In Production\nPartial\nReady to Dispatch\nDispatched\nDelayed", reqd=1, in_list_view=1),
	F("expected_dispatch_date", "Date", "Expected Dispatch Date"),
	F("sec_details", "Section Break"),
	F("remarks", "Small Text", "Remarks", reqd=1),
	F("col_stamp", "Column Break"),
	F("created_by", "Link", "Updated By", options="User", read_only=1),
	F("created_on", "Datetime", "Updated On", read_only=1),
], naming_series="PO-MS-.YYYY.-.#####", title_field="purchase_order",
	permissions=[
		perm("Purchase User", write=0, create=0),
		perm("Purchase Manager", write=0),
		perm("System Manager", write=0, delete=1),
		PORTAL_READ,
	])

make_doctype(M, "PO Shipment Item", [
	F("po_item", "Data", "PO Line", reqd=1, read_only=1),
	F("item_code", "Link", "Item Code", options="Item", in_list_view=1, read_only=1, columns=2),
	F("item_name", "Data", "Item Name", in_list_view=1, read_only=1, columns=2),
	F("uom", "Link", "UOM", options="UOM", read_only=1),
	F("ordered_qty", "Float", "Ordered Qty", in_list_view=1, read_only=1, columns=1),
	F("already_shipped_qty", "Float", "Shipped Earlier", in_list_view=1, read_only=1, columns=1),
	F("shipped_qty", "Float", "Qty in this Shipment", reqd=1, in_list_view=1, columns=2),
	F("remaining_qty", "Float", "Remaining Qty", in_list_view=1, read_only=1, columns=1),
], istable=1)

make_doctype(M, "PO Shipment", [
	F("purchase_order", "Link", "Purchase Order", options="Purchase Order", reqd=1, in_list_view=1, in_standard_filter=1, search_index=1),
	F("supplier", "Link", "Supplier", options="Supplier", fetch_from="purchase_order.supplier", read_only=1, in_list_view=1, in_standard_filter=1),
	F("company", "Link", "Company", options="Company", fetch_from="purchase_order.company", read_only=1),
	F("col_1", "Column Break"),
	F("shipment_date", "Date", "Shipment Date", reqd=1, default="Today", in_list_view=1),
	F("expected_arrival_date", "Date", "Expected Arrival"),
	F("shipment_status", "Select", "Shipment Status", options="\nPartially Shipped\nFully Shipped", read_only=1, in_list_view=1),
	F("delivery_status", "Select", "Delivery Status", options="\nIn Transit\nPartially Delivered\nDelivered", read_only=1, allow_on_submit=1, in_list_view=1),
	F("sec_transport", "Section Break", "Transport"),
	F("mode_of_transport", "Select", "Mode of Transport", options="\nRoad\nAir\nSea\nRail\nCourier\nHand Delivery\nOther"),
	F("transporter", "Data", "Transporter / Carrier"),
	F("lr_awb_no", "Data", "LR / AWB No"),
	F("tracking_url", "Data", "Tracking URL", options="URL"),
	F("col_2", "Column Break"),
	F("vehicle_no", "Data", "Vehicle No"),
	F("driver_name", "Data", "Driver Name"),
	F("driver_contact", "Data", "Driver Contact", options="Phone"),
	F("attachment", "Attach", "Shipping Document"),
	F("sec_items", "Section Break", "Lines"),
	F("items", "Table", "Lines", options="PO Shipment Item", reqd=1),
	F("total_shipped_qty", "Float", "Total Qty Shipped", read_only=1),
	F("remarks", "Small Text", "Remarks"),
], naming_series="SHP-.YYYY.-.#####", is_submittable=1, title_field="purchase_order", js=True,
	permissions=[
		perm("Purchase User", submit=1),
		perm("Purchase Manager", submit=1, cancel=1, amend=1, delete=1),
		perm("Stock User", write=0, create=0),
		perm("System Manager", submit=1, cancel=1, amend=1, delete=1),
		PORTAL_READ,
	])

# ---- Supplier integration channel (6.19) ----------------------------------------------
make_doctype(M, "Supplier Channel", [
	F("channel_name", "Data", "Channel Name", reqd=1, in_list_view=1),
	F("supplier", "Link", "Supplier", options="Supplier", reqd=1, in_list_view=1, in_standard_filter=1),
	F("company", "Link", "Company", options="Company", description="Blank = every company"),
	F("col_1", "Column Break"),
	F("channel_type", "Select", "Channel Type", options="REST\nEDI\nFSP\nAS2\nEmail PDF", reqd=1, in_list_view=1),
	F("connector", "Select", "Connector", options="Email PDF\nTexas Instruments REST\nCustom", reqd=1, default="Email PDF", in_list_view=1),
	F("connector_class", "Data", "Connector Class", depends_on="eval:doc.connector=='Custom'",
		description="Dotted path to a class extending universal_buying.ub_ordering.integrations.base.SupplierConnector"),
	F("enabled", "Check", "Enabled", default="1", in_list_view=1),
	F("sandbox_mode", "Check", "Sandbox Mode"),
	F("sec_creds", "Section Break", "Credentials"),
	F("base_url", "Data", "Base URL", description="Leave blank to use the connector default"),
	F("client_id", "Data", "Client ID"),
	F("client_secret", "Password", "Client Secret"),
	F("col_2", "Column Break"),
	F("username", "Data", "Username"),
	F("password", "Password", "Password"),
	F("api_key", "Password", "API Key"),
	F("sec_cfg", "Section Break", "Connector Settings"),
	F("ship_to_account", "Data", "Ship-to Account No"),
	F("sold_to_account", "Data", "Sold-to Account No"),
	F("checkout_profile_id", "Data", "Checkout Profile ID"),
	F("end_customer_number", "Data", "End Customer No"),
	F("col_3", "Column Break"),
	F("email_to", "Small Text", "Send PO To (emails)", description="Email PDF connector. One address per line; blank = supplier portal users / supplier email."),
	F("print_format", "Link", "Print Format", options="Print Format"),
	F("extra_config", "Code", "Extra Config (JSON)", options="JSON"),
], naming_series="SCH-.#####", title_field="channel_name", js=False,
	search_fields="supplier,channel_type",
	permissions=[
		perm("Purchase Manager", delete=1),
		perm("System Manager", delete=1),
		perm("Purchase User", write=0, create=0),
	])

print("UB Ordering doctypes generated")
