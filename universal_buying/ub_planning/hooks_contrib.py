# UB Planning hook contributions - PURE DATA, no imports.

DOC_EVENTS = {
	"Item": {"validate": "universal_buying.ub_planning.events.item_validate"},
	"Item Manufacturer": {"validate": "universal_buying.ub_planning.events.item_manufacturer_validate"},
	"Item Price": {"validate": "universal_buying.ub_planning.events.item_price_validate"},
	"Purchase Order": {"validate": "universal_buying.ub_planning.events.purchase_order_validate_mpn"},
}

SCHEDULER_EVENTS = {
	"cron": {
		# Requirement Engine rebuild (BRD 6.10); the handler enqueues the real job on the long queue
		"0 3 * * *": ["universal_buying.ub_planning.requirement_engine.scheduled_rebuild"],
	},
	"weekly": ["universal_buying.ub_planning.item_classification.scheduled_classification"],
	"daily": [
		"universal_buying.ub_planning.jobs.scheduled_consumables_auto_po",
		"universal_buying.ub_planning.jobs.purge_draft_auto_pos",
	],
}

DOCTYPE_JS = {
	"Item": "ub_planning/client/item.js",
	"Item Price": "ub_planning/client/item_price.js",
	"Item Manufacturer": "ub_planning/client/item_manufacturer.js",
	"Material Request": "ub_planning/client/material_request.js",
}
