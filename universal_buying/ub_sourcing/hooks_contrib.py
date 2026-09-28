# UB Sourcing hook contributions (pure data - no imports).

OVERRIDE_DOCTYPE_CLASS = {
	"Request for Quotation": "universal_buying.ub_sourcing.overrides.request_for_quotation.UBRequestForQuotation",
	"Supplier Quotation": "universal_buying.ub_sourcing.overrides.supplier_quotation.UBSupplierQuotation",
}

DOCTYPE_JS = {
	"Request for Quotation": "ub_sourcing/public/js/request_for_quotation.js",
	"Supplier Quotation": "ub_sourcing/public/js/supplier_quotation.js",
}

OVERRIDE_WHITELISTED_METHODS = {
	"erpnext.buying.doctype.supplier_quotation.supplier_quotation.make_purchase_order":
		"universal_buying.ub_sourcing.overrides.supplier_quotation.make_purchase_order",
}

SCHEDULER_EVENTS = {
	"cron": {
		"*/15 * * * *": ["universal_buying.ub_sourcing.bidding.process_bid_deadlines"],
	},
}

UB_ON_SETTINGS_UPDATE = ["universal_buying.ub_sourcing.workflow.on_settings_update"]
