# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt
"""Supplier Onboarding (BRD 6.3).

Submit creates, in one transaction: the Supplier, its primary Address and Contact, the party
Bank Account (from the onboarding bank fields), a portal User with the Supplier role, marks the
Prospective Supplier Onboarded and re-points open RFQ supplier rows / Supplier Quotations from the
prospective supplier to the new Supplier. The token link expires on submit.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, now_datetime, validate_email_address

from universal_buying.ub_supplier.utils import (
	add_pan_comment,
	audit_required_for_group,
	check_duplicate_gstin,
	check_duplicate_pan,
	create_supplier_bank_account,
	validate_gstin,
	validate_pan,
)
from universal_buying.universal_buying.settings import get_setting

SEVERITY_RANK = {
	"Loss of Company Reputation": 5,
	"Customer dissatisfaction": 4,
	"Time and cost Overrunning of the Project": 3,
	"Marginal effect on the project": 2,
	"No effect on the project": 1,
}
OCCURRENCE_RANK = {
	"Very high chance of occurance": 5,
	"High chance of occurance": 4,
	"Medium chance of occurance": 3,
	"Low chance of occurance": 2,
	"Very low chance of occurance": 1,
}
PREVENTION_RANK = {
	"No control available": 5,
	"Guide lines not available for design": 4,
	"Minor changes in proven design": 3,
	"Control available but not followed": 2,
	"Already proven parameters used in the project": 1,
}
RPN_FIELDS = {
	"mitigation_plan": "Mitigation Plan",
	"responsibility": "Owner",
	"target_date": "Target Date",
	"status": "Status",
}

# Onboarding field -> Supplier Document Type key (vault rows created on submit)
VAULT_MAP = [
	("gst_certificate", "gst_registration", None),
	("pan_card", "pan_card", None),
	("msme_certificate", "msme_udyam", "msme_expiry"),
	("iso_9001", "quality_certifications", None),
]
OTHER_VAULT_DOCS = [
	("iso_14001", "ISO 14001"),
	("iso_45001", "ISO 45001"),
	("iatf_16949", "IATF 16949"),
	("iso_ts_22163", "ISO / TS 22163"),
	("as_9100", "AS 9100"),
	("company_registration", "Company Registration"),
	("attach_1", "Other Certificate 1"),
	("attach_2", "Other Certificate 2"),
	("attach_3", "Other Certificate 3"),
]


def rpn_threshold():
	"""RPN at or above which mitigation is required; 0 disables the rule."""
	value = get_setting("rpn_mitigation_threshold", default=27)
	return cint(value)


class SupplierOnboarding(Document):
	# ------------------------------------------------------------------ validate
	def validate(self):
		self.supplier_name = (self.supplier_name or "").strip()
		if not self.status:
			self.status = "Draft"
		self.validate_email()
		self.validate_unique_supplier_name()
		# V-3.2
		self.pan = validate_pan(self.pan)
		self.gstin = validate_gstin(self.gstin, self.pan)
		if self.gstin:
			check_duplicate_gstin(self, self.gstin)
		if self.pan:
			check_duplicate_pan(self, self.pan)
		if self.ifsc_code:
			self.ifsc_code = self.ifsc_code.strip().upper()

		if self.docstatus == 0:
			self.questionnaire_enabled = cint(get_setting("onboarding_questionnaire"))
			self.audit_required = 1 if audit_required_for_group(self.supplier_group) else 0
		if self.questionnaire_enabled:
			self.load_questions()
			self.compute_risk()
			self.compute_ranking()

	def before_insert(self):
		if frappe.session.user == "Guest":
			# public web form (supplier_onboarding_form): the supplier filled it in
			self.status = "Pending Approval"
			self.portal_submitted_on = now_datetime()
			for field in ("prospective_supplier", "supplier", "portal_user", "supplier_audit_log", "onboarding_token", "onboarding_link"):
				self.set(field, None)
			self.token_expired = 0

	def after_insert(self):
		add_pan_comment(self)
		if frappe.session.user == "Guest":
			from universal_buying.www.supplier_onboarding import notify_purchase_team

			notify_purchase_team(self)

	def validate_email(self):
		self.email = (self.email or "").strip()
		if self.email and not validate_email_address(self.email):
			frappe.throw(_("Invalid email address: {0}").format(self.email))

	def validate_unique_supplier_name(self):
		"""V-3.1: unique across Suppliers and other live Onboardings."""
		if not self.supplier_name:
			return
		supplier = frappe.db.get_value("Supplier", {"supplier_name": self.supplier_name}, "name")
		if supplier and supplier != self.supplier:
			frappe.throw(
				_("A Supplier named {0} already exists ({1}).").format(frappe.bold(self.supplier_name), supplier),
				title=_("Duplicate Supplier Name"),
			)
		other = frappe.db.get_value(
			"Supplier Onboarding",
			{"supplier_name": self.supplier_name, "name": ("!=", self.name), "docstatus": ("<", 2), "status": ("!=", "Rejected")},
			"name",
		)
		if other:
			frappe.throw(
				_("Supplier Name {0} is already used in Supplier Onboarding {1}.").format(frappe.bold(self.supplier_name), other),
				title=_("Duplicate Supplier Name"),
			)

	# ------------------------------------------------------------- questionnaire
	def load_questions(self, force=False):
		"""Fill empty questionnaire tables from the question bank (Risk / Evaluation / Ranking)."""
		from universal_buying.ub_supplier.api import get_default_question_bank, get_question_list

		if not self.question_bank:
			self.question_bank = get_default_question_bank()
		if not self.question_bank:
			return
		rows = get_question_list(self.question_bank)
		if force or not self.risk_analysis:
			self.set("risk_analysis", [])
			for q in rows:
				if q["category"] == "Risk":
					self.append("risk_analysis", {"question_no": q["question_no"], "main_question": q["main_question"], "question": q["question"]})
		if force or not self.evaluation:
			self.set("evaluation", [])
			for q in rows:
				if q["category"] == "Evaluation":
					self.append("evaluation", {"question_no": q["question_no"], "main_question": q["main_question"], "question": q["question"]})
		if force or not self.evaluation_ranking:
			self.set("evaluation_ranking", [])
			sl = 0
			for q in rows:
				if q["category"] == "Ranking":
					sl += 1
					self.append("evaluation_ranking", {
						"sl_no": sl, "evaluation_criteria": q["question"],
						"option_5": q["option_5"], "option_4": q["option_4"], "option_3": q["option_3"],
						"option_2": q["option_2"], "option_1": q["option_1"],
					})

	def compute_risk(self):
		"""RPN = severity x occurrence x prevention (server side; the source computed it only in the browser)."""
		for row in self.risk_analysis:
			row.severity_value = SEVERITY_RANK.get(row.severity_ranking or "", 0)
			row.occurrence_value = OCCURRENCE_RANK.get(row.probability_of_occurance or "", 0)
			row.prevention_value = PREVENTION_RANK.get(row.prevention_control_if_any or "", 0)
			if row.severity_value and row.occurrence_value and row.prevention_value:
				row.risk_priority_no = row.severity_value * row.occurrence_value * row.prevention_value
			else:
				row.risk_priority_no = 0

	def compute_ranking(self):
		total = 0
		for row in self.evaluation_ranking:
			row.rating = 0
			if row.ranking_select:
				for score in (5, 4, 3, 2, 1):
					if row.get(f"option_{score}") and row.get(f"option_{score}") == row.ranking_select:
						row.rating = score
						break
				if not row.rating:
					frappe.throw(_("Evaluation Ranking row {0}: {1} is not one of the options.").format(row.idx, frappe.bold(row.ranking_select)))
			total += cint(row.rating)
		self.evaluation_score = total

	def validate_questionnaire(self):
		"""V-3.3"""
		threshold = rpn_threshold()
		errors = []
		for row in self.risk_analysis:
			missing = []
			if not row.effect:
				missing.append(_("Effect"))
			if not row.severity_ranking:
				missing.append(_("Severity"))
			if not row.probability_of_occurance:
				missing.append(_("Occurrence"))
			if not row.prevention_control_if_any:
				missing.append(_("Prevention"))
			if threshold and cint(row.risk_priority_no) >= threshold:
				missing += [_(label) for field, label in RPN_FIELDS.items() if not row.get(field)]
			if missing:
				errors.append(_("Risk Analysis row {0} ({1}): {2}").format(row.idx, row.question, ", ".join(missing)))
		for row in self.evaluation:
			if not row.response:
				errors.append(_("Evaluation row {0} ({1}): Yes / No").format(row.idx, row.question))
		for row in self.evaluation_ranking:
			if not row.ranking_select:
				errors.append(_("Evaluation Ranking row {0} ({1}): Ranking").format(row.idx, row.evaluation_criteria))
		if errors:
			shown = errors[:15]
			more = len(errors) - len(shown)
			frappe.throw(
				_("Complete the questionnaire before submitting:") + "<br>" + "<br>".join(shown)
				+ (("<br>" + _("... and {0} more").format(more)) if more > 0 else ""),
				title=_("Questionnaire Incomplete"),
			)

	# -------------------------------------------------------------------- submit
	def before_submit(self):
		if self.questionnaire_enabled:
			self.validate_questionnaire()
		self.validate_audit()
		self.validate_master_data()

	def validate_audit(self):
		"""V-3.4"""
		if not self.audit_required:
			return
		audit = frappe.db.get_value(
			"Supplier Audit Log", {"supplier_onboarding": self.name, "docstatus": 1}, "name", order_by="creation desc"
		)
		if not audit:
			frappe.throw(
				_("Supplier Group {0} requires a submitted Supplier Audit Log for this onboarding.").format(frappe.bold(self.supplier_group)),
				title=_("Audit Required"),
			)
		self.supplier_audit_log = audit

	def validate_master_data(self):
		"""AC-3.1: a new Supplier must get an address, a contact and (when required) a bank account."""
		missing = []
		for field in ("supplier_group", "country", "address_line1", "city", "email"):
			if not self.get(field):
				missing.append(self.meta.get_label(field))
		if cint(get_setting("require_bank_account")):
			if not self.bank_name:
				missing.append(self.meta.get_label("bank_name"))
			if not (self.bank_account_no or self.iban):
				missing.append(self.meta.get_label("bank_account_no"))
		if missing:
			frappe.throw(_("Please fill: {0}").format(", ".join(missing)), title=_("Missing Details"))

	def on_submit(self):
		supplier = make_supplier_from_onboarding(self)
		self.db_set({"supplier": supplier, "status": "Approved", "token_expired": 1})
		frappe.msgprint(
			_("Supplier {0} created with address, contact, bank account and portal user.").format(
				frappe.utils.get_link_to_form("Supplier", supplier)
			),
			alert=True,
		)

	def on_cancel(self):
		self.db_set("token_expired", 1)

	# -------------------------------------------------------------------- token
	def ensure_token(self):
		from universal_buying.ub_supplier.api import get_onboarding_link

		if self.onboarding_token and not self.token_expired:
			return self.onboarding_token
		if self.docstatus != 0:
			frappe.throw(_("The onboarding link cannot be issued for a submitted or cancelled onboarding."))
		token = frappe.generate_hash(length=32)
		self.db_set({"onboarding_token": token, "token_expired": 0, "onboarding_link": get_onboarding_link(token)})
		return token

	@frappe.whitelist()
	def send_onboarding_link(self):
		self.check_permission("write")
		from universal_buying.ub_supplier.api import send_onboarding_email

		recipient = send_onboarding_email(self)
		frappe.msgprint(_("Onboarding link sent to {0}").format(recipient), alert=True)
		return self.onboarding_link

	@frappe.whitelist()
	def reject(self, reason=None):
		self.check_permission("write")
		if self.docstatus != 0:
			frappe.throw(_("Only a draft onboarding can be rejected."))
		self.db_set({"status": "Rejected", "token_expired": 1})
		if reason:
			self.add_comment("Comment", _("Rejected: {0}").format(reason))

	@frappe.whitelist()
	def reload_questions(self):
		self.check_permission("write")
		self.load_questions(force=True)
		self.save()

	# ------------------------------------------------------------------- audit
	@frappe.whitelist()
	def create_audit_log(self):
		"""Create a draft Supplier Audit Log from the active checklist, carrying the supplier's self ratings."""
		self.check_permission("write")
		if self.is_new():
			frappe.throw(_("Save the onboarding first."))
		existing = frappe.db.get_value("Supplier Audit Log", {"supplier_onboarding": self.name, "docstatus": ("<", 2)}, "name")
		if existing:
			return existing
		if not self.supplier_audit_type:
			frappe.throw(_("Select the Industry Type first."))
		from universal_buying.ub_supplier.api import get_active_checklist

		checklist = get_active_checklist()
		if not checklist:
			frappe.throw(_("Create an active Supplier Audit Checklist first."))
		log = frappe.new_doc("Supplier Audit Log")
		log.update({
			"supplier_onboarding": self.name,
			"supplier_name": self.supplier_name,
			"supplier": self.supplier,
			"supplier_audit_type": self.supplier_audit_type,
			"supplier_audit_checklist": checklist,
			"audit_type": "New Supplier Qualification",
		})
		log.load_checklist()
		self_rating = {(r.group, r.question): r for r in self.audit_self_assessment}
		for row in log.audit_rows:
			src = self_rating.get((row.group, row.question))
			if src:
				row.supplier_self_rating = src.supplier_self_rating
				row.answer = src.answer
				row.reference_procedure = src.reference_procedure
		log.insert()
		self.db_set("supplier_audit_log", log.name)
		return log.name

	@frappe.whitelist()
	def load_self_assessment(self):
		"""Fill the self-assessment table with the checklist questions for the industry type."""
		self.check_permission("write")
		from universal_buying.ub_supplier.api import get_audit_questions

		self.set("audit_self_assessment", [])
		for q in get_audit_questions(self.supplier_audit_type):
			self.append("audit_self_assessment", {
				"group": q["group"], "question": q["question"], "option_list": frappe.as_json(q["options"]),
				"max_score": q["max_score"], "min_score": q["min_score"],
			})
		self.save()

	# ------------------------------------------------------------ portal (guest)
	def apply_portal_submission(self, data):
		"""A-3.1: data typed by the supplier on the token page."""
		allowed = (
			"supplier_type", "supplier_group", "country", "gst_category", "gstin", "pan", "website",
			"contact_person", "designation", "email", "phone", "mobile",
			"address_type", "address_line1", "address_line2", "city", "state", "pincode",
			"bank_name", "account_holder_name", "bank_account_no", "ifsc_code", "bank_branch", "iban", "swift_code",
			"msme", "msme_category", "msme_registration_no", "msme_expiry",
			"escalation_contact_person", "escalation_designation", "escalation_email", "escalation_phone",
			"supplier_notes", "incoterm", "default_currency",
		)
		for field in allowed:
			if field in data:
				value = data.get(field)
				df = self.meta.get_field(field)
				if df and df.fieldtype == "Link" and value and not frappe.db.exists(df.options, value):
					continue
				self.set(field, value)
		self.status = "Pending Approval"
		self.portal_submitted_on = now_datetime()
		self.flags.ignore_permissions = True
		self.save()


# ---------------------------------------------------------------------------
# Submit side effects (A-3.2 .. A-3.4)
# ---------------------------------------------------------------------------


def make_supplier_from_onboarding(so):
	sup_meta = frappe.get_meta("Supplier")
	sup = frappe.new_doc("Supplier")
	sup.update({
		"supplier_name": so.supplier_name,
		"supplier_group": so.supplier_group,
		"supplier_type": so.supplier_type or "Company",
		"country": so.country,
		"default_currency": so.default_currency,
		"default_price_list": so.default_price_list,
		"payment_terms": so.payment_terms,
		"website": so.website,
		"tax_id": so.gstin or None,
		"tax_category": so.tax_category,
		"tax_withholding_category": so.tax_withholding_category,
		"ub_onboarding": so.name,
		"ub_moq_per_line": cint(so.moq_per_line),
		"ub_msme": cint(so.msme),
		"ub_msme_category": so.msme_category if so.msme else None,
		"ub_msme_certificate": so.msme_certificate if so.msme else None,
		"ub_msme_expiry": so.msme_expiry if so.msme else None,
		"supplier_details": so.supplier_notes,
	})
	incoterm_field = "incoterm" if sup_meta.has_field("incoterm") else "ub_incoterm"
	if sup_meta.has_field(incoterm_field):
		sup.set(incoterm_field, so.incoterm)
	for field in ("pan", "ub_pan"):
		if sup_meta.has_field(field):
			sup.set(field, so.pan)
			break
	if sup_meta.has_field("gstin"):
		sup.gstin = so.gstin
	if sup_meta.has_field("gst_category") and so.gst_category:
		sup.gst_category = so.gst_category

	user = get_or_create_portal_user(so)
	if user:
		sup.append("portal_users", {"user": user})
	add_vault_rows(so, sup)

	sup.flags.ignore_permissions = True
	sup.flags.ignore_mandatory = True
	sup.insert()

	address = create_primary_address(so, sup.name)
	contact = create_primary_contact(so, sup.name, user)
	create_escalation_contact(so, sup.name)
	updates = {}
	if address:
		from frappe.contacts.doctype.address.address import get_address_display

		updates["supplier_primary_address"] = address
		updates["primary_address"] = get_address_display(frappe.get_doc("Address", address).as_dict())
	if contact:
		updates["supplier_primary_contact"] = contact
		updates["email_id"] = so.email
		updates["mobile_no"] = so.mobile or so.phone
	if updates:
		frappe.db.set_value("Supplier", sup.name, updates)

	create_supplier_bank_account(
		sup.name,
		so.bank_name,
		account_no=(so.bank_account_no or "").strip() or None,
		branch_code=so.ifsc_code,
		iban=(so.iban or "").strip() or None,
		account_name=so.account_holder_name or so.supplier_name,
	)

	if so.portal_user != user:
		so.db_set("portal_user", user)
	if so.supplier_audit_log:
		frappe.db.set_value("Supplier Audit Log", so.supplier_audit_log, "supplier", sup.name)

	link_prospective_supplier(so, sup.name)
	repoint_prospective_documents(so.prospective_supplier, sup.name)
	return sup.name


def get_or_create_portal_user(so):
	email = (so.email or "").strip().lower()
	if not email:
		return None
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
		if "Supplier" not in [r.role for r in user.roles]:
			user.flags.ignore_permissions = True
			user.add_roles("Supplier")
		return user.name
	first_name = (so.contact_person or so.supplier_name or email).strip()
	user = frappe.get_doc({
		"doctype": "User",
		"email": email,
		"first_name": first_name[:140],
		"user_type": "Website User",
		"send_welcome_email": 0 if frappe.flags.in_test else 1,
		"roles": [{"role": "Supplier"}],
	})
	user.flags.ignore_permissions = True
	user.insert()
	return user.name


def create_primary_address(so, supplier):
	if not (so.address_line1 and so.city and so.country):
		return None
	address = frappe.get_doc({
		"doctype": "Address",
		"address_title": so.supplier_name,
		"address_type": so.address_type or "Billing",
		"address_line1": so.address_line1,
		"address_line2": so.address_line2,
		"city": so.city,
		"state": so.state,
		"pincode": so.pincode,
		"country": so.country,
		"email_id": so.email,
		"phone": so.phone or so.mobile,
		"is_primary_address": 1,
		"is_shipping_address": 1,
		"links": [{"link_doctype": "Supplier", "link_name": supplier}],
	})
	if so.gstin and address.meta.has_field("gstin"):
		address.gstin = so.gstin
	if so.gst_category and address.meta.has_field("gst_category"):
		address.gst_category = so.gst_category
	address.flags.ignore_permissions = True
	address.flags.ignore_mandatory = True
	address.insert()
	return address.name


def _make_contact(supplier, first_name, email=None, phone=None, mobile=None, designation=None, is_primary=0, user=None):
	contact = frappe.new_doc("Contact")
	contact.first_name = (first_name or supplier)[:140]
	contact.designation = designation
	contact.is_primary_contact = is_primary
	if user and contact.meta.has_field("user"):
		contact.user = user
	if email:
		contact.append("email_ids", {"email_id": email, "is_primary": 1})
	if phone:
		contact.append("phone_nos", {"phone": phone, "is_primary_phone": 1})
	if mobile:
		contact.append("phone_nos", {"phone": mobile, "is_primary_mobile_no": 1})
	contact.append("links", {"link_doctype": "Supplier", "link_name": supplier})
	contact.flags.ignore_permissions = True
	contact.flags.ignore_mandatory = True
	contact.insert()
	return contact.name


def create_primary_contact(so, supplier, user=None):
	if not (so.contact_person or so.email or so.phone or so.mobile):
		return None
	return _make_contact(
		supplier, so.contact_person or so.supplier_name, email=so.email, phone=so.phone, mobile=so.mobile,
		designation=so.designation, is_primary=1, user=user,
	)


def create_escalation_contact(so, supplier):
	if not (so.escalation_contact_person and (so.escalation_email or so.escalation_phone)):
		return None
	return _make_contact(
		supplier, so.escalation_contact_person, email=so.escalation_email, phone=so.escalation_phone,
		designation=so.escalation_designation or _("Escalation"),
	)


def add_vault_rows(so, sup):
	if not frappe.db.exists("DocType", "Supplier Document Type") or not sup.meta.has_field("ub_document_vault"):
		return
	used = set()
	for field, key, expiry_field in VAULT_MAP:
		url = so.get(field)
		if url and key not in used and frappe.db.exists("Supplier Document Type", key):
			used.add(key)
			sup.append("ub_document_vault", {
				"document_type": key, "doc_key": key, "attachment": url,
				"expires_on": so.get(expiry_field) if expiry_field else None,
			})
	if frappe.db.exists("Supplier Document Type", "other"):
		for field, label in OTHER_VAULT_DOCS:
			if so.get(field):
				sup.append("ub_document_vault", {"document_type": "other", "doc_key": "other", "custom_label": label, "attachment": so.get(field)})


def link_prospective_supplier(so, supplier):
	"""A-3.3"""
	if so.prospective_supplier and frappe.db.exists("Prospective Supplier", so.prospective_supplier):
		frappe.db.set_value(
			"Prospective Supplier", so.prospective_supplier,
			{"linked_supplier": supplier, "status": "Onboarded", "supplier_onboarding": so.name},
		)


def repoint_prospective_documents(prospective_supplier, supplier):
	"""A-3.4: open RFQ supplier rows and Supplier Quotations move from the prospective to the new Supplier.
	The ub_prospective_supplier fields belong to UB Sourcing; skip silently while they do not exist."""
	if not prospective_supplier:
		return {"rfq_rows": 0, "quotations": 0}
	supplier_name = frappe.db.get_value("Supplier", supplier, "supplier_name")
	moved_rows = moved_sq = 0

	if frappe.get_meta("Request for Quotation Supplier").has_field("ub_prospective_supplier"):
		rows = frappe.get_all(
			"Request for Quotation Supplier",
			filters={"ub_prospective_supplier": prospective_supplier, "parenttype": "Request for Quotation"},
			fields=["name", "parent", "supplier"],
		)
		for row in rows:
			if frappe.db.get_value("Request for Quotation", row.parent, "docstatus") == 2:
				continue
			if row.supplier and row.supplier != supplier:
				continue
			frappe.db.set_value("Request for Quotation Supplier", row.name, {"supplier": supplier, "supplier_name": supplier_name}, update_modified=False)
			moved_rows += 1

	if frappe.get_meta("Supplier Quotation").has_field("ub_prospective_supplier"):
		for sq in frappe.get_all(
			"Supplier Quotation",
			filters={"ub_prospective_supplier": prospective_supplier, "docstatus": ("<", 2), "status": ("not in", ["Expired", "Stopped", "Cancelled"])},
			pluck="name",
		):
			frappe.db.set_value("Supplier Quotation", sq, {"supplier": supplier, "supplier_name": supplier_name}, update_modified=False)
			moved_sq += 1
	return {"rfq_rows": moved_rows, "quotations": moved_sq}
