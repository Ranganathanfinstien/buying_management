// Universal Buying - Request for Quotation (BRD v2 6.13)

const UB_RFQ_API = "universal_buying.ub_sourcing.";
const UB_RFQ_FINAL = ["Awarded", "Rejected"];
const UB_RFQ_NOT_IN_APPROVAL = ["", "Draft", "Open", "Awarded", "Rejected", "Correction Required"];

// ---- suppliers table: Supplier OR Prospective Supplier (V-13.1) --------------------------------
frappe.ui.form.on("Request for Quotation Supplier", {
	ub_prospective_supplier(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.ub_prospective_supplier) return;
		frappe.model.set_value(cdt, cdn, "supplier", "");
		frappe.model.set_value(cdt, cdn, "contact", "");
		frappe.db
			.get_value("Prospective Supplier", row.ub_prospective_supplier, ["email", "contact_person", "supplier_name"])
			.then((r) => {
				const d = r.message || {};
				frappe.model.set_value(cdt, cdn, "email_id", d.email || "");
				frappe.model.set_value(cdt, cdn, "supplier_name", d.contact_person || d.supplier_name || row.ub_prospective_supplier);
			});
	},
	supplier(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.supplier && row.ub_prospective_supplier) {
			frappe.model.set_value(cdt, cdn, "ub_prospective_supplier", "");
		}
	},
});

// ---- form -------------------------------------------------------------------------------------
frappe.ui.form.on("Request for Quotation", {
	onload(frm) {
		if (!frm.is_new()) return;
		if (!frm.doc.ub_bid_deadline) {
			frappe
				.call(UB_RFQ_API + "bidding.default_bid_deadline", { base_date: frm.doc.transaction_date })
				.then((r) => r.message && !frm.doc.ub_bid_deadline && frm.set_value("ub_bid_deadline", r.message));
		}
		if (!frm.doc.ub_po_type) {
			frappe.db.get_value("PO Type", { is_default: 1 }, "name").then((r) => {
				if (r.message && r.message.name && !frm.doc.ub_po_type) frm.set_value("ub_po_type", r.message.name);
			});
		}
	},

	refresh(frm) {
		ub_rfq.setup_suppliers_grid(frm);
		ub_rfq.toggle_item_fields(frm);
		ub_rfq.bid_headline(frm);
		if (frm.doc.docstatus !== 1) return;

		const state = frm.doc.workflow_state || "";
		const finalised = UB_RFQ_FINAL.includes(state) || ["Awarded", "Rejected"].includes(frm.doc.ub_bid_status);

		frm.add_custom_button(__("Quotation Comparison"), () => {
			window.open(`/quotation-comparison?rfq=${encodeURIComponent(frm.doc.name)}`, "_blank");
		}).addClass("btn-primary");

		if (!finalised && ["Open", "Correction Required"].includes(state)) {
			frm.add_custom_button(__("Send RFQ Portal Link"), () => ub_rfq.send_portal_links(frm), __("Suppliers"));
		}
		if (!finalised && UB_RFQ_NOT_IN_APPROVAL.includes(state)) {
			frm.add_custom_button(__("Extend Bid Deadline"), () => ub_rfq.extend_deadline(frm), __("Suppliers"));
		}
		if (finalised) {
			frm.remove_custom_button(__("Supplier Quotation"), __("Create"));
		}
		// the comparison page replaces the core comparison report link
		frm.remove_custom_button(__("Supplier Quotation Comparison"), __("View"));
	},

	ub_po_type(frm) {
		ub_rfq.toggle_item_fields(frm);
	},

	// V-8.2: Send Back for Correction and Resubmit need a comment (stored on the timeline)
	before_workflow_action(frm) {
		const action = frm.selected_workflow_action;
		const dialogs = {
			"Send Back for Correction": __("Correction Reason"),
			Resubmit: __("Resubmit Notes"),
		};
		if (!dialogs[action]) return;
		return new Promise((resolve, reject) => {
			let done = false;
			frappe.dom.unfreeze();
			const d = new frappe.ui.Dialog({
				title: __(action),
				fields: [{ fieldname: "comment", fieldtype: "Small Text", label: dialogs[action], reqd: 1 }],
				primary_action_label: __("Continue"),
				primary_action(values) {
					const comment = (values.comment || "").trim();
					if (!comment) return;
					done = true;
					d.hide();
					frappe.dom.freeze();
					frappe
						.call(UB_RFQ_API + "api.log_workflow_comment", {
							reference_doctype: frm.doctype,
							reference_name: frm.doc.name,
							action_type: action,
							workflow_state: frm.doc.workflow_state,
							comments: comment,
						})
						.then((r) => {
							if (r && r.exc) {
								frappe.dom.unfreeze();
								reject();
							} else {
								resolve();
							}
						})
						.catch(() => {
							frappe.dom.unfreeze();
							reject();
						});
				},
			});
			d.onhide = () => {
				if (!done) {
					frappe.dom.unfreeze();
					reject();
				}
			};
			d.show();
		});
	},
});

frappe.provide("ub_rfq");

ub_rfq.setup_suppliers_grid = function (frm) {
	const grid = frm.fields_dict.suppliers && frm.fields_dict.suppliers.grid;
	if (!grid) return;
	grid.update_docfield_property("supplier", "reqd", 0);
	grid.update_docfield_property("supplier", "in_list_view", 1);
	grid.update_docfield_property("ub_prospective_supplier", "in_list_view", 1);
	grid.update_docfield_property("email_id", "in_list_view", 1);
	frm.set_query("supplier", "suppliers", () => ({ filters: { disabled: 0 } }));
};

ub_rfq.toggle_item_fields = function (frm) {
	const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
	if (!grid) return;
	const apply = (item_required) => {
		grid.update_docfield_property("item_code", "reqd", item_required ? 1 : 0);
		grid.update_docfield_property("ub_item_description", "reqd", item_required ? 0 : 1);
		grid.update_docfield_property("ub_item_description", "hidden", item_required ? 1 : 0);
		grid.update_docfield_property("item_name", "reqd", item_required ? 1 : 0);
		grid.update_docfield_property("uom", "reqd", item_required ? 1 : 0);
		grid.update_docfield_property("stock_uom", "reqd", item_required ? 1 : 0);
		grid.update_docfield_property("conversion_factor", "reqd", item_required ? 1 : 0);
		grid.refresh();
	};
	if (!frm.doc.ub_po_type) {
		apply(true);
		return;
	}
	frappe.db.get_value("PO Type", frm.doc.ub_po_type, "item_required").then((r) => {
		apply(!r.message || cint(r.message.item_required));
	});
};

ub_rfq.bid_headline = function (frm) {
	if (frm.doc.docstatus !== 1 || !frm.doc.ub_bid_deadline) return;
	const state = frm.doc.workflow_state || "";
	if (UB_RFQ_FINAL.includes(state)) return;
	const passed = frappe.datetime.str_to_obj(frm.doc.ub_bid_deadline) <= new Date();
	const when = frappe.datetime.str_to_user(frm.doc.ub_bid_deadline);
	let msg, color;
	if (!UB_RFQ_NOT_IN_APPROVAL.includes(state)) {
		msg = __("Under approval ({0}). Suppliers cannot submit or revise quotations.", [state]);
		color = "orange";
	} else if (passed) {
		msg = __("Bidding closed on {0}.", [when]);
		color = "red";
	} else {
		msg = __("Bidding open until {0}.", [when]);
		color = "blue";
	}
	frm.dashboard.set_headline(msg, color);
};

ub_rfq.send_portal_links = function (frm) {
	const rows = (frm.doc.suppliers || []).filter((r) => r.supplier || r.ub_prospective_supplier);
	if (!rows.length) {
		frappe.msgprint(__("No supplier rows found."));
		return;
	}
	const list = rows
		.map((r) => {
			const kind = r.ub_prospective_supplier ? __("Prospective, token link") : __("Registered, portal login");
			const name = frappe.utils.escape_html(r.supplier_name || r.supplier || r.ub_prospective_supplier);
			return `<li><strong>${name}</strong> <small class="text-muted">(${kind})</small> - ${frappe.utils.escape_html(r.email_id || __("no email"))}</li>`;
		})
		.join("");
	frappe.confirm(
		`<p>${__("The invitation will be (re)sent to")}:</p><ul>${list}</ul>
		<p class="text-muted small">${__("Existing links stay valid; tokens are not regenerated.")}</p>`,
		() => {
			frappe.call({
				method: UB_RFQ_API + "api.send_rfq_portal_links",
				args: { rfq_name: frm.doc.name },
				freeze: true,
				freeze_message: __("Sending..."),
				callback(r) {
					const res = r.message || [];
					const sent = res.filter((x) => x.status === "sent");
					const failed = res.filter((x) => x.status === "failed");
					let msg = `<p>${__("{0} email(s) queued.", [sent.length])}</p>`;
					if (failed.length) {
						msg += `<p class="text-danger">${__("Failed")}:</p><ul>${failed
							.map((x) => `<li>${frappe.utils.escape_html(x.display_name || "")}: ${x.error}</li>`)
							.join("")}</ul>`;
					}
					frappe.msgprint({ title: __("RFQ invitations"), message: msg, indicator: failed.length ? "orange" : "green" });
					frm.reload_doc();
				},
			});
		}
	);
};

ub_rfq.extend_deadline = function (frm) {
	const current = frm.doc.ub_bid_deadline;
	const d = new frappe.ui.Dialog({
		title: __("Extend Bid Deadline"),
		fields: [
			{
				fieldtype: "HTML",
				options: current
					? `<p>${__("Current deadline")}: <strong>${frappe.datetime.str_to_user(current)}</strong></p>`
					: `<p>${__("No deadline is set yet.")}</p>`,
			},
			{ fieldtype: "Datetime", fieldname: "new_deadline", label: __("New Bid Deadline"), reqd: 1 },
			{ fieldtype: "Small Text", fieldname: "reason", label: __("Reason (sent to suppliers)"), reqd: 1 },
		],
		primary_action_label: __("Extend & Notify Suppliers"),
		primary_action(values) {
			frappe.call({
				method: UB_RFQ_API + "bidding.extend_bid_deadline",
				args: { rfq_name: frm.doc.name, new_deadline: values.new_deadline, reason: values.reason },
				freeze: true,
				freeze_message: __("Extending deadline..."),
				callback(r) {
					d.hide();
					const m = r.message || {};
					const failed = (m.mail_failed || []).length;
					frappe.show_alert(
						{
							message: __("Bid deadline extended to {0}. {1} supplier(s) notified{2}.", [
								m.new_deadline_fmt,
								(m.notified || []).length,
								failed ? __(", {0} email(s) failed", [failed]) : "",
							]),
							indicator: failed ? "orange" : "green",
						},
						10
					);
					frm.reload_doc();
				},
			});
		},
	});
	d.show();
};
