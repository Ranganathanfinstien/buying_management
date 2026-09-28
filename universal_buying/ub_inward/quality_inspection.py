"""Quality Inspection rules for incoming inspections (BRD v2 6.24).

Doc events (hooks_contrib.py): validate, before_submit, on_submit, on_cancel.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, nowdate

from universal_buying.ub_inward.utils import get_rejected_warehouse, green_card_skips_iqc
from universal_buying.universal_buying.settings import get_setting
from universal_buying.universal_buying.utils import as_system_user

PR = "Purchase Receipt"


def _is_receipt_qi(doc):
	return doc.get("reference_type") == PR and doc.get("reference_name")


def matching_receipt_rows(pr, qi):
	"""Receipt rows an inspection covers: the child row, else same item (+ batch when the QI has one)."""
	rows = [r for r in pr.get("items") if r.item_code == qi.item_code]
	if qi.get("child_row_reference") and not qi.get("batch_no"):
		exact = [r for r in rows if r.name == qi.child_row_reference]
		if exact:
			return exact
	if qi.get("batch_no"):
		rows = [r for r in rows if r.get("batch_no") == qi.batch_no]
	return rows


def lot_qty(rows):
	"""Received quantity of the rows in stock UOM."""
	total = 0.0
	for r in rows:
		received = flt(r.get("received_qty")) or (flt(r.get("qty")) + flt(r.get("rejected_qty")))
		total += received * flt(r.get("conversion_factor") or 1)
	return total


# ---------------------------------------------------------------------------
# sampling band
# ---------------------------------------------------------------------------


def sample_size_for(template, qty):
	"""Sample size from the template's sampling bands (None when the template has no bands)."""
	if not template or not frappe.get_meta("Quality Inspection Template").has_field("ub_sampling_bands"):
		return None
	bands = frappe.get_all(
		"UB QI Sampling Band",
		filters={"parent": template, "parenttype": "Quality Inspection Template"},
		fields=["qty_from", "qty_to", "sample_qty"],
		order_by="qty_from asc",
	)
	return pick_band(bands, qty, template)


def pick_band(bands, qty, template=None):
	if not bands:
		return None
	qty = flt(qty)
	if qty < 1:
		return 1
	for band in bands:
		if qty >= flt(band.qty_from) and (not flt(band.qty_to) or qty <= flt(band.qty_to)):
			return min(flt(band.sample_qty), qty)
	frappe.throw(
		_("No sampling band in template {0} covers a lot of {1}.").format(frappe.bold(template or ""), qty),
		title=_("Sampling Plan"),
	)


def _template_of(doc):
	return doc.get("quality_inspection_template") or frappe.get_cached_value(
		"Item", doc.item_code, "quality_inspection_template"
	)


# ---------------------------------------------------------------------------
# approved MPN (V-24.1)
# ---------------------------------------------------------------------------


def get_approved_mpns(item_code):
	"""Enabled Item Manufacturer rows of the item (and its template)."""
	items = [item_code]
	template = frappe.get_cached_value("Item", item_code, "variant_of")
	if template:
		items.append(template)
	filters = {"item_code": ("in", items)}
	if frappe.get_meta("Item Manufacturer").has_field("ub_disabled"):
		filters["ub_disabled"] = 0
	return frappe.get_all(
		"Item Manufacturer", filters=filters, fields=["manufacturer", "manufacturer_part_no"]
	)


def validate_received_mpn(doc, approved=None, on_submit=False):
	if cint(doc.get("ub_alternate_mpn")):
		return
	mpn = (doc.get("ub_received_manufacturer_part_no") or "").strip()
	manufacturer = (doc.get("ub_received_manufacturer") or "").strip()
	if approved is None:
		approved = get_approved_mpns(doc.item_code)

	if not mpn and not manufacturer:
		if on_submit and approved:
			frappe.throw(
				_("Received Manufacturer Part No is required, or tick Alternate MPN."),
				title=_("Received MPN"),
			)
		return

	if not approved:
		frappe.throw(
			_("Item {0} has no approved Item Manufacturer. Tick Alternate MPN to continue.").format(
				frappe.bold(doc.item_code)
			),
			title=_("Unapproved MPN"),
		)

	if mpn:
		matches = [a for a in approved if (a.manufacturer_part_no or "").strip() == mpn]
		if not matches:
			frappe.throw(
				_(
					"Received MPN {0} is not an approved Item Manufacturer of {1}. Tick Alternate MPN to accept it."
				).format(frappe.bold(mpn), frappe.bold(doc.item_code)),
				title=_("Unapproved MPN"),
			)
		if manufacturer and manufacturer not in {a.manufacturer for a in matches}:
			frappe.throw(
				_("Received Manufacturer {0} does not match MPN {1}.").format(
					frappe.bold(manufacturer), frappe.bold(mpn)
				),
				title=_("Unapproved MPN"),
			)
		if not manufacturer and len({a.manufacturer for a in matches}) == 1:
			doc.ub_received_manufacturer = matches[0].manufacturer
	elif manufacturer:
		matches = [a for a in approved if a.manufacturer == manufacturer]
		if not matches:
			frappe.throw(
				_("Manufacturer {0} is not approved for {1}.").format(
					frappe.bold(manufacturer), frappe.bold(doc.item_code)
				),
				title=_("Unapproved MPN"),
			)
		if len(matches) == 1:
			doc.ub_received_manufacturer_part_no = matches[0].manufacturer_part_no


# ---------------------------------------------------------------------------
# doc events
# ---------------------------------------------------------------------------


def validate(doc, method=None):
	_check_template_active(doc)
	if doc.get("inspection_type") != "Incoming":
		return
	validate_received_mpn(doc)
	if not _is_receipt_qi(doc) or doc.docstatus != 0:
		return

	pr = frappe.get_doc(PR, doc.reference_name)
	qty = lot_qty(matching_receipt_rows(pr, doc))
	doc.ub_batch_qty = qty
	band = sample_size_for(_template_of(doc), qty)
	if band is not None and (doc.is_new() or flt(doc.sample_size) < band):
		doc.sample_size = band


def _check_template_active(doc):
	template = doc.get("quality_inspection_template")
	if not template:
		return
	meta = frappe.get_meta("Quality Inspection Template")
	if meta.has_field("disabled") and cint(
		frappe.db.get_value("Quality Inspection Template", template, "disabled")
	):
		frappe.throw(_("Quality Inspection Template {0} is disabled.").format(frappe.bold(template)))
	if meta.has_field("is_active") and not cint(
		frappe.db.get_value("Quality Inspection Template", template, "is_active")
	):
		frappe.throw(_("Quality Inspection Template {0} is not active.").format(frappe.bold(template)))


def _receipt_green_card(doc):
	if not _is_receipt_qi(doc):
		return False
	fields = ["supplier", "company"]
	if frappe.get_meta(PR).has_field("ub_green_card"):
		fields.append("ub_green_card")
	pr = frappe.db.get_value(PR, doc.reference_name, fields, as_dict=True)
	return bool(pr) and green_card_skips_iqc(pr)


def check_sample_complete(doc):
	"""V-24.2: sample taken must reach the sample size (green card suppliers exempt when allowed)."""
	if doc.get("inspection_type") != "Incoming" or _receipt_green_card(doc):
		return
	if flt(doc.get("ub_sample_taken")) < flt(doc.sample_size):
		frappe.throw(
			_("Sample taken ({0}) is less than the sample size ({1}). Complete the inspection first.").format(
				flt(doc.get("ub_sample_taken")), flt(doc.sample_size)
			),
			title=_("Inspection Incomplete"),
		)


def before_submit(doc, method=None):
	if doc.get("inspection_type") != "Incoming":
		return
	check_sample_complete(doc)
	validate_received_mpn(doc, on_submit=True)
	if _is_receipt_qi(doc):
		pr = frappe.get_doc(PR, doc.reference_name)
		doc.ub_batch_qty = lot_qty(matching_receipt_rows(pr, doc))


def on_submit(doc, method=None):
	if not _is_receipt_qi(doc) or doc.status != "Rejected":
		return
	pr = frappe.get_doc(PR, doc.reference_name)
	rows = route_rejection_to_receipt(doc, pr)
	create_non_conformance(doc, pr, rows)


def on_cancel(doc, method=None):
	"""Undo the rejection routing while the receipt is still a draft."""
	if not _is_receipt_qi(doc) or doc.status != "Rejected":
		return
	pr = frappe.get_doc(PR, doc.reference_name)
	if pr.docstatus != 0:
		return
	rejected_wh = get_rejected_warehouse(pr.company, throw=False)
	changed = False
	for row in matching_receipt_rows(pr, doc):
		if flt(row.rejected_qty) and not flt(row.qty) and row.rejected_warehouse == rejected_wh:
			row.qty = row.rejected_qty
			row.rejected_qty = 0
			row.rejected_warehouse = None
			if row.get("rejected_serial_and_batch_bundle") and not row.get("serial_and_batch_bundle"):
				row.serial_and_batch_bundle = row.rejected_serial_and_batch_bundle
				row.rejected_serial_and_batch_bundle = None
				bundle = frappe.get_doc("Serial and Batch Bundle", row.serial_and_batch_bundle)
				_move_bundle(bundle, row.warehouse, rejected=False)
			changed = True
	if changed:
		pr.flags.ignore_permissions = True
		with as_system_user():  # the inspector has no accounting rights (see route_rejection_to_receipt)
			pr.save()


# ---------------------------------------------------------------------------
# A-24.1 rejection -> rejected warehouse
# ---------------------------------------------------------------------------


def _move_bundle(bundle, warehouse, rejected):
	bundle.warehouse = warehouse
	bundle.is_rejected = 1 if rejected else 0
	for entry in bundle.get("entries"):
		entry.warehouse = warehouse
	bundle.flags.ignore_permissions = True
	bundle.save()


def route_rejection_to_receipt(qi, pr):
	"""Move the whole received qty of the covered rows of a draft receipt to the rejected warehouse."""
	rows = matching_receipt_rows(pr, qi)
	if pr.docstatus != 0:
		frappe.msgprint(
			_(
				"Purchase Receipt {0} is already submitted. Handle the rejected stock through the Item Non Conformance."
			).format(pr.name),
			indicator="orange",
		)
		return rows
	if not rows:
		return rows

	rejected_wh = get_rejected_warehouse(pr.company)
	for row in rows:
		total = flt(row.received_qty) or (flt(row.qty) + flt(row.rejected_qty))
		row.received_qty = total
		row.rejected_qty = total
		row.qty = 0
		row.rejected_warehouse = rejected_wh

		bundle_name = row.get("serial_and_batch_bundle")
		if not bundle_name:
			continue
		bundle = frappe.get_doc("Serial and Batch Bundle", bundle_name)
		if bundle.docstatus != 0:
			continue
		if not bundle.has_serial_no and bundle.has_batch_no:
			# batch only: drop the draft bundle and let ERPNext rebuild it for the rejected qty on submit
			batches = {e.batch_no for e in bundle.get("entries") if e.batch_no}
			row.serial_and_batch_bundle = None
			if len(batches) == 1:
				row.batch_no = batches.pop()
				row.use_serial_batch_fields = 1
				frappe.delete_doc("Serial and Batch Bundle", bundle_name, ignore_permissions=True, force=True)
			else:
				row.rejected_serial_and_batch_bundle = bundle_name
				_move_bundle(bundle, rejected_wh, rejected=True)
		else:
			row.serial_and_batch_bundle = None
			row.rejected_serial_and_batch_bundle = bundle_name
			_move_bundle(bundle, rejected_wh, rejected=True)

	pr.flags.ignore_permissions = True
	# the inspector (Quality roles) has no Account read; ERPNext v16 checks it in get_party_account on save
	with as_system_user():
		pr.save()
	return rows


def create_non_conformance(qi, pr, rows):
	"""A-24.1: open an Item Non Conformance for the rejected lot (when enabled)."""
	if not cint(get_setting("auto_create_inc", company=pr.company, default=1)):
		return None
	if not rows:
		return None
	existing = frappe.db.get_value(
		"Item Non Conformance", {"quality_inspection": qi.name, "docstatus": ("<", 2)}, "name"
	)
	if existing:
		return existing

	first = rows[0]
	conversion = flt(first.get("conversion_factor") or 1)
	rejected = sum(flt(r.rejected_qty) * flt(r.get("conversion_factor") or 1) for r in rows)
	warehouse = first.get("rejected_warehouse")
	if not rejected:  # receipt already submitted with accepted stock
		rejected = sum(flt(r.get("stock_qty")) for r in rows)
		warehouse = first.get("warehouse")
	if flt(rejected) <= 0:
		return None
	rate = flt(first.get("base_net_rate") or first.get("base_rate")) / (conversion or 1)

	inc = frappe.get_doc(
		{
			"doctype": "Item Non Conformance",
			"company": pr.company,
			"date": nowdate(),
			"inspection_type": "Incoming",
			"reference_type": PR,
			"reference_name": pr.name,
			"quality_inspection": qi.name,
			"supplier": pr.supplier,
			"supplier_invoice_no": pr.get("ub_supplier_invoice_no"),
			"project": first.get("project") or pr.get("project"),
			"item_code": qi.item_code,
			"batch_no": qi.get("batch_no") or first.get("batch_no"),
			"purchase_receipt_item": first.name,
			"rejected_qty": rejected,
			"rate": rate,
			"amount": rate * rejected,
			"rejected_warehouse": warehouse,
			"remarks": qi.get("remarks"),
		}
	)
	inc.flags.ignore_permissions = True
	inc.flags.ignore_mandatory = True
	inc.insert()
	qi.db_set("ub_item_non_conformance", inc.name, update_modified=False)
	frappe.msgprint(
		_("Item Non Conformance {0} created.").format(frappe.utils.get_link_to_form(inc.doctype, inc.name)),
		alert=True,
		indicator="orange",
	)
	return inc.name


# ---------------------------------------------------------------------------
# create inspections grouped by item + batch
# ---------------------------------------------------------------------------


def make_inspections_for_receipt(pr):
	"""One draft QI per (item, batch) for inspection-required rows without an inspection."""
	from universal_buying.ub_inward.utils import item_needs_inspection

	groups = {}
	for row in pr.get("items"):
		if not row.item_code or row.get("quality_inspection") or not item_needs_inspection(row.item_code):
			continue
		key = (row.item_code, row.get("batch_no") or "")
		groups.setdefault(key, []).append(row)

	existing = {
		(q.item_code, q.batch_no or "")
		for q in frappe.get_all(
			"Quality Inspection",
			filters={"reference_type": PR, "reference_name": pr.name, "docstatus": ("<", 2)},
			fields=["item_code", "batch_no"],
		)
	}

	created = []
	for (item_code, batch_no), rows in groups.items():
		if (item_code, batch_no) in existing:
			continue
		qi = frappe.get_doc(
			{
				"doctype": "Quality Inspection",
				"inspection_type": "Incoming",
				"inspected_by": frappe.session.user,
				"reference_type": PR,
				"reference_name": pr.name,
				"item_code": item_code,
				"batch_no": batch_no or None,
				"child_row_reference": rows[0].name if not batch_no else None,
				"company": pr.company,
				"description": rows[0].get("description"),
				"sample_size": 1,
				"manual_inspection": 1,
			}
		)
		qi.insert()
		created.append(qi.name)
	return created
