# UB Ordering hook contributions (pure data, no imports).

_P = "universal_buying.ub_ordering.permissions."

OVERRIDE_DOCTYPE_CLASS = {
	"Purchase Order": "universal_buying.ub_ordering.overrides.purchase_order.CustomPurchaseOrder",
}

DOCTYPE_JS = {
	"Purchase Order": "ub_ordering/public/js/purchase_order.js",
}

DOC_EVENTS = {
	# BRD 6.21: shipment delivery status from the receipt (3-Way) or the invoice (2-Way)
	"Purchase Receipt": {
		"on_submit": "universal_buying.ub_ordering.portal.refresh_shipment_delivery_status",
		"on_cancel": "universal_buying.ub_ordering.portal.refresh_shipment_delivery_status",
	},
	"Purchase Invoice": {
		"on_submit": "universal_buying.ub_ordering.portal.refresh_shipment_delivery_status",
		"on_cancel": "universal_buying.ub_ordering.portal.refresh_shipment_delivery_status",
	},
}

# AC-21.1: supplier portal users see only their own documents
PERMISSION_QUERY_CONDITIONS = {
	"Purchase Order": _P + "purchase_order_query",
	"Supplier Quotation": _P + "supplier_quotation_query",
	"Request for Quotation": _P + "request_for_quotation_query",
	"Purchase Receipt": _P + "purchase_receipt_query",
	"Purchase Invoice": _P + "purchase_invoice_query",
	"PO Acknowledgement": _P + "po_acknowledgement_query",
	"PO Material Status": _P + "po_material_status_query",
	"PO Shipment": _P + "po_shipment_query",
}

HAS_PERMISSION = {
	"Purchase Order": _P + "procurement_read_only",
	"Supplier Quotation": _P + "procurement_read_only",
	"Request for Quotation": _P + "procurement_read_only",
	"Purchase Receipt": _P + "procurement_read_only",
	"Purchase Invoice": _P + "procurement_read_only",
	"PO Acknowledgement": _P + "procurement_read_only",
	"PO Material Status": _P + "procurement_read_only",
	"PO Shipment": _P + "procurement_read_only",
}

ROLE_HOME_PAGE = {
	"Supplier": "supplier_portal",
}

STANDARD_PORTAL_MENU_ITEMS = [
	{"title": "Supplier Portal", "route": "/supplier_portal", "role": "Supplier"},
	{"title": "RFQs", "route": "/supplier_portal/rfqs", "role": "Supplier"},
	{"title": "Quotations", "route": "/supplier_portal/quotations", "role": "Supplier"},
	{"title": "Purchase Orders", "route": "/supplier_portal/purchase_orders", "role": "Supplier"},
	{"title": "Goods Receipts", "route": "/supplier_portal/receipts", "role": "Supplier"},
	{"title": "Invoices", "route": "/supplier_portal/invoices", "role": "Supplier"},
	{"title": "Document Vault", "route": "/supplier_portal/document_vault", "role": "Supplier"},
	{"title": "Profile", "route": "/supplier_portal/profile", "role": "Supplier"},
]
