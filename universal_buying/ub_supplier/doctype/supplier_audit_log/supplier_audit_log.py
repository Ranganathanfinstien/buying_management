# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt
"""Supplier Audit Log (BRD 6.4).

A-4.1 score, percentage and industry minimum are computed on save.
V-4.1 every question needs a company rating on submit.
A-4.2 each NC row creates an ERPNext "Non Conformance" (quality management) linked to the supplier and audit.
"""

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, escape_html, flt, get_link_to_form

from universal_buying.universal_buying.settings import get_setting


class SupplierAuditLog(Document):
	def validate(self):
		if self.supplier and not self.supplier_name:
			self.supplier_name = frappe.db.get_value("Supplier", self.supplier, "supplier_name")
		if not self.supplier and not self.supplier_onboarding:
			frappe.throw(_("Select a Supplier or a Supplier Onboarding."))
		if not self.audit_rows and self.supplier_audit_checklist:
			self.load_checklist()
		self.refresh_min_scores()
		self.calculate_score()

	@frappe.whitelist()
	def get_questions(self):
		"""Button: (re)load the checklist questions for the selected checklist and industry."""
		self.check_permission("write")
		self.load_checklist()
		self.calculate_score()
		return self.as_dict()

	def load_checklist(self):
		from universal_buying.ub_supplier.api import get_audit_questions

		self.set("audit_rows", [])
		for q in get_audit_questions(self.supplier_audit_type, self.supplier_audit_checklist):
			self.append("audit_rows", {
				"group": q["group"],
				"question": q["question"],
				"option_list": json.dumps(q["options"]),
				"max_score": q["max_score"],
				"min_score": q["min_score"],
			})

	def refresh_min_scores(self):
		"""Minimum scores follow the industry type selected on the log."""
		from universal_buying.ub_supplier.api import INDUSTRY_FIELD

		key = INDUSTRY_FIELD.get(self.supplier_audit_type or "")
		if not key or not self.supplier_audit_checklist:
			return
		mins = {
			(r.group, r.question): cint(r.get(key))
			for r in frappe.get_all(
				"Supplier Audit Checklist Detail",
				filters={"parent": self.supplier_audit_checklist, "parenttype": "Supplier Audit Checklist"},
				fields=["group", "question", key],
			)
		}
		for row in self.audit_rows:
			if (row.group, row.question) in mins:
				row.min_score = mins[(row.group, row.question)]

	def calculate_score(self):
		"""A-4.1"""
		total = minimum = score = 0
		for row in self.audit_rows:
			max_score = cint(row.max_score)
			for field in ("company_rating", "supplier_self_rating"):
				value = cint(row.get(field))
				if value < 0 or (max_score and value > max_score):
					frappe.throw(_("Row {0}: {1} must be between 0 and {2}.").format(row.idx, _(row.meta.get_label(field)), max_score))
			row.answer = answer_for_rating(row)
			total += max_score
			minimum += cint(row.min_score)
			score += cint(row.company_rating)
		self.total_score = total
		self.minimum_score = minimum
		self.audit_score = score
		self.audit_score_percent = flt(score * 100.0 / total, 2) if total else 0
		self.meets_minimum = 1 if (total and score >= minimum) else 0

	def before_submit(self):
		"""V-4.1"""
		# Int fields store 0 when empty: a 0 rating counts as rated only when an observation explains it
		missing = [row for row in self.audit_rows if row.question and not cint(row.company_rating) and not row.observation]
		if not self.audit_rows:
			frappe.throw(_("Load the checklist questions before submitting."))
		if missing:
			names = "<br>".join(frappe.bold(escape_html(r.question or "")) for r in missing[:10])
			more = _("<br>... and {0} more").format(len(missing) - 10) if len(missing) > 10 else ""
			frappe.throw(
				_("Every question needs a Company Rating (enter an observation to record a rating of 0):") + "<br>" + names + more,
				title=_("Company Rating Missing"),
			)

	def on_submit(self):
		created = []
		for row in self.audit_rows:
			if (row.audit_finding_category or "").upper() == "NC" and not row.non_conformance:
				nc = create_non_conformance(self, row)
				if nc:
					row.db_set("non_conformance", nc, update_modified=False)
					created.append(nc)
		if self.supplier_onboarding:
			frappe.db.set_value("Supplier Onboarding", self.supplier_onboarding, "supplier_audit_log", self.name, update_modified=False)
		if created:
			frappe.msgprint(
				_("Created Non Conformance {0}").format(", ".join(get_link_to_form("Non Conformance", n) for n in created)),
				alert=True,
			)


def answer_for_rating(row):
	"""Checklist options are listed lowest score first, starting at 0: option[index] = rating."""
	try:
		options = json.loads(row.option_list or "[]")
	except (TypeError, ValueError):
		options = []
	if not options:
		return row.answer
	rating = row.company_rating if cint(row.company_rating) else row.supplier_self_rating
	if rating in (None, ""):
		return None
	idx = min(max(cint(rating), 0), len(options) - 1)
	return options[idx]


def create_non_conformance(log, row):
	"""A-4.2: ERPNext Non Conformance with the supplier and audit in subject and details."""
	if not frappe.db.exists("DocType", "Non Conformance"):
		return None
	party = log.supplier_name or log.supplier or log.supplier_onboarding
	subject = f"{party}: {row.question or row.group}"
	details = "<br>".join([
		f"<b>{_('Supplier')}:</b> {escape_html(log.supplier or '-')} ({escape_html(log.supplier_name or '')})",
		f"<b>{_('Supplier Onboarding')}:</b> {escape_html(log.supplier_onboarding or '-')}",
		f"<b>{_('Supplier Audit Log')}:</b> {get_link_to_form(log.doctype, log.name)}",
		f"<b>{_('Group')}:</b> {escape_html(row.group or '')}",
		f"<b>{_('Question')}:</b> {escape_html(row.question or '')}",
		f"<b>{_('Company Rating')}:</b> {cint(row.company_rating)} / {cint(row.max_score)}",
		f"<b>{_('Observation')}:</b> {escape_html(row.observation or '')}",
	])
	nc = frappe.new_doc("Non Conformance")
	nc.subject = subject[:140]
	nc.status = "Open"
	nc.details = details
	procedure = get_setting("audit_nc_procedure", default=None)
	if procedure and frappe.db.exists("Quality Procedure", procedure):
		nc.procedure = procedure
	nc.flags.ignore_permissions = True
	nc.flags.ignore_mandatory = True
	nc.insert()
	return nc.name
