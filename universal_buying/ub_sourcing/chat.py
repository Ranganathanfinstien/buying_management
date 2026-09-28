"""Quotation discussion (BRD v1 section 15): one thread per RFQ supplier row.

The thread is keyed to the RFQ Supplier row, not to a quotation, so it survives quotation revisions and the
switch from Prospective Supplier to Supplier after onboarding.

- Buyers (anyone who may view the quotation comparison) read everything and post messages or internal notes.
- Suppliers read and post through their RFQ portal token; internal notes are never sent to them.
"""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, format_datetime, pretty_date

from universal_buying.universal_buying.utils import notify_users

MSG = "Quotation Message"
RFQ = "Request for Quotation"
RFQ_SUPPLIER = "Request for Quotation Supplier"
SQ = "Supplier Quotation"
MAX_LENGTH = 2000
_ROW_FIELDS = ["name", "parent", "supplier", "supplier_name", "ub_prospective_supplier"]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _clean(message):
	text = (message or "").strip()
	if not text:
		frappe.throw(_("Please type a message."))
	if len(text) > MAX_LENGTH:
		frappe.throw(_("A message can have at most {0} characters.").format(MAX_LENGTH))
	return text


def _rows(rfq_name):
	return frappe.get_all(RFQ_SUPPLIER, filters={"parent": rfq_name, "parenttype": RFQ}, fields=_ROW_FIELDS, order_by="idx")


def _row(rfq_name, row_name):
	row = frappe.db.get_value(RFQ_SUPPLIER, {"name": row_name, "parent": rfq_name, "parenttype": RFQ}, _ROW_FIELDS, as_dict=True)
	if not row:
		frappe.throw(_("This supplier is not on RFQ {0}.").format(rfq_name))
	return row


def _party(row):
	if row.ub_prospective_supplier and not row.supplier:
		return "Prospective Supplier", row.ub_prospective_supplier
	return "Supplier", row.supplier


def _party_name(row):
	if row.supplier_name:
		return row.supplier_name
	if row.ub_prospective_supplier and frappe.db.exists("Prospective Supplier", row.ub_prospective_supplier):
		return frappe.db.get_value("Prospective Supplier", row.ub_prospective_supplier, "supplier_name") or row.ub_prospective_supplier
	return row.supplier or row.ub_prospective_supplier


def rfq_of_quotation(sq_name):
	return frappe.db.get_value("Supplier Quotation Item", {"parent": sq_name, "request_for_quotation": ["is", "set"]},
		"request_for_quotation")


def row_for_quotation(sq_name, rfq_name=None):
	"""The RFQ Supplier row a quotation belongs to (matched on prospective supplier, then supplier)."""
	rfq_name = rfq_name or rfq_of_quotation(sq_name)
	if not rfq_name:
		return None
	sq = frappe.db.get_value(SQ, sq_name, ["supplier", "ub_prospective_supplier"], as_dict=True)
	if not sq:
		return None
	rows = _rows(rfq_name)
	if sq.ub_prospective_supplier:
		for row in rows:
			if row.ub_prospective_supplier == sq.ub_prospective_supplier:
				return row
	if sq.supplier:
		for row in rows:
			if row.supplier == sq.supplier:
				return row
	return None


def _latest_quotation(row):
	"""Newest live quotation of the row's party on its RFQ (for reference on new messages)."""
	from universal_buying.ub_sourcing.portal import party_quotations

	party_type, party = _party(row)
	quotes = party_quotations(row.parent, supplier=party if party_type == "Supplier" else None,
		prospective_supplier=party if party_type == "Prospective Supplier" else None)
	live = [q for q in quotes if not q.ub_revised] or quotes
	return live[-1].name if live else None


def _serialize(m):
	return {
		"name": m.name,
		"sender_type": m.sender_type,
		"sender_name": m.sender_name or m.sender or m.sender_type,
		"message": m.message,
		"is_internal": cint(m.is_internal),
		"supplier_quotation": m.supplier_quotation,
		"time": format_datetime(m.creation, "dd-MM-yyyy HH:mm"),
		"ago": pretty_date(m.creation),
	}


def get_messages(rfq_supplier_row, include_internal):
	filters = {"rfq_supplier_row": rfq_supplier_row}
	if not include_internal:
		filters["is_internal"] = 0
	rows = frappe.get_all(MSG, filters=filters, order_by="creation asc", limit_page_length=500,
		fields=["name", "sender_type", "sender", "sender_name", "message", "is_internal", "supplier_quotation", "creation"])
	return [_serialize(m) for m in rows]


def _insert(row, sender_type, message, is_internal=0):
	party_type, party = _party(row)
	user = frappe.session.user
	if sender_type == "Buyer":
		sender_name = frappe.utils.get_fullname(user)
	else:
		sender_name = _party_name(row)
		if user and user != "Guest":
			sender_name = f"{sender_name} ({frappe.utils.get_fullname(user)})"
	doc = frappe.get_doc({
		"doctype": MSG,
		"request_for_quotation": row.parent,
		"rfq_supplier_row": row.name,
		"party_type": party_type,
		"party": party,
		"party_name": _party_name(row),
		"supplier_quotation": _latest_quotation(row),
		"sender_type": sender_type,
		"sender": user if user != "Guest" else None,
		"sender_name": sender_name,
		"is_internal": 1 if (sender_type == "Buyer" and cint(is_internal)) else 0,
		"message": message,
	})
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc


def _supplier_portal_users(row):
	if not row.supplier:
		return []
	return frappe.get_all("Portal User", filters={"parent": row.supplier, "parenttype": "Supplier"}, pluck="user")


# ---------------------------------------------------------------------------
# buyer side (desk / comparison page)
# ---------------------------------------------------------------------------


def _assert_staff():
	from universal_buying.ub_sourcing.comparison import _assert_can_view

	_assert_can_view()


@frappe.whitelist()
def get_threads(rfq_name):
	"""{rfq_supplier_row: {party_name, messages}} for every supplier on the RFQ."""
	_assert_staff()
	frappe.get_doc(RFQ, rfq_name).check_permission("read")
	return {
		row.name: {"party_name": _party_name(row), "messages": get_messages(row.name, include_internal=True)}
		for row in _rows(rfq_name)
	}


@frappe.whitelist()
def get_thread_for_quotation(sq_name):
	"""Thread of the supplier behind a Supplier Quotation (for the quotation form)."""
	_assert_staff()
	rfq_name = rfq_of_quotation(sq_name)
	row = row_for_quotation(sq_name, rfq_name) if rfq_name else None
	if not row:
		return {"rfq": rfq_name, "row": None, "messages": []}
	return {"rfq": rfq_name, "row": row.name, "party_name": _party_name(row),
		"messages": get_messages(row.name, include_internal=True)}


@frappe.whitelist(methods=["POST"])
def post_message(rfq_name, rfq_supplier_row, message, is_internal=0):
	"""Buyer message to a supplier (or internal note). Returns the updated thread."""
	_assert_staff()
	rfq = frappe.get_doc(RFQ, rfq_name)
	rfq.check_permission("read")
	if rfq.docstatus == 2:
		frappe.throw(_("RFQ {0} is cancelled.").format(rfq_name))
	row = _row(rfq_name, rfq_supplier_row)
	doc = _insert(row, "Buyer", _clean(message), is_internal)

	if not doc.is_internal:
		users = _supplier_portal_users(row)
		if users:
			notify_users(users, _("New message from the buyer on RFQ {0}").format(rfq_name),
				frappe.utils.escape_html(doc.message), RFQ, rfq_name)
	return get_messages(row.name, include_internal=True)


# ---------------------------------------------------------------------------
# supplier side (RFQ portal token)
# ---------------------------------------------------------------------------


def _row_from_token(token):
	from universal_buying.ub_sourcing.portal import get_row_by_token

	row = get_row_by_token(token)
	return frappe._dict({k: row.get(k) for k in _ROW_FIELDS})


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=240, seconds=60 * 60)
def portal_get_thread(token):
	row = _row_from_token(token)
	return get_messages(row.name, include_internal=False)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=40, seconds=60 * 60)
def portal_post_message(token, message):
	row = _row_from_token(token)
	if frappe.db.get_value(RFQ, row.parent, "docstatus") == 2:
		frappe.throw(_("This Request for Quotation is no longer active."))
	doc = _insert(row, "Supplier", _clean(message))

	owner = frappe.db.get_value(RFQ, row.parent, "owner")
	notify_users([owner], _("{0} replied on RFQ {1}").format(doc.party_name, row.parent),
		frappe.utils.escape_html(doc.message), RFQ, row.parent)
	return get_messages(row.name, include_internal=False)
