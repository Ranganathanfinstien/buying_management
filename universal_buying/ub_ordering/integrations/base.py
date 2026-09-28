"""Supplier integration channels (BRD v2 6.19).

One ``Supplier Channel`` per connector; the PO keeps one ``PO Confirmation`` table (ub_confirmations)
whatever the connector. A connector implements ``send_order``, ``fetch_status`` and ``send_amendment``.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime

CONNECTORS = {
	"Email PDF": "universal_buying.ub_ordering.integrations.email_pdf.EmailPDFConnector",
	"Texas Instruments REST": "universal_buying.ub_ordering.integrations.texas.TexasInstrumentsConnector",
}


class SupplierConnector:
	"""Base class. Subclasses override the three actions they support."""

	label = "Connector"

	def __init__(self, channel, po):
		self.channel = channel
		self.po = po

	# ---- actions -----------------------------------------------------------------------
	def send_order(self):
		frappe.throw(_("{0} cannot send orders.").format(self.label))

	def fetch_status(self):
		frappe.throw(_("{0} cannot fetch order status.").format(self.label))

	def send_amendment(self):
		frappe.throw(_("{0} cannot send amendments.").format(self.label))

	# ---- helpers -----------------------------------------------------------------------
	def set_status(self, status=None, reference=None):
		values = {"ub_channel": self.channel.name}
		if status is not None:
			values["ub_channel_status"] = status
		if reference:
			values["ub_channel_reference"] = reference
		frappe.db.set_value("Purchase Order", self.po.name, values, update_modified=False)

	def record(self, event, rows, replace_status=False):
		"""Append PO Confirmation rows. ``rows`` are dicts with PO Confirmation fieldnames."""
		if replace_status:
			frappe.db.delete("PO Confirmation", {"parent": self.po.name, "parenttype": "Purchase Order",
				"parentfield": "ub_confirmations", "event": event})
		idx = frappe.db.sql("""select coalesce(max(idx), 0) from `tabPO Confirmation`
			where parent=%s and parenttype='Purchase Order' and parentfield='ub_confirmations'""", self.po.name)[0][0]
		for row in rows:
			idx += 1
			child = frappe.get_doc({"doctype": "PO Confirmation", "parent": self.po.name, "parenttype": "Purchase Order",
				"parentfield": "ub_confirmations", "idx": idx, "channel": self.channel.name, "event": event,
				"updated_on": now_datetime(), **row})
			child.db_insert()

	def requested_rows(self, event="Sent"):
		return [{"po_item": d.name, "line_no": d.idx, "item_code": d.item_code,
			"manufacturer_part_no": d.get("manufacturer_part_no"), "requested_qty": d.qty,
			"requested_date": d.schedule_date, "requested_rate": d.rate, "status": event} for d in self.po.items]

	def log_request(self, url, data=None, output=None, error=None, status="Completed"):
		try:
			frappe.get_doc({
				"doctype": "Integration Request", "integration_request_service": self.label,
				"request_description": self.label, "url": url, "data": frappe.as_json(data) if data is not None else None,
				"output": frappe.as_json(output) if output is not None else None,
				"error": frappe.as_json(error) if error is not None else None, "status": status,
				"reference_doctype": "Purchase Order", "reference_docname": self.po.name,
			}).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(title=f"{self.label} request log failed")


def get_channel(po):
	"""Channel on the PO, else the supplier's enabled channel (company specific first)."""
	if po.get("ub_channel"):
		ch = frappe.get_doc("Supplier Channel", po.ub_channel)
		return ch if ch.enabled else None
	rows = frappe.get_all("Supplier Channel", filters={"supplier": po.supplier, "enabled": 1},
		fields=["name", "company"], order_by="creation asc")
	rows = [r for r in rows if not r.company or r.company == po.company]
	rows.sort(key=lambda r: 0 if r.company else 1)
	return frappe.get_doc("Supplier Channel", rows[0].name) if rows else None


def get_connector(channel, po):
	path = channel.connector_class if channel.connector == "Custom" else CONNECTORS.get(channel.connector)
	if not path:
		frappe.throw(_("Supplier Channel {0} has no connector.").format(channel.name))
	cls = frappe.get_attr(path)
	if not issubclass(cls, SupplierConnector):
		frappe.throw(_("{0} is not a SupplierConnector.").format(path))
	return cls(channel, po)


def _load_po(name):
	po = frappe.get_doc("Purchase Order", name)
	po.check_permission("write")
	if po.docstatus != 1:
		frappe.throw(_("Submit the Purchase Order first."))
	channel = get_channel(po)
	if not channel:
		frappe.throw(_("Supplier {0} has no enabled Supplier Channel.").format(po.supplier))
	return get_connector(channel, po)


@frappe.whitelist()
def get_channel_info(purchase_order):
	"""A-17.4: which connector buttons the PO form shows."""
	frappe.has_permission("Purchase Order", "read", doc=purchase_order, throw=True)
	po = frappe.get_doc("Purchase Order", purchase_order)
	channel = get_channel(po)
	if not channel:
		return None
	return {"channel": channel.name, "connector": channel.connector, "channel_type": channel.channel_type}


@frappe.whitelist()
def send_order(purchase_order):
	return _load_po(purchase_order).send_order()


@frappe.whitelist()
def fetch_status(purchase_order):
	return _load_po(purchase_order).fetch_status()


@frappe.whitelist()
def send_amendment(purchase_order):
	return _load_po(purchase_order).send_amendment()
