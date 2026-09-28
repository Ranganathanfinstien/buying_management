"""Lightweight document stand-ins so the rules can be tested without master data."""

import frappe


class FakeDoc(frappe._dict):
	doctype = "Purchase Receipt"

	def is_new(self):
		return not self.get("name")

	def is_internal_transfer(self):
		return False


def fake_receipt(**kwargs):
	items = [frappe._dict(r) for r in kwargs.pop("items", [])]
	doc = FakeDoc(
		{
			"name": "PR-TEST-0001",
			"company": "_Test UB Company",
			"supplier": "_Test UB Supplier",
			"posting_date": "2026-09-26",
			"is_return": 0,
			"ub_is_bonded": 0,
			"ub_green_card": 0,
			"docstatus": 0,
		}
	)
	doc.update(kwargs)
	doc["items"] = items
	return doc


def settings(values):
	"""side_effect for a patched get_setting(fieldname, company=None, default=None)."""

	def _get(fieldname, company=None, default=None):
		return values.get(fieldname, default)

	return _get
