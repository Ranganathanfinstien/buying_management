# UB Finance hook contributions (pure data, no imports).

OVERRIDE_DOCTYPE_CLASS = {
	"Purchase Invoice": "universal_buying.ub_finance.overrides.purchase_invoice.UBPurchaseInvoice",
}

DOCTYPE_JS = {
	"Purchase Invoice": "ub_finance/public/js/purchase_invoice.js",
}

DOC_EVENTS = {
	"Purchase Invoice": {
		"on_change": "universal_buying.ub_finance.invoice_approval.notify_on_state_change",
	},
	"Supplier": {
		"validate": "universal_buying.ub_finance.tds.supplier_validate",
	},
}

UB_ON_SETTINGS_UPDATE = [
	"universal_buying.ub_finance.invoice_approval.sync_invoice_approval_workflow",
]
