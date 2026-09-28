"""Batch handling for Purchase Receipts (BRD v2 6.23 step 4, V-23.3, V-23.4, A-23.2).

Batches are created as plain Batch records and written to the receipt row as ``batch_no`` with
``use_serial_batch_fields = 1``. ERPNext v16 then builds the Serial and Batch Bundles itself on submit
(``StockController.make_bundle_using_old_serial_batch_fields``), including the rejected-qty bundle, so
no draft bundles have to be created or kept in sync here.
"""

from collections import OrderedDict

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from universal_buying.ub_inward.utils import (
	is_batch_exempt,
	item_built_type,
	item_has_batch,
	row_item_code,
)
from universal_buying.universal_buying.settings import get_setting

# ---------------------------------------------------------------------------
# Shelf life (V-23.4)
# ---------------------------------------------------------------------------


def remaining_shelf_life_percent(manufacturing_date, posting_date, shelf_life_in_days):
	"""Pure helper: remaining shelf life in % (None when the item has no shelf life)."""
	shelf_life_in_days = flt(shelf_life_in_days)
	if shelf_life_in_days <= 0 or not manufacturing_date:
		return None
	age = max((getdate(posting_date or nowdate()) - getdate(manufacturing_date)).days, 0)
	remaining = max(shelf_life_in_days - age, 0)
	return remaining / shelf_life_in_days * 100.0


def validate_remaining_shelf_life(row, posting_date, company=None, shelf_life_in_days=None):
	"""Throw when a row's remaining shelf life is below min_remaining_shelf_life_percent."""
	manufacturing_date = row.get("ub_manufacturing_date")
	if not manufacturing_date:
		return None

	if getdate(manufacturing_date) > getdate(posting_date or nowdate()):
		frappe.throw(
			_("Row #{0}: Manufacturing Date {1} cannot be after the posting date.").format(
				row.get("idx"), frappe.format(manufacturing_date, "Date")
			)
		)

	min_percent = flt(get_setting("min_remaining_shelf_life_percent", company=company))
	if min_percent <= 0:
		return None

	if shelf_life_in_days is None:
		shelf_life_in_days = frappe.get_cached_value("Item", row_item_code(row), "shelf_life_in_days")

	percent = remaining_shelf_life_percent(manufacturing_date, posting_date, shelf_life_in_days)
	if percent is None:
		return None

	if percent < min_percent:
		remaining_days = flt(shelf_life_in_days) * percent / 100.0
		frappe.throw(
			_(
				"Row #{0}: Item {1} has only {2}% shelf life left ({3} of {4} days). Minimum required is {5}%."
			).format(
				row.get("idx"),
				frappe.bold(row_item_code(row)),
				flt(percent, 2),
				round(remaining_days),
				int(flt(shelf_life_in_days)),
				flt(min_percent, 2),
			),
			title=_("Shelf Life Too Short"),
		)
	return percent


# ---------------------------------------------------------------------------
# Create Batches button (step 4)
# ---------------------------------------------------------------------------


def _row_needs_batch(row):
	if row.get("batch_no") or row.get("serial_and_batch_bundle"):
		return False
	item_code = row_item_code(row)
	return bool(item_code and item_has_batch(item_code))


def _new_batch(pr, item_code, batch_id, first_row=None, system=False):
	"""Create a Batch linked to the receipt (reference_doctype/name), collision safe."""
	base, counter = batch_id, 1
	while frappe.db.exists("Batch", batch_id):
		existing_item = frappe.db.get_value("Batch", batch_id, "item")
		if existing_item == item_code and frappe.db.get_value("Batch", batch_id, "reference_name") == pr.name:
			return batch_id
		batch_id = f"{base}-{counter}"
		counter += 1

	batch = frappe.new_doc("Batch")
	batch.batch_id = batch_id
	batch.item = item_code
	batch.supplier = pr.get("supplier")
	batch.reference_doctype = pr.doctype
	batch.reference_name = pr.name
	if first_row is not None and not system:
		batch.manufacturing_date = first_row.get("ub_manufacturing_date")
		if batch.meta.has_field("ub_manufacturer_batch_no"):
			batch.ub_manufacturer_batch_no = first_row.get("ub_manufacturer_batch_no")
			batch.ub_manufacturer_part_no = first_row.get("manufacturer_part_no")
	batch.flags.ignore_permissions = True
	batch.insert()
	return batch.name


def _next_group_no(pr):
	used = set()
	prefix = f"{pr.name}-"
	for row in pr.get("items"):
		bn = row.get("batch_no") or ""
		if bn.startswith(prefix):
			tail = bn[len(prefix) :].split("-")[0]
			if tail.isdigit():
				used.add(int(tail))
	return (max(used) + 1) if used else 1


def create_batches_for_receipt(pr):
	"""Group rows by (item, manufacturing date, manufacturer batch) and give each group one Batch.

	Returns the number of groups processed. Rows that already have a batch or bundle are left alone.
	"""
	if pr.docstatus != 0:
		frappe.throw(_("Batches can only be created on a draft Purchase Receipt."))
	if pr.get("is_return"):
		frappe.throw(_("Batches are not created for returns."))

	groups = OrderedDict()
	shelf_cache = {}
	for row in pr.get("items"):
		if not _row_needs_batch(row):
			continue
		item_code = row_item_code(row)
		if is_batch_exempt(item_code):
			continue  # a system batch is assigned on submit

		if item_code not in shelf_cache:
			shelf_cache[item_code] = frappe.get_cached_value("Item", item_code, "shelf_life_in_days")
		validate_remaining_shelf_life(row, pr.posting_date, pr.company, shelf_cache[item_code])

		if (
			item_built_type(item_code).lower() != "custom"
			and not (row.get("manufacturer_part_no") or "").strip()
		):
			frappe.throw(
				_("Row #{0}: Manufacturer Part No is required for Standard item {1}.").format(
					row.idx, frappe.bold(item_code)
				),
				title=_("MPN Required"),
			)

		mfr_batch = (row.get("ub_manufacturer_batch_no") or "").strip()
		if not mfr_batch or not row.get("ub_manufacturing_date"):
			frappe.throw(
				_("Row #{0}: Manufacturer Batch No and Manufacturing Date are required for {1}.").format(
					row.idx, frappe.bold(item_code)
				)
			)
		key = (item_code, str(getdate(row.ub_manufacturing_date)), mfr_batch)
		groups.setdefault(key, []).append(row)

	if not groups:
		return 0

	# reuse a batch already assigned to a row with the same key
	existing = {}
	for row in pr.get("items"):
		if row.get("batch_no") and row.get("ub_manufacturer_batch_no") and row.get("ub_manufacturing_date"):
			key = (
				row_item_code(row),
				str(getdate(row.ub_manufacturing_date)),
				row.ub_manufacturer_batch_no.strip(),
			)
			existing.setdefault(key, row.batch_no)

	next_no = _next_group_no(pr)
	for key, rows in groups.items():
		batch_name = existing.get(key)
		if not batch_name:
			batch_name = _new_batch(pr, key[0], f"{pr.name}-{next_no}", rows[0])
			next_no += 1
			existing[key] = batch_name
		for row in rows:
			row.batch_no = batch_name
			row.use_serial_batch_fields = 1

	return len(groups)


def assign_system_batches(pr, rows):
	"""Batch for batch-tracked rows that need no manual batch (exempt groups, bonded route)."""
	count = 0
	for row in rows:
		if not _row_needs_batch(row):
			continue
		row.batch_no = _new_batch(pr, row_item_code(row), f"{pr.name}-S{row.idx}", system=True)
		row.use_serial_batch_fields = 1
		count += 1
	return count


# ---------------------------------------------------------------------------
# V-23.3 batch required
# ---------------------------------------------------------------------------


def rows_missing_batch(pr):
	"""(row, exempt) for batch-tracked rows without batch/bundle."""
	out = []
	for row in pr.get("items"):
		if not _row_needs_batch(row):
			continue
		out.append((row, is_batch_exempt(row_item_code(row))))
	return out


def validate_batches_before_submit(pr, assign=True, bonded=False):
	"""Block rows without a batch; exempt groups (and the bonded route) get a system batch instead."""
	missing = rows_missing_batch(pr)
	if not missing:
		return
	auto_rows = [row for row, exempt in missing if exempt or bonded]
	blocked = [row for row, exempt in missing if not (exempt or bonded)]
	if blocked:
		frappe.throw(
			_("Batch is required for: {0}. Use Create > Batches.").format(
				", ".join(f"#{r.idx} {r.item_code}" for r in blocked)
			),
			title=_("Batch Required"),
		)
	if assign and auto_rows:
		assign_system_batches(pr, auto_rows)


# ---------------------------------------------------------------------------
# A-23.2 draft delete
# ---------------------------------------------------------------------------


def _batch_used_elsewhere(batch_no, pr_name):
	if frappe.db.sql(
		"""select 1 from `tabPurchase Receipt Item` where batch_no = %s and parent != %s limit 1""",
		(batch_no, pr_name),
	):
		return True
	return bool(
		frappe.db.sql(
			"""select 1 from `tabSerial and Batch Entry` sbe
			inner join `tabSerial and Batch Bundle` sbb on sbb.name = sbe.parent
			where sbe.batch_no = %s and sbb.docstatus = 1 and sbb.is_cancelled = 0
				and sbb.voucher_no != %s
			limit 1""",
			(batch_no, pr_name),
		)
	)


def prepare_draft_delete(pr):
	"""Called from on_trash before ERPNext removes draft bundles and the batches referencing this receipt.

	Frees the row links so ERPNext can delete the empty batches, and detaches (keeps) any referenced batch
	that is already used by another document.
	"""
	if pr.docstatus != 0 or not pr.name:
		return
	frappe.db.sql(
		"""update `tabPurchase Receipt Item` set batch_no = null where parent = %s""",
		pr.name,
	)
	for batch in frappe.get_all(
		"Batch", filters={"reference_doctype": pr.doctype, "reference_name": pr.name}, pluck="name"
	):
		if _batch_used_elsewhere(batch, pr.name) or frappe.db.exists(
			"Quality Inspection", {"batch_no": batch, "docstatus": ("<", 2)}
		):
			frappe.db.set_value("Batch", batch, {"reference_doctype": None, "reference_name": None})
