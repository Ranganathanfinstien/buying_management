"""Shared helpers for the UB Supplier module.

- PAN / GSTIN format checks (V-2.2, V-2.3, V-3.2)
- duplicate GSTIN (block) / PAN (warn + comment) across Supplier, Prospective Supplier, Supplier Onboarding
- bank account helpers (V-5.3)
- portal ownership helpers (V-6.1)
- approval route used by the "UB Supplier Approval" workflow (BRD 6.5)

india_compliance is NOT a dependency: the Supplier GSTIN lives in the standard ``tax_id``
field (and in ``gstin`` when india_compliance happens to be installed); the PAN lives in
``pan`` when present, otherwise in our ``ub_pan`` custom field.
"""

import re

import frappe
from frappe import _
from frappe.utils import get_link_to_form

PAN_REGEX = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
# 2-digit state code + 10-char PAN + entity code (1-9/A-Z) + 'Z' + check character
GSTIN_REGEX = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")

APPROVAL_WORKFLOW = "UB Supplier Approval"
ROUTE_FULL = "Full"
ROUTE_FINANCE = "Finance"
ROUTE_DIRECT = "Direct"


# ---------------------------------------------------------------------------
# PAN / GSTIN format
# ---------------------------------------------------------------------------


def clean_code(value):
	return (value or "").strip().upper().replace(" ", "")


def is_valid_pan(pan):
	return bool(PAN_REGEX.match(clean_code(pan)))


def is_valid_gstin(gstin):
	return bool(GSTIN_REGEX.match(clean_code(gstin)))


def validate_pan(pan, label=None):
	"""Throw when a non-empty PAN is not AAAAA9999A. Returns the cleaned value."""
	pan = clean_code(pan)
	if pan and not PAN_REGEX.match(pan):
		frappe.throw(
			_("Invalid {0}: use 5 letters, 4 digits and 1 letter, e.g. ABCDE1234F.").format(label or _("PAN")),
			title=_("Invalid PAN"),
		)
	return pan


def validate_gstin(gstin, pan=None, label=None):
	"""Throw when a non-empty GSTIN is malformed or does not carry the PAN. Returns the cleaned value."""
	gstin = clean_code(gstin)
	if not gstin:
		return gstin
	if len(gstin) != 15 or not GSTIN_REGEX.match(gstin):
		frappe.throw(
			_("Invalid {0}: it must be 15 characters, e.g. 29ABCDE1234F1Z5.").format(label or _("GSTIN")),
			title=_("Invalid GSTIN"),
		)
	pan = clean_code(pan)
	if pan and gstin[2:12] != pan:
		frappe.throw(_("GSTIN does not match PAN"), title=_("GSTIN / PAN Mismatch"))
	return gstin


# ---------------------------------------------------------------------------
# Duplicate GSTIN / PAN
# ---------------------------------------------------------------------------


def supplier_gstin_fields():
	meta = frappe.get_meta("Supplier")
	return [f for f in ("tax_id", "gstin") if meta.has_field(f)]


def supplier_pan_fields():
	meta = frappe.get_meta("Supplier")
	return [f for f in ("pan", "ub_pan") if meta.has_field(f)]


def _sources(kind):
	"""(doctype, fields, extra filters) searched for duplicates."""
	if kind == "gstin":
		return [
			("Supplier", supplier_gstin_fields(), {}),
			("Prospective Supplier", ["gstin"], {}),
			("Supplier Onboarding", ["gstin"], {"docstatus": ("<", 2), "status": ("!=", "Rejected")}),
		]
	return [
		("Supplier", supplier_pan_fields(), {}),
		("Prospective Supplier", ["pan"], {}),
		("Supplier Onboarding", ["pan"], {"docstatus": ("<", 2), "status": ("!=", "Rejected")}),
	]


def _related(doc):
	"""Records that legitimately share the same identity with ``doc`` (its own chain)."""
	related = {(doc.doctype, doc.name)}
	if doc.doctype == "Supplier Onboarding":
		if doc.get("prospective_supplier"):
			related.add(("Prospective Supplier", doc.prospective_supplier))
		if doc.get("supplier"):
			related.add(("Supplier", doc.supplier))
	elif doc.doctype == "Prospective Supplier":
		if doc.get("linked_supplier"):
			related.add(("Supplier", doc.linked_supplier))
		if not doc.is_new():
			for name in frappe.get_all("Supplier Onboarding", {"prospective_supplier": doc.name}, pluck="name"):
				related.add(("Supplier Onboarding", name))
	elif doc.doctype == "Supplier":
		if doc.get("ub_onboarding"):
			related.add(("Supplier Onboarding", doc.ub_onboarding))
			ps = frappe.db.get_value("Supplier Onboarding", doc.ub_onboarding, "prospective_supplier")
			if ps:
				related.add(("Prospective Supplier", ps))
		if not doc.is_new():
			for name in frappe.get_all("Prospective Supplier", {"linked_supplier": doc.name}, pluck="name"):
				related.add(("Prospective Supplier", name))
			for name in frappe.get_all("Supplier Onboarding", {"supplier": doc.name}, pluck="name"):
				related.add(("Supplier Onboarding", name))
	return related


def find_duplicates(doc, kind, value):
	"""Return [frappe._dict(doctype, name)] of other records carrying ``value`` as GSTIN / PAN."""
	value = clean_code(value)
	if not value:
		return []
	related = _related(doc)
	hits = []
	for doctype, fields, extra in _sources(kind):
		if not fields or not frappe.db.exists("DocType", doctype):
			continue
		for field in fields:
			filters = dict(extra)
			filters[field] = value
			for name in frappe.get_all(doctype, filters=filters, pluck="name"):
				if (doctype, name) in related:
					continue
				hits.append(frappe._dict(doctype=doctype, name=name))
	seen, out = set(), []
	for h in hits:
		if (h.doctype, h.name) not in seen:
			seen.add((h.doctype, h.name))
			out.append(h)
	return out


def _format_hits(hits):
	if frappe.session.user == "Guest":
		# the public onboarding page must not reveal other parties
		return _("an existing record")
	return ", ".join(f"{_(h.doctype)} {get_link_to_form(h.doctype, h.name)}" for h in hits)


def check_duplicate_gstin(doc, gstin):
	"""V-2.4 / V-3.2: duplicate GSTIN blocks."""
	hits = find_duplicates(doc, "gstin", gstin)
	if hits:
		frappe.throw(
			_("GSTIN {0} already exists on {1}.").format(frappe.bold(clean_code(gstin)), _format_hits(hits)),
			title=_("Duplicate GSTIN"),
		)


def check_duplicate_pan(doc, pan):
	"""V-3.2: duplicate PAN only warns (one PAN may hold one GSTIN per state) and leaves a comment."""
	hits = find_duplicates(doc, "pan", pan)
	if not hits:
		return []
	frappe.msgprint(
		_("PAN {0} is already used by {1}. Please make sure this is not a duplicate supplier.").format(
			frappe.bold(clean_code(pan)), _format_hits(hits)
		),
		title=_("Duplicate PAN"),
		indicator="orange",
	)
	if doc.is_new():
		doc.flags.ub_pan_hits = (clean_code(pan), hits)
	else:
		add_pan_comment(doc, clean_code(pan), hits)
	return hits


def add_pan_comment(doc, pan=None, hits=None):
	if pan is None:
		pan, hits = doc.flags.get("ub_pan_hits") or (None, None)
	if not pan or not hits:
		return
	marker = f"Duplicate PAN warning: PAN {pan}"
	if frappe.db.exists(
		"Comment",
		{"reference_doctype": doc.doctype, "reference_name": doc.name, "content": ("like", f"%{marker}%")},
	):
		return
	doc.add_comment("Comment", f"{marker} is also used by {_format_hits(hits)}.")
	doc.flags.ub_pan_hits = None


# ---------------------------------------------------------------------------
# Bank account
# ---------------------------------------------------------------------------


def has_active_bank_account(supplier):
	if not supplier:
		return False
	return bool(frappe.db.exists("Bank Account", {"party_type": "Supplier", "party": supplier, "disabled": 0}))


def get_or_create_bank(bank_name):
	bank_name = (bank_name or "").strip()
	if not bank_name:
		return None
	if not frappe.db.exists("Bank", bank_name):
		frappe.get_doc({"doctype": "Bank", "bank_name": bank_name}).insert(ignore_permissions=True)
	return bank_name


def create_supplier_bank_account(supplier, bank_name, account_no=None, branch_code=None, iban=None,
		account_name=None, is_default=1):
	"""Create a party Bank Account for ``supplier``. Returns its name (or the existing one)."""
	bank = get_or_create_bank(bank_name)
	if not bank or not (account_no or iban):
		return None

	existing = frappe.db.get_value(
		"Bank Account",
		{"party_type": "Supplier", "party": supplier, "bank": bank, "bank_account_no": account_no or ""},
		"name",
	) if account_no else None
	if existing:
		return existing

	supplier_name = frappe.db.get_value("Supplier", supplier, "supplier_name") or supplier
	account_name = (account_name or supplier_name).strip()
	# Bank Account autonames "<account_name> - <bank>" without de-duplication.
	if frappe.db.exists("Bank Account", f"{account_name} - {bank}"):
		account_name = f"{account_name} ({supplier})"
		n = 2
		while frappe.db.exists("Bank Account", f"{account_name} - {bank}"):
			account_name = f"{account_name.rsplit(' #', 1)[0]} #{n}"
			n += 1

	ba = frappe.get_doc({
		"doctype": "Bank Account",
		"account_name": account_name,
		"bank": bank,
		"party_type": "Supplier",
		"party": supplier,
		"is_company_account": 0,
		"bank_account_no": account_no,
		"branch_code": branch_code,
		"iban": iban,
		"is_default": 1 if is_default else 0,
	})
	ba.flags.ignore_mandatory = True
	ba.insert(ignore_permissions=True)
	return ba.name


# ---------------------------------------------------------------------------
# Portal ownership
# ---------------------------------------------------------------------------


def get_user_suppliers(user=None):
	"""Suppliers the user is a portal user of."""
	user = user or frappe.session.user
	if not user or user == "Guest":
		return []
	return frappe.get_all("Portal User", filters={"user": user, "parenttype": "Supplier"}, pluck="parent")


def user_can_act_for_supplier(supplier, user=None):
	"""Portal user of that supplier, or a desk user with write access on it."""
	if not supplier or not frappe.db.exists("Supplier", supplier):
		return False
	user = user or frappe.session.user
	if supplier in get_user_suppliers(user):
		return True
	return frappe.has_permission("Supplier", "write", supplier, user=user)


def assert_supplier_access(supplier):
	if not user_can_act_for_supplier(supplier):
		frappe.throw(_("You do not have access to this supplier."), frappe.PermissionError)


def is_linked(record_doctype, record_name, link_doctype, link_name):
	"""True when an Address / Contact carries a Dynamic Link to ``link_doctype``:``link_name``."""
	if not record_name or not link_name:
		return False
	return bool(frappe.db.exists("Dynamic Link", {
		"parenttype": record_doctype, "parent": record_name,
		"link_doctype": link_doctype, "link_name": link_name,
	}))


# ---------------------------------------------------------------------------
# Approval route (BRD 6.5)
# ---------------------------------------------------------------------------


def _group_chain(supplier_group):
	"""The group itself plus its ancestors, so a setting on a parent group covers its children."""
	if not supplier_group:
		return []
	chain = [supplier_group]
	try:
		from frappe.utils.nestedset import get_ancestors_of

		chain += get_ancestors_of("Supplier Group", supplier_group) or []
	except Exception:
		pass
	return chain


def get_approval_route(supplier_group):
	"""Full (purchase -> quality -> finance), Finance (finance only) or Direct (purchase user approves)."""
	from universal_buying.universal_buying.settings import get_list

	chain = set(_group_chain(supplier_group))
	if chain & set(get_list("approval_full_chain_groups") or []):
		return ROUTE_FULL
	if chain & set(get_list("approval_finance_only_groups") or []):
		return ROUTE_FINANCE
	return ROUTE_DIRECT


def audit_required_for_group(supplier_group):
	from universal_buying.universal_buying.settings import get_list

	return bool(set(_group_chain(supplier_group)) & set(get_list("audit_required_groups") or []))
