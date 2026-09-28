"""UB Sourcing install data: custom fields on RFQ / Supplier Quotation, property setters, workflows.

Merged by universal_buying.setup.install.run(). Everything here is idempotent.
"""

ROLES = []

_BID_STATUS = "\nOpen\nUnder Evaluation\nClosed\nAwarded\nRejected"

CUSTOM_FIELDS = {
	"Request for Quotation": [
		{"fieldname": "ub_po_type", "label": "PO Type", "fieldtype": "Link", "options": "PO Type",
		 "insert_after": "company", "reqd": 1, "in_standard_filter": 1,
		 "description": "Decides whether an Item Code is required on every line."},
		{"fieldname": "ub_bidding_section", "label": "Bidding", "fieldtype": "Section Break",
		 "insert_after": "amended_from", "collapsible": 0},
		{"fieldname": "ub_bid_deadline", "label": "Bid Deadline", "fieldtype": "Datetime",
		 "insert_after": "ub_bidding_section", "reqd": 1, "allow_on_submit": 1, "no_copy": 1,
		 "description": "Suppliers can quote and revise until this moment."},
		{"fieldname": "ub_bid_status", "label": "Bid Status", "fieldtype": "Select", "options": _BID_STATUS,
		 "insert_after": "ub_bid_deadline", "read_only": 1, "allow_on_submit": 1, "no_copy": 1,
		 "in_standard_filter": 1, "in_list_view": 1},
		{"fieldname": "ub_bidding_col", "fieldtype": "Column Break", "insert_after": "ub_bid_status"},
		{"fieldname": "ub_bid_reminder_sent", "label": "Bid Reminder Sent", "fieldtype": "Check",
		 "insert_after": "ub_bidding_col", "read_only": 1, "hidden": 1, "allow_on_submit": 1, "no_copy": 1},
		{"fieldname": "ub_bid_closed_notified", "label": "Bid Closed Notified", "fieldtype": "Check",
		 "insert_after": "ub_bid_reminder_sent", "read_only": 1, "hidden": 1, "allow_on_submit": 1, "no_copy": 1},
		{"fieldname": "ub_deadline_history", "label": "Deadline History", "fieldtype": "Table",
		 "options": "RFQ Deadline Extension", "insert_after": "ub_bid_closed_notified", "read_only": 1,
		 "allow_on_submit": 1, "no_copy": 1},
		{"fieldname": "ub_award_section", "label": "Award", "fieldtype": "Section Break",
		 "insert_after": "ub_deadline_history", "collapsible": 1,
		 "depends_on": "eval:doc.ub_awarded_quotation || doc.ub_award_remarks"},
		{"fieldname": "ub_awarded_quotation", "label": "Awarded Quotation", "fieldtype": "Link",
		 "options": "Supplier Quotation", "insert_after": "ub_award_section", "read_only": 1,
		 "allow_on_submit": 1, "no_copy": 1},
		{"fieldname": "ub_awarded_by", "label": "Decision By", "fieldtype": "Link", "options": "User",
		 "insert_after": "ub_awarded_quotation", "read_only": 1, "allow_on_submit": 1, "no_copy": 1},
		{"fieldname": "ub_award_col", "fieldtype": "Column Break", "insert_after": "ub_awarded_by"},
		{"fieldname": "ub_awarded_on", "label": "Decision On", "fieldtype": "Datetime",
		 "insert_after": "ub_award_col", "read_only": 1, "allow_on_submit": 1, "no_copy": 1},
		{"fieldname": "ub_award_remarks", "label": "Decision Remarks", "fieldtype": "Small Text",
		 "insert_after": "ub_awarded_on", "read_only": 1, "allow_on_submit": 1, "no_copy": 1},
	],
	"Request for Quotation Item": [
		{"fieldname": "ub_item_description", "label": "Item Description (free text)", "fieldtype": "Small Text",
		 "insert_after": "item_code", "in_list_view": 1,
		 "description": "Used when the PO Type does not require an Item Code."},
	],
	"Request for Quotation Supplier": [
		{"fieldname": "ub_prospective_supplier", "label": "Prospective Supplier", "fieldtype": "Link",
		 "options": "Prospective Supplier", "insert_after": "supplier", "in_list_view": 1,
		 "read_only_depends_on": "eval:doc.supplier"},
		{"fieldname": "ub_rfq_token", "label": "RFQ Portal Token", "fieldtype": "Data",
		 "insert_after": "email_id", "read_only": 1, "hidden": 1, "allow_on_submit": 1, "no_copy": 1},
	],
	"Supplier Quotation": [
		{"fieldname": "ub_prospective_supplier", "label": "Prospective Supplier", "fieldtype": "Link",
		 "options": "Prospective Supplier", "insert_after": "supplier", "in_standard_filter": 1,
		 "read_only_depends_on": "eval:doc.supplier && !doc.__islocal"},
		{"fieldname": "ub_po_type", "label": "PO Type", "fieldtype": "Link", "options": "PO Type",
		 "insert_after": "company"},
		{"fieldname": "ub_lead_time_days", "label": "Lead Time (Days)", "fieldtype": "Int",
		 "insert_after": "valid_till"},
		{"fieldname": "ub_sq_status", "label": "Award Status", "fieldtype": "Select", "options": "\nApproved\nRejected",
		 "insert_after": "ub_lead_time_days", "read_only": 1, "allow_on_submit": 1, "no_copy": 1,
		 "in_standard_filter": 1},
		{"fieldname": "ub_portal_revision", "label": "Portal Version", "fieldtype": "Int",
		 "insert_after": "ub_sq_status", "read_only": 1, "no_copy": 1},
		{"fieldname": "ub_raised_by", "label": "Raised By (Portal User)", "fieldtype": "Link", "options": "User",
		 "insert_after": "ub_portal_revision", "read_only": 1, "no_copy": 1},
		# revision tracking (A-14.2 / A-14.4)
		{"fieldname": "ub_revision_section", "label": "Revision", "fieldtype": "Section Break",
		 "insert_after": "amended_from", "collapsible": 1,
		 "depends_on": "eval:doc.ub_revised || doc.ub_revision_requested"},
		{"fieldname": "ub_revised", "label": "Revised (superseded)", "fieldtype": "Check",
		 "insert_after": "ub_revision_section", "read_only": 1, "allow_on_submit": 1, "no_copy": 1,
		 "in_standard_filter": 1},
		{"fieldname": "ub_revision_requested", "label": "Revision Requested", "fieldtype": "Check",
		 "insert_after": "ub_revised", "read_only": 1, "allow_on_submit": 1, "no_copy": 1},
		{"fieldname": "ub_revision_col", "fieldtype": "Column Break", "insert_after": "ub_revision_requested"},
		{"fieldname": "ub_revision_reason", "label": "Revision Reason", "fieldtype": "Small Text",
		 "insert_after": "ub_revision_col", "read_only": 1, "allow_on_submit": 1, "no_copy": 1},
		{"fieldname": "ub_revision_requested_on", "label": "Revision Requested On", "fieldtype": "Datetime",
		 "insert_after": "ub_revision_reason", "read_only": 1, "allow_on_submit": 1, "no_copy": 1},
		# commercial terms (A-14 supplier enters)
		{"fieldname": "ub_commercial_section", "label": "Commercial Terms", "fieldtype": "Section Break",
		 "insert_after": "in_words", "collapsible": 1},
		{"fieldname": "ub_freight_insurance", "label": "Freight & Insurance", "fieldtype": "Select",
		 "options": "\nIncluded\nExcluded", "insert_after": "ub_commercial_section"},
		{"fieldname": "ub_freight_insurance_desc", "label": "Freight & Insurance Remarks", "fieldtype": "Small Text",
		 "insert_after": "ub_freight_insurance"},
		{"fieldname": "ub_commercial_col1", "fieldtype": "Column Break", "insert_after": "ub_freight_insurance_desc"},
		{"fieldname": "ub_packing_forwarding", "label": "Packing & Forwarding", "fieldtype": "Select",
		 "options": "\nIncluded\nExcluded", "insert_after": "ub_commercial_col1"},
		{"fieldname": "ub_packing_forwarding_desc", "label": "Packing & Forwarding Remarks", "fieldtype": "Small Text",
		 "insert_after": "ub_packing_forwarding"},
		{"fieldname": "ub_commercial_col2", "fieldtype": "Column Break", "insert_after": "ub_packing_forwarding_desc"},
		{"fieldname": "ub_installation", "label": "Installation & Commissioning", "fieldtype": "Select",
		 "options": "\nIncluded\nExcluded", "insert_after": "ub_commercial_col2"},
		{"fieldname": "ub_installation_desc", "label": "Installation & Commissioning Remarks", "fieldtype": "Small Text",
		 "insert_after": "ub_installation"},
		{"fieldname": "ub_terms_section", "label": "Payment Terms and Technical Specification", "fieldtype": "Section Break",
		 "insert_after": "ub_installation_desc", "collapsible": 1},
		{"fieldname": "ub_payment_terms", "label": "Payment Terms (Supplier)", "fieldtype": "Table",
		 "options": "SQ Payment Term", "insert_after": "ub_terms_section"},
		{"fieldname": "ub_technical_spec", "label": "Technical Specification", "fieldtype": "Table",
		 "options": "Supplier Quotation Technical Spec", "insert_after": "ub_payment_terms"},
		{"fieldname": "ub_quotation_attachment", "label": "Supplier Quotation Attachment", "fieldtype": "Attach",
		 "insert_after": "ub_technical_spec"},
		{"fieldname": "ub_hod_remarks", "label": "HOD Recommendation", "fieldtype": "Small Text",
		 "insert_after": "ub_quotation_attachment", "allow_on_submit": 1, "no_copy": 1},
		{"fieldname": "ub_discussion_section", "label": "Discussion with Supplier", "fieldtype": "Section Break",
		 "insert_after": "ub_hod_remarks"},
		{"fieldname": "ub_discussion_html", "label": "Discussion", "fieldtype": "HTML",
		 "insert_after": "ub_discussion_section"},
	],
	"Supplier Quotation Item": [
		{"fieldname": "ub_item_description", "label": "Item Description (free text)", "fieldtype": "Small Text",
		 "insert_after": "item_code", "in_list_view": 1},
		{"fieldname": "ub_rfq_qty", "label": "RFQ Qty", "fieldtype": "Float", "insert_after": "qty",
		 "read_only": 1, "no_copy": 1},
		{"fieldname": "ub_moq", "label": "MOQ (Supplier)", "fieldtype": "Float", "insert_after": "lead_time_days"},
		{"fieldname": "ub_spq", "label": "SPQ (Supplier)", "fieldtype": "Float", "insert_after": "ub_moq"},
		{"fieldname": "ub_remarks", "label": "Supplier Remarks", "fieldtype": "Small Text", "insert_after": "is_free_item"},
	],
}

PROPERTY_SETTERS = [
	# V-13.1: a supplier row carries either a Supplier or a Prospective Supplier.
	{"doctype": "Request for Quotation Supplier", "fieldname": "supplier", "property": "reqd", "value": "0",
	 "property_type": "Check"},
	{"doctype": "Request for Quotation Supplier", "fieldname": "supplier", "property": "mandatory_depends_on",
	 "value": "eval:!doc.ub_prospective_supplier", "property_type": "Data"},
	{"doctype": "Request for Quotation Supplier", "fieldname": "supplier", "property": "read_only_depends_on",
	 "value": "eval:doc.ub_prospective_supplier", "property_type": "Data"},
	# V-13.3: item code only when the PO Type requires it (enforced in the controller).
	{"doctype": "Request for Quotation Item", "fieldname": "item_code", "property": "reqd", "value": "0",
	 "property_type": "Check"},
	{"doctype": "Supplier Quotation Item", "fieldname": "item_code", "property": "reqd", "value": "0",
	 "property_type": "Check"},
	# Prospective supplier quotations have no Supplier until onboarding completes.
	{"doctype": "Supplier Quotation", "fieldname": "supplier", "property": "reqd", "value": "0",
	 "property_type": "Check"},
	{"doctype": "Supplier Quotation", "fieldname": "supplier", "property": "mandatory_depends_on",
	 "value": "eval:!doc.ub_prospective_supplier", "property_type": "Data"},
]


def setup():
	from universal_buying.ub_sourcing.workflow import (
		ensure_approver_permissions,
		rebuild_rfq_workflow,
		rebuild_sq_workflow,
	)

	rebuild_rfq_workflow()
	rebuild_sq_workflow()
	ensure_approver_permissions()
