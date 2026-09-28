frappe.listview_settings["Auto PO Run"] = {
	add_fields: ["status", "docstatus"],
	get_indicator(doc) {
		const colors = { "Not Started": "gray", Queued: "blue", "In Progress": "orange", Completed: "green", Failed: "red" };
		if (doc.docstatus === 2) return [__("Cancelled"), "red", "docstatus,=,2"];
		if (doc.docstatus === 0) return [__("Draft"), "gray", "docstatus,=,0"];
		return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
	},
};
