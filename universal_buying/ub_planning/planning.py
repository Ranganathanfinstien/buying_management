"""Shortage-to-order planning shared by Auto PO Run, Auto PO Exception and the exception report.

Based on the earlier auto_po_run.py / shortage_engine.py. The earlier SQL is replaced by small Python
steps so every rule reads Buying Control Settings:

1. ``get_planning_lines``   - Shortage rows of the Requirement Log for purchase items, required date =
   delivery date minus ``planning_buffer_days`` (minus the line card lead time in lead-time mode), bucketed
   by ``planning_bucket`` (Month / Week / Exact Date), netted against open PO lines that the engine did
   not reserve - draft POs included, so a second run on the same day does not order the same quantity
   again (AC-11.2) - then enriched with supplier, price, MOQ, SPQ and ABC class.
2. ``classify_lines``       - No Supplier / No Price / MOQ Exception / eligible. The item's total shortage
   must reach MOQ x abc_threshold(class); an unknown class uses the default class (never dropped).
3. ``apply_spq_carry_forward`` / ``apply_moq_top_up`` - SPQ rounding with the surplus carried to later
   buckets, then a MOQ top-up on the last line. Suppliers with ``ub_moq_per_line`` round to MOQ per line.

Shortage rows in the Requirement Log are already net of engine PO reservations, so "subtract PO
reservations in the same bucket" (BRD 6.11 step 3) is implicit.
"""

import math
from collections import OrderedDict, defaultdict
from datetime import timedelta

import frappe
from frappe.utils import add_days, cint, flt, get_first_day, getdate, nowdate

from universal_buying.ub_planning import common
from universal_buying.ub_planning.api import get_current_item_price
from universal_buying.universal_buying.settings import abc_threshold, get_setting

EPS = 1e-9
NO_SUPPLIER = "No Supplier"
NO_PRICE = "No Price"
MOQ_EXCEPTION = "MOQ Exception"


# ----------------------------------------------------------------------------------------------- dates


def bucket_date(date, bucket):
	"""First day of the bucket that contains `date` (Month / Week (Monday) / Exact Date)."""
	date = getdate(date)
	if bucket == "Week":
		return date - timedelta(days=date.weekday())
	if bucket == "Exact Date":
		return date
	return get_first_day(date)


def ceil_to(qty, pack):
	"""Round qty up to a multiple of pack (float safe)."""
	pack = flt(pack) or 1.0
	if qty <= EPS:
		return 0.0
	return math.ceil(flt(qty / pack, 6) - 1e-9) * pack


# ----------------------------------------------------------------------------------------------- lines


def _get_shortage_rows(company, to_date, project, plan_by_project, lead_time_mode, item_codes=None):
	conditions = [
		"rl.company = %(company)s",
		"rl.reservation_type = 'Shortage'",
		"it.is_purchase_item = 1",
		"ifnull(it.disabled, 0) = 0",
	]
	params = {"company": company, "to_date": to_date}
	if plan_by_project and project:
		conditions.append("rl.project = %(project)s")
		params["project"] = project
	if not lead_time_mode:
		# lead-time mode filters on the order date after the lead time is known
		conditions.append("rl.delivery_date <= %(to_date)s")
	if item_codes:
		conditions.append("rl.item_code in %(item_codes)s")
		params["item_codes"] = tuple(item_codes)
	return frappe.db.sql(
		f"""select rl.item_code, rl.project, rl.delivery_date, sum(rl.qty) as qty
		from `tabRequirement Log` rl inner join `tabItem` it on it.name = rl.item_code
		where {" and ".join(conditions)}
		group by rl.item_code, rl.project, rl.delivery_date
		order by rl.item_code, rl.delivery_date""",
		params,
		as_dict=True,
	)


def get_unreserved_open_po(company, item_codes, project=None, plan_by_project=False):
	"""{(project_key, item_code): stock qty} of open PO lines not reserved by the engine.

	Draft POs (never reserved by the engine) count in full, so quantities already on draft POs of an
	earlier run are not ordered again. Submitted lines count for the part the engine did not reserve.
	"""
	if not item_codes:
		return {}
	conditions = [
		"po.company = %(company)s",
		"po.docstatus < 2",
		"po.status not in ('Closed', 'On Hold', 'Completed', 'Delivered')",
		"poi.qty > ifnull(poi.received_qty, 0)",
		"poi.item_code in %(items)s",
	]
	params = {"company": company, "items": tuple(item_codes)}
	if plan_by_project and project:
		conditions.append("poi.project = %(project)s")
		params["project"] = project
	rows = frappe.db.sql(
		f"""select poi.name, poi.item_code, poi.project,
			(poi.qty - ifnull(poi.received_qty, 0)) * ifnull(nullif(poi.conversion_factor, 0), 1) as pending
		from `tabPurchase Order Item` poi inner join `tabPurchase Order` po on po.name = poi.parent
		where {" and ".join(conditions)}""",
		params,
		as_dict=True,
	)
	if not rows:
		return {}
	reserved = dict(frappe.db.sql(
		"""select purchase_order_item, sum(qty) from `tabRequirement Log`
		where company = %s and reservation_type = 'Purchase Order' and purchase_order_item in %s
		group by purchase_order_item""",
		(company, tuple(r.name for r in rows)),
	))
	pool = defaultdict(float)
	for r in rows:
		free = flt(r.pending) - flt(reserved.get(r.name))
		if free > EPS:
			key = (r.project or None) if plan_by_project else None
			pool[(key, r.item_code)] += free
	return pool


def allocate_unreserved_po(lines, pool):
	"""Net lines (sorted by item, date) against the unreserved PO pool. Mutates `stock_qty`."""
	for line in lines:
		for key in ((line.project, line.item_code), (None, line.item_code)):
			free = pool.get(key, 0)
			if free <= EPS or line.stock_qty <= EPS:
				continue
			take = min(free, line.stock_qty)
			pool[key] = free - take
			line.stock_qty -= take


def get_planning_lines(company, to_date, project=None, lead_time_mode=False, item_codes=None):
	"""Bucketed, netted and enriched shortage lines (purchase UOM). See module docstring."""
	to_date = getdate(to_date)
	today = getdate(nowdate())
	buffer_days = cint(get_setting("planning_buffer_days", company=company))
	bucket = get_setting("planning_bucket", company=company) or "Month"
	plan_by_project = cint(get_setting("plan_by_project", company=company))

	raw = _get_shortage_rows(company, to_date, project, plan_by_project, lead_time_mode, item_codes)
	lead_times = {}
	grouped = OrderedDict()
	for r in raw:
		required_by = add_days(getdate(r.delivery_date), -buffer_days)
		plan_date = required_by
		if lead_time_mode:
			if r.item_code not in lead_times:
				lead_times[r.item_code] = common.get_min_lead_time(r.item_code, company)
			plan_date = add_days(required_by, -lead_times[r.item_code])
			if getdate(plan_date) > to_date:
				continue
		b = bucket_date(plan_date, bucket)
		project_key = (r.project or None) if plan_by_project else None
		key = (r.item_code, b, project_key)
		line = grouped.get(key)
		if not line:
			line = grouped[key] = frappe._dict(
				item_code=r.item_code, project=project_key, bucket=b, stock_qty=0.0,
				required_by=getdate(required_by), delivery_date=getdate(r.delivery_date),
			)
		line.stock_qty += flt(r.qty)
		line.required_by = min(line.required_by, getdate(required_by))
		line.delivery_date = min(line.delivery_date, getdate(r.delivery_date))

	lines = sorted(grouped.values(), key=lambda x: (x.item_code, x.bucket, x.project or ""))
	pool = get_unreserved_open_po(company, list({x.item_code for x in lines}), project, plan_by_project)
	allocate_unreserved_po(lines, pool)
	lines = [x for x in lines if x.stock_qty > EPS]

	item_cache = {}
	price_cache = {}
	for line in lines:
		info = item_cache.get(line.item_code)
		if info is None:
			info = item_cache[line.item_code] = get_item_planning_info(line.item_code, company, line.project)
		line.update(info)
		line.po_shortage = flt(line.stock_qty / (info.conversion_factor or 1.0), 6)
		# PO "Required By": bucket start or, in lead-time mode, the real required date
		line.schedule_date = max(line.required_by if lead_time_mode else line.bucket, today)
		line.required_by = max(line.required_by, today)
		line.rate = None
		line.item_price = None
		if info.supplier:
			price_key = (line.item_code, info.supplier, line.schedule_date)
			if price_key not in price_cache:
				price_cache[price_key] = get_current_item_price(line.item_code, info.supplier, company,
					line.schedule_date)
			price = price_cache[price_key]
			if price:
				line.rate = price_rate_for_uom(line.item_code, price, line.uom)
				line.currency = price["currency"]
				line.price_list = price["price_list"]
				line.item_price = price["name"]
				line.manufacturer = price.get("manufacturer") or info.manufacturer
				line.manufacturer_part_no = price.get("manufacturer_part_no") or info.manufacturer_part_no
	return lines


def price_rate_for_uom(item_code, price, uom):
	"""Item Price rate converted from the price row's UOM to `uom` (blank price UOM = same UOM)."""
	rate = flt(price.get("price_list_rate"))
	price_uom = price.get("uom")
	if not price_uom or not uom or price_uom == uom:
		return rate
	return rate * common.get_conversion_factor(item_code, uom) / (common.get_conversion_factor(item_code, price_uom) or 1.0)


def get_item_planning_info(item_code, company, project=None):
	item = frappe.get_cached_value("Item", item_code, ["item_name", "description"], as_dict=True) or {}
	supplier, card_row = common.resolve_supplier(item_code, company)
	uom = common.get_purchase_uom(item_code)
	return frappe._dict(
		item_name=item.get("item_name"),
		description=item.get("description"),
		uom=uom,
		conversion_factor=common.get_conversion_factor(item_code, uom),
		supplier=supplier,
		moq_per_line=common.supplier_moq_per_line(supplier),
		moq=common.get_moq(item_code, card_row),
		spq=common.get_spq(item_code, card_row),
		item_class=common.get_item_class(item_code, company, project),
		manufacturer=card_row.manufacturer if card_row else None,
		manufacturer_part_no=card_row.manufacturer_part_no if card_row else None,
		currency=None,
		price_list=None,
	)


# ----------------------------------------------------------------------------------------------- rules


def effective_class(item_class):
	cls = (item_class or "").upper()
	if cls not in ("A", "B", "C"):
		cls = (get_setting("abc_default_class") or "C").upper()
	return cls


def classify_lines(lines, threshold_fn=None):
	"""Split lines into (eligible_lines, exception_rows).

	exception_rows: one row per (item, exception type) with the total shortage.
	"""
	threshold_fn = threshold_fn or abc_threshold
	eligible, exceptions = [], []
	by_item = OrderedDict()
	for line in lines:
		by_item.setdefault(line.item_code, []).append(line)

	for item_code, item_lines in by_item.items():
		first = item_lines[0]
		if not first.supplier:
			exceptions.append(_exception_row(NO_SUPPLIER, item_lines))
			continue
		no_price = [x for x in item_lines if x.rate is None]
		priced = [x for x in item_lines if x.rate is not None]
		if no_price:
			exceptions.append(_exception_row(NO_PRICE, no_price))
		if not priced:
			continue
		total = sum(flt(x.po_shortage) for x in priced)
		cls = effective_class(first.item_class)
		if total + EPS >= flt(first.moq) * flt(threshold_fn(cls)):
			eligible.extend(priced)
		else:
			exceptions.append(_exception_row(MOQ_EXCEPTION, priced))
	return eligible, exceptions


def _exception_row(exception_type, item_lines):
	first = item_lines[0]
	return frappe._dict(
		exception_type=exception_type,
		item_code=first.item_code,
		item_name=first.get("item_name"),
		description=first.get("description"),
		project=first.get("project"),
		item_class=effective_class(first.get("item_class")),
		po_shortage=flt(sum(flt(x.po_shortage) for x in item_lines), 6),
		uom=first.get("uom"),
		required_by=min(x.get("required_by") or x.get("schedule_date") for x in item_lines),
		moq=first.get("moq"),
		spq=first.get("spq"),
		default_supplier=first.get("supplier"),
		rate=first.get("rate"),
		currency=first.get("currency"),
		manufacturer=first.get("manufacturer"),
		mpn=first.get("manufacturer_part_no"),
	)


def apply_spq_carry_forward(item_lines):
	"""SPQ rounding with the surplus carried forward to the item's later lines (sorted by date).

	Sets `qty` on each line and returns only the lines that still need ordering. With `moq_per_line`
	the pack is the MOQ and every line is at least one MOQ.
	"""
	result = []
	excess = 0.0
	for line in item_lines:
		pack = flt(line.moq) if line.get("moq_per_line") and flt(line.moq) > 0 else flt(line.spq) or 1.0
		need = flt(line.po_shortage) - excess
		if need <= EPS:
			excess = -need
			line.qty = 0.0
			continue
		qty = ceil_to(need, pack)
		excess = qty - need
		line.qty = qty
		result.append(line)
	return result


def apply_moq_top_up(item_lines):
	"""Top the item's total up to MOQ on the last line, rounded to SPQ. Safe on an empty list."""
	if not item_lines:
		return item_lines
	last = item_lines[-1]
	total = sum(flt(x.qty) for x in item_lines)
	moq = flt(last.moq)
	if moq > 0 and total + EPS < moq:
		pack = flt(last.moq) if last.get("moq_per_line") else flt(last.spq) or 1.0
		last.qty = ceil_to(flt(last.qty) + (moq - total), pack)
	return item_lines


def round_eligible(eligible):
	"""Apply carry-forward and MOQ per item. Returns the lines to order (qty > 0)."""
	by_item = OrderedDict()
	for line in eligible:
		by_item.setdefault(line.item_code, []).append(line)
	out = []
	for item_lines in by_item.values():
		item_lines.sort(key=lambda x: (x.bucket, x.project or ""))
		out.extend(apply_moq_top_up(apply_spq_carry_forward(item_lines)))
	return [x for x in out if flt(x.qty) > EPS]


# ----------------------------------------------------------------------------------------------- exceptions


def get_handled_items(company, project=None, exclude_doc=None):
	"""Items that must not be repeated on a new exception (AC-12.2 + anti-duplication).

	- a row with Follow-up, an Item Price Request or a Purchase Order on any non-cancelled exception;
	- any row on another exception that is still draft (still open, not yet reviewed).
	"""
	conditions = ["ape.company = %(company)s", "ape.docstatus < 2"]
	params = {"company": company, "exclude": exclude_doc or ""}
	if project:
		conditions.append("ifnull(ape.project, '') = %(project)s")
		params["project"] = project
	else:
		conditions.append("ifnull(ape.project, '') = ''")
	rows = frappe.db.sql(
		f"""select distinct aped.item_code, aped.exception_type
		from `tabAuto PO Exception Detail` aped
		inner join `tabAuto PO Exception` ape on ape.name = aped.parent
		where {" and ".join(conditions)} and ape.name != %(exclude)s
			and (ifnull(aped.follow_up, '') != '' or ifnull(aped.item_price_request, '') != ''
				or ifnull(aped.purchase_order, '') != '' or ape.docstatus = 0)""",
		params,
	)
	return {(item_code, exc_type) for item_code, exc_type in rows}


def compute_exception_rows(company, to_date, project=None, lead_time_mode=False, exclude_doc=None,
		skip_handled=True, lines=None):
	if lines is None:
		lines = get_planning_lines(company, to_date, project, lead_time_mode)
	_eligible, exceptions = classify_lines(lines)
	if skip_handled:
		handled = get_handled_items(company, project, exclude_doc)
		exceptions = [r for r in exceptions if (r.item_code, r.exception_type) not in handled]
	return exceptions
