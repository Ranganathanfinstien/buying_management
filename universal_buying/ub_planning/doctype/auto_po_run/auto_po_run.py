# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt

"""Auto PO Run (BRD v2 6.11): draft Purchase Orders for shortages that have an approved source.

Submitting the run enqueues ``run_auto_po`` on the long queue; progress is pushed to the form with
``frappe.publish_progress``. One draft PO is created per supplier (and currency / price list); items
that cannot be ordered land on one Auto PO Exception per run.
"""

from collections import OrderedDict

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, cint, flt, getdate, now_datetime, nowdate

from universal_buying.ub_planning import planning
from universal_buying.ub_planning.po_builder import build_purchase_order
from universal_buying.universal_buying.settings import get_setting

ORIGIN = "Auto PO Run"


class AutoPORun(Document):
	def validate(self):
		self.validate_to_date()
		if self.project:
			if not cint(get_setting("plan_by_project", company=self.company)):
				frappe.msgprint(_("Plan by Project is off in Buying Control Settings: the project is ignored."),
					indicator="orange", alert=True)
			project_company = frappe.db.get_value("Project", self.project, "company")
			if project_company and project_company != self.company:
				frappe.throw(_("Project {0} belongs to company {1}.").format(self.project, project_company))

	def validate_to_date(self):
		"""V-11.1: not in the past, not beyond today + planning_horizon_days."""
		today = getdate(nowdate())
		to_date = getdate(self.to_date)
		horizon = cint(get_setting("planning_horizon_days", company=self.company)) or 365
		max_date = getdate(add_days(today, horizon))
		if to_date < today:
			frappe.throw(_("To Date cannot be in the past."))
		if to_date > max_date:
			frappe.throw(_("To Date cannot be later than {0} ({1} days planning horizon).").format(
				frappe.bold(frappe.format(max_date, {"fieldtype": "Date"})), horizon))

	def before_submit(self):
		self.status = "Queued"

	def on_submit(self):
		frappe.enqueue(
			"universal_buying.ub_planning.doctype.auto_po_run.auto_po_run.run_auto_po",
			queue="long",
			timeout=3600,
			job_id=f"auto_po_run::{self.name}",
			deduplicate=True,
			enqueue_after_commit=True,
			name=self.name,
		)
		frappe.msgprint(_("Purchase Order creation queued. The form updates when the run finishes."), alert=True)

	def on_cancel(self):
		if self.status in ("Queued", "In Progress"):
			frappe.throw(_("The run is still in progress."))

	@property
	def effective_project(self):
		return self.project if cint(get_setting("plan_by_project", company=self.company)) else None


def _progress(doc, percent, description):
	frappe.publish_progress(percent, title=_("Auto PO Run"), doctype=doc.doctype, docname=doc.name,
		description=description)


def run_auto_po(name):
	"""Background job (A-11.1)."""
	doc = frappe.get_doc("Auto PO Run", name)
	if doc.docstatus != 1:
		return
	doc.db_set({"status": "In Progress", "started_at": now_datetime(), "error_message": None}, notify=True)
	frappe.db.commit()
	try:
		result = execute_run(doc)
		doc.db_set({
			"status": "Completed",
			"completed_at": now_datetime(),
			"po_count": len(result["purchase_orders"]),
			"purchase_orders": "\n".join(result["purchase_orders"]),
			"exception_count": result["exception_count"],
			"auto_po_exception": result["exception"],
			"error_message": "\n\n".join(result["errors"]) or None,
		}, notify=True)
		frappe.db.commit()
		_progress(doc, 100, _("Completed"))
	except Exception:
		frappe.db.rollback()
		doc.db_set({"status": "Failed", "completed_at": now_datetime(), "error_message": frappe.get_traceback()},
			notify=True)
		frappe.db.commit()
		frappe.log_error(title=f"Auto PO Run {name} failed")


def execute_run(doc):
	project = doc.effective_project
	_progress(doc, 5, _("Reading shortages"))
	lines = planning.get_planning_lines(doc.company, doc.to_date, project, cint(doc.lead_time_order))

	_progress(doc, 25, _("Checking suppliers, prices and MOQ"))
	eligible, _exceptions = planning.classify_lines(lines)

	allowed = {r.item_code for r in doc.items_filter or [] if r.item_code}
	if allowed:
		eligible = [x for x in eligible if x.item_code in allowed]
	to_order = planning.round_eligible(eligible)

	errors = []
	purchase_orders = create_purchase_orders(doc, to_order, project, errors)

	_progress(doc, 90, _("Writing exceptions"))
	exception_name, exception_count = create_or_update_exception(doc, project, lines)
	return {"purchase_orders": purchase_orders, "exception": exception_name, "exception_count": exception_count,
		"errors": errors}


def create_purchase_orders(doc, to_order, project, errors):
	groups = OrderedDict()
	for line in to_order:
		groups.setdefault((line.supplier, line.currency, line.price_list), []).append(line)

	created = []
	total = len(groups) or 1
	for idx, ((supplier, currency, price_list), lines) in enumerate(groups.items(), 1):
		po_lines = [
			{
				"item_code": x.item_code,
				"qty": x.qty,
				"uom": x.uom,
				"rate": x.rate,
				"schedule_date": x.schedule_date,
				"project": x.project or project,
				"manufacturer": x.get("manufacturer"),
				"manufacturer_part_no": x.get("manufacturer_part_no"),
				"required_by": x.required_by,
				"supplier_delivery_date": x.schedule_date,
			}
			for x in lines
		]
		frappe.db.savepoint("ub_auto_po")
		try:
			po = build_purchase_order(doc.company, supplier, po_lines, ORIGIN, doc.name, currency=currency,
				price_list=price_list, project=project)
		except Exception:
			# one bad supplier must not lose the other POs; the error is kept on the run
			frappe.db.rollback(save_point="ub_auto_po")
			errors.append(_("Supplier {0}: {1}").format(supplier, frappe.get_traceback()))
			frappe.clear_last_message()
			continue
		created.append(po.name)
		_progress(doc, 30 + int(55 * idx / total), _("Created {0} for {1}").format(po.name, supplier))
	return created


def create_or_update_exception(doc, project, lines):
	"""One Auto PO Exception per run (BRD 6.11 step 9); refreshed if the run is executed again."""
	existing = frappe.db.get_value("Auto PO Exception", {"auto_po_reference": doc.name, "docstatus": 0}, "name")
	rows = planning.compute_exception_rows(doc.company, doc.to_date, project, cint(doc.lead_time_order),
		exclude_doc=existing, lines=lines)
	if not rows and not existing:
		return None, 0
	exc = frappe.get_doc("Auto PO Exception", existing) if existing else frappe.new_doc("Auto PO Exception")
	exc.company = doc.company
	exc.project = project
	exc.to_date = doc.to_date
	exc.lead_time_order = cint(doc.lead_time_order)
	exc.auto_po_reference = doc.name
	exc.set("items", [exception_child(row) for row in rows])
	exc.flags.ignore_permissions = True
	exc.save()
	return exc.name, len(rows)


def exception_child(row):
	return {
		"exception_type": row.exception_type,
		"item_code": row.item_code,
		"item_name": row.item_name,
		"description": row.description,
		"project": row.project,
		"item_class": row.item_class,
		"po_shortage": flt(row.po_shortage, 6),
		"uom": row.uom,
		"required_by": row.required_by,
		"moq": row.moq,
		"spq": row.spq,
		"default_supplier": row.default_supplier,
		"rate": row.rate,
		"currency": row.currency,
		"manufacturer": row.manufacturer,
		"mpn": row.mpn,
		"status": "Open",
	}
