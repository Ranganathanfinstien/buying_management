frappe.ready(function () {
	const TABLE = "audit_self_assessment";
	const HIDE = ["company_rating", "audit_finding_category", "observation", "non_conformance", "answer", "min_score"];

	function tune_grid() {
		const field = frappe.web_form.fields_dict[TABLE];
		if (!field || !field.grid) return;
		HIDE.forEach((f) => field.grid.update_docfield_property(f, "hidden", 1));
		field.grid.update_docfield_property("supplier_self_rating", "read_only", 0);
		field.grid.cannot_add_rows = true;
		field.grid.wrapper.find(".grid-add-row, .grid-remove-rows, .grid-remove-all-rows").hide();
	}
	tune_grid();

	["pan", "gstin", "ifsc_code"].forEach((f) => {
		frappe.web_form.on(f, (field, value) => {
			const v = (value || "").trim().toUpperCase();
			if (v !== (value || "")) frappe.web_form.set_value(f, v);
		});
	});

	frappe.web_form.on("supplier_audit_type", (field, value) => {
		frappe.web_form.doc[TABLE] = [];
		if (!value) {
			frappe.web_form.fields_dict[TABLE].refresh();
			return;
		}
		frappe.call({
			method: "universal_buying.ub_supplier.api.get_audit_questions",
			args: { supplier_audit_type: value },
			callback: (r) => {
				(r.message || []).forEach((q, i) => {
					frappe.web_form.doc[TABLE].push({
						doctype: "Supplier Audit Log Detail",
						idx: i + 1,
						group: q.group,
						question: q.question,
						option_list: JSON.stringify(q.options),
						max_score: q.max_score,
						min_score: q.min_score,
						supplier_self_rating: 0,
					});
				});
				frappe.web_form.fields_dict[TABLE].refresh();
				tune_grid();
			},
		});
	});

	frappe.web_form.validate = () => {
		const pan = frappe.web_form.get_value("pan");
		const gstin = frappe.web_form.get_value("gstin");
		if (pan && !/^[A-Z]{5}[0-9]{4}[A-Z]$/.test(pan)) {
			frappe.msgprint(__("Invalid PAN. Example: ABCDE1234F"));
			return false;
		}
		if (gstin && pan && gstin.substring(2, 12) !== pan) {
			frappe.msgprint(__("GSTIN does not match PAN"));
			return false;
		}
		return true;
	};
});
