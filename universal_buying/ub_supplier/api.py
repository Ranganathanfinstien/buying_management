"""UB Supplier public API (BUILD_SPEC 6.3 contracts).

Contracts implemented here:
	create_onboarding_from_prospective(prospective_supplier, send_email=1) -> str        (server-side, used by C at award)
	get_supplier_for_prospective(prospective_supplier) -> str | None                     (C, D)
	submit_profile_change_request(supplier, changes)                                     (whitelisted, D portal)
	get_document_vault(supplier) / upload_vault_document(...) / delete_vault_document(...) (whitelisted, D portal)
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, get_url, getdate, now_datetime, nowdate

from universal_buying.ub_supplier.utils import (
	assert_supplier_access,
	is_linked,
)

ONBOARDING_ROUTE = "/supplier_onboarding"
VAULT_FIELD = "ub_document_vault"
VAULT_CATEGORY_ORDER = ["Insurance", "Financial", "Statutory", "Quality", "Legal", "Customs", "Other"]
EXPIRING_WINDOW_DAYS = 30


# ---------------------------------------------------------------------------
# Prospective supplier -> onboarding
# ---------------------------------------------------------------------------


def _default_supplier_group():
	from universal_buying.universal_buying.settings import get_setting

	group = get_setting("default_onboarding_supplier_group", default=None)
	if not group and frappe.get_meta("Buying Settings").has_field("supplier_group"):
		group = frappe.db.get_single_value("Buying Settings", "supplier_group")
	return group


def get_open_onboarding(prospective_supplier):
	return frappe.db.get_value(
		"Supplier Onboarding",
		{"prospective_supplier": prospective_supplier, "docstatus": ("<", 2), "status": ("!=", "Rejected")},
		"name",
		order_by="creation desc",
	)


def create_onboarding_from_prospective(prospective_supplier, send_email=1):
	"""Create (or reuse) a Supplier Onboarding for a Prospective Supplier, give it a token link,
	optionally email the link, and mark the prospective supplier "Onboarding Sent".

	Returns the Supplier Onboarding name. Safe to call repeatedly (idempotent per prospective supplier);
	for an already onboarded prospective supplier it returns the submitted onboarding and sends nothing.
	"""
	ps = frappe.get_doc("Prospective Supplier", prospective_supplier)
	if ps.linked_supplier:
		# already onboarded: nothing to send, return the onboarding that created the supplier
		return ps.supplier_onboarding or frappe.db.get_value(
			"Supplier Onboarding", {"prospective_supplier": ps.name, "docstatus": 1}, "name"
		)

	name = get_open_onboarding(ps.name)
	if name:
		so = frappe.get_doc("Supplier Onboarding", name)
	else:
		so = frappe.new_doc("Supplier Onboarding")
		so.update({
			"supplier_name": ps.supplier_name,
			"supplier_type": ps.supplier_type or "Company",
			"supplier_group": _default_supplier_group(),
			"country": ps.country or frappe.db.get_default("country"),
			"gst_category": ps.gst_category or ("Registered Regular" if ps.gstin else "Unregistered"),
			"gstin": ps.gstin,
			"pan": ps.pan,
			"website": ps.website,
			"contact_person": ps.contact_person or ps.supplier_name,
			"designation": ps.designation,
			"email": ps.email,
			"phone": ps.phone,
			"mobile": ps.mobile,
			"address_line1": ps.address_line1,
			"address_line2": ps.address_line2,
			"city": ps.city,
			"state": ps.state,
			"pincode": ps.pincode,
			"prospective_supplier": ps.name,
			"supplier_notes": ps.notes,
		})
		so.flags.ignore_permissions = True
		so.flags.ignore_mandatory = True
		so.insert()

	so.ensure_token()

	updates = {"supplier_onboarding": so.name}
	if ps.status == "Active":
		updates["status"] = "Onboarding Sent"
	frappe.db.set_value("Prospective Supplier", ps.name, updates)

	if cint(send_email):
		send_onboarding_email(so)
	return so.name


def get_onboarding_link(token):
	return get_url(f"{ONBOARDING_ROUTE}?token={token}")


def send_onboarding_email(so):
	"""Email the token link to the supplier contact of the onboarding."""
	so.ensure_token()
	recipient = so.email or (so.prospective_supplier and frappe.db.get_value("Prospective Supplier", so.prospective_supplier, "email"))
	if not recipient:
		frappe.throw(_("Supplier Onboarding {0} has no email address.").format(so.name))
	link = get_onboarding_link(so.onboarding_token)
	company = frappe.db.get_default("company") or ""
	message = _(
		"<p>Dear {0},</p>"
		"<p>Please complete your supplier registration{1} using the link below. "
		"Your basic details are already filled in; please review them, add your address, bank "
		"and tax details, and submit the form.</p>"
		'<p style="margin:24px 0;"><a href="{2}" style="background:#2b6cb0;color:#fff;padding:10px 24px;'
		'border-radius:4px;text-decoration:none;">Complete Supplier Registration</a></p>'
		'<p style="color:#666;font-size:12px;">If the button does not work, open this link: <a href="{2}">{2}</a></p>'
		"<p>Regards,<br>Procurement Team</p>"
	).format(frappe.utils.escape_html(so.supplier_name or ""), f" with {frappe.utils.escape_html(company)}" if company else "", link)
	frappe.sendmail(
		recipients=[recipient],
		subject=_("Action Required: Complete Your Supplier Registration"),
		message=message,
		reference_doctype="Supplier Onboarding",
		reference_name=so.name,
	)
	return recipient


def get_supplier_for_prospective(prospective_supplier):
	"""The Supplier created for a Prospective Supplier, or None while it is not onboarded yet."""
	if not prospective_supplier:
		return None
	supplier = frappe.db.get_value("Prospective Supplier", prospective_supplier, "linked_supplier")
	if supplier:
		return supplier
	return frappe.db.get_value(
		"Supplier Onboarding",
		{"prospective_supplier": prospective_supplier, "docstatus": 1, "supplier": ("is", "set")},
		"supplier",
	) or None


# ---------------------------------------------------------------------------
# Question bank / audit checklist
# ---------------------------------------------------------------------------


def get_default_question_bank():
	return frappe.db.get_value("Supplier Onboarding Question Bank", {"is_default": 1}, "name") or frappe.db.get_value(
		"Supplier Onboarding Question Bank", {}, "name", order_by="creation asc"
	)


@frappe.whitelist()
def get_question_list(question_bank=None, category=None):
	"""Rows of a question bank (default bank when not given), optionally filtered by category."""
	question_bank = question_bank or get_default_question_bank()
	if not question_bank or not frappe.db.exists("Supplier Onboarding Question Bank", question_bank):
		return []
	bank = frappe.get_cached_doc("Supplier Onboarding Question Bank", question_bank)
	out = []
	for row in bank.questions:
		if category and row.category != category:
			continue
		out.append({
			"category": row.category,
			"question_no": row.question_no,
			"main_question": row.main_question,
			"question": row.question,
			"weightage": row.weightage,
			"option_5": row.option_5,
			"option_4": row.option_4,
			"option_3": row.option_3,
			"option_2": row.option_2,
			"option_1": row.option_1,
		})
	return out


INDUSTRY_FIELD = {
	"Industrial": "industrial",
	"Automotive": "automotive",
	"Medical": "medical",
	"Railways": "railways",
	"Defence / Aerospace": "defence_aerospace",
}


def get_active_checklist(company=None):
	filters = {"is_active": 1}
	if company:
		name = frappe.db.get_value("Supplier Audit Checklist", dict(filters, company=company), "name")
		if name:
			return name
	return frappe.db.get_value("Supplier Audit Checklist", dict(filters, company=("is", "not set")), "name") or frappe.db.get_value(
		"Supplier Audit Checklist", filters, "name", order_by="creation asc"
	)


@frappe.whitelist(allow_guest=True)
def get_audit_questions(supplier_audit_type=None, checklist=None):
	"""Checklist questions with the minimum score for the industry. Guest-safe: questions are not secret."""
	checklist = checklist or get_active_checklist()
	if not checklist or not frappe.db.exists("Supplier Audit Checklist", checklist):
		return []
	key = INDUSTRY_FIELD.get(supplier_audit_type or "")
	doc = frappe.get_cached_doc("Supplier Audit Checklist", checklist)
	out = []
	for q in doc.checklist_detail:
		out.append({
			"group": q.group,
			"question": q.question,
			"options": [o.strip() for o in (q.options or "").splitlines() if o.strip()],
			"max_score": cint(q.max_score),
			"min_score": cint(q.get(key)) if key else 0,
		})
	return out


# ---------------------------------------------------------------------------
# Supplier Profile Change Request (BRD 6.6) - portal API
# ---------------------------------------------------------------------------

CONTACT_ROW_FIELDS = ("existing_contact", "is_primary_contact", "first_name", "last_name", "designation", "email", "phone", "mobile", "remove")
ADDRESS_ROW_FIELDS = ("existing_address", "is_primary_address", "address_type", "address_title", "address_line1", "address_line2", "city", "state", "country", "pincode", "remove")
BANK_ROW_FIELDS = ("existing_bank_account", "action", "is_default", "account_name", "bank", "account_type", "bank_account_no", "iban", "branch_code")


def get_pending_change_request(supplier):
	return frappe.db.get_value("Supplier Profile Change Request", {"supplier": supplier, "docstatus": 0}, "name")


def _merge_rows(req, table, rows, key_field, allowed_fields):
	"""An edit/remove of a live record replaces any pending row for that record; new rows append."""
	for row in rows or []:
		row = frappe._dict(row)
		key = row.get(key_field)
		if key:
			req.set(table, [r for r in req.get(table) if r.get(key_field) != key])
		req.append(table, {f: row.get(f) for f in allowed_fields if f in row})


def assert_change_targets_owned(supplier, contacts=None, addresses=None, bank_accounts=None):
	"""V-6.1: every existing record being changed must belong to the supplier."""
	for row in contacts or []:
		name = row.get("existing_contact")
		if name and not is_linked("Contact", name, "Supplier", supplier):
			frappe.throw(_("You can only change your own contacts."), frappe.PermissionError)
	for row in addresses or []:
		name = row.get("existing_address")
		if name and not is_linked("Address", name, "Supplier", supplier):
			frappe.throw(_("You can only change your own addresses."), frappe.PermissionError)
	for row in bank_accounts or []:
		name = row.get("existing_bank_account")
		if name:
			ba = frappe.db.get_value("Bank Account", name, ["party_type", "party"], as_dict=True)
			if not ba or ba.party_type != "Supplier" or ba.party != supplier:
				frappe.throw(_("You can only change your own bank accounts."), frappe.PermissionError)


@frappe.whitelist()
def submit_profile_change_request(supplier, changes=None, contacts=None, addresses=None, bank_accounts=None,
		gstin=None, gst_certificate=None):
	"""Merge a supplier's profile edits into its single open draft change request (A-6.1).

	``changes`` = {"contacts": [...], "addresses": [...], "bank_accounts": [...], "gstin": "...", "gst_certificate": "/private/files/.."}
	Each list holds delta rows: a new record has no ``existing_*`` key; an edit / remove carries the
	live record's name. Omitted keys are untouched. Nothing live changes until a Purchase User submits
	the request. The separate keyword arguments are accepted for backwards compatibility.
	Returns {"ok": True, "name": <request>}.
	"""
	assert_supplier_access(supplier)

	changes = frappe.parse_json(changes) if changes else {}
	changes = frappe._dict(changes or {})
	for key, value in (("contacts", contacts), ("addresses", addresses), ("bank_accounts", bank_accounts),
			("gstin", gstin), ("gst_certificate", gst_certificate)):
		if value is not None and key not in changes:
			changes[key] = value

	def _rows(key):
		value = changes.get(key)
		if value is None:
			return None
		value = frappe.parse_json(value) if isinstance(value, str) else value
		return [dict(r) for r in (value or [])]

	c_rows, a_rows, b_rows = _rows("contacts"), _rows("addresses"), _rows("bank_accounts")
	new_gstin = changes.get("gstin")
	certificate = changes.get("gst_certificate")

	if not any([c_rows, a_rows, b_rows]) and new_gstin is None and not certificate:
		frappe.throw(_("Nothing to submit."))

	assert_change_targets_owned(supplier, c_rows, a_rows, b_rows)

	name = get_pending_change_request(supplier)
	if name:
		req = frappe.get_doc("Supplier Profile Change Request", name)
	else:
		req = frappe.new_doc("Supplier Profile Change Request")
		req.supplier = supplier
		req.requested_by = frappe.session.user
		req.request_date = now_datetime()

	if c_rows is not None:
		_merge_rows(req, "contacts", c_rows, "existing_contact", CONTACT_ROW_FIELDS)
	if a_rows is not None:
		_merge_rows(req, "addresses", a_rows, "existing_address", ADDRESS_ROW_FIELDS)
	if b_rows is not None:
		_merge_rows(req, "bank_accounts", b_rows, "existing_bank_account", BANK_ROW_FIELDS)
	if new_gstin is not None:
		req.gstin = (new_gstin or "").strip().upper()
	if certificate:
		req.gst_certificate = certificate

	req.flags.ignore_permissions = True
	req.save()

	if certificate:
		_claim_file(certificate, "Supplier Profile Change Request", req.name, "gst_certificate")
	return {"ok": True, "name": req.name}


@frappe.whitelist()
def get_pending_profile_change(supplier):
	"""The supplier's open draft change request, grouped for the portal 'Pending Approval' view."""
	assert_supplier_access(supplier)
	name = get_pending_change_request(supplier)
	if not name:
		return {"name": None, "contacts": [], "addresses": [], "bank_accounts": [], "gstin": None}
	req = frappe.get_doc("Supplier Profile Change Request", name)
	return {
		"name": name,
		"gstin": req.gstin,
		"contacts": [{f: r.get(f) for f in CONTACT_ROW_FIELDS} for r in req.contacts],
		"addresses": [{f: r.get(f) for f in ADDRESS_ROW_FIELDS} for r in req.addresses],
		"bank_accounts": [dict({f: r.get(f) for f in BANK_ROW_FIELDS}, masked=mask_account_no(r.bank_account_no)) for r in req.bank_accounts],
	}


@frappe.whitelist()
def get_supplier_profile(supplier):
	"""Live contacts, addresses and (masked) bank accounts of a supplier, for the portal profile page."""
	assert_supplier_access(supplier)
	contacts = frappe.db.sql(
		"""select c.name, c.first_name, c.last_name, c.designation, c.email_id, c.phone, c.mobile_no, c.is_primary_contact
		from `tabContact` c join `tabDynamic Link` dl on dl.parent = c.name and dl.parenttype = 'Contact'
		where dl.link_doctype = 'Supplier' and dl.link_name = %s
		order by c.is_primary_contact desc, c.creation asc""",
		supplier, as_dict=True,
	)
	addresses = frappe.db.sql(
		"""select a.name, a.address_type, a.address_title, a.address_line1, a.address_line2, a.city, a.state,
			a.country, a.pincode, a.is_primary_address
		from `tabAddress` a join `tabDynamic Link` dl on dl.parent = a.name and dl.parenttype = 'Address'
		where dl.link_doctype = 'Supplier' and dl.link_name = %s
		order by a.is_primary_address desc, a.creation asc""",
		supplier, as_dict=True,
	)
	banks = frappe.get_all(
		"Bank Account",
		filters={"party_type": "Supplier", "party": supplier, "disabled": 0},
		fields=["name", "account_name", "bank", "bank_account_no", "branch_code", "iban", "is_default"],
		order_by="is_default desc, creation asc",
	)
	for b in banks:
		b["masked"] = mask_account_no(b.pop("bank_account_no", None))
	sup = frappe.db.get_value("Supplier", supplier, ["supplier_name", "tax_id"], as_dict=True)
	return {"supplier": supplier, "supplier_name": sup.supplier_name, "gstin": sup.tax_id,
		"contacts": contacts, "addresses": addresses, "bank_accounts": banks}


def mask_account_no(no):
	no = (no or "").strip()
	return ("XXXX" + no[-4:]) if len(no) >= 4 else (no or "-")


# ---------------------------------------------------------------------------
# Document vault (Supplier.ub_document_vault)
# ---------------------------------------------------------------------------


def derive_document_status(attachment, expires_on, window=EXPIRING_WINDOW_DAYS):
	if not attachment:
		return "Not Uploaded"
	if expires_on:
		expires_on, today = getdate(expires_on), getdate(nowdate())
		if expires_on < today:
			return "Expired"
		if expires_on <= getdate(add_days(today, window)):
			return "Expiring"
	return "Uploaded"


def get_supplier_doc_types():
	return frappe.get_all(
		"Supplier Document Type",
		filters={"is_active": 1},
		fields=["name", "document_key", "label", "category", "is_required", "renewal_months", "allow_custom_label", "sort_order"],
		order_by="sort_order asc, label asc",
	)


def _vault_row(t, row, label, is_add=False):
	row = row or {}
	attachment = row.get("attachment") or ""
	expires_on = row.get("expires_on")
	return {
		"key": t["document_key"],
		"category": t["category"],
		"label": label,
		"required": bool(t["is_required"]),
		"allow_custom_label": bool(t["allow_custom_label"]),
		"row_name": row.get("name") or "",
		"is_add": is_add,
		"attachment": attachment,
		"status": derive_document_status(attachment, expires_on),
		"uploaded_on": row.get("uploaded_on"),
		"expires_on": expires_on,
		"expires_display": getdate(expires_on).strftime("%d %b %Y") if expires_on else "",
	}


def build_vault(supplier):
	types = get_supplier_doc_types()
	saved = {}
	for row in frappe.get_all(
		"Supplier Document",
		filters={"parent": supplier, "parenttype": "Supplier", "parentfield": VAULT_FIELD},
		fields=["name", "doc_key", "document_type", "custom_label", "attachment", "status", "uploaded_on", "expires_on"],
		order_by="idx asc",
	):
		saved.setdefault(row.doc_key or row.document_type, []).append(row)

	docs = []
	for t in types:
		rows = saved.get(t["document_key"], [])
		if t["allow_custom_label"]:
			docs += [_vault_row(t, r, r.custom_label or t["label"]) for r in rows]
			docs.append(_vault_row(t, None, t["label"], is_add=True))
		else:
			docs.append(_vault_row(t, rows[0] if rows else None, t["label"]))

	required = [d for d in docs if d["required"] and not d["allow_custom_label"]]
	required_on_file = [d for d in required if d["attachment"]]
	stats = {
		"compliance": int(round(100 * len(required_on_file) / len(required))) if required else 100,
		"required_total": len(required),
		"required_on_file": len(required_on_file),
		"on_file": len([d for d in docs if d["attachment"]]),
		"total": len(types),
		"expiring": len([d for d in docs if d["status"] == "Expiring"]),
		"expired": len([d for d in docs if d["status"] == "Expired"]),
	}
	stats["action_required"] = stats["expired"]
	counts = {
		"all": len(docs),
		"required": len(required),
		"on_file": stats["on_file"],
		"expiring": stats["expiring"],
		"expired": stats["expired"],
		"missing": len([d for d in docs if d["status"] == "Not Uploaded" and not d["is_add"]]),
	}
	cats = VAULT_CATEGORY_ORDER + [t["category"] for t in types if t["category"] not in VAULT_CATEGORY_ORDER]
	groups = []
	for cat in dict.fromkeys(cats):
		rows = [d for d in docs if d["category"] == cat]
		if rows:
			groups.append({"category": cat, "rows": rows})
	return {"supplier": supplier, "stats": stats, "counts": counts, "groups": groups}


@frappe.whitelist()
def get_document_vault(supplier):
	"""Document catalog merged with the supplier's uploads: {stats, counts, groups:[{category, rows}]}."""
	assert_supplier_access(supplier)
	return build_vault(supplier)


def _get_doc_type(doc_key):
	t = frappe.db.get_value(
		"Supplier Document Type",
		{"document_key": doc_key, "is_active": 1},
		["name", "document_key", "category", "allow_custom_label"],
		as_dict=True,
	)
	if not t:
		frappe.throw(_("Unknown or inactive document type {0}.").format(doc_key))
	return t


@frappe.whitelist()
def upload_vault_document(supplier, doc_key, file_url, expires_on=None, custom_label=None, row_name=None):
	"""Attach an uploaded file (``file_url`` from /api/method/upload_file) to a vault row.

	Normal types keep one row per type; free-label types append a row unless ``row_name`` points at one.
	Only a File uploaded by the session user and not yet attached elsewhere is re-attached to the Supplier.
	"""
	assert_supplier_access(supplier)
	t = _get_doc_type(doc_key)
	if not file_url:
		frappe.throw(_("A file is required."))
	expires_on = (expires_on or "").strip() or None
	custom_label = (custom_label or "").strip() or None

	doc = frappe.get_doc("Supplier", supplier)
	rows = doc.get(VAULT_FIELD) or []
	if t.allow_custom_label:
		row = next((r for r in rows if r.name == row_name), None) if row_name else None
		if not row:
			row = doc.append(VAULT_FIELD, {})
		row.custom_label = custom_label or t.document_key
	else:
		row = next((r for r in rows if (r.doc_key or r.document_type) == t.document_key), None)
		if not row:
			row = doc.append(VAULT_FIELD, {})

	row.document_type = t.name
	row.doc_key = t.document_key
	row.category = t.category
	row.attachment = file_url
	row.expires_on = expires_on
	row.uploaded_on = now_datetime()

	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.save()
	_claim_file(file_url, "Supplier", supplier)
	return {"ok": True, "doc_key": doc_key, "row_name": row.name, "status": derive_document_status(file_url, expires_on), "file_url": file_url}


@frappe.whitelist()
def delete_vault_document(supplier, doc_key, row_name=None):
	"""Remove an upload: free-label rows are deleted, normal rows are cleared back to Not Uploaded."""
	assert_supplier_access(supplier)
	t = _get_doc_type(doc_key)
	doc = frappe.get_doc("Supplier", supplier)
	rows = doc.get(VAULT_FIELD) or []
	if t.allow_custom_label and row_name:
		kept = [r for r in rows if r.name != row_name]
		if len(kept) == len(rows):
			return {"ok": True, "doc_key": doc_key}
		doc.set(VAULT_FIELD, kept)
	else:
		row = next((r for r in rows if (r.doc_key or r.document_type) == t.document_key), None)
		if not row or not row.attachment:
			return {"ok": True, "doc_key": doc_key, "status": "Not Uploaded"}
		row.attachment = None
		row.expires_on = None
		row.uploaded_on = None
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.save()
	return {"ok": True, "doc_key": doc_key, "status": "Not Uploaded"}


def sync_vault_rows(doc, method=None):
	"""Supplier.validate: keep vault row status / category / uploaded_on in step with the attachment."""
	for row in doc.get(VAULT_FIELD) or []:
		if row.document_type:
			info = frappe.db.get_value("Supplier Document Type", row.document_type, ["document_key", "category"], as_dict=True)
			if info:
				row.doc_key = info.document_key
				row.category = info.category
		row.status = derive_document_status(row.attachment, row.expires_on)
		if row.attachment and not row.uploaded_on:
			row.uploaded_on = now_datetime()
		if not row.attachment:
			row.uploaded_on = None


def refresh_vault_statuses():
	"""Daily: recompute Expiring / Expired on vault rows (status is time dependent)."""
	rows = frappe.get_all(
		"Supplier Document",
		filters={"parenttype": "Supplier", "parentfield": VAULT_FIELD, "attachment": ("is", "set"), "expires_on": ("is", "set")},
		fields=["name", "attachment", "expires_on", "status"],
	)
	for r in rows:
		status = derive_document_status(r.attachment, r.expires_on)
		if status != r.status:
			frappe.db.set_value("Supplier Document", r.name, "status", status, update_modified=False)


def _claim_file(file_url, doctype, name, fieldname=None):
	"""Attach a File the session user uploaded (and that is still unattached) to ``doctype``/``name``."""
	file_name = frappe.db.get_value(
		"File",
		{"file_url": file_url, "owner": frappe.session.user, "attached_to_name": ("is", "not set")},
		"name",
	)
	if not file_name:
		return
	values = {"attached_to_doctype": doctype, "attached_to_name": name}
	if fieldname:
		values["attached_to_field"] = fieldname
	frappe.db.set_value("File", file_name, values)
