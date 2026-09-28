"""Purchase Receipt controller override (BRD v2 6.23).

Generic receiving rules only: no legacy freeze, client-specific asset fields or stencil/combo hard-coding.
"""

import frappe
from erpnext.stock.doctype.purchase_receipt.purchase_receipt import PurchaseReceipt
from frappe import _
from frappe.utils import cint, flt

from universal_buying.ub_inward.batch import prepare_draft_delete, validate_batches_before_submit
from universal_buying.ub_inward.iqc import check_iqc_gate, iqc_exempt
from universal_buying.ub_inward.receipt import (
	apply_boe_exchange_rate,
	apply_bonded_route,
	notify_manufacturing_shortage,
	set_receipt_flags,
	validate_boe,
	validate_gate_entry,
	validate_over_receipt,
	validate_rows_from_po,
)
from universal_buying.ub_inward.utils import bonded_route_active
from universal_buying.universal_buying.settings import get_setting

BACKGROUND_SUBMIT_TIMEOUT = 4600
BACKGROUND_CANCEL_TIMEOUT = 2000


class UBPurchaseReceipt(PurchaseReceipt):
	# ------------------------------------------------------------------ validate
	def before_validate(self):
		super().before_validate()
		set_receipt_flags(self)
		apply_bonded_route(self)
		apply_boe_exchange_rate(self)

	def validate(self):
		super().validate()
		if self.get("is_return") or getattr(self, "_action", None) == "update_after_submit":
			return
		validate_rows_from_po(self)
		validate_gate_entry(self)
		validate_over_receipt(self)
		notify_manufacturing_shortage(self)

	def validate_inspection(self):
		"""Replace ERPNext's Stock Settings driven check with the iqc_gate setting (V-23.5)."""
		if self.get("is_return") or getattr(self, "_action", None) == "update_after_submit":
			return
		submitting = self.docstatus == 1
		check_iqc_gate(self, submitting=submitting)
		if submitting and not iqc_exempt(self):
			for row in self.get("items"):
				# a rejected QI whose qty was not moved to rejected_qty still follows Stock Settings
				if row.get("quality_inspection") and flt(row.qty) > 0:
					self.validate_qi_rejection(row)

	def before_submit(self):
		parent = getattr(super(), "before_submit", None)
		if parent:
			parent()
		if self.get("is_return"):
			return
		validate_boe(self)
		validate_batches_before_submit(self, assign=True, bonded=bonded_route_active(self))

	def run_submit_prechecks(self):
		"""Submit-time rules that can be checked before queueing a background submit (no side effects)."""
		if self.get("is_return"):
			return
		check_iqc_gate(self, submitting=True)
		validate_boe(self)
		validate_batches_before_submit(self, assign=False, bonded=bonded_route_active(self))

	# ------------------------------------------------------ A-23.1 background
	def _run_in_background(self):
		if frappe.flags.in_test or getattr(frappe, "in_test", False) or frappe.flags.in_import:
			return False
		if frappe.flags.ub_force_foreground:
			return False
		limit = cint(get_setting("background_submit_rows", company=self.company))
		return bool(limit and len(self.get("items") or []) > limit)

	@frappe.whitelist()
	def submit(self):
		if not self._run_in_background():
			return self._submit()

		# persist the latest client values as a draft, run the submit checks now so the user sees errors
		# immediately, then submit in the background (execute_action unlocks and calls _submit).
		self.docstatus = 0
		self.save()
		self.run_submit_prechecks()
		self._queue("submit", BACKGROUND_SUBMIT_TIMEOUT)
		return self

	@frappe.whitelist()
	def cancel(self):
		if not self._run_in_background():
			return self._cancel()
		self._queue("cancel", BACKGROUND_CANCEL_TIMEOUT)
		return self

	def _queue(self, action, timeout):
		try:
			self.queue_action(action, queue="long", timeout=timeout)
		except frappe.DocumentLockedError:
			frappe.msgprint(
				_("This Purchase Receipt is already queued or being processed in the background."),
				indicator="orange",
				alert=True,
			)
			return
		self.flags.ub_background_action = action
		frappe.msgprint(
			_(
				"{0} of {1} rows has been queued. You will see the result on the document when it completes; errors are added as a comment."
			).format(_("Submit") if action == "submit" else _("Cancel"), len(self.get("items") or [])),
			title=_("Queued"),
			indicator="blue",
		)

	# ------------------------------------------------------------ cancel/trash
	def on_cancel(self):
		super().on_cancel()
		discrepancy = self.get("ub_inward_discrepancy")
		if discrepancy and frappe.db.get_value("Inward Discrepancy", discrepancy, "docstatus") == 1:
			doc = frappe.get_doc("Inward Discrepancy", discrepancy)
			doc.flags.ignore_permissions = True
			doc.flags.ub_cancelled_by_receipt = True
			doc.cancel()

	def on_trash(self):
		prepare_draft_delete(self)
		super().on_trash()
