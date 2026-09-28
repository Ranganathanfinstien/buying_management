"""Generate the UB Sourcing child doctypes (deadline history, quotation payment terms, technical spec)."""

import sys

sys.path.insert(0, "/home/finstein-emp/frappe-v16/apps/universal_buying/tools")
from make_doctype import F, make_doctype

M = "UB Sourcing"

make_doctype(M, "RFQ Deadline Extension", [
	F("old_deadline", "Datetime", "Previous Deadline", read_only=1, in_list_view=1),
	F("new_deadline", "Datetime", "New Deadline", read_only=1, reqd=1, in_list_view=1),
	F("reason", "Small Text", "Reason", read_only=1, reqd=1, in_list_view=1),
	F("extended_by", "Link", "Extended By", options="User", read_only=1, in_list_view=1),
	F("extended_on", "Datetime", "Extended On", read_only=1),
], istable=1, extra={"editable_grid": 1})

make_doctype(M, "SQ Payment Term", [
	F("term", "Data", "Milestone / Term", in_list_view=1, reqd=1),
	F("percentage", "Percent", "Percentage", in_list_view=1),
], istable=1, extra={"editable_grid": 1})

make_doctype(M, "Supplier Quotation Technical Spec", [
	F("parameter", "Data", "Parameter", in_list_view=1, reqd=1),
	F("column_break_value", "Column Break"),
	F("value", "Data", "Value / Compliance", in_list_view=1),
], istable=1, extra={"editable_grid": 1})

print("UB Sourcing doctypes generated")
