"""Request for Quotation controller override (BRD v2 6.13).

* V-13.1 each supplier row has a Supplier or a Prospective Supplier, no duplicates.
  ERPNext's own checks iterate ``row.supplier`` (duplicate check, scorecard, contact e-mail, the
  standard supplier mail, quote status); all of them are overridden to cope with blank suppliers.
* V-13.2 a bid deadline in the past blocks submit (default = AC-13.1).
* V-13.3 item code required unless PO Type ``item_required`` is off.
* BR-12 / V-5.1 only Enabled registered suppliers (``assert_supplier_enabled``).
* A-13.1 at Open: prospective suppliers get a token link, registered suppliers a portal email; the
  standard ERPNext supplier email is suppressed.
* A-13.4 workflow mails for every state of the built workflow; Bid Status follows the workflow.
"""

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime

from erpnext.buying.doctype.request_for_quotation.request_for_quotation import RequestforQuotation

from universal_buying.ub_sourcing.bidding import (
	BID_OPEN,
	get_default_bid_deadline,
	sync_bid_status_with_workflow,
)


class UBRequestForQuotation(RequestforQuotation):
	# ---------------------------------------------------------------- defaults

	def before_insert(self):
		super().before_insert()
		self.set_ub_defaults()

	def before_validate(self):
		self.set_ub_defaults()
		super().before_validate()

	def set_ub_defaults(self):
		if self.meta.has_field("ub_bid_deadline") and not self.get("ub_bid_deadline"):
			self.ub_bid_deadline = get_default_bid_deadline()
		if self.meta.has_field("ub_po_type") and not self.get("ub_po_type"):
			from universal_buying.universal_buying.doctype.po_type.po_type import get_default_po_type

			self.ub_po_type = get_default_po_type()
		for row in self.get("suppliers") or []:
			if row.get("ub_prospective_supplier") and not row.get("supplier"):
				self._fill_prospective_row(row)

	def _fill_prospective_row(self, row):
		ps = frappe.db.get_value("Prospective Supplier", row.ub_prospective_supplier,
			["email", "contact_person", "supplier_name"], as_dict=True)
		if not ps:
			return
		if not row.email_id:
			row.email_id = ps.email
		if not row.supplier_name:
			row.supplier_name = ps.contact_person or ps.supplier_name

	# ---------------------------------------------------------------- validate

	def validate(self):
		self.validate_supplier_or_prospective()
		self.validate_bid_deadline()
		if self.item_code_required():
			super().validate()
		else:
			self.validate_freeform_items()
			self._validate_with_freeform_bypass()

	def validate_supplier_or_prospective(self):
		"""V-13.1"""
		if not self.get("suppliers"):
			frappe.throw(_("Add at least one Supplier or Prospective Supplier."))
		for d in self.suppliers:
			if not d.supplier and not d.get("ub_prospective_supplier"):
				frappe.throw(
					_("Row {0} in Suppliers: set either a Supplier or a Prospective Supplier.").format(d.idx)
				)

	def validate_duplicate_supplier(self):
		suppliers = [d.supplier for d in self.suppliers if d.supplier]
		prospective = [d.ub_prospective_supplier for d in self.suppliers if d.get("ub_prospective_supplier") and not d.supplier]
		if len(suppliers) != len(set(suppliers)):
			frappe.throw(_("Same supplier has been entered multiple times"))
		if len(prospective) != len(set(prospective)):
			frappe.throw(_("Same prospective supplier has been entered multiple times"))

	def validate_supplier_list(self):
		"""Scorecard checks for registered suppliers only; prospective rows are skipped."""
		for d in self.suppliers:
			if not d.supplier:
				continue
			prevent_rfqs = frappe.db.get_value("Supplier", d.supplier, "prevent_rfqs")
			if prevent_rfqs:
				standing = frappe.db.get_value("Supplier Scorecard", d.supplier, "status")
				frappe.throw(
					_("RFQs are not allowed for {0} due to a scorecard standing of {1}").format(d.supplier, standing)
				)
			if frappe.db.get_value("Supplier", d.supplier, "warn_rfqs"):
				standing = frappe.db.get_value("Supplier Scorecard", d.supplier, "status")
				frappe.msgprint(
					_("{0} currently has a {1} Supplier Scorecard standing, and RFQs to this supplier should be "
					  "issued with caution.").format(d.supplier, standing),
					title=_("Caution"), indicator="orange",
				)

	def update_email_id(self):
		for row in self.suppliers:
			if row.get("ub_prospective_supplier") and not row.supplier:
				self._fill_prospective_row(row)
			elif not row.email_id and row.contact:
				row.email_id = frappe.db.get_value("Contact", row.contact, "email_id")

	def validate_bid_deadline(self):
		"""V-13.2: only at submit, so a buyer can park a draft with any date."""
		if self.docstatus != 1 or self.get_doc_before_save() and self.get_doc_before_save().docstatus == 1:
			return
		if not self.get("ub_bid_deadline"):
			frappe.throw(_("Bid Deadline is required."), title=_("Bid Deadline"))
		if get_datetime(self.ub_bid_deadline) <= now_datetime():
			frappe.throw(
				_("Bid Deadline ({0}) must be in the future.").format(
					frappe.format(self.ub_bid_deadline, {"fieldtype": "Datetime"})
				),
				title=_("Bid Deadline"),
			)

	# ---------------------------------------------------------------- V-13.3

	def get_po_type(self):
		from universal_buying.universal_buying.doctype.po_type.po_type import get_po_type

		return get_po_type(self.get("ub_po_type"))

	def item_code_required(self):
		return bool(self.get_po_type().item_required)

	def validate_freeform_items(self):
		for row in self.items:
			if not row.item_code and not row.get("ub_item_description"):
				frappe.throw(_("Row #{0}: either Item Code or Item Description is required").format(row.idx))
			if not row.item_code:
				row.item_name = (row.ub_item_description or "")[:140]
				row.description = row.description or row.ub_item_description
				row.uom = row.uom or "Nos"
				row.stock_uom = row.stock_uom or row.uom
				row.conversion_factor = row.conversion_factor or 1
				row.stock_qty = flt(row.qty) * flt(row.conversion_factor)
				if not flt(row.qty) and not self.get("has_unit_price_items"):
					frappe.throw(_("Row #{0}: Quantity cannot be zero.").format(row.idx))

	def _validate_with_freeform_bypass(self):
		"""Run the standard validation on rows that have an item code only."""
		original = list(self.items)
		self.items = [d for d in original if d.item_code]
		try:
			super().validate()
		finally:
			self.items = original

	# ---------------------------------------------------------------- submit

	def before_submit(self):
		from universal_buying.universal_buying.utils import assert_supplier_enabled

		for row in self.suppliers:
			if row.supplier:
				assert_supplier_enabled(row.supplier, _("Request for Quotation row {0}").format(row.idx))

	def on_submit(self):
		"""Standard on_submit minus ERPNext's supplier email (A-13.1 sends ours)."""
		self.db_set("status", "Submitted")
		if self.meta.has_field("ub_bid_status"):
			self.db_set("ub_bid_status", BID_OPEN, update_modified=False)
		for supplier in self.suppliers:
			supplier.db_set("email_sent", 0, update_modified=False)
			supplier.db_set("quote_status", "Pending", update_modified=False)
		from universal_buying.ub_sourcing.notifications import invite_suppliers

		invite_suppliers(self)

	def send_to_supplier(self):
		"""Called by ERPNext's "Send Emails to Suppliers" button: send our invitations instead
		(tokens are re-used, rows without an email are reported)."""
		from universal_buying.ub_sourcing.notifications import invite_suppliers

		results = invite_suppliers(self, only_unsent=False)
		failed = [r for r in results if r.get("status") == "failed"]
		if failed:
			frappe.msgprint(
				"<br>".join(f"{frappe.utils.escape_html(r['display_name'] or '')}: {r['error']}" for r in failed),
				title=_("Some suppliers were not emailed"), indicator="orange",
			)
		return results

	def update_rfq_supplier_status(self, sup_name=None):
		"""Standard logic for registered rows; prospective rows are counted on their SQ link."""
		for supplier in self.suppliers:
			if sup_name is not None and sup_name not in (supplier.supplier, supplier.get("ub_prospective_supplier")):
				continue
			field, value = ("supplier", supplier.supplier) if supplier.supplier else (
				"ub_prospective_supplier", supplier.get("ub_prospective_supplier"))
			if not value:
				continue
			quote_status = _("Received")
			for item in self.items:
				count = frappe.db.sql(
					f"""SELECT COUNT(sqi.name) FROM `tabSupplier Quotation Item` sqi
					JOIN `tabSupplier Quotation` sq ON sq.name = sqi.parent
					WHERE sq.`{field}` = %s AND sqi.docstatus = 1 AND sqi.request_for_quotation_item = %s""",
					(value, item.name),
				)[0][0]
				if not count:
					quote_status = _("Pending")
			supplier.quote_status = quote_status

	def before_print(self, settings=None):
		if self.vendor or not self.suppliers:
			return
		first = next((s.supplier for s in self.suppliers if s.supplier), None)
		if first:
			self.update_supplier_part_no(first)

	# ---------------------------------------------------------------- workflow

	def before_update_after_submit(self):
		before = self.get_doc_before_save()
		old_state = before.get("workflow_state") if before else None
		new_state = self.get("workflow_state")
		if old_state != new_state:
			from universal_buying.ub_sourcing.api import assert_correction_comment

			assert_correction_comment(self, old_state, new_state)

	def on_update_after_submit(self):
		before = self.get_doc_before_save()
		old_state = before.get("workflow_state") if before else None
		new_state = self.get("workflow_state")
		sync_bid_status_with_workflow(self)
		if old_state != new_state:
			from universal_buying.ub_sourcing.notifications import notify_state_change

			notify_state_change(self, old_state, new_state)
