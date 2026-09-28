"""Texas Instruments REST connector.

Changes from the source:
* credentials and account numbers come from the Supplier Channel (no hard-coded company maps),
* TI part number = PO line ``manufacturer_part_no`` (no TI Item Mapping doctype),
* responses go to the PO Confirmation table (one table for every connector),
* request logs go to the standard Integration Request doctype.
"""

import json

import frappe
import requests
from frappe import _
from frappe.integrations.utils import make_get_request, make_post_request
from frappe.utils import add_to_date, format_date, now_datetime, time_diff_in_seconds

from universal_buying.ub_ordering.integrations.base import SupplierConnector

LIVE_URL = "https://transact.ti.com"
SANDBOX_URL = "https://transact-pre.ti.com"
MAX_RETRIES = 3
DELIVERY_STATES = ("Not Delivered", "Partially Delivered", "Fully Delivered")


class TexasInstrumentsConnector(SupplierConnector):
	label = "Texas Instruments REST"

	def __init__(self, channel, po):
		super().__init__(channel, po)
		self.base_url = (channel.base_url or (SANDBOX_URL if channel.sandbox_mode else LIVE_URL)).rstrip("/")
		self.auth_url = self.base_url + "/v1/oauth/accesstoken"
		self.orders_url = self.base_url + "/v2/backlog/orders"
		self.change_url = self.base_url + "/v2/backlog/orders/changeByCustomerPurchaseOrderNumber"
		self._retried = False

	# ---- auth ---------------------------------------------------------------------------
	def _cache_key(self):
		return f"ub_ti_token::{self.channel.name}"

	def get_token(self):
		cached = frappe.cache.get_value(self._cache_key()) or {}
		if cached.get("token") and time_diff_in_seconds(cached.get("expiry"), now_datetime()) > 150:
			return cached["token"]
		return self.fetch_token()

	def fetch_token(self):
		client_id = self.channel.client_id
		secret = self.channel.get_password("client_secret", raise_exception=False)
		if not (client_id and secret):
			frappe.throw(_("Client ID / Secret are not set on Supplier Channel {0}.").format(self.channel.name))
		res = make_post_request(self.auth_url, data={"client_id": client_id, "client_secret": secret,
			"grant_type": "client_credentials"})
		token = "{} {}".format((res.get("token_type") or "Bearer").title(), res.get("access_token"))
		expiry = add_to_date(None, seconds=int(res.get("expires_in") or 3600))
		frappe.cache.set_value(self._cache_key(), {"token": token, "expiry": str(expiry)},
			expires_in_sec=int(res.get("expires_in") or 3600))
		return token

	def headers(self, json_body=True):
		h = {"authorization": self.get_token()}
		if json_body:
			h["content-type"] = "application/json"
		return h

	def request(self, method, url, data=None):
		try:
			if method == "post":
				res = make_post_request(url, headers=self.headers(), data=json.dumps(data))
			else:
				res = make_get_request(url, headers=self.headers(json_body=False))
		except requests.exceptions.HTTPError as e:
			if e.response is not None and e.response.status_code in (401, 403) and not self._retried:
				self._retried = True
				frappe.cache.delete_value(self._cache_key())
				return self.request(method, url, data)
			err = None
			try:
				err = e.response.json()
			except Exception:
				err = str(e)
			self.log_request(url, data, error=err, status="Failed")
			frappe.throw(_("Texas Instruments rejected the request: {0}").format(frappe.as_json(err)))
		self.log_request(url, data, output=res)
		return res or {}

	# ---- payloads -----------------------------------------------------------------------
	def _order_header(self):
		ch = self.channel
		if not ch.ship_to_account or not ch.end_customer_number:
			frappe.throw(_("Set Ship-to Account No and End Customer No on Supplier Channel {0}.").format(ch.name))
		head = {"customerPurchaseOrderNumber": self.po.name, "shipToAccountNumber": ch.ship_to_account,
			"endCustomerNumber": ch.end_customer_number}
		if ch.checkout_profile_id:
			head["checkoutProfileId"] = ch.checkout_profile_id
		return head

	def _line(self, d, change=None):
		if not d.get("manufacturer_part_no"):
			frappe.throw(_("Row {0}: TI part number (MPN) is missing.").format(d.idx))
		line = {
			"customerLineItemNumber": d.idx, "tiPartNumber": d.manufacturer_part_no,
			"customerAnticipatedUnitPrice": d.rate, "customerCurrencyCode": self.po.currency,
			"schedules": [{"requestedQuantity": d.qty, "requestedDeliveryDate": format_date(d.schedule_date, "yyyy-mm-dd")}],
		}
		if change:
			line["lineItemChangeIndicator"] = change
		return line

	def _sent_lines(self):
		return set(frappe.get_all("PO Confirmation", filters={"parent": self.po.name, "parenttype": "Purchase Order",
			"event": "Sent"}, pluck="po_item"))

	# ---- actions ------------------------------------------------------------------------
	def send_order(self):
		sent = self._sent_lines()
		lines = [d for d in self.po.items if d.name not in sent]
		if not lines:
			frappe.msgprint(_("All lines are already sent."))
			return None
		order = self._order_header()
		order["lineItems"] = [self._line(d) for d in lines]
		res = self.request("post", self.orders_url, {"order": order})
		self._apply_response(res)
		self.record("Sent", [r for r in self.requested_rows("Sent") if r["po_item"] in {d.name for d in lines}])
		return self.po.get("ub_channel_status")

	def send_amendment(self):
		order = self._order_header()
		order.pop("checkoutProfileId", None)
		order["lineItems"] = [self._line(d, "U") for d in self.po.items if d.name in self._sent_lines()]
		if not order["lineItems"]:
			frappe.throw(_("Nothing sent yet; use Send Order."))
		res = self.request("post", self.change_url, {"order": order})
		self._apply_response(res)
		self.record("Amendment", self.requested_rows("Amendment Sent"))
		return "Amendment Sent"

	def fetch_status(self):
		res = self.request("get", self.orders_url + "?customerPurchaseOrderNumber=" + self.po.name)
		self._apply_response(res, record_lines=True)
		return self.po.get("ub_channel_status")

	def _apply_response(self, res, record_lines=False):
		orders = (res or {}).get("orders") or []
		if not orders:
			frappe.throw(_("Unexpected response from Texas Instruments."))
		head = orders[0]
		status = head.get("orderStatus")
		self.set_status(status, head.get("orderNumber") if status != "REJECT" else None)
		self.po.ub_channel_status = status

		messages = [m.get("message") for m in head.get("messages") or []]
		by_line = {str(d.idx): d for d in self.po.items}
		rows = []
		for order in orders:
			for li in order.get("lineItems") or []:
				for m in li.get("messages") or []:
					messages.append(_("Line {0}: {1}").format(li.get("customerLineItemNumber"), m.get("message")))
				if not record_lines or li.get("status") not in DELIVERY_STATES:
					continue
				d = by_line.get(str(li.get("customerLineItemNumber")))
				sched = (li.get("schedules") or [{}])[0]
				confs = sched.get("confirmations") or []
				rows.append({
					"po_item": d.name if d else None, "line_no": li.get("customerLineItemNumber"),
					"item_code": d.item_code if d else None, "manufacturer_part_no": li.get("tiPartNumber"),
					"requested_qty": sched.get("requestedQuantity"), "requested_date": sched.get("requestedDeliveryDate"),
					"requested_rate": li.get("customerAnticipatedUnitPrice"),
					"confirmed_qty": sum(c.get("scheduledQuantity") or 0 for c in confs),
					"shipped_qty": sum(c.get("shippedQuantity") or 0 for c in confs),
					"confirmed_date": confs[0].get("estimatedDeliveryDate") if confs else None,
					"confirmed_rate": li.get("tiUnitPrice"), "status": li.get("status"),
					"reference": head.get("orderNumber"),
				})
		if rows:
			self.record("Status", rows, replace_status=True)
		if messages:
			frappe.msgprint("<br>".join(frappe.utils.escape_html(m or "") for m in messages), title=_("Texas Instruments"))
