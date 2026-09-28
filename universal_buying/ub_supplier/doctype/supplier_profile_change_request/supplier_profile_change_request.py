# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt
"""Supplier Profile Change Request (BRD 6.6).

The supplier raises contact / address / bank / GSTIN changes from the portal
(universal_buying.ub_supplier.api.submit_profile_change_request). A Purchase User approves by
submitting; only then are the changes applied to the live records.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import escape_html

from universal_buying.ub_supplier.utils import clean_code, is_linked, validate_gstin


class SupplierProfileChangeRequest(Document):
	def before_insert(self):
		if not self.request_date:
			self.request_date = frappe.utils.now_datetime()
		if not self.requested_by:
			self.requested_by = frappe.session.user

	def validate(self):
		if self.docstatus == 0:
			other = frappe.db.get_value(
				"Supplier Profile Change Request",
				{"supplier": self.supplier, "docstatus": 0, "name": ("!=", self.name)},
				"name",
			)
			if other:
				frappe.throw(_("Supplier {0} already has an open change request {1}.").format(self.supplier, other))
		self.validate_ownership()
		# V-6.2: one primary contact / address
		self._single_primary(self.contacts, "is_primary_contact", _("contact"))
		self._single_primary(self.addresses, "is_primary_address", _("address"))
		if self.gstin:
			pan = clean_code(self.gstin)[2:12] if len(clean_code(self.gstin)) == 15 else None
			self.gstin = validate_gstin(self.gstin, pan)
			from universal_buying.ub_supplier.utils import find_duplicates

			hits = find_duplicates(frappe.get_doc("Supplier", self.supplier), "gstin", self.gstin)
			if hits:
				frappe.throw(_("GSTIN {0} already exists on {1} {2}.").format(self.gstin, _(hits[0].doctype), hits[0].name))
		for row in self.bank_accounts:
			if (row.action or "Add") == "Remove" and not row.existing_bank_account:
				frappe.throw(_("Bank Accounts row {0}: select the account to remove.").format(row.idx))
			if (row.action or "Add") == "Add" and not row.existing_bank_account and not (row.bank and (row.bank_account_no or row.iban)):
				frappe.throw(_("Bank Accounts row {0}: Bank and Account Number (or IBAN) are required.").format(row.idx))

	def validate_ownership(self):
		"""V-6.1 (re-checked here so desk-created requests are covered too)."""
		for row in self.contacts:
			if row.existing_contact and not is_linked("Contact", row.existing_contact, "Supplier", self.supplier):
				frappe.throw(_("Contact {0} does not belong to supplier {1}.").format(row.existing_contact, self.supplier))
		for row in self.addresses:
			if row.existing_address and not is_linked("Address", row.existing_address, "Supplier", self.supplier):
				frappe.throw(_("Address {0} does not belong to supplier {1}.").format(row.existing_address, self.supplier))
		for row in self.bank_accounts:
			if row.existing_bank_account:
				ba = frappe.db.get_value("Bank Account", row.existing_bank_account, ["party_type", "party"], as_dict=True)
				if not ba or ba.party_type != "Supplier" or ba.party != self.supplier:
					frappe.throw(_("Bank Account {0} does not belong to supplier {1}.").format(row.existing_bank_account, self.supplier))

	def _single_primary(self, rows, flag, label):
		active = [r for r in rows or [] if not r.get("remove")]
		primaries = [r for r in active if r.get(flag)]
		if len(primaries) > 1:
			frappe.throw(_("Only one {0} can be marked as primary.").format(label))

	# ------------------------------------------------------------------ summary
	@frappe.whitelist()
	def get_changes_summary(self):
		"""Current -> Requested comparison for the approver; flags which sections change."""
		sup = frappe.db.get_value("Supplier", self.supplier, ["tax_id"], as_dict=True) if self.supplier else None
		gst_blocks, contact_blocks, address_blocks, bank_blocks = [], [], [], []

		if self.gstin:
			current = (sup.tax_id if sup else "") or ""
			if current != self.gstin:
				gst_blocks.append(_summary_block(_("GSTIN / Tax ID"), [("GSTIN", current, self.gstin)]))

		for c in self.contacts:
			if c.existing_contact and frappe.db.exists("Contact", c.existing_contact):
				cur = frappe.db.get_value("Contact", c.existing_contact, ["first_name", "last_name", "email_id", "phone", "mobile_no"], as_dict=True) or {}
				if c.remove:
					changes, title = [(_("Status"), _("Linked"), _("Removed"))], _("Contact {0} (remove)").format(c.existing_contact)
				else:
					pairs = [(_("First Name"), cur.get("first_name"), c.first_name), (_("Last Name"), cur.get("last_name"), c.last_name),
						(_("Email"), cur.get("email_id"), c.email), (_("Phone"), cur.get("phone"), c.phone), (_("Mobile"), cur.get("mobile_no"), c.mobile)]
					changes = [(lbl, o, n) for (lbl, o, n) in pairs if (o or "") != (n or "")]
					title = _("Contact {0} (edit)").format(c.existing_contact)
			else:
				pairs = [(_("First Name"), c.first_name), (_("Last Name"), c.last_name), (_("Email"), c.email), (_("Phone"), c.phone), (_("Mobile"), c.mobile)]
				changes = [(lbl, "", n) for (lbl, n) in pairs if n]
				title = _("Contact {0} (new)").format(c.first_name or "-")
			if c.is_primary_contact:
				title += " - " + _("Primary")
			if changes:
				contact_blocks.append(_summary_block(title, changes))

		for a in self.addresses:
			fields = ["address_type", "address_line1", "address_line2", "city", "state", "country", "pincode"]
			labels = [_("Type"), _("Line 1"), _("Line 2"), _("City"), _("State"), _("Country"), _("Pincode")]
			if a.existing_address and frappe.db.exists("Address", a.existing_address):
				cur = frappe.db.get_value("Address", a.existing_address, fields, as_dict=True) or {}
				if a.remove:
					changes, title = [(_("Status"), _("Linked"), _("Removed"))], _("Address {0} (remove)").format(a.existing_address)
				else:
					changes = [(lbl, cur.get(f), a.get(f)) for f, lbl in zip(fields, labels) if (cur.get(f) or "") != (a.get(f) or "")]
					title = _("Address {0} (edit)").format(a.existing_address)
			else:
				changes = [(lbl, "", a.get(f)) for f, lbl in zip(fields, labels) if a.get(f)]
				title = _("Address {0} (new)").format(a.address_line1 or "-")
			if a.is_primary_address:
				title += " - " + _("Primary")
			if changes:
				address_blocks.append(_summary_block(title, changes))

		for b in self.bank_accounts:
			fields = ["account_name", "bank", "bank_account_no", "iban", "branch_code"]
			labels = [_("Account Holder"), _("Bank"), _("Account No"), _("IBAN"), _("Branch / IFSC")]
			if (b.action or "Add") == "Remove":
				bank_blocks.append(_summary_block(_("Bank Account {0} (remove)").format(b.existing_bank_account or "-"), [(_("Status"), _("Active"), _("Disabled"))]))
				continue
			if b.existing_bank_account and frappe.db.exists("Bank Account", b.existing_bank_account):
				cur = frappe.db.get_value("Bank Account", b.existing_bank_account, fields, as_dict=True) or {}
				changes = [(lbl, cur.get(f), b.get(f)) for f, lbl in zip(fields, labels) if (cur.get(f) or "") != (b.get(f) or "")]
				title = _("Bank Account {0} (edit)").format(b.existing_bank_account)
			else:
				changes = [(lbl, "", b.get(f)) for f, lbl in zip(fields, labels) if b.get(f)]
				title = _("Bank Account {0} (new)").format(b.account_name or "-")
			if b.is_default:
				title += " - " + _("Default")
			if changes:
				bank_blocks.append(_summary_block(title, changes))

		blocks = gst_blocks + contact_blocks + address_blocks + bank_blocks
		html = "".join(blocks) or "<div class='text-muted' style='padding:10px;'>{0}</div>".format(_("No field-level changes detected."))
		return {
			"html": html,
			"sections": {"gst": bool(gst_blocks), "contacts": bool(contact_blocks), "addresses": bool(address_blocks), "bank": bool(bank_blocks)},
		}

	# -------------------------------------------------------------------- apply
	def on_submit(self):
		"""A-6.1: approval applies the requested changes to the Supplier."""
		self.apply_to_supplier()

	def apply_to_supplier(self):
		sup = frappe.get_doc("Supplier", self.supplier)
		primary_contact = self._apply_contacts(sup)
		primary_address = self._apply_addresses(sup)
		self._apply_bank_accounts(sup)

		updates = {}
		if primary_contact:
			updates["supplier_primary_contact"] = primary_contact
			contact = frappe.db.get_value("Contact", primary_contact, ["email_id", "mobile_no"], as_dict=True)
			updates["email_id"] = contact.email_id
			updates["mobile_no"] = contact.mobile_no
		if primary_address:
			from frappe.contacts.doctype.address.address import get_address_display

			updates["supplier_primary_address"] = primary_address
			updates["primary_address"] = get_address_display(frappe.get_doc("Address", primary_address).as_dict())
		if self.gstin:
			updates["tax_id"] = self.gstin
			if sup.meta.has_field("gstin"):
				updates["gstin"] = self.gstin
		if updates:
			frappe.db.set_value("Supplier", sup.name, updates)
		if self.gst_certificate:
			self._attach_gst_certificate(sup)
		sup.add_comment("Info", _("Profile changes applied from {0}").format(frappe.utils.get_link_to_form(self.doctype, self.name)))

	def _apply_contacts(self, sup):
		from universal_buying.ub_supplier.utils import is_linked as _linked

		primary = None
		for row in self.contacts:
			if row.remove:
				self._unlink("Contact", row.existing_contact, sup, "supplier_primary_contact")
				continue
			if row.existing_contact and frappe.db.exists("Contact", row.existing_contact) and _linked("Contact", row.existing_contact, "Supplier", sup.name):
				contact = frappe.get_doc("Contact", row.existing_contact)
			else:
				contact = frappe.new_doc("Contact")
				contact.append("links", {"link_doctype": "Supplier", "link_name": sup.name})
			contact.first_name = row.first_name or sup.supplier_name
			contact.last_name = row.last_name or ""
			if row.designation is not None:
				contact.designation = row.designation
			set_primary_email(contact, row.email)
			set_primary_phone(contact, row.phone, row.mobile)
			contact.is_primary_contact = 1 if row.is_primary_contact else 0
			contact.flags.ignore_permissions = True
			contact.flags.ignore_mandatory = True
			contact.save()
			if not row.existing_contact:
				row.db_set("existing_contact", contact.name, update_modified=False)
			if row.is_primary_contact:
				primary = contact.name
		if primary:
			self._clear_other_primary("Contact", "is_primary_contact", sup.name, primary)
		return primary

	def _apply_addresses(self, sup):
		primary = None
		for row in self.addresses:
			if row.remove:
				self._unlink("Address", row.existing_address, sup, "supplier_primary_address")
				continue
			if row.existing_address and frappe.db.exists("Address", row.existing_address) and is_linked("Address", row.existing_address, "Supplier", sup.name):
				address = frappe.get_doc("Address", row.existing_address)
			else:
				address = frappe.new_doc("Address")
				address.append("links", {"link_doctype": "Supplier", "link_name": sup.name})
			address.address_type = row.address_type or "Billing"
			address.address_title = row.address_title or sup.supplier_name
			address.address_line1 = row.address_line1
			address.address_line2 = row.address_line2
			address.city = row.city
			address.state = row.state
			address.pincode = row.pincode
			if row.country and frappe.db.exists("Country", row.country):
				address.country = row.country
			elif not address.country:
				address.country = sup.country or frappe.db.get_default("country")
			address.is_primary_address = 1 if row.is_primary_address else 0
			if row.is_primary_address and self.gstin and address.meta.has_field("gstin"):
				address.gstin = self.gstin
			address.flags.ignore_permissions = True
			address.flags.ignore_mandatory = True
			address.save()
			if not row.existing_address:
				row.db_set("existing_address", address.name, update_modified=False)
			if row.is_primary_address:
				primary = address.name
		if primary:
			self._clear_other_primary("Address", "is_primary_address", sup.name, primary)
		return primary

	def _clear_other_primary(self, doctype, flag, supplier, keep):
		others = frappe.db.sql(
			f"""select d.name from `tab{doctype}` d join `tabDynamic Link` dl on dl.parent = d.name and dl.parenttype = %s
			where dl.link_doctype = 'Supplier' and dl.link_name = %s and d.name != %s and d.`{flag}` = 1""",
			(doctype, supplier, keep),
		)
		for (name,) in others:
			frappe.db.set_value(doctype, name, flag, 0, update_modified=False)

	def _unlink(self, doctype, name, sup, primary_field):
		"""Drop the supplier link from an existing Contact / Address; the record itself is kept."""
		if not (name and frappe.db.exists(doctype, name)):
			return
		doc = frappe.get_doc(doctype, name)
		doc.links = [lnk for lnk in doc.links if not (lnk.link_doctype == "Supplier" and lnk.link_name == sup.name)]
		doc.flags.ignore_permissions = True
		doc.flags.ignore_mandatory = True
		doc.save()
		if frappe.db.get_value("Supplier", sup.name, primary_field) == name:
			frappe.db.set_value("Supplier", sup.name, primary_field, None)

	def _apply_bank_accounts(self, sup):
		from universal_buying.ub_supplier.utils import create_supplier_bank_account

		new_default = None
		for row in self.bank_accounts:
			if (row.action or "Add") == "Remove":
				if row.existing_bank_account and frappe.db.exists("Bank Account", row.existing_bank_account):
					frappe.db.set_value("Bank Account", row.existing_bank_account, {"disabled": 1, "is_default": 0})
				continue
			if row.existing_bank_account and frappe.db.exists("Bank Account", row.existing_bank_account):
				ba = frappe.get_doc("Bank Account", row.existing_bank_account)
				for field in ("bank", "account_type", "bank_account_no", "iban", "branch_code"):
					if row.get(field):
						ba.set(field, row.get(field))
				ba.is_default = 1 if row.is_default else ba.is_default
				ba.disabled = 0
				ba.flags.ignore_permissions = True
				ba.flags.ignore_mandatory = True
				ba.save()
				name = ba.name
			else:
				name = create_supplier_bank_account(
					sup.name, row.bank, account_no=row.bank_account_no, branch_code=row.branch_code,
					iban=row.iban, account_name=row.account_name, is_default=row.is_default,
				)
				if name and row.account_type:
					frappe.db.set_value("Bank Account", name, "account_type", row.account_type)
				if name:
					row.db_set("existing_bank_account", name, update_modified=False)
			if row.is_default and name:
				new_default = name
		if new_default:
			for other in frappe.get_all(
				"Bank Account",
				filters={"party_type": "Supplier", "party": sup.name, "name": ("!=", new_default), "is_default": 1},
				pluck="name",
			):
				frappe.db.set_value("Bank Account", other, "is_default", 0)

	def _attach_gst_certificate(self, sup):
		if frappe.db.exists("File", {"file_url": self.gst_certificate, "attached_to_doctype": "Supplier", "attached_to_name": sup.name}):
			return
		frappe.get_doc({
			"doctype": "File",
			"file_url": self.gst_certificate,
			"file_name": self.gst_certificate.rsplit("/", 1)[-1],
			"attached_to_doctype": "Supplier",
			"attached_to_name": sup.name,
			"is_private": 1,
		}).insert(ignore_permissions=True, ignore_if_duplicate=True)


def set_primary_email(contact, email):
	email = (email or "").strip()
	if not email:
		return
	for row in contact.email_ids:
		row.is_primary = 0
	existing = next((r for r in contact.email_ids if r.email_id == email), None)
	if existing:
		existing.is_primary = 1
	else:
		contact.append("email_ids", {"email_id": email, "is_primary": 1})


def set_primary_phone(contact, phone, mobile):
	phone, mobile = (phone or "").strip(), (mobile or "").strip()
	if phone:
		for row in contact.phone_nos:
			row.is_primary_phone = 0
		existing = next((r for r in contact.phone_nos if r.phone == phone), None)
		if existing:
			existing.is_primary_phone = 1
		else:
			contact.append("phone_nos", {"phone": phone, "is_primary_phone": 1})
	if mobile:
		for row in contact.phone_nos:
			row.is_primary_mobile_no = 0
		existing = next((r for r in contact.phone_nos if r.phone == mobile), None)
		if existing:
			existing.is_primary_mobile_no = 1
		else:
			contact.append("phone_nos", {"phone": mobile, "is_primary_mobile_no": 1})


def _summary_block(title, rows):
	body = "".join(
		"<tr><td style='padding:4px 10px;'>{0}</td><td style='padding:4px 10px;color:var(--red-600);'>{1}</td>"
		"<td style='padding:4px 10px;color:var(--green-600);font-weight:600;'>{2}</td></tr>".format(
			escape_html(str(label)), escape_html(str(old or "-")), escape_html(str(new or "-"))
		)
		for (label, old, new) in rows
	)
	return (
		"<div style='margin:0 0 12px;border:1px solid var(--border-color);border-radius:6px;overflow:hidden;'>"
		"<div style='background:var(--subtle-fg);padding:6px 10px;font-weight:600;'>{0}</div>"
		"<table style='width:100%;border-collapse:collapse;'><thead><tr class='text-muted'>"
		"<th style='text-align:left;padding:4px 10px;width:25%;'>{1}</th><th style='text-align:left;padding:4px 10px;'>{2}</th>"
		"<th style='text-align:left;padding:4px 10px;'>{3}</th></tr></thead><tbody>{4}</tbody></table></div>"
	).format(escape_html(str(title)), _("Field"), _("Current"), _("Requested"), body)
