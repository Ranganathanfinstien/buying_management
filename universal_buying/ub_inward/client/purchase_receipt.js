// Universal Buying - Purchase Receipt (BRD v2 6.22 / 6.23)
// Server rules live in ub_inward/overrides/purchase_receipt.py; this file only helps the user.

const UB_PR_API = "universal_buying.ub_inward.api";

frappe.ui.form.on("Purchase Receipt", {
	setup(frm) {
		frm.set_query("ub_gate_entry", () => {
			const filters = { entry_type: "In", docstatus: 1 };
			if (frm.doc.company) filters.company = frm.doc.company;
			const days = cint(frm.__ub_settings && frm.__ub_settings.gate_entry_lookback_days);
			if (days) {
				filters.entry_date = [
					">=",
					frappe.datetime.add_days(frm.doc.posting_date || frappe.datetime.get_today(), -days),
				];
			}
			return { filters };
		});
	},

	onload(frm) {
		ub_pr_load_settings(frm);
	},

	company(frm) {
		ub_pr_load_settings(frm);
	},

	refresh(frm) {
		ub_pr_toggle_fields(frm);
		ub_pr_block_manual_rows(frm);
		if (frm.doc.is_return) return;

		if (frm.doc.docstatus === 0 && frm.doc.supplier) {
			frm.add_custom_button(__("Purchase Order (Pending Lines)"), () => ub_pr_po_picker(frm), __("Get Items From"));
		}

		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			if ((frm.doc.items || []).some((d) => !d.batch_no && !d.serial_and_batch_bundle)) {
				frm.add_custom_button(__("Batches"), () => ub_pr_create_batches(frm), __("Create"));
			}
			frm.add_custom_button(__("Inspections by Batch"), () => ub_pr_make_inspections(frm), __("Create"));
			if (!frm.doc.ub_inward_discrepancy) {
				frm.add_custom_button(
					__("Inward Discrepancy"),
					() =>
						frappe.model.open_mapped_doc({
							method: `${UB_PR_API}.make_inward_discrepancy`,
							frm: frm,
						}),
					__("Create")
				);
			}
			frm.add_custom_button(__("Check IQC"), () => ub_pr_check_iqc(frm), __("Actions"));
		}

		if (
			frm.doc.docstatus === 1 &&
			!["Completed", "Closed"].includes(frm.doc.status) &&
			frm.__ub_settings &&
			frm.__ub_settings.can_edit_invoice_no
		) {
			frm.add_custom_button(__("Edit Supplier Invoice No"), () => ub_pr_edit_invoice_no(frm), __("Actions"));
		}
	},

	ub_is_bonded(frm) {
		ub_pr_toggle_fields(frm);
	},

	ub_is_import(frm) {
		ub_pr_toggle_fields(frm);
	},
});

frappe.ui.form.on("Purchase Receipt Item", {
	items_add(frm, cdt, cdn) {
		// V-23.1: rows only come from a Purchase Order (the server blocks it too)
		const row = locals[cdt][cdn];
		if (!frm.doc.is_return && !row.purchase_order_item && !frm.__ub_mapping) {
			frappe.show_alert({
				message: __("Add rows with Get Items From > Purchase Order."),
				indicator: "orange",
			});
		}
	},
});

function ub_pr_load_settings(frm) {
	frappe.call({
		method: `${UB_PR_API}.get_inward_settings`,
		args: { company: frm.doc.company },
		callback(r) {
			frm.__ub_settings = r.message || {};
			ub_pr_toggle_fields(frm);
			frm.refresh_fields();
		},
	});
}

function ub_pr_toggle_fields(frm) {
	const s = frm.__ub_settings || {};
	const bonded = cint(frm.doc.ub_is_bonded) && cint(s.bonded_goods_enabled);
	frm.set_df_property("ub_is_bonded", "hidden", cint(s.bonded_goods_enabled) ? 0 : 1);
	frm.set_df_property("ub_gate_entry", "reqd", !frm.doc.is_return && cint(s.gate_entry_required) && !bonded ? 1 : 0);
	frm.set_df_property("ub_gate_entry", "read_only", bonded ? 1 : 0);
	frm.set_df_property("ub_boe_date", "reqd", cint(frm.doc.ub_is_import) && !frm.doc.is_return ? 1 : 0);
}

function ub_pr_block_manual_rows(frm) {
	const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
	if (!grid) return;
	const block = frm.doc.docstatus === 0 && !frm.doc.is_return;
	grid.cannot_add_rows = block;
	grid.df.cannot_add_rows = block;
	grid.refresh();
}

function ub_pr_po_picker(frm) {
	frappe.call({
		method: `${UB_PR_API}.get_purchase_order_items`,
		args: { supplier: frm.doc.supplier, company: frm.doc.company, exclude_pr: frm.is_new() ? null : frm.doc.name },
		freeze: true,
		callback(r) {
			const in_doc = {};
			(frm.doc.items || []).forEach((d) => {
				if (d.purchase_order_item) in_doc[d.purchase_order_item] = (in_doc[d.purchase_order_item] || 0) + flt(d.qty);
			});
			const rows = (r.message || [])
				.map((d) => Object.assign(d, { pending_qty: flt(d.pending_qty) - flt(in_doc[d.name]) }))
				.filter((d) => d.pending_qty > 0);
			if (!rows.length) {
				frappe.msgprint(__("No pending Purchase Order lines for {0}.", [frm.doc.supplier]));
				return;
			}
			ub_pr_show_picker(frm, rows);
		},
	});
}

function ub_pr_show_picker(frm, rows) {
	let table;
	const dialog = new frappe.ui.Dialog({
		title: __("Select Purchase Order Lines"),
		size: "extra-large",
		fields: [{ fieldtype: "HTML", fieldname: "lines" }],
		primary_action_label: __("Get Items"),
		primary_action() {
			const picked = [];
			table.rowmanager.checkMap.forEach((checked, i) => checked && picked.push(rows[i]));
			if (!picked.length) {
				frappe.msgprint(__("Select at least one line."));
				return;
			}
			const drafts = picked.filter((d) => flt(d.draft_pr_qty) > 0);
			const go = () => {
				dialog.hide();
				ub_pr_map(frm, picked);
			};
			if (!drafts.length) return go();

			const body = drafts
				.map((d) => {
					const links = (d.draft_pr_details || "")
						.split("|")
						.filter(Boolean)
						.map((e) => {
							const [name, qty] = e.split(":");
							return `<a href="/app/purchase-receipt/${encodeURIComponent(name)}" target="_blank">${frappe.utils.escape_html(name)}</a> (${flt(qty)})`;
						})
						.join(", ");
					return `<tr><td>${frappe.utils.escape_html(d.purchase_order)}</td><td>${frappe.utils.escape_html(d.item_code)}</td>
						<td class="text-right">${flt(d.pending_qty)}</td><td class="text-right">${flt(d.draft_pr_qty)}</td><td>${links}</td></tr>`;
				})
				.join("");
			frappe.confirm(
				`<p class="text-danger">${__("These lines are already on draft Purchase Receipts. Receiving them again may double receive.")}</p>
				<table class="table table-bordered table-condensed"><thead><tr><th>${__("Purchase Order")}</th><th>${__("Item")}</th>
				<th class="text-right">${__("Pending")}</th><th class="text-right">${__("Draft Qty")}</th><th>${__("Draft Receipts")}</th></tr></thead>
				<tbody>${body}</tbody></table><p>${__("Continue anyway?")}</p>`,
				go
			);
		},
	});
	dialog.show();
	setTimeout(() => {
		const wrapper = dialog.fields_dict.lines.$wrapper.get(0);
		table = new frappe.DataTable(wrapper, {
			columns: [
				{ id: "purchase_order", name: __("Purchase Order"), editable: false },
				{ id: "item_code", name: __("Item"), editable: false },
				{ id: "item_name", name: __("Item Name"), editable: false },
				{ id: "pending_qty", name: __("Pending Qty"), editable: false },
				{ id: "draft_pr_qty", name: __("On Draft Receipts"), editable: false },
				{ id: "uom", name: __("UOM"), editable: false },
				{ id: "rate", name: __("Rate"), editable: false },
				{ id: "schedule_date", name: __("Required By"), editable: false },
			],
			data: rows,
			layout: "fluid",
			inlineFilters: true,
			serialNoColumn: false,
			checkboxColumn: true,
			noDataMessage: __("No Data"),
		});
		$(wrapper).find(".dt-scrollable").css("max-height", "360px");
	}, 300);
}

function ub_pr_map(frm, picked) {
	const purchase_orders = [...new Set(picked.map((d) => d.purchase_order))];
	const qty = {};
	picked.forEach((d) => (qty[d.name] = d.pending_qty));
	if (frm.doc.items && frm.doc.items.length && !frm.doc.items[0].item_code) {
		frm.doc.items.splice(0, 1);
	}
	frm.__ub_mapping = true;
	frappe.call({
		type: "POST",
		method: "frappe.model.mapper.map_docs",
		args: {
			method: `${UB_PR_API}.make_purchase_receipt`,
			source_names: purchase_orders,
			target_doc: frm.doc,
			args: { filtered_children: picked.map((d) => d.name), filtered_children_qty: qty },
		},
		freeze: true,
		callback(r) {
			frm.__ub_mapping = false;
			if (r.exc || !r.message) return;
			frappe.model.sync(r.message);
			frm.dirty();
			frm.refresh();
			ub_pr_show_shortage(frm);
		},
		error() {
			frm.__ub_mapping = false;
		},
	});
}

function ub_pr_show_shortage(frm) {
	const items = (frm.doc.items || []).filter((d) => d.item_code).map((d) => ({ item_code: d.item_code }));
	if (!items.length) return;
	frappe.call({
		method: `${UB_PR_API}.get_manufacturing_shortage_for_pr`,
		args: { items, company: frm.doc.company },
		callback(r) {
			if (r.message && r.message.has_shortage) {
				frappe.msgprint({ title: __("Manufacturing Shortage"), message: r.message.message, indicator: "orange" });
			}
		},
	});
}

function ub_pr_create_batches(frm) {
	if (frm.is_dirty()) {
		frappe.msgprint(__("Save the Purchase Receipt first."));
		return;
	}
	frappe.call({
		method: `${UB_PR_API}.create_batches`,
		args: { purchase_receipt: frm.doc.name },
		freeze: true,
		freeze_message: __("Creating batches..."),
		callback(r) {
			const n = (r.message && r.message.groups) || 0;
			frappe.show_alert({
				message: n ? __("{0} batch group(s) created", [n]) : __("Nothing to create"),
				indicator: n ? "green" : "blue",
			});
			frm.reload_doc();
		},
	});
}

function ub_pr_make_inspections(frm) {
	if (frm.is_dirty()) {
		frappe.msgprint(__("Save the Purchase Receipt first."));
		return;
	}
	frappe.call({
		method: `${UB_PR_API}.make_quality_inspections`,
		args: { purchase_receipt: frm.doc.name },
		freeze: true,
		callback(r) {
			const names = r.message || [];
			if (!names.length) {
				frappe.msgprint(__("No inspection needed or all inspections already exist."));
			} else if (names.length === 1) {
				frappe.set_route("Form", "Quality Inspection", names[0]);
			} else {
				frappe.route_options = { reference_type: frm.doctype, reference_name: frm.doc.name };
				frappe.set_route("List", "Quality Inspection");
			}
		},
	});
}

function ub_pr_check_iqc(frm) {
	frappe.call({
		method: `${UB_PR_API}.check_iqc`,
		args: { purchase_receipt: frm.doc.name },
		callback(r) {
			const pending = r.message || [];
			if (!pending.length) {
				frappe.show_alert({ message: __("IQC complete"), indicator: "green" });
			} else {
				frappe.msgprint({
					title: __("IQC Pending"),
					indicator: "orange",
					message: pending.map((d) => `#${d.idx} ${frappe.utils.escape_html(d.item_code)} ${d.batch_no || ""}`).join("<br>"),
				});
			}
			frm.reload_doc();
		},
	});
}

function ub_pr_edit_invoice_no(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Edit Supplier Invoice No"),
		fields: [
			{ fieldname: "old", fieldtype: "Data", label: __("Current"), read_only: 1, default: frm.doc.ub_supplier_invoice_no },
			{ fieldname: "supplier_invoice_no", fieldtype: "Data", label: __("New Supplier Invoice No"), reqd: 1 },
			{
				fieldname: "supplier_invoice_date",
				fieldtype: "Date",
				label: __("Supplier Invoice Date"),
				default: frm.doc.ub_supplier_invoice_date,
			},
		],
		primary_action_label: __("Update"),
		primary_action(values) {
			frappe.call({
				method: `${UB_PR_API}.update_supplier_invoice_no`,
				args: {
					purchase_receipt: frm.doc.name,
					supplier_invoice_no: values.supplier_invoice_no,
					supplier_invoice_date: values.supplier_invoice_date,
				},
				callback() {
					d.hide();
					frm.reload_doc();
				},
			});
		},
	});
	d.show();
}
