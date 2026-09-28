"""Test fixtures for UB Supplier tests."""

import random
import string

import frappe


def random_pan():
	letters = "".join(random.choices(string.ascii_uppercase, k=5))
	digits = "".join(random.choices(string.digits, k=4))
	return f"{letters}{digits}{random.choice(string.ascii_uppercase)}"


def gstin_for(pan, state="29"):
	return f"{state}{pan}1Z5"


def unique(prefix):
	return f"{prefix} {frappe.generate_hash(length=6)}"


def make_supplier_group(name, parent="All Supplier Groups"):
	if not frappe.db.exists("Supplier Group", name):
		frappe.get_doc({"doctype": "Supplier Group", "supplier_group_name": name, "parent_supplier_group": parent, "is_group": 0}).insert(ignore_permissions=True)
	return name


def make_parent_group(name):
	if not frappe.db.exists("Supplier Group", name):
		frappe.get_doc({"doctype": "Supplier Group", "supplier_group_name": name, "parent_supplier_group": "All Supplier Groups", "is_group": 1}).insert(ignore_permissions=True)
	return name


def make_incoterm(code="UBT"):
	if not frappe.db.exists("Incoterm", code):
		frappe.get_doc({"doctype": "Incoterm", "code": code, "title": "UB Test Incoterm"}).insert(ignore_permissions=True)
	return code


def set_supplier_settings(full=None, finance=None, audit=None, questionnaire=0, require_bank=1):
	"""Point the Supplier settings of Buying Control Settings at the given groups."""
	settings = frappe.get_single("Buying Control Settings")
	settings.set("approval_full_chain_groups", [{"supplier_group": g} for g in (full or [])])
	settings.set("approval_finance_only_groups", [{"supplier_group": g} for g in (finance or [])])
	settings.set("audit_required_groups", [{"supplier_group": g} for g in (audit or [])])
	settings.onboarding_questionnaire = questionnaire
	settings.require_bank_account = require_bank
	settings.flags.ignore_permissions = True
	settings.flags.ignore_mandatory = True
	settings.save()
	frappe.clear_document_cache("Buying Control Settings", "Buying Control Settings")
