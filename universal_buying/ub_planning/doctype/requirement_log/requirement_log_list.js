frappe.listview_settings["Requirement Log"] = {
	hide_name_column: true,
	get_indicator(doc) {
		const colors = { Stock: "green", "Purchase Order": "blue", "Work Order": "purple", Shortage: "red" };
		return [__(doc.reservation_type), colors[doc.reservation_type] || "gray", "reservation_type,=," + doc.reservation_type];
	},
	onload(listview) {
		listview.page.add_inner_button(__("Rebuild Now"), () => ub_requirement_rebuild_dialog());
		listview.page.add_inner_button(__("Rebuild History"), () => frappe.set_route("List", "Requirement Rebuild"));
	},
};

window.ub_requirement_rebuild_dialog = function () {
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
};
