"""IQC gate for Purchase Receipts (BRD v2 V-23.5, BR-17).

Fix from the source design: the earlier ``validate_iqc_complete`` only threw when ``method == "Submit"``, which a
doc event never receives, so the block never fired. Here the gate is evaluated inside the receipt
controller on every save (informational) and on submit (enforced by the ``iqc_gate`` Off / Warn / Block
setting).

A row is covered when a submitted Quality Inspection exists for it:
- linked on the row (``quality_inspection``), or
- any submitted QI of this receipt for the same item and batch, or whose ``child_row_reference`` is the row, or
- (sibling rule) another row of the same item and manufacturer batch number is covered.
"""

import frappe
from frappe import _

from universal_buying.ub_inward.utils import bonded_route_active, green_card_skips_iqc, item_needs_inspection
from universal_buying.universal_buying.settings import apply_mode, get_setting


def iqc_exempt(doc):
	"""Whole receipt is exempt: return, bonded route, or green card supplier when allowed."""
	if doc.get("is_return"):
		return True
	if bonded_route_active(doc):
		return True
	return green_card_skips_iqc(doc)


def _receipt_inspections(doc):
	if not doc.name or doc.is_new():
		return []
	return frappe.get_all(
		"Quality Inspection",
		filters={"reference_type": doc.doctype, "reference_name": doc.name, "docstatus": 1},
		fields=["name", "item_code", "batch_no", "child_row_reference", "status"],
	)


def get_rows_pending_iqc(doc, inspections=None):
	"""Rows that need an inspection and have no submitted one."""
	rows = [r for r in doc.get("items") if r.get("item_code") and item_needs_inspection(r.item_code)]
	if not rows:
		return []

	if inspections is None:
		inspections = _receipt_inspections(doc)
	submitted_names = {qi.name for qi in inspections}
	linked = [r.quality_inspection for r in rows if r.get("quality_inspection")]
	if linked:
		submitted_names |= set(
			frappe.get_all(
				"Quality Inspection", filters={"name": ("in", linked), "docstatus": 1}, pluck="name"
			)
		)

	def covered(row):
		if row.get("quality_inspection") and row.quality_inspection in submitted_names:
			return True
		for qi in inspections:
			if qi.item_code != row.item_code:
				continue
			if qi.child_row_reference and qi.child_row_reference == row.name:
				return True
			if qi.batch_no and row.get("batch_no") and qi.batch_no == row.batch_no:
				return True
		return False

	covered_keys = set()
	pending = []
	for row in rows:
		if covered(row):
			if row.get("ub_manufacturer_batch_no"):
				covered_keys.add((row.item_code, row.ub_manufacturer_batch_no.strip()))
		else:
			pending.append(row)

	return [
		row
		for row in pending
		if not (
			row.get("ub_manufacturer_batch_no")
			and (row.item_code, row.ub_manufacturer_batch_no.strip()) in covered_keys
		)
	]


def check_iqc_gate(doc, submitting=False):
	"""Evaluate the gate, set ``ub_iqc_complete`` and enforce on submit. Returns the pending rows."""
	if iqc_exempt(doc):
		doc.ub_iqc_complete = 1
		return []

	mode = get_setting("iqc_gate", company=doc.get("company")) or "Block"
	pending = get_rows_pending_iqc(doc)
	doc.ub_iqc_complete = 0 if pending else 1
	if not pending or mode == "Off":
		return pending

	message = _("Submitted Quality Inspection missing for: {0}").format(
		", ".join(f"#{r.idx} {frappe.bold(r.item_code)}" for r in pending)
	)
	if submitting:
		apply_mode(mode, message, title=_("IQC Pending"))
	elif not frappe.flags.in_import:
		frappe.msgprint(message, title=_("IQC Pending"), indicator="blue", alert=True)
	return pending
