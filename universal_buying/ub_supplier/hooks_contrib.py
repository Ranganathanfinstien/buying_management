# UB Supplier hook contributions (pure data - no imports).

DOC_EVENTS = {
	"Supplier": {
		"validate": "universal_buying.ub_supplier.supplier.validate",
		"after_insert": "universal_buying.ub_supplier.supplier.after_insert",
		"on_update": "universal_buying.ub_supplier.supplier.on_update",
	},
}

DOCTYPE_JS = {
	"Supplier": "ub_supplier/client/supplier.js",
}

SCHEDULER_EVENTS = {
	"daily": [
		"universal_buying.ub_supplier.api.refresh_vault_statuses",
	],
}

UB_ON_SETTINGS_UPDATE = [
	"universal_buying.ub_supplier.supplier.recompute_approval_routes",
]

WEBSITE_ROUTE_RULES = [
	# friendly alias for the token page (www/supplier_onboarding.py)
	{"from_route": "/supplier-onboarding", "to_route": "supplier_onboarding"},
]
