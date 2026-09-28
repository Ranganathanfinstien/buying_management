from universal_buying.ub_ordering.portal_pages import fmt_date, list_docs, prepare

no_cache = 1


def get_context(context):
	suppliers = prepare(context, "shipments", "Shipments")
	if not suppliers:
		return
	context.shipments = list_docs(context, "PO Shipment", suppliers,
		["name", "purchase_order", "shipment_date", "expected_arrival_date", "mode_of_transport", "transporter",
			"lr_awb_no", "tracking_url", "shipment_status", "delivery_status", "total_shipped_qty"],
		extra_filters={"docstatus": 1}, search_field="purchase_order", order_by="shipment_date desc, name desc")
	for s in context.shipments:
		s.date_fmt = fmt_date(s.shipment_date)
		s.eta_fmt = fmt_date(s.expected_arrival_date)
