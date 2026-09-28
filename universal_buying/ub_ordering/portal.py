"""Supplier portal after the PO (BRD v2 6.21).

* A-17.2  PO submit -> portal status Pending Acceptance, supplier portal users are emailed.
* Acknowledge -> append-only PO Acknowledgement, latest wins, portal status Accepted, buyer emailed.
* Material status -> append-only PO Material Status (rules in the doctype controller).
* Shipment -> PO Shipment against PO lines, over-shipping blocked; portal status becomes
  Partially Dispatched / Dispatched from submitted shipments; delivery status from the receipt
  (3-Way) or the invoice (2-Way).
* Uploads -> supplier invoice documents (unique bill number per PO) and QC attachments as child rows.

Every whitelisted endpoint resolves the supplier from the session (never from the client).
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, get_url, getdate, now_datetime

from universal_buying.ub_ordering.permissions import get_user_suppliers, supplier_portal_users
from universal_buying.universal_buying.utils import notify_users, users_with_role

PO = "Purchase Order"
PENDING_ACCEPTANCE = "Pending Acceptance"
ACCEPTED = "Accepted"
PARTIALLY_DISPATCHED = "Partially Dispatched"
DISPATCHED = "Dispatched"
HIGH_PRIORITY_STATUSES = ("Ready to Dispatch", "Dispatched", "Delayed")
QTY_TOLERANCE = 0.000001


# ======================================================================================
# Access
# ======================================================================================
def assert_po_access(po_name, submitted=True):
	"""Return the PO supplier when the session user is a portal user of it."""
	suppliers = get_user_suppliers()
	if not suppliers:
		frappe.throw(_("Your login is not linked to any supplier."), frappe.PermissionError)
	row = frappe.db.get_value(PO, po_name, ["supplier", "docstatus"], as_dict=True)
	if not row or row.supplier not in suppliers:
		frappe.throw(_("You do not have access to this Purchase Order."), frappe.PermissionError)
	if submitted and row.docstatus != 1:
		frappe.throw(_("This Purchase Order is not open."))
	return row.supplier


def _attach_file(file_url, po_name):
	"""Attach a file the portal user uploaded themselves (never someone else's file_url)."""
	name = frappe.db.get_value("File", {"file_url": file_url, "owner": frappe.session.user}, "name")
	if not name:
		frappe.throw(_("Upload the file first."))
	frappe.db.set_value("File", name, {"attached_to_doctype": PO, "attached_to_name": po_name})


def _append_po_child(po_name, child_doctype, parentfield, values):
	"""Append one row to a submitted PO child table without re-saving the PO."""
	idx = frappe.db.sql(
		f"select coalesce(max(idx), 0) + 1 from `tab{child_doctype}` where parent=%s and parenttype=%s and parentfield=%s",
		(po_name, PO, parentfield),
	)[0][0]
	row = frappe.get_doc({"doctype": child_doctype, "parent": po_name, "parenttype": PO,
		"parentfield": parentfield, "idx": idx, **values})
	row.db_insert()
	frappe.db.set_value(PO, po_name, "modified", now_datetime(), update_modified=False)
	return row


# ======================================================================================
# Recipients
# ======================================================================================
def buyer_recipients(po):
	owner = po.get("owner")
	if owner and owner not in ("Administrator", "Guest"):
		return [owner]
	return users_with_role("Purchase Manager")


def _safe_notify(users, subject, message, doc):
	try:
		notify_users(users, subject, message, doc.doctype, doc.name)
	except Exception:
		frappe.log_error(title=f"Supplier portal notification failed: {doc.name}")


# ======================================================================================
# A-17.2: PO submitted
# ======================================================================================
def on_po_submit(po):
	if not po.get("ub_portal_status"):
		po.db_set("ub_portal_status", PENDING_ACCEPTANCE, update_modified=False)
	users = supplier_portal_users(po.supplier)
	if not users:
		return
	link = get_url(f"/supplier_portal/purchase_orders?name={po.name}")
	_safe_notify(
		users,
		_("New Purchase Order {0} - please acknowledge").format(po.name),
		_("Purchase Order {0} has been issued to you. Please review it and acknowledge it with a confirmed delivery date."
			"<br><br><a href=\"{1}\">Open in the Supplier Portal</a>").format(po.name, link),
		po,
	)


# ======================================================================================
# Acknowledgement snapshot (called from PO Acknowledgement.after_insert)
# ======================================================================================
def sync_acknowledgement(ack):
	later = frappe.db.exists("PO Acknowledgement", {
		"purchase_order": ack.purchase_order, "name": ["!=", ack.name], "acknowledged_on": [">", ack.acknowledged_on]})
	if later:
		return
	values = {"ub_confirmed_delivery_date": ack.confirmed_delivery_date}
	current = frappe.db.get_value(PO, ack.purchase_order, "ub_portal_status")
	if current in (None, "", PENDING_ACCEPTANCE):
		values["ub_portal_status"] = ACCEPTED
	frappe.db.set_value(PO, ack.purchase_order, values, update_modified=False)

	po = frappe.get_doc(PO, ack.purchase_order)
	_safe_notify(
		buyer_recipients(po),
		_("PO {0} acknowledged by {1}").format(po.name, po.supplier_name or po.supplier),
		_("Purchase Order {0} was {1} by {2}. Confirmed delivery date: {3}.{4}").format(
			po.name, (ack.event_type or "").lower(), po.supplier_name or po.supplier,
			frappe.format(ack.confirmed_delivery_date, {"fieldtype": "Date"}),
			("<br>" + _("Notes: {0}").format(frappe.utils.escape_html(ack.notes))) if ack.notes else ""),
		po,
	)


def sync_material_status(ms):
	frappe.db.set_value(PO, ms.purchase_order, {
		"ub_material_status": ms.status,
		"ub_expected_dispatch_date": ms.expected_dispatch_date,
	}, update_modified=False)
	po = frappe.get_doc(PO, ms.purchase_order)
	prefix = "[!] " if ms.status in HIGH_PRIORITY_STATUSES else ""
	_safe_notify(
		buyer_recipients(po),
		prefix + _("PO {0} material status: {1}").format(po.name, ms.status),
		_("Supplier {0} reported {1} for Purchase Order {2}. Remarks: {3}").format(
			po.supplier_name or po.supplier, frappe.bold(ms.status), po.name, frappe.utils.escape_html(ms.remarks or "")),
		po,
	)


# ======================================================================================
# Shipments
# ======================================================================================
def ordered_map(po_name):
	return {r.name: r for r in frappe.get_all("Purchase Order Item", filters={"parent": po_name, "parenttype": PO},
		fields=["name", "item_code", "item_name", "uom", "qty", "idx"], order_by="idx")}


def shipped_map(po_name, exclude=None, submitted_only=False):
	"""{po_item: qty} over non-cancelled (or submitted) PO Shipments of the PO."""
	cond = "s.docstatus = 1" if submitted_only else "s.docstatus < 2"
	return {r[0]: flt(r[1]) for r in frappe.db.sql(
		f"""select si.po_item, sum(si.shipped_qty) from `tabPO Shipment Item` si
		join `tabPO Shipment` s on s.name = si.parent
		where s.purchase_order = %s and {cond} and s.name != %s group by si.po_item""",
		(po_name, exclude or ""))}


def refresh_po_dispatch_status(po_name):
	"""Portal status from submitted shipments: Partially Dispatched / Dispatched (else back to acceptance)."""
	ordered = ordered_map(po_name)
	shipped = shipped_map(po_name, submitted_only=True)
	if any(flt(v) > 0 for v in shipped.values()):
		full = all(flt(shipped.get(k)) >= flt(r.qty) - QTY_TOLERANCE for k, r in ordered.items())
		status = DISPATCHED if full else PARTIALLY_DISPATCHED
	else:
		acked = frappe.db.exists("PO Acknowledgement", {"purchase_order": po_name})
		status = ACCEPTED if acked else PENDING_ACCEPTANCE
	if frappe.db.get_value(PO, po_name, "ub_portal_status") != status:
		frappe.db.set_value(PO, po_name, "ub_portal_status", status, update_modified=False)
	return status


def _receipt_required(po_name):
	from universal_buying.universal_buying.doctype.po_type.po_type import get_po_type

	return cint(get_po_type(frappe.db.get_value(PO, po_name, "ub_po_type")).get("receipt_required"))


def delivery_status(po_name):
	"""In Transit / Partially Delivered / Delivered from the receipt (3-Way) or the invoice (2-Way)."""
	ordered = flt(frappe.db.sql("select sum(qty) from `tabPurchase Order Item` where parent=%s", po_name)[0][0])
	if ordered <= 0:
		return None
	if _receipt_required(po_name):
		done = frappe.db.sql("""select sum(pri.received_qty) from `tabPurchase Receipt Item` pri
			join `tabPurchase Receipt` pr on pr.name = pri.parent
			where pr.docstatus = 1 and pri.purchase_order = %s""", po_name)[0][0]
	else:
		done = frappe.db.sql("""select sum(pii.qty) from `tabPurchase Invoice Item` pii
			join `tabPurchase Invoice` pi on pi.name = pii.parent
			where pi.docstatus = 1 and pii.purchase_order = %s""", po_name)[0][0]
	done = flt(done)
	if done <= 0:
		return "In Transit"
	return "Delivered" if done >= ordered - QTY_TOLERANCE else "Partially Delivered"


def refresh_shipment_delivery_status(doc, method=None):
	"""Purchase Receipt / Purchase Invoice on_submit / on_cancel hook."""
	pos = {r.get("purchase_order") for r in doc.get("items") or [] if r.get("purchase_order")}
	for po_name in pos:
		status = delivery_status(po_name)
		if not status:
			continue
		for name in frappe.get_all("PO Shipment", filters={"purchase_order": po_name, "docstatus": 1}, pluck="name"):
			frappe.db.set_value("PO Shipment", name, "delivery_status", status, update_modified=False)


# ======================================================================================
# Whitelisted portal endpoints
# ======================================================================================
@frappe.whitelist()
def acknowledge_po(po_id, confirmed_delivery_date, notes=None):
	supplier = assert_po_access(po_id)
	doc = frappe.get_doc({
		"doctype": "PO Acknowledgement", "purchase_order": po_id, "supplier": supplier,
		"confirmed_delivery_date": getdate(confirmed_delivery_date) if confirmed_delivery_date else None,
		"notes": notes,
	})
	doc.insert(ignore_permissions=True)
	return {"name": doc.name, "event_type": doc.event_type, "confirmed_delivery_date": doc.confirmed_delivery_date}


@frappe.whitelist()
def update_material_status(po_id, status, remarks=None, expected_dispatch_date=None):
	supplier = assert_po_access(po_id)
	doc = frappe.get_doc({
		"doctype": "PO Material Status", "purchase_order": po_id, "supplier": supplier, "status": status,
		"remarks": remarks, "expected_dispatch_date": getdate(expected_dispatch_date) if expected_dispatch_date else None,
	})
	doc.insert(ignore_permissions=True)
	return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def upload_invoice(purchase_order, file_url, bill_no, bill_date=None, amount=None):
	assert_po_access(purchase_order)
	bill_no = (bill_no or "").strip()
	if not bill_no:
		frappe.throw(_("Supplier Invoice No is required."))
	if not file_url:
		frappe.throw(_("Attach the invoice document."))
	if frappe.db.exists("Portal PO Invoice", {"parent": purchase_order, "parenttype": PO, "bill_no": bill_no}):
		frappe.throw(_("Invoice No {0} is already uploaded for this Purchase Order.").format(frappe.bold(bill_no)))
	_attach_file(file_url, purchase_order)
	row = _append_po_child(purchase_order, "Portal PO Invoice", "ub_invoice_uploads", {
		"bill_no": bill_no, "bill_date": getdate(bill_date) if bill_date else None, "amount": flt(amount),
		"attachment": file_url, "uploaded_on": now_datetime(), "uploaded_by": frappe.session.user,
	})
	po = frappe.get_doc(PO, purchase_order)
	_safe_notify(buyer_recipients(po), _("Invoice {0} uploaded for PO {1}").format(bill_no, po.name),
		_("Supplier {0} uploaded invoice {1} against Purchase Order {2}.").format(po.supplier_name or po.supplier, bill_no, po.name), po)
	return {"name": row.name}


@frappe.whitelist()
def add_qc_attachment(purchase_order, file_url, title=None, po_item=None):
	assert_po_access(purchase_order)
	if not file_url:
		frappe.throw(_("Attach the QC document."))
	item_code = item_name = None
	if po_item:
		line = frappe.db.get_value("Purchase Order Item", {"name": po_item, "parent": purchase_order},
			["item_code", "item_name"], as_dict=True)
		if not line:
			frappe.throw(_("The line is not part of this Purchase Order."))
		item_code, item_name = line.item_code, line.item_name
	_attach_file(file_url, purchase_order)
	row = _append_po_child(purchase_order, "Portal PO QC Attachment", "ub_qc_attachments", {
		"po_item": po_item, "item_code": item_code, "item_name": item_name,
		"title": (title or "").strip() or file_url.rsplit("/", 1)[-1], "attachment": file_url,
		"uploaded_on": now_datetime(), "uploaded_by": frappe.session.user,
	})
	return {"name": row.name}


@frappe.whitelist()
def get_po_lines_for_shipment(purchase_order, shipment=None):
	assert_po_access(purchase_order)
	return shipment_lines(purchase_order, shipment)


def shipment_lines(purchase_order, shipment=None):
	other = shipped_map(purchase_order, exclude=shipment)
	out = []
	for name, r in ordered_map(purchase_order).items():
		already = flt(other.get(name))
		out.append({"po_item": name, "item_code": r.item_code, "item_name": r.item_name, "uom": r.uom,
			"ordered_qty": flt(r.qty), "already_shipped_qty": already, "remaining_qty": max(flt(r.qty) - already, 0)})
	return out


_SHIPMENT_FIELDS = ("shipment_date", "expected_arrival_date", "mode_of_transport", "transporter", "lr_awb_no",
	"tracking_url", "vehicle_no", "driver_name", "driver_contact", "attachment", "remarks")


@frappe.whitelist()
def create_shipment(payload):
	"""Supplier dispatches (part of) a PO: creates and submits a PO Shipment."""
	data = frappe.parse_json(payload) or {}
	po_name = data.get("purchase_order")
	assert_po_access(po_name)
	doc = frappe.new_doc("PO Shipment")
	doc.purchase_order = po_name
	for f in _SHIPMENT_FIELDS:
		if data.get(f):
			doc.set(f, data.get(f))
	for it in data.get("items") or []:
		if flt(it.get("shipped_qty")) > 0:
			doc.append("items", {"po_item": it.get("po_item"), "shipped_qty": flt(it.get("shipped_qty"))})
	if not doc.items:
		frappe.throw(_("Enter the quantity shipped on at least one line."))
	if doc.attachment:
		_attach_file(doc.attachment, po_name)
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	return {"name": doc.name, "shipment_status": doc.shipment_status}
