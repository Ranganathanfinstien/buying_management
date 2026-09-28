frappe.listview_settings["Requirement Rebuild"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colors = { Queued: "blue", Running: "orange", Completed: "green", Failed: "red", Skipped: "gray" };
		return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
	},
	onload(listview) {
		listview.page.add_inner_button(__("Rebuild Now"), () => {
			frappe.prompt(
				[{ fieldname: "company", fieldtype: "Link", options: "Company", label: __("Company (empty = all)") }],
				(v) => {
					frappe
						.xcall("universal_buying.ub_planning.requirement_engine.enqueue_rebuild", { company: v.company })
						.then((msg) => frappe.show_alert({ message: msg, indicator: "blue" }));
				},
				__("Rebuild Requirement Log"),
				__("Queue")
			);
		});
	},
};
