"""Daily jobs: consumables auto PO and purge of stale draft Auto PO Run orders."""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, nowdate

from universal_buying.ub_planning import common, planning
from universal_buying.ub_planning.api import get_current_item_price
from universal_buying.ub_planning.po_builder import build_purchase_order
from universal_buying.universal_buying.settings import get_list, get_setting

# ------------------------------------------------------------------------------------ consumables


def scheduled_consumables_auto_po():
	if not cint(get_setting("consumables_auto_po_enabled")):
		return
	frappe.enqueue("universal_buying.ub_planning.jobs.create_consumables_purchase_orders", queue="long",
		timeout=3600, job_id="ub_consumables_auto_po", deduplicate=True)


@frappe.whitelist()
def create_consumables_po_for_mr(material_request):
	"""Button on a submitted Purchase Material Request."""
	frappe.has_permission("Purchase Order", "create", throw=True)
	if not cint(get_setting("consumables_auto_po_enabled")):
		frappe.throw(_("Consumables auto PO is switched off in Buying Control Settings."))
	return create_consumables_purchase_orders(material_requests=[material_request])


def get_pending_consumable_lines(groups, material_requests=None):
	"""Submitted Purchase MR lines of consumable item groups not yet on any (draft or submitted) PO."""
	conditions = [
		"mr.docstatus = 1",
		"mr.material_request_type = 'Purchase'",
		"mr.status not in ('Stopped', 'Cancelled', 'Ordered', 'Received')",
		"mri.stock_qty > ifnull(mri.ordered_qty, 0)",
		"it.item_group in %(groups)s",
	]
	params = {"groups": tuple(groups)}
	if material_requests:
		conditions.append("mr.name in %(mrs)s")
		params["mrs"] = tuple(material_requests)
	return frappe.db.sql(
		f"""select mr.name as material_request, mr.company, mri.name as material_request_item, mri.item_code,
			mri.uom, ifnull(nullif(mri.conversion_factor, 0), 1) as conversion_factor, mri.warehouse,
			mri.schedule_date, mri.project,
			(mri.stock_qty - ifnull(mri.ordered_qty, 0)) - ifnull((
				select sum(poi.stock_qty) from `tabPurchase Order Item` poi
				where poi.material_request_item = mri.name and poi.docstatus = 0), 0) as pending_stock_qty
		from `tabMaterial Request Item` mri
		inner join `tabMaterial Request` mr on mr.name = mri.parent
		inner join `tabItem` it on it.name = mri.item_code
		where {" and ".join(conditions)}
		order by mr.name, mri.idx""",
		params,
		as_dict=True,
	)


def create_consumables_purchase_orders(material_requests=None):
	"""One draft PO per Material Request and supplier; origin "Material Request".

	Fixes from the earlier create_auto_po_for_consumable: it auto-submitted every draft MR, queried a
	non-existent "Supplier Line Card Detail" doctype and used the returned list as supplier, and a
	``return`` inside the MR loop stopped at the first MR without consumables.
	"""
	groups = get_list("consumable_item_groups")
	if not groups:
		return []
	project = get_setting("consumables_project")
	created, skipped = [], []
	buckets = {}
	for line in get_pending_consumable_lines(groups, material_requests):
		if flt(line.pending_stock_qty) <= 0:
			continue
		supplier, _card = common.resolve_supplier(line.item_code, line.company)
		if not supplier:
			skipped.append((line.material_request, line.item_code, _("no supplier")))
			continue
		schedule_date = max(getdate(line.schedule_date or nowdate()), getdate(nowdate()))
		price = get_current_item_price(line.item_code, supplier, line.company, schedule_date)
		if not price:
			skipped.append((line.material_request, line.item_code, _("no price")))
			continue
		key = (line.material_request, line.company, supplier, price["currency"], price["price_list"])
		buckets.setdefault(key, []).append({
			"item_code": line.item_code,
			"qty": flt(line.pending_stock_qty) / flt(line.conversion_factor),
			"uom": line.uom,
			"rate": planning.price_rate_for_uom(line.item_code, price, line.uom),
			"schedule_date": schedule_date,
			"warehouse": line.warehouse,
			"project": line.project or project,
			"manufacturer": price.get("manufacturer"),
			"manufacturer_part_no": price.get("manufacturer_part_no"),
			"material_request": line.material_request,
			"material_request_item": line.material_request_item,
			"required_by": schedule_date,
		})

	for (mr, company, supplier, currency, price_list), lines in buckets.items():
		frappe.db.savepoint("ub_consumables")
		try:
			po = build_purchase_order(company, supplier, lines, "Material Request", mr, currency=currency,
				price_list=price_list, project=project)
			created.append(po.name)
		except Exception:
			frappe.db.rollback(save_point="ub_consumables")
			frappe.log_error(title=f"Consumables auto PO failed for {mr} / {supplier}")
	if skipped:
		frappe.log_error(title="Consumables auto PO: lines skipped",
			message="\n".join(f"{mr} {item}: {why}" for mr, item, why in skipped))
	frappe.db.commit()
	return created


# ------------------------------------------------------------------------------------ purge


def purge_draft_auto_pos():
	"""A-11.2: delete draft POs created by Auto PO Run older than purge_draft_auto_po_days (0 = off)."""
	days = cint(get_setting("purge_draft_auto_po_days"))
	if days <= 0 or not frappe.get_meta("Purchase Order").has_field("ub_origin_doctype"):
		return 0
	cutoff = add_days(nowdate(), -days)
	names = frappe.get_all(
		"Purchase Order",
		filters={"docstatus": 0, "ub_origin_doctype": "Auto PO Run", "transaction_date": ("<=", cutoff)},
		pluck="name",
	)
	deleted = 0
	for name in names:
		try:
			frappe.delete_doc("Purchase Order", name, force=1, ignore_permissions=True)
			deleted += 1
		except Exception:
			frappe.log_error(title=f"Draft Auto PO purge failed for {name}")
	frappe.db.commit()
	return deleted
