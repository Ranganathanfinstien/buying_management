"""Quotation Message: one discussion thread per RFQ supplier row (buyer <-> supplier, plus internal notes)."""
import sys
sys.path.insert(0, "/home/finstein-emp/frappe-v16/apps/universal_buying/tools")
from make_doctype import F, make_doctype, perm

make_doctype("UB Sourcing", "Quotation Message", [
	F("request_for_quotation", "Link", "Request for Quotation", options="Request for Quotation", reqd=1, in_list_view=1, in_standard_filter=1, search_index=1),
	F("rfq_supplier_row", "Data", "RFQ Supplier Row", reqd=1, read_only=1, search_index=1),
	F("party_type", "Select", "Party Type", options="Supplier\nProspective Supplier", read_only=1),
	F("party", "Dynamic Link", "Party", options="party_type", read_only=1, in_list_view=1, in_standard_filter=1),
	F("party_name", "Data", "Party Name", read_only=1),
	F("supplier_quotation", "Link", "Supplier Quotation", options="Supplier Quotation", read_only=1),
	F("col_1", "Column Break"),
	F("sender_type", "Select", "Sender Type", options="Buyer\nSupplier", reqd=1, read_only=1, in_list_view=1),
	F("sender", "Link", "Sender", options="User", read_only=1),
	F("sender_name", "Data", "Sender Name", read_only=1),
	F("is_internal", "Check", "Internal Note (not shown to supplier)", read_only=1, in_list_view=1),
	F("msg_section", "Section Break"),
	F("message", "Small Text", "Message", reqd=1, read_only=1),
], autoname="hash", title_field="party_name", sort_field="creation", sort_order="DESC",
	permissions=[perm("System Manager", delete=1), perm("Purchase Manager", write=0, create=0), perm("Purchase User", write=0, create=0)],
	extra={"in_create": 1})
print("ok")
