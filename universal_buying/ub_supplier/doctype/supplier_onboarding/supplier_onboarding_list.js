frappe.listview_settings["Supplier Onboarding"] = {
	add_fields: ["status", "docstatus"],
	get_indicator(doc) {
		const colors = {
			Draft: "red",
			"Pending Approval": "orange",
			Approved: "green",
			Rejected: "gray",
		};
		if (doc.docstatus === 2) return [__("Cancelled"), "red", "docstatus,=,2"];
		return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
	},
};
