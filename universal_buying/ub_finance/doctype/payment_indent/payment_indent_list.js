frappe.listview_settings["Payment Indent"] = {
	add_fields: ["status", "requested_amount", "currency"],
	get_indicator(doc) {
		const colors = { Draft: "red", Submitted: "blue", "Payment Requested": "green", Cancelled: "gray" };
		return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
	},
};
