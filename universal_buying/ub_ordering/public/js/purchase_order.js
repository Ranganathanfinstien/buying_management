// Universal Buying - Purchase Order form (BRD v2 6.17 - 6.21)
// Server rules are authoritative; this file only mirrors them for the user.

frappe.provide("universal_buying.po");

universal_buying.po.API = "universal_buying.ub_ordering.api.";
universal_buying.po.APPROVAL = "universal_buying.ub_ordering.approval.";
universal_buying.po.CHANNEL = "universal_buying.ub_ordering.integrations.base.";

frappe.ui.form.on("Purchase Order", {
	onload(frm) {
		universal_buying.po.load_settings(frm);
	},

	refresh(frm) {
		universal_buying.po.load_settings(frm);
		if (frm.is_new()) return;
		universal_buying.po.render_approval(frm);
		if (frm.doc.docstatus === 1) {
			universal_buying.po.render_channel_buttons(frm);
			if (!["Closed", "Completed"].includes(frm.doc.status)) {
				frm.add_custom_button(
					__("PO Amendment"),
					() => frappe.new_doc("PO Amendment", { purchase_order: frm.doc.name }),
					__("Create")
				);
			}
			if (frm.doc.ub_portal_status) {
				frm.dashboard.add_indicator(
					__("Portal: {0}", [__(frm.doc.ub_portal_status)]),
					frm.doc.ub_portal_status === "Pending Acceptance" ? "orange" : "blue"
				);
			}
		}
	},

	company(frm) {
		universal_buying.po.load_settings(frm, true);
	},

	ub_po_type(frm) {
		universal_buying.po.load_settings(frm, true);
	},

	supplier_address(frm) {
		universal_buying.po.apply_tax_template(frm);
	},
	billing_address(frm) {
		universal_buying.po.apply_tax_template(frm);
	},
	shipping_address(frm) {
		universal_buying.po.apply_tax_template(frm);
	},
});

frappe.ui.form.on("Purchase Order Item", {
	item_code(frm, cdt, cdn) {
		// let ERPNext fill uom / conversion first
		setTimeout(() => universal_buying.po.fetch_rate(frm, cdt, cdn), 800);
	},
	uom(frm, cdt, cdn) {
		universal_buying.po.fetch_rate(frm, cdt, cdn);
	},
	schedule_date(frm, cdt, cdn) {
		universal_buying.po.fetch_rate(frm, cdt, cdn);
	},
});

// ---------------------------------------------------------------------------- settings
universal_buying.po.load_settings = function (frm, force) {
	if (frm._ub_settings && !force) {
		universal_buying.po.apply_locks(frm);
		return;
	}
	frappe.call({
		method: universal_buying.po.API + "get_form_settings",
		args: { company: frm.doc.company, po_type: frm.doc.ub_po_type },
		callback(r) {
			frm._ub_settings = r.message || {};
			if (frm.doc.docstatus === 0 && !frm.doc.ub_po_type && frm._ub_settings.default_po_type) {
				frm.set_value("ub_po_type", frm._ub_settings.default_po_type);
			}
			universal_buying.po.apply_locks(frm);
		},
	});
};

universal_buying.po.apply_locks = function (frm) {
	const s = frm._ub_settings || {};
	const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
	if (!grid) return;
	const strict = s.price_control_mode === "Strict";
	["rate", "price_list_rate", "discount_percentage", "discount_amount", "margin_rate_or_amount"].forEach((f) => {
		grid.update_docfield_property(f, "read_only", strict ? 1 : 0);
	});
	grid.update_docfield_property("item_code", "reqd", s.item_required ? 1 : 0);
	frm.refresh_field("items");
};

// ---------------------------------------------------------------------------- price control
universal_buying.po.fetch_rate = function (frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const s = frm._ub_settings || {};
	if (!row || !row.item_code || !frm.doc.supplier || s.price_control_mode === "Free") return;
	frappe.call({
		method: universal_buying.po.API + "get_line_rate",
		args: {
			item_code: row.item_code,
			supplier: frm.doc.supplier,
			company: frm.doc.company,
			transaction_date: frm.doc.transaction_date,
			schedule_date: row.schedule_date,
			uom: row.uom,
			stock_uom: row.stock_uom,
			conversion_factor: row.conversion_factor,
			currency: frm.doc.currency,
			conversion_rate: frm.doc.conversion_rate,
			supplier_quotation_item: row.supplier_quotation_item,
		},
		callback(r) {
			const res = r.message || {};
			if (res.rate === null || res.rate === undefined) {
				frappe.show_alert(
					{
						message: __("No valid price for {0}. Create an Item Price before saving.", [row.item_code]),
						indicator: res.mode === "Strict" ? "red" : "orange",
					},
					8
				);
				if (res.mode === "Strict") frappe.model.set_value(cdt, cdn, "rate", 0);
				return;
			}
			if (res.mode === "Strict" || !flt(row.rate)) {
				frappe.model.set_value(cdt, cdn, "price_list_rate", res.rate);
				frappe.model.set_value(cdt, cdn, "rate", res.rate);
			} else if (flt(row.rate) !== flt(res.rate)) {
				frappe.show_alert({ message: __("Valid price for {0} is {1}", [row.item_code, res.rate]), indicator: "orange" });
			}
		},
	});
};

// ---------------------------------------------------------------------------- tax template
universal_buying.po.apply_tax_template = function (frm) {
	if (frm.doc.docstatus !== 0 || !frm.doc.company || !frm.doc.supplier) return;
	frappe.call({
		method: "universal_buying.ub_ordering.po_rules.get_tax_template_for_po",
		args: {
			company: frm.doc.company,
			supplier: frm.doc.supplier,
			supplier_address: frm.doc.supplier_address,
			billing_address: frm.doc.billing_address,
			shipping_address: frm.doc.shipping_address,
		},
		callback(r) {
			const res = r.message || {};
			if (res.template && res.template !== frm.doc.taxes_and_charges) {
				frm.set_value("taxes_and_charges", res.template);
			}
		},
	});
};

// ---------------------------------------------------------------------------- approval
universal_buying.po.render_approval = function (frm) {
	if (frm.doc.docstatus !== 0) return;
	frappe.call({
		method: universal_buying.po.APPROVAL + "get_approval_context",
		args: { name: frm.doc.name },
		callback(r) {
			const st = r.message;
			if (!st || !st.enabled) return;
			const colors = { Draft: "gray", Pending: "orange", Approved: "green", Rejected: "red" };
			let msg = __("Approval: {0}", [__(st.status)]);
			if (st.status === "Pending") {
				msg += " - " + __("step {0} of {1}, waiting for {2}", [st.step, st.total_steps, st.pending_roles.join(" / ")]);
			} else if (st.status === "Draft" && st.required) {
				msg += " - " + __("{0} step(s) required before submit", [st.total_steps]);
			}
			frm.set_intro(msg, colors[st.status] || "blue");

			if (st.can_send) {
				frm.add_custom_button(__("Send for Approval"), () => {
					const go = () =>
						frappe.call({
							method: universal_buying.po.APPROVAL + "send_for_approval",
							args: { name: frm.doc.name },
							freeze: true,
							callback: () => frm.reload_doc(),
						});
					frm.is_dirty() ? frm.save().then(go) : go();
				}).addClass("btn-primary");
			}
			if (st.can_approve) {
				frm.add_custom_button(
					__("Approve"),
					() => {
						frappe.prompt(
							[{ fieldname: "remarks", fieldtype: "Small Text", label: __("Remarks") }],
							(v) =>
								frappe.call({
									method: universal_buying.po.APPROVAL + "approve",
									args: { name: frm.doc.name, remarks: v.remarks },
									freeze: true,
									callback: () => frm.reload_doc(),
								}),
							__("Approve Purchase Order"),
							__("Approve")
						);
					},
					__("Approval")
				);
			}
			if (st.can_reject) {
				frm.add_custom_button(
					__("Reject"),
					() => {
						frappe.prompt(
							[{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 }],
							(v) =>
								frappe.call({
									method: universal_buying.po.APPROVAL + "reject",
									args: { name: frm.doc.name, reason: v.reason },
									freeze: true,
									callback: () => frm.reload_doc(),
								}),
							__("Reject Purchase Order"),
							__("Reject")
						);
					},
					__("Approval")
				);
			}
		},
	});
};

// ---------------------------------------------------------------------------- channels (A-17.4)
universal_buying.po.render_channel_buttons = function (frm) {
	frappe.call({
		method: universal_buying.po.CHANNEL + "get_channel_info",
		args: { purchase_order: frm.doc.name },
		callback(r) {
			const ch = r.message;
			if (!ch) return;
			const group = __("Supplier Channel");
			const run = (method, label) =>
				frappe.call({
					method: universal_buying.po.CHANNEL + method,
					args: { purchase_order: frm.doc.name },
					freeze: true,
					freeze_message: label,
					callback: () => frm.reload_doc(),
				});
			frm.add_custom_button(__("Send Order"), () => run("send_order", __("Sending order...")), group);
			if (ch.connector !== "Email PDF") {
				frm.add_custom_button(__("Fetch Status"), () => run("fetch_status", __("Fetching status...")), group);
			}
			frm.add_custom_button(__("Send Amendment"), () => run("send_amendment", __("Sending amendment...")), group);
		},
	});
};
