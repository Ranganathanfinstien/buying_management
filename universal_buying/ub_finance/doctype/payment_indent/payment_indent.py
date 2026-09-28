# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt

"""Payment Indent (BRD v2 6.28).

One supplier, one currency, several of that supplier's submitted Purchase Orders.
V-28.1  requested amount <= indent_cap_percent % of the indent value.
V-28.2  on submit, above indent_approval_limit_inr (company currency) / indent_approval_limit_fx
        (any other currency) the user needs a role in indent_approver_roles.
A-28.1  on submit a draft Outward Payment Request is created per Purchase Order for its share of
        the requested amount and linked back on the PO row (new: the sources created nothing).

Fixed from the source: SQL built with str.format (injection), shortage only for the first PO line,
child table marked submittable with a duplicate amended_from, hard-coded 110 % / 5 lakh / 5000 /
"N-Purchase Manager", no server check of indent qty <= PO qty, supplier currency assumed INR.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

from universal_buying.universal_buying.settings import get_list, get_setting, has_any_role


class PaymentIndent(Document):
	# ------------------------------------------------------------------ lifecycle
	def validate(self):
		self.validate_supplier_fixed()
		self.validate_purchase_orders()
		self.validate_items()
		self.set_totals()
		self.validate_requested_amount()
		self.allocate_requested_amount()
		self.approval_required = 1 if self.needs_approval() else 0
		if self.docstatus == 0:
			self.status = "Draft"

	def before_submit(self):
		self.check_approval()

	def on_submit(self):
		self.db_set("status", "Submitted")
		self.create_payment_requests()

	def on_cancel(self):
		self.cancel_payment_requests()
		self.db_set("status", "Cancelled")

	# ------------------------------------------------------------------ validations
	def validate_supplier_fixed(self):
		if self.is_new():
			return
		before = self.get_doc_before_save()
		if before and before.supplier != self.supplier and (before.get("purchase_orders") or []):
			frappe.throw(_("Supplier cannot be changed after Purchase Orders are selected. Create a new indent."))

	def get_po_details(self, purchase_orders):
		"""{po: dict(supplier, company, currency, docstatus, status, grand_total, advance_paid)}."""
		if not purchase_orders:
			return {}
		rows = frappe.get_all(
			"Purchase Order",
			filters={"name": ("in", list(purchase_orders))},
			fields=["name", "supplier", "company", "currency", "docstatus", "status", "grand_total", "advance_paid"],
		)
		return {r.name: r for r in rows}

	def validate_purchase_orders(self):
		pos = [d.purchase_order for d in self.purchase_orders if d.purchase_order]
		if len(pos) != len(set(pos)):
			frappe.throw(_("A Purchase Order is listed more than once."))
		details = self.get_po_details(pos)
		currencies = set()
		for d in self.purchase_orders:
			po = details.get(d.purchase_order)
			if not po:
				frappe.throw(_("Row {0}: Purchase Order {1} not found").format(d.idx, d.purchase_order))
			if po.supplier != self.supplier:
				frappe.throw(
					_("Row {0}: Purchase Order {1} belongs to supplier {2}, not {3}.").format(
						d.idx, frappe.bold(d.purchase_order), po.supplier, self.supplier
					)
				)
			if po.company != self.company:
				frappe.throw(_("Row {0}: Purchase Order {1} is for another company.").format(d.idx, d.purchase_order))
			if po.docstatus != 1 or po.status in ("Closed", "On Hold", "Completed"):
				frappe.throw(
					_("Row {0}: Purchase Order {1} must be submitted and open (status {2}).").format(
						d.idx, d.purchase_order, po.status
					)
				)
			d.supplier, d.currency = po.supplier, po.currency
			d.grand_total, d.advance_paid = po.grand_total, po.advance_paid
			currencies.add(po.currency)
		if len(currencies) > 1:
			frappe.throw(
				_("All Purchase Orders on one indent must be in the same currency ({0}).").format(", ".join(sorted(currencies)))
			)
		if currencies:
			self.currency = currencies.pop()

	def validate_items(self):
		pos = {d.purchase_order for d in self.purchase_orders}
		for d in self.get("items") or []:
			if d.purchase_order not in pos:
				frappe.throw(
					_("Row {0}: Purchase Order {1} is not in the Purchase Orders table.").format(d.idx, d.purchase_order)
				)
			if flt(d.indent_qty) < 0:
				frappe.throw(_("Row {0}: Indent Qty cannot be negative.").format(d.idx))
			if flt(d.indent_qty) > flt(d.qty):
				frappe.throw(
					_("Row {0}: Indent Qty {1} cannot be more than the PO line qty {2}.").format(d.idx, d.indent_qty, d.qty)
				)
			d.value = flt(d.indent_qty) * flt(d.rate)
			d.currency = self.currency

	def set_totals(self):
		self.total_value = sum(flt(d.value) for d in self.get("items") or [])

	def cap_amount(self):
		cap = flt(get_setting("indent_cap_percent", company=self.company, default=110))
		return flt(self.total_value) * cap / 100.0, cap

	def validate_requested_amount(self):
		if flt(self.requested_amount) <= 0:
			frappe.throw(_("Requested Amount must be greater than zero."))
		limit, cap = self.cap_amount()
		if flt(self.requested_amount) > flt(limit, 2) + 0.005:
			frappe.throw(
				_("Requested Amount {0} cannot be more than {1}% of the indent value {2} (maximum {3}).").format(
					frappe.bold(flt(self.requested_amount)), cap, flt(self.total_value), frappe.bold(flt(limit, 2))
				),
				title=_("Indent Cap Exceeded"),
			)

	def allocate_requested_amount(self):
		"""Split the requested amount over the POs in proportion to each PO's indent value."""
		value_by_po = {}
		for d in self.get("items") or []:
			value_by_po[d.purchase_order] = value_by_po.get(d.purchase_order, 0) + flt(d.value)
		total = sum(value_by_po.values())
		for d in self.purchase_orders:
			d.allocated_amount = 0
		rows = [d for d in self.purchase_orders if value_by_po.get(d.purchase_order)]
		if not total or not rows:
			return
		remaining = flt(self.requested_amount)
		for i, d in enumerate(rows):
			if i == len(rows) - 1:
				d.allocated_amount = flt(remaining, 2)
			else:
				d.allocated_amount = flt(flt(self.requested_amount) * value_by_po[d.purchase_order] / total, 2)
				remaining -= d.allocated_amount

	# ------------------------------------------------------------------ approval (V-28.2)
	def approval_limit(self):
		company_currency = frappe.get_cached_value("Company", self.company, "default_currency")
		if not self.currency or self.currency == company_currency:
			return flt(get_setting("indent_approval_limit_inr", company=self.company, default=500000))
		return flt(get_setting("indent_approval_limit_fx", company=self.company, default=5000))

	def needs_approval(self):
		limit = self.approval_limit()
		return bool(limit) and flt(self.requested_amount) > limit

	def check_approval(self):
		if not self.needs_approval():
			return
		roles = get_list("indent_approver_roles")
		if frappe.session.user != "Administrator" and not has_any_role(roles):
			frappe.throw(
				_("Requested Amount {0} {1} is above the approval limit {2}. Only {3} can submit this indent.").format(
					self.currency, flt(self.requested_amount), flt(self.approval_limit()), ", ".join(roles) or _("an approver")
				),
				frappe.PermissionError,
				title=_("Approval Required"),
			)
		self.approved_by = frappe.session.user
		self.approved_on = now_datetime()

	# ------------------------------------------------------------------ Payment Request (A-28.1)
	def create_payment_requests(self):
		created = []
		for d in self.purchase_orders:
			if not flt(d.allocated_amount) or d.payment_request:
				continue
			pr = make_indent_payment_request(self, d.purchase_order, flt(d.allocated_amount))
			if pr:
				d.db_set("payment_request", pr.name)
				created.append(pr.name)
		if created:
			self.db_set("status", "Payment Requested")
			frappe.msgprint(
				_("Payment Request(s) created: {0}").format(
					", ".join(frappe.utils.get_link_to_form("Payment Request", n) for n in created)
				),
				alert=True,
				indicator="green",
			)

	def cancel_payment_requests(self):
		for d in self.purchase_orders:
			if not d.payment_request or not frappe.db.exists("Payment Request", d.payment_request):
				continue
			docstatus = frappe.db.get_value("Payment Request", d.payment_request, "docstatus")
			if docstatus == 0:
				frappe.delete_doc("Payment Request", d.payment_request, ignore_permissions=True)
				d.db_set("payment_request", None)
			elif docstatus == 1:
				frappe.throw(
					_("Cancel the submitted Payment Request {0} before cancelling this indent.").format(
						frappe.utils.get_link_to_form("Payment Request", d.payment_request)
					)
				)

	# ------------------------------------------------------------------ Get Items
	@frappe.whitelist()
	def get_po_items(self):
		"""Lines of the selected POs with MOQ / SPQ and current / +1 / +3 month shortage."""
		pos = [d.purchase_order for d in self.purchase_orders if d.purchase_order]
		if not pos:
			frappe.throw(_("Add Purchase Orders first."))
		rows = frappe.db.sql(
			"""
			select poi.parent as purchase_order, poi.name as po_detail, poi.item_code, poi.item_name,
				poi.description, poi.schedule_date, poi.qty, poi.received_qty, poi.rate, po.currency
			from `tabPurchase Order Item` poi
			inner join `tabPurchase Order` po on po.name = poi.parent
			where po.name in %(pos)s and po.supplier = %(supplier)s and po.docstatus = 1
			order by poi.schedule_date, poi.parent, poi.idx
			""",
			{"pos": tuple(pos), "supplier": self.supplier},
			as_dict=True,
		)
		item_codes = sorted({r.item_code for r in rows if r.item_code})
		fields = ["name", "min_order_qty"]
		if frappe.get_meta("Item").has_field("ub_standard_packing_qty"):
			fields.append("ub_standard_packing_qty")
		items = (
			{i.name: i for i in frappe.get_all("Item", filters={"name": ("in", item_codes)}, fields=fields)}
			if item_codes
			else {}
		)
		shortage = {m: _shortage_map(item_codes, self.company, m) for m in (0, 1, 3)}

		out = []
		for r in rows:
			it = items.get(r.item_code) or frappe._dict()
			pending = max(flt(r.qty) - flt(r.received_qty), 0)
			out.append({
				"purchase_order": r.purchase_order,
				"po_detail": r.po_detail,
				"item_code": r.item_code,
				"item_name": r.item_name,
				"description": r.description,
				"schedule_date": r.schedule_date,
				"qty": r.qty,
				"pending_qty": pending,
				"rate": r.rate,
				"currency": r.currency,
				"indent_qty": pending,
				"value": pending * flt(r.rate),
				"min_order_qty": it.get("min_order_qty"),
				"standard_packing_qty": it.get("ub_standard_packing_qty"),
				"cur_month_shortage": shortage[0].get(r.item_code, 0),
				"cur_plus1_month_shortage": shortage[1].get(r.item_code, 0),
				"cur_plus3_month_shortage": shortage[3].get(r.item_code, 0),
			})
		return out


def _shortage_map(item_codes, company, months):
	"""{item_code: shortage qty} from worker B's Requirement Log API; empty when not available."""
	if not item_codes:
		return {}
	try:
		from universal_buying.ub_planning.api import get_shortage_map
	except ImportError:
		return {}
	try:
		raw = get_shortage_map(item_codes, company, months=months) or {}
	except Exception:
		frappe.log_error(title="UB Finance: get_shortage_map failed")
		return {}
	out = {}
	for item, value in raw.items():
		if isinstance(value, dict):
			value = value.get("shortage_qty", value.get("shortage", value.get("qty", 0)))
		out[item] = flt(value)
	return out


def make_indent_payment_request(indent, purchase_order, amount):
	"""Create a draft Outward Payment Request against the PO for ``amount`` (capped at what the PO still allows).

	Uses ERPNext's make_payment_request when the user may create Payment Requests; otherwise (the
	indent approver is often a purchase role without Payment Request rights) the same document is
	built directly."""
	from erpnext.accounts.doctype.payment_request.payment_request import (
		get_amount,
		get_existing_payment_request_amount,
		make_payment_request,
	)

	po = frappe.get_doc("Purchase Order", purchase_order)
	available = flt(get_amount(po)) - flt(get_existing_payment_request_amount(po))
	if available <= 0:
		frappe.msgprint(
			_("No Payment Request made for {0}: nothing left to request on the Purchase Order.").format(purchase_order),
			indicator="orange",
		)
		return None
	grand_total = min(flt(amount), available)
	if grand_total < flt(amount):
		frappe.msgprint(
			_("Payment Request for {0} limited to {1} (open amount of the Purchase Order).").format(
				purchase_order, grand_total
			),
			indicator="orange",
		)

	has_draft = frappe.db.exists(
		"Payment Request", {"reference_doctype": "Purchase Order", "reference_name": purchase_order, "docstatus": 0}
	)
	pr = None
	if not has_draft and frappe.has_permission("Payment Request", "create"):
		pr = make_payment_request(
			dt="Purchase Order",
			dn=purchase_order,
			party_type="Supplier",
			party=po.supplier,
			party_name=po.supplier_name,
			payment_request_type="Outward",
			mute_email=1,
			return_doc=1,
		)
	if pr is None:
		pr = _build_payment_request(po)

	pr.grand_total = grand_total
	pr.subject = _("Payment Request for {0} (Payment Indent {1})").format(purchase_order, indent.name)
	pr.flags.ignore_permissions = True
	# with Accounts Settings "create_pr_in_draft_status" ERPNext has already inserted it
	pr.insert() if pr.is_new() else pr.save()
	pr.add_comment(
		"Comment", _("Created from Payment Indent {0}").format(frappe.utils.get_link_to_form("Payment Indent", indent.name))
	)
	return pr


def _build_payment_request(po):
	from erpnext.accounts.doctype.account.account import get_account_currency
	from erpnext.accounts.doctype.bank_account.bank_account import get_party_bank_account
	from erpnext.accounts.party import get_party_account

	party_account_currency = po.get("party_account_currency") or get_account_currency(
		get_party_account("Supplier", po.supplier, po.company)
	)
	pr = frappe.new_doc("Payment Request")
	pr.update({
		"payment_request_type": "Outward",
		"transaction_date": frappe.utils.nowdate(),
		"currency": po.currency,
		"party_account_currency": party_account_currency,
		"reference_doctype": po.doctype,
		"reference_name": po.name,
		"company": po.company,
		"party_type": "Supplier",
		"party": po.supplier,
		"party_name": po.supplier_name,
		"bank_account": get_party_bank_account("Supplier", po.supplier),
		"email_to": po.owner,
		"mute_email": 1,
		"cost_center": po.get("cost_center"),
		"project": po.get("project"),
	})
	return pr
