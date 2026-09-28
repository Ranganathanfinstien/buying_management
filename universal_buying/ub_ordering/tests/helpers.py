"""Test data for UB Ordering tests. Everything is created inside the test transaction (rolled back)."""

from contextlib import ExitStack
from unittest.mock import patch

import frappe
from frappe.utils import add_days, today

SUPPLIER = "_Test UB Ordering Supplier"
ITEM = "_Test UB Ordering Item"


def settings(values):
	"""side_effect for a patched get_setting(fieldname, company=None, default=None)."""

	def _get(fieldname, company=None, default=None):
		return values.get(fieldname, default)

	return _get


def get_company():
	return (frappe.db.get_value("Company", {"abbr": "UBD"}, "name")
		or frappe.defaults.get_global_default("company")
		or frappe.db.get_value("Company", {}, "name"))


def get_warehouse(company):
	return (frappe.db.get_value("Warehouse", {"company": company, "is_group": 0, "name": ["like", "Stores%"]}, "name")
		or frappe.db.get_value("Warehouse", {"company": company, "is_group": 0}, "name"))


def leaf(doctype):
	return frappe.db.get_value(doctype, {"is_group": 0}, "name")


def make_item(code=ITEM, moq=0):
	if not frappe.db.exists("Item", code):
		frappe.get_doc({
			"doctype": "Item", "item_code": code, "item_name": code, "item_group": leaf("Item Group"),
			"stock_uom": "Nos", "is_stock_item": 1, "is_purchase_item": 1, "min_order_qty": moq,
		}).insert(ignore_permissions=True)
	else:
		frappe.db.set_value("Item", code, "min_order_qty", moq)
	return code


def make_supplier(name=SUPPLIER):
	if not frappe.db.exists("Supplier", name):
		doc = frappe.get_doc({"doctype": "Supplier", "supplier_name": name, "supplier_group": leaf("Supplier Group")})
		doc.flags.ignore_permissions = True
		doc.insert()
	if frappe.get_meta("Supplier").has_field("workflow_state"):
		frappe.db.set_value("Supplier", name, "workflow_state", "Enabled")
	return name


def buying_price_list(company):
	name = frappe.db.get_single_value("Buying Settings", "buying_price_list") or "Standard Buying"
	if not frappe.db.exists("Price List", name):
		frappe.get_doc({"doctype": "Price List", "price_list_name": name, "buying": 1,
			"currency": frappe.get_cached_value("Company", company, "default_currency")}).insert(ignore_permissions=True)
	return name


def make_item_price(item, supplier, rate, company):
	frappe.db.delete("Item Price", {"item_code": item, "supplier": supplier})
	return frappe.get_doc({
		"doctype": "Item Price", "item_code": item, "supplier": supplier, "price_list": buying_price_list(company),
		"price_list_rate": rate, "buying": 1, "currency": frappe.get_cached_value("Company", company, "default_currency"),
		"valid_from": add_days(today(), -30),
	}).insert(ignore_permissions=True)


def tax_account(company):
	return frappe.db.get_value("Account", {"company": company, "account_type": "Tax", "is_group": 0}, "name")


def make_po(qty=10, rate=100, tax_rate=18, item=ITEM, supplier=SUPPLIER, do_save=True, **extra):
	company = get_company()
	po = frappe.new_doc("Purchase Order")
	po.update({
		"supplier": supplier, "company": company, "transaction_date": today(), "schedule_date": add_days(today(), 10),
		"currency": frappe.get_cached_value("Company", company, "default_currency"), "conversion_rate": 1,
		"buying_price_list": buying_price_list(company),
	})
	po.update(extra)
	po.append("items", {"item_code": item, "qty": qty, "rate": rate, "warehouse": get_warehouse(company),
		"schedule_date": add_days(today(), 10), "uom": "Nos", "conversion_factor": 1})
	acc = tax_account(company) if tax_rate else None
	if acc:
		po.append("taxes", {"charge_type": "On Net Total", "account_head": acc, "rate": tax_rate,
			"description": "Test Tax", "category": "Total", "add_deduct_tax": "Add"})
	if do_save:
		po.flags.ignore_permissions = True
		po.insert()
	return po


def submit_gates_off():
	"""Patch the submit gates (approval, addresses, supplier approval, price control) for data setup."""
	stack = ExitStack()
	stack.enter_context(patch("universal_buying.ub_ordering.approval.is_enabled", return_value=False))
	stack.enter_context(patch("universal_buying.ub_ordering.po_rules.validate_addresses"))
	stack.enter_context(patch("universal_buying.ub_ordering.overrides.purchase_order.assert_supplier_enabled"))
	stack.enter_context(patch("universal_buying.ub_ordering.po_rules.get_setting", side_effect=settings({"price_control_mode": "Free"})))
	return stack


def make_submitted_po(**kwargs):
	make_item()
	make_supplier()
	with submit_gates_off():
		po = make_po(**kwargs)
		po.submit()
	return po


def make_user(email, roles):
	if not frappe.db.exists("User", email):
		frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
			"send_welcome_email": 0, "user_type": "System User"}).insert(ignore_permissions=True)
	user = frappe.get_doc("User", email)
	user.remove_roles(*[r.role for r in user.roles])
	user.add_roles(*roles)
	return email
