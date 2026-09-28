// Universal Buying - Supplier Quotation (BRD v2 6.14 / 6.15). No "Create Capex" button (AC-15.1).

frappe.ui.form.on("Supplier Quotation", {
	refresh(frm) {
		ub_sq.toggle_item_fields(frm);
		ub_sq.indicators(frm);
		ub_sq.revision_button(frm);
		ub_sq.comparison_button(frm);
		ub_sq.guard_purchase_order(frm);
		ub_sq.render_discussion(frm);
	},

	ub_po_type(frm) {
		ub_sq.toggle_item_fields(frm);
	},

	ub_prospective_supplier(frm) {
		if (frm.doc.ub_prospective_supplier && frm.doc.supplier) {
			frm.set_value("supplier", "");
		}
		if (frm.doc.ub_prospective_supplier) {
			frappe.db.get_value("Prospective Supplier", frm.doc.ub_prospective_supplier, "supplier_name").then((r) => {
				if (r.message && r.message.supplier_name) frm.set_value("supplier_name", r.message.supplier_name);
			});
		}
	},
});

frappe.provide("ub_sq");

ub_sq.rfq = function (frm) {
	const row = (frm.doc.items || []).find((d) => d.request_for_quotation);
	return row ? row.request_for_quotation : null;
};

ub_sq.toggle_item_fields = function (frm) {
	const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
	if (!grid) return;
	const apply = (item_required) => {
		grid.update_docfield_property("item_code", "reqd", item_required ? 1 : 0);
		grid.update_docfield_property("ub_item_description", "hidden", item_required ? 1 : 0);
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

ub_sq.indicators = function (frm) {
	if (frm.doc.ub_revised) {
		frm.dashboard.add_indicator(__("Superseded by a newer version"), "gray");
		frm.set_intro(__("The supplier submitted a newer version of this quotation. This one is kept for reference only."), "orange");
	} else if (frm.doc.ub_revision_requested) {
		frm.dashboard.add_indicator(__("Revision Requested"), "orange");
	}
	if (frm.doc.ub_prospective_supplier && !frm.doc.supplier) {
		frm.dashboard.add_indicator(__("Prospective Supplier"), "blue");
	}
};

ub_sq.revision_button = function (frm) {
	if (frm.is_new() || frm.doc.docstatus !== 0 || frm.doc.ub_revised || frm.doc.ub_revision_requested) return;
	if (!ub_sq.rfq(frm)) return;
	frm.add_custom_button(__("Mark for Revision"), () => {
		frappe.prompt(
			[
				{
					fieldname: "reason",
					fieldtype: "Small Text",
					label: __("Reason for revision"),
					reqd: 1,
					description: __("Sent to the supplier. They submit a new version through their RFQ link."),
				},
			],
			(values) => {
				frappe.call({
					method: "universal_buying.ub_sourcing.api.mark_for_revision",
					args: { supplier_quotation: frm.doc.name, reason: values.reason },
					freeze: true,
					callback(r) {
						if (r.message && r.message.ok) {
							frappe.show_alert({ message: __("Revision requested"), indicator: "orange" });
							frm.reload_doc();
						}
					},
				});
			},
			__("Mark for Revision"),
			__("Send")
		);
	});
};

ub_sq.comparison_button = function (frm) {
	const rfq = ub_sq.rfq(frm);
	if (!rfq || frm.is_new()) return;
	frm.add_custom_button(
		__("Quotation Comparison"),
		() => window.open(`/quotation-comparison?rfq=${encodeURIComponent(rfq)}`, "_blank"),
		__("View")
	);
};

ub_sq.guard_purchase_order = function (frm) {
	// rejected or superseded quotations are never ordered (server blocks it too)
	if (frm.doc.docstatus === 1 && (frm.doc.ub_sq_status === "Rejected" || frm.doc.ub_revised)) {
		frm.remove_custom_button(__("Purchase Order"), __("Create"));
	}
};

// ---------------------------------------------------------------------------
// Discussion with the supplier (same thread as the comparison page and the RFQ portal)
// ---------------------------------------------------------------------------

ub_sq.render_discussion = function (frm) {
	const field = frm.fields_dict.ub_discussion_html;
	if (!field) return;
	const $w = $(field.wrapper).empty();
	if (frm.is_new() || !ub_sq.rfq(frm)) {
		frm.toggle_display("ub_discussion_section", false);
		return;
	}
	frm.toggle_display("ub_discussion_section", true);
	$w.html(`
		<div class="ub-chat" style="border:1px solid var(--border-color);border-radius:8px;overflow:hidden;">
			<div class="ub-chat-msgs" style="max-height:320px;overflow-y:auto;padding:10px;background:var(--subtle-fg);"></div>
			<div style="padding:10px;border-top:1px solid var(--border-color);">
				<textarea class="form-control ub-chat-input" rows="2" placeholder="${__("Write to the supplier...")}"></textarea>
				<div style="display:flex;justify-content:space-between;align-items:center;margin-top:6px;">
					<label style="margin:0;font-size:12px;"><input type="checkbox" class="ub-chat-internal"> ${__("Internal note (not shown to supplier)")}</label>
					<button class="btn btn-primary btn-xs ub-chat-send">${__("Send")}</button>
				</div>
			</div>
		</div>`);
	const load = () =>
		frappe.call({
			method: "universal_buying.ub_sourcing.chat.get_thread_for_quotation",
			args: { sq_name: frm.doc.name },
			callback(r) {
				const t = r.message || {};
				frm.__ub_chat = t;
				ub_sq.paint_messages($w.find(".ub-chat-msgs"), t.messages || []);
			},
		});
	$w.find(".ub-chat-send").on("click", () => {
		const t = frm.__ub_chat || {};
		const text = ($w.find(".ub-chat-input").val() || "").trim();
		if (!text) return;
		if (!t.row) {
			frappe.msgprint(__("This quotation is not linked to a supplier row of its RFQ."));
			return;
		}
		frappe.call({
			method: "universal_buying.ub_sourcing.chat.post_message",
			args: { rfq_name: t.rfq, rfq_supplier_row: t.row, message: text, is_internal: $w.find(".ub-chat-internal").is(":checked") ? 1 : 0 },
			callback(r) {
				$w.find(".ub-chat-input").val("");
				ub_sq.paint_messages($w.find(".ub-chat-msgs"), r.message || []);
			},
		});
	});
	load();
};

ub_sq.paint_messages = function ($box, messages) {
	if (!messages.length) {
		$box.html(`<div class="text-muted small">${__("No messages yet.")}</div>`);
		return;
	}
	$box.html(
		messages
			.map((m) => {
				const buyer = m.sender_type === "Buyer";
				const bg = m.is_internal ? "#fef3c7" : buyer ? "#e0ecff" : "#ffffff";
				const tag = m.is_internal ? ` <span class="badge" style="background:#f59e0b;color:#fff;">${__("Internal")}</span>` : "";
				return `<div style="display:flex;justify-content:${buyer ? "flex-end" : "flex-start"};margin:4px 0;">
					<div style="max-width:80%;background:${bg};border:1px solid var(--border-color);border-radius:8px;padding:6px 10px;">
						<div style="font-size:11px;color:var(--text-muted);">${frappe.utils.escape_html(m.sender_name)} · ${m.time}${tag}</div>
						<div style="white-space:pre-wrap;">${frappe.utils.escape_html(m.message)}</div>
					</div></div>`;
			})
			.join("")
	);
	$box.scrollTop($box[0].scrollHeight);
};
