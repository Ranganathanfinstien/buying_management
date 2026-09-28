frappe.listview_settings["Inward Discrepancy"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colors = { Draft: "red", Open: "orange", Closed: "green", Cancelled: "grey" };
		return [__(doc.status), colors[doc.status] || "grey", "status,=," + doc.status];
	},
};
