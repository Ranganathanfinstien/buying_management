// UB Finance – Purchase Invoice form (BRD v2 6.27)
// - "Get Items by Supplier Invoice No": all unbilled receipt rows carrying the Bill No.
// - "Exchange Rate from Receipt (BoE)": conversion rate of the receipt with the same Bill of Entry.

frappe.ui.form.on("Purchase Invoice", {
	refresh(frm) {
		if (frm.doc.docstatus !== 0 || frm.doc.is_return) return;

		frm.add_custom_button(
			__("Receipts by Supplier Invoice No"),
			() => ub_fetch_rows_by_bill_no(frm),
			__("Get Items From")
		);

		if (frm.doc.ub_boe_no) {
			frm.add_custom_button(__("Exchange Rate from Receipt (BoE)"), () => ub_fetch_boe_rate(frm), __("Actions"));
		}
	},

	ub_boe_no(frm) {
		const company_currency = frm.doc.company ? erpnext.get_currency(frm.doc.company) : null;
		if (frm.doc.ub_boe_no && frm.doc.currency && company_currency && frm.doc.currency !== company_currency) {
			ub_fetch_boe_rate(frm);
		}
		frm.refresh();
	},
});

function ub_fetch_rows_by_bill_no(frm) {
	if (!frm.doc.company || !frm.doc.supplier) {
		frappe.msgprint(__("Select Company and Supplier first."));
		return;
	}
	const run = (bill_no) =>
		frappe.call({
			method: "universal_buying.ub_finance.api.get_items_by_supplier_invoice",
			args: { target_doc: frm.doc, supplier_invoice_no: bill_no },
			freeze: true,
			freeze_message: __("Fetching receipt rows ..."),
			callback(r) {
				if (!r.exc && r.message) {
					frappe.model.sync(r.message);
					frm.dirty();
					frm.refresh();
				}
			},
		});

	if (frm.doc.bill_no) {
		run(frm.doc.bill_no);
		return;
	}
	frappe.prompt(
		{ fieldname: "bill_no", fieldtype: "Data", label: __("Supplier Invoice No"), reqd: 1 },
		(v) => run(v.bill_no),
		__("Get Items by Supplier Invoice No")
	);
}

function ub_fetch_boe_rate(frm) {
	if (!frm.doc.ub_boe_no) {
		frappe.msgprint(__("Enter the Bill of Entry No first."));
		return;
	}
	frappe.call({
		method: "universal_buying.ub_finance.api.get_receipt_exchange_rate",
		args: { boe_no: frm.doc.ub_boe_no, company: frm.doc.company, supplier: frm.doc.supplier },
		freeze: true,
		freeze_message: __("Fetching exchange rate from Purchase Receipt ..."),
		callback(r) {
			const m = r.message || {};
			if (m.status === "success") {
				frm.set_value("conversion_rate", m.conversion_rate);
				if (m.boe_date && !frm.doc.ub_boe_date) frm.set_value("ub_boe_date", m.boe_date);
				frappe.show_alert({
					message: __("Exchange rate {0} taken from {1}", [m.conversion_rate, m.purchase_receipt]),
					indicator: "green",
				});
			} else if (m.message) {
				frappe.msgprint(m.message);
			}
		},
	});
}
