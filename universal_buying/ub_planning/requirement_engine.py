"""Requirement Engine (BRD v2 6.10).

For each company the engine walks pending demand in date order and earmarks supply:

1. demand = pending Sales Order lines (stock UOM), plus - when ``include_open_production`` is on - the
   pending component requirements of open Work Orders, plus - when ``include_safety_stock`` is on - the
   item safety stock (processed last).
2. each demand line is covered from warehouse stock (warehouses named in ``excluded_warehouse_names``
   are ignored), then from open submitted Purchase Order lines, then (``include_open_production``) from
   open Work Orders of the item.
3. what is still uncovered is exploded through the item's default BOM of the company (multi level); an
   item without a BOM - or a BOM line flagged ``do_not_explode`` - is written as a ``Shortage`` row.

Every allocation is written as one ``Requirement Log`` row (Stock / Purchase Order / Work Order /
Shortage). ``Shortage`` rows therefore hold the NET uncovered quantity (BR-03: demand - stock - open
supply) of the item; there is no double counting with the Purchase Order rows.

The whole company table is replaced in one transaction (delete + ``frappe.db.bulk_insert``) so readers
never see a half written log. A Redis lock prevents two rebuilds running at once and a
``Requirement Rebuild`` row records status per company.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, get_first_day, getdate, now, now_datetime, nowdate

from universal_buying.universal_buying.settings import get_lines, get_setting

LOG_DOCTYPE = "Requirement Log"
STATUS_DOCTYPE = "Requirement Rebuild"
LOCK_KEY = "ub_requirement_engine_rebuild"
LOCK_TIMEOUT = 4 * 60 * 60
MAX_BOM_DEPTH = 25
EPS = 1e-9

LOG_FIELDS = (
	"company",
	"rebuild_id",
	"posting_datetime",
	"demand_type",
	"sales_order",
	"sales_order_item",
	"demand_work_order",
	"project",
	"cost_center",
	"fg_item_code",
	"item_code",
	"stock_uom",
	"bom_no",
	"bom_item_type",
	"level",
	"reservation_type",
	"qty",
	"delivery_date",
	"grouped_delivery_date",
	"warehouse",
	"purchase_order",
	"purchase_order_item",
	"work_order",
)
SYSTEM_FIELDS = ("creation", "modified", "owner", "modified_by", "docstatus")


# --------------------------------------------------------------------------------------------- entry points


def scheduled_rebuild():
	"""Cron hook (03:00). Enqueues the real work on the long queue."""
	if not cint(get_setting("requirement_engine_enabled")):
		return
	frappe.enqueue(
		"universal_buying.ub_planning.requirement_engine.rebuild_all_companies",
		queue="long",
		timeout=LOCK_TIMEOUT,
		job_id="ub_requirement_engine_rebuild",
		deduplicate=True,
	)


@frappe.whitelist()
def enqueue_rebuild(company=None):
	"""Manual 'Rebuild now' from the Requirement Log / Requirement Rebuild list."""
	frappe.has_permission(STATUS_DOCTYPE, "create", throw=True)
	if not cint(get_setting("requirement_engine_enabled")):
		frappe.throw(_("The Requirement Engine is switched off in Buying Control Settings."))
	frappe.enqueue(
		"universal_buying.ub_planning.requirement_engine.rebuild_all_companies",
		queue="long",
		timeout=LOCK_TIMEOUT,
		companies=[company] if company else None,
		triggered_by=frappe.session.user,
	)
	return _("Requirement rebuild queued. Check Requirement Rebuild for the result.")


def rebuild_all_companies(companies=None, triggered_by=None):
	"""Rebuild the log for each (or the given) non-group company under a global lock."""
	lock = None
	try:
		cache = frappe.cache()
		lock = cache.lock(cache.make_key(LOCK_KEY), timeout=LOCK_TIMEOUT)
		if not lock.acquire(blocking=False):
			for company in companies or _companies():
				_create_status(company, "Skipped", triggered_by, error="Another rebuild is running.")
			frappe.db.commit()
			return
	except Exception:
		# Redis lock is best effort; never block the rebuild because of it
		frappe.log_error(title="Requirement Engine: lock failed")
		lock = None

	try:
		for company in companies or _companies():
			rebuild_company(company, triggered_by=triggered_by)
	finally:
		if lock is not None:
			try:
				lock.release()
			except Exception:
				pass


def rebuild_company(company, triggered_by=None):
	"""Recompute and replace the Requirement Log rows of one company. Returns the row count."""
	rebuild_id = frappe.generate_hash(length=10)
	status = _create_status(company, "Running", triggered_by, rebuild_id=rebuild_id)
	frappe.db.commit()
	try:
		engine = RequirementEngine(company, rebuild_id=rebuild_id)
		rows = engine.run()
		write_log(company, rows)
		shortage_rows = sum(1 for r in rows if r["reservation_type"] == "Shortage")
		_mark_status(status, "Completed", row_count=len(rows), shortage_rows=shortage_rows)
		frappe.db.commit()
		return len(rows)
	except Exception:
		frappe.db.rollback()
		_mark_status(status, "Failed", error=frappe.get_traceback())
		frappe.db.commit()
		frappe.log_error(title=f"Requirement Engine failed for {company}")
		return 0


def write_log(company, rows):
	"""Replace the company's rows. Caller commits (one transaction: readers keep the old snapshot)."""
	frappe.db.delete(LOG_DOCTYPE, {"company": company})
	if not rows:
		return
	ts = now()
	user = frappe.session.user or "Administrator"
	prefix = rows[0].get("rebuild_id") or frappe.generate_hash(length=10)
	fields = ["name", *LOG_FIELDS, *SYSTEM_FIELDS]
	values = (
		[f"{prefix}-{i}"] + [r.get(f) for f in LOG_FIELDS] + [ts, ts, user, user, 0]
		for i, r in enumerate(rows, 1)
	)
	frappe.db.bulk_insert(LOG_DOCTYPE, fields, values, chunk_size=5000)


def _companies():
	return frappe.get_all("Company", filters={"is_group": 0}, pluck="name", order_by="name")


def _create_status(company, status, triggered_by=None, rebuild_id=None, error=None):
	try:
		doc = frappe.get_doc({
			"doctype": STATUS_DOCTYPE,
			"company": company,
			"status": status,
			"rebuild_id": rebuild_id,
			"triggered_by": triggered_by or "Administrator",
			"started_at": now_datetime(),
			"completed_at": now_datetime() if status in ("Skipped", "Failed") else None,
			"error_message": error,
		})
		doc.insert(ignore_permissions=True)
		return doc.name
	except Exception:
		frappe.log_error(title="Requirement Rebuild status insert failed")
		return None


def _mark_status(name, status, row_count=None, shortage_rows=None, error=None):
	if not name:
		return
	try:
		values = {"status": status, "completed_at": now_datetime()}
		if row_count is not None:
			values["row_count"] = row_count
		if shortage_rows is not None:
			values["shortage_rows"] = shortage_rows
		if error:
			values["error_message"] = error
		frappe.db.set_value(STATUS_DOCTYPE, name, values, update_modified=True)
	except Exception:
		frappe.log_error(title="Requirement Rebuild status update failed")


def get_last_rebuild(company):
	return frappe.db.get_value(
		STATUS_DOCTYPE,
		{"company": company, "status": "Completed"},
		["name", "completed_at", "row_count", "shortage_rows"],
		as_dict=True,
		order_by="completed_at desc",
	)


# --------------------------------------------------------------------------------------------- the engine


class RequirementEngine:
	"""Pure in-memory allocation. `run()` returns a list of Requirement Log dicts (no DB writes)."""

	def __init__(self, company, rebuild_id=None, posting_datetime=None):
		self.company = company
		self.rebuild_id = rebuild_id or frappe.generate_hash(length=10)
		self.posting_datetime = posting_datetime or now_datetime()
		self.today = getdate(nowdate())
		self.excluded_order_types = get_lines("excluded_order_types")
		self.excluded_warehouse_names = get_lines("excluded_warehouse_names")
		self.include_open_production = cint(get_setting("include_open_production", company=company))
		self.include_safety_stock = cint(get_setting("include_safety_stock", company=company))
		self.rows = []
		self._bom_items = {}
		self._bom_company = {}
		self._stock_uom = {}

	# ------------------------------------------------------------------ loaders
	def load(self):
		self.stock = self.get_stock()
		self.po_pool = self.get_open_purchase_orders()
		self.wo_pool = self.get_open_work_orders() if self.include_open_production else {}
		self.default_boms = self.get_default_boms()

	def get_stock(self):
		"""{item_code: [[warehouse, qty], ...]} - leaf, enabled warehouses of the company, excluded names out."""
		conditions = ["wh.company = %(company)s", "ifnull(wh.disabled, 0) = 0", "ifnull(wh.is_group, 0) = 0",
			"bin.actual_qty > 0"]
		params = {"company": self.company}
		if self.excluded_warehouse_names:
			conditions.append("wh.warehouse_name not in %(excluded)s")
			params["excluded"] = tuple(self.excluded_warehouse_names)
		rows = frappe.db.sql(
			f"""select bin.item_code, bin.warehouse, bin.actual_qty
			from `tabBin` bin inner join `tabWarehouse` wh on wh.name = bin.warehouse
			where {" and ".join(conditions)}
			order by bin.item_code, bin.actual_qty desc, bin.warehouse""",
			params,
		)
		stock = {}
		for item_code, warehouse, qty in rows:
			stock.setdefault(item_code, []).append([warehouse, flt(qty)])
		return stock

	def get_open_purchase_orders(self):
		"""{item_code: [[purchase_order, purchase_order_item, pending_stock_qty], ...]} earliest first."""
		rows = frappe.db.sql(
			"""select poi.item_code, poi.parent, poi.name,
				(poi.qty - ifnull(poi.received_qty, 0)) * ifnull(nullif(poi.conversion_factor, 0), 1) as pending
			from `tabPurchase Order Item` poi
			inner join `tabPurchase Order` po on po.name = poi.parent
			where po.docstatus = 1 and po.company = %s
				and po.status not in ('Closed', 'On Hold', 'Completed', 'Delivered')
				and poi.qty > ifnull(poi.received_qty, 0)
			order by poi.schedule_date, po.transaction_date, poi.parent, poi.idx""",
			(self.company,),
		)
		pool = {}
		for item_code, po, poi, pending in rows:
			if flt(pending) > EPS:
				pool.setdefault(item_code, []).append([po, poi, flt(pending)])
		return pool

	def get_open_work_orders(self):
		"""{production_item: [[work_order, pending_qty], ...]} (include_open_production)."""
		rows = frappe.db.sql(
			"""select production_item, name, qty - ifnull(produced_qty, 0)
			from `tabWork Order`
			where docstatus = 1 and company = %s
				and status not in ('Completed', 'Stopped', 'Closed', 'Cancelled')
				and qty > ifnull(produced_qty, 0)
			order by ifnull(expected_delivery_date, planned_start_date), planned_start_date, name""",
			(self.company,),
		)
		pool = {}
		for item_code, wo, pending in rows:
			pool.setdefault(item_code, []).append([wo, flt(pending)])
		return pool

	def get_default_boms(self):
		"""{item: (bom, quantity)} - active, submitted, default BOMs of this company."""
		rows = frappe.db.sql(
			"""select item, name, quantity from `tabBOM`
			where is_default = 1 and is_active = 1 and docstatus = 1 and company = %s""",
			(self.company,),
		)
		return {item: (name, flt(qty) or 1.0) for item, name, qty in rows}

	def get_bom(self, bom_no):
		"""(quantity, [bom item dicts]) of a BOM, cached."""
		if bom_no not in self._bom_items:
			quantity = flt(frappe.db.get_value("BOM", bom_no, "quantity")) or 1.0
			items = frappe.db.sql(
				"""select item_code, stock_qty, bom_no, ifnull(do_not_explode, 0) as do_not_explode,
					ifnull(stock_uom, '') as stock_uom
				from `tabBOM Item`
				where parent = %s and parenttype = 'BOM' and ifnull(sourced_by_supplier, 0) = 0
				order by idx""",
				(bom_no,),
				as_dict=True,
			)
			self._bom_items[bom_no] = (quantity, items)
		return self._bom_items[bom_no]

	def bom_company(self, bom_no):
		if bom_no not in self._bom_company:
			self._bom_company[bom_no] = frappe.db.get_value("BOM", bom_no, "company")
		return self._bom_company[bom_no]

	def stock_uom(self, item_code):
		if item_code not in self._stock_uom:
			self._stock_uom[item_code] = frappe.get_cached_value("Item", item_code, "stock_uom")
		return self._stock_uom[item_code]

	# ------------------------------------------------------------------ demand
	def get_sales_order_demand(self):
		conditions = [
			"so.docstatus = 1",
			"so.company = %(company)s",
			"so.status not in ('Closed', 'On Hold', 'Completed')",
			"soi.qty > ifnull(soi.delivered_qty, 0)",
		]
		params = {"company": self.company}
		if self.excluded_order_types:
			conditions.append("ifnull(so.order_type, '') not in %(order_types)s")
			params["order_types"] = tuple(self.excluded_order_types)
		rows = frappe.db.sql(
			f"""select soi.name as sales_order_item, soi.parent as sales_order, soi.item_code,
				(soi.qty - ifnull(soi.delivered_qty, 0)) * ifnull(nullif(soi.conversion_factor, 0), 1) as qty,
				ifnull(soi.delivery_date, so.delivery_date) as delivery_date,
				coalesce(nullif(soi.project, ''), so.project) as project,
				coalesce(nullif(soi.cost_center, ''), so.cost_center) as cost_center,
				nullif(soi.bom_no, '') as bom_no
			from `tabSales Order Item` soi
			inner join `tabSales Order` so on so.name = soi.parent
			where {" and ".join(conditions)}
			order by ifnull(soi.delivery_date, so.delivery_date), soi.parent, soi.idx""",
			params,
			as_dict=True,
		)
		for r in rows:
			r.demand_type = "Sales Order"
			r.demand_work_order = None
			r.fg_item_code = r.item_code
			r.level = 0
			r.parent_bom = None
			r.bom_item_type = "Finished Good"
		return rows

	def get_work_order_demand(self):
		"""Pending component need of open Work Orders (include_open_production)."""
		rows = frappe.db.sql(
			"""select woi.item_code, wo.name as demand_work_order, wo.sales_order, wo.sales_order_item,
				wo.project, wo.production_item as fg_item_code, wo.bom_no as parent_bom,
				date(coalesce(wo.planned_start_date, wo.expected_delivery_date, wo.creation)) as delivery_date,
				woi.required_qty - greatest(ifnull(woi.transferred_qty, 0), ifnull(woi.consumed_qty, 0)) as qty
			from `tabWork Order Item` woi
			inner join `tabWork Order` wo on wo.name = woi.parent
			where wo.docstatus = 1 and wo.company = %s
				and wo.status not in ('Completed', 'Stopped', 'Closed', 'Cancelled')
				and woi.required_qty > greatest(ifnull(woi.transferred_qty, 0), ifnull(woi.consumed_qty, 0))
			order by delivery_date, wo.name, woi.idx""",
			(self.company,),
			as_dict=True,
		)
		for r in rows:
			r.demand_type = "Work Order"
			r.cost_center = None
			r.level = 1
			r.bom_no = None
			r.bom_item_type = "Component"
		return rows

	def get_safety_stock_demand(self):
		rows = frappe.db.sql(
			"""select it.name as item_code, it.safety_stock as qty
			from `tabItem` it
			inner join `tabItem Default` idf on idf.parent = it.name and idf.parenttype = 'Item'
				and idf.company = %s
			where ifnull(it.disabled, 0) = 0 and ifnull(it.safety_stock, 0) > 0 and ifnull(it.has_variants, 0) = 0
			order by it.name""",
			(self.company,),
			as_dict=True,
		)
		for r in rows:
			r.update({
				"demand_type": "Safety Stock", "sales_order": None, "sales_order_item": None,
				"demand_work_order": None, "project": None, "cost_center": None, "fg_item_code": r.item_code,
				"delivery_date": self.today, "level": 0, "parent_bom": None, "bom_no": None,
				"bom_item_type": None,
			})
		return rows

	# ------------------------------------------------------------------ run
	def run(self):
		self.load()
		demand = self.get_sales_order_demand()
		if self.include_open_production:
			demand += self.get_work_order_demand()
			demand.sort(key=lambda d: (getdate(d.delivery_date or self.today), d.get("sales_order") or "",
				d.get("demand_work_order") or ""))
		for d in demand:
			if flt(d.qty) <= EPS:
				continue
			self.reserve(d.item_code, flt(d.qty), d, bom_no=d.get("bom_no"), parent_bom=d.parent_bom,
				bom_item_type=d.bom_item_type, level=d.level)
		if self.include_safety_stock:
			for d in self.get_safety_stock_demand():
				self.reserve(d.item_code, flt(d.qty), d, bom_no=None, parent_bom=None, bom_item_type=None, level=0)
		return self.rows

	def log(self, ctx, item_code, qty, reservation_type, parent_bom, bom_item_type, level, warehouse=None,
			purchase_order=None, purchase_order_item=None, work_order=None):
		delivery_date = getdate(ctx.get("delivery_date") or self.today)
		self.rows.append({
			"company": self.company,
			"rebuild_id": self.rebuild_id,
			"posting_datetime": self.posting_datetime,
			"demand_type": ctx.get("demand_type"),
			"sales_order": ctx.get("sales_order"),
			"sales_order_item": ctx.get("sales_order_item"),
			"demand_work_order": ctx.get("demand_work_order"),
			"project": ctx.get("project") or None,
			"cost_center": ctx.get("cost_center") or None,
			"fg_item_code": ctx.get("fg_item_code"),
			"item_code": item_code,
			"stock_uom": self.stock_uom(item_code),
			"bom_no": parent_bom,
			"bom_item_type": bom_item_type,
			"level": level,
			"reservation_type": reservation_type,
			"qty": flt(qty, 9),
			"delivery_date": delivery_date,
			"grouped_delivery_date": get_first_day(delivery_date),
			"warehouse": warehouse,
			"purchase_order": purchase_order,
			"purchase_order_item": purchase_order_item,
			"work_order": work_order,
		})

	def reserve(self, item_code, qty, ctx, bom_no=None, parent_bom=None, bom_item_type=None, level=0,
			do_not_explode=False):
		"""Allocate `qty` (stock UOM) of `item_code`; explode the uncovered rest through its BOM."""
		# 1. stock
		for entry in self.stock.get(item_code, []):
			if qty <= EPS:
				break
			take = min(entry[1], qty)
			if take > EPS:
				entry[1] -= take
				qty -= take
				self.log(ctx, item_code, take, "Stock", parent_bom, bom_item_type, level, warehouse=entry[0])
		if qty <= EPS:
			return

		# 2. open purchase orders (FG / sub-assembly POs stop the explosion for their qty)
		for entry in self.po_pool.get(item_code, []):
			if qty <= EPS:
				break
			take = min(entry[2], qty)
			if take > EPS:
				entry[2] -= take
				qty -= take
				self.log(ctx, item_code, take, "Purchase Order", parent_bom, bom_item_type, level,
					purchase_order=entry[0], purchase_order_item=entry[1])
		if qty <= EPS:
			return

		# 3. open work orders (include_open_production)
		for entry in self.wo_pool.get(item_code, []):
			if qty <= EPS:
				break
			take = min(entry[1], qty)
			if take > EPS:
				entry[1] -= take
				qty -= take
				self.log(ctx, item_code, take, "Work Order", parent_bom, bom_item_type, level, work_order=entry[0])
		if qty <= EPS:
			return

		# 4. BOM explosion of the uncovered rest
		bom = None
		if not do_not_explode and level < MAX_BOM_DEPTH:
			if bom_no and self.bom_company(bom_no) == self.company:
				bom = bom_no
			elif item_code in self.default_boms:
				bom = self.default_boms[item_code][0]
		if bom:
			quantity, bom_items = self.get_bom(bom)
			if bom_items:
				for bi in bom_items:
					child_qty = qty * flt(bi.stock_qty) / quantity
					if child_qty <= EPS:
						continue
					child_type = "Sub Assembly" if (bi.bom_no or bi.item_code in self.default_boms) and not \
						bi.do_not_explode else "Component"
					self.reserve(bi.item_code, child_qty, ctx, bom_no=bi.bom_no, parent_bom=bom,
						bom_item_type=child_type, level=level + 1, do_not_explode=cint(bi.do_not_explode))
				return

		# 5. what is left is a shortage
		self.log(ctx, item_code, qty, "Shortage", parent_bom, bom_item_type, level)
