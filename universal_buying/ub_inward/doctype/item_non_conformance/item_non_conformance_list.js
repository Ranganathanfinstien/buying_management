frappe.listview_settings["Item Non Conformance"] = {
	add_fields: ["status", "disposition"],
	get_indicator(doc) {
		const colors = { Draft: "red", Open: "orange", Completed: "green", Cancelled: "grey" };
		return [__(doc.status), colors[doc.status] || "grey", "status,=," + doc.status];
	},
};
