# UB Inward hook contributions (pure data, no imports).

OVERRIDE_DOCTYPE_CLASS = {
	"Purchase Receipt": "universal_buying.ub_inward.overrides.purchase_receipt.UBPurchaseReceipt",
}

DOCTYPE_JS = {
	"Purchase Receipt": "ub_inward/client/purchase_receipt.js",
	"Quality Inspection": "ub_inward/client/quality_inspection.js",
	"Landed Cost Voucher": "ub_inward/client/landed_cost_voucher.js",
}

OVERRIDE_WHITELISTED_METHODS = {
	# currency-safe purchase return (keeps ERPNext bundles/batches handling, see api.make_purchase_return)
	"erpnext.stock.doctype.purchase_receipt.purchase_receipt.make_purchase_return": "universal_buying.ub_inward.api.make_purchase_return",
}

DOC_EVENTS = {
	"Quality Inspection": {
		"validate": "universal_buying.ub_inward.quality_inspection.validate",
		"before_submit": "universal_buying.ub_inward.quality_inspection.before_submit",
		"on_submit": "universal_buying.ub_inward.quality_inspection.on_submit",
		"on_cancel": "universal_buying.ub_inward.quality_inspection.on_cancel",
	},
	"Stock Entry": {
		"validate": "universal_buying.ub_inward.stock_entry.enforce_inc_rate",
	},
	"Landed Cost Voucher": {
		"validate": "universal_buying.ub_inward.landed_cost_voucher.validate_landed_cost_voucher",
	},
}
