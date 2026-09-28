"""Public token page for Supplier Onboarding (BRD 6.3, A-3.1 / AC-3.2).

/supplier_onboarding?token=<token>  (alias /supplier-onboarding)

The link works without login and expires when the onboarding is submitted (or rejected / cancelled).
A guest submit sets the onboarding to "Pending Approval" and notifies Purchase Manager / Purchase User.
"""

import base64

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

no_cache = 1
allow_guest = True

UPLOAD_FIELDS = {
	"gst_certificate": "GST Certificate",
	"pan_card": "PAN Card",
	"company_registration": "Company Registration",
	"msme_certificate": "MSME Certificate",
	"iso_9001": "ISO 9001",
	"iatf_16949": "IATF 16949",
	"as_9100": "AS 9100",
}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png")


def _get_onboarding(token):
	token = (token or "").strip()
	if len(token) < 20:
		return None
	name = frappe.db.get_value("Supplier Onboarding", {"onboarding_token": token}, "name")
	return frappe.get_doc("Supplier Onboarding", name) if name else None


def _is_open(so):
	return so.docstatus == 0 and not so.token_expired and so.status in ("Draft", "Pending Approval")


def get_context(context):
	context.no_cache = 1
	context.show_sidebar = False
	so = _get_onboarding(frappe.form_dict.get("token"))
	context.title = _("Supplier Registration")
	if not so:
		context.invalid = True
		return context
	context.token = frappe.form_dict.get("token")
	context.supplier_name = so.supplier_name
	if so.docstatus == 1 or so.status == "Approved":
		context.already_approved = True
		return context
	if not _is_open(so):
		context.invalid = True
		return context
	context.submitted = so.status == "Pending Approval"
	context.so = so
	context.title = _("Supplier Registration - {0}").format(so.supplier_name)
	context.supplier_groups = frappe.get_all("Supplier Group", filters={"is_group": 0}, pluck="name", order_by="name asc")
	context.countries = frappe.get_all("Country", pluck="name", order_by="name asc")
	context.currencies = frappe.get_all("Currency", filters={"enabled": 1}, pluck="name", order_by="name asc")
	context.incoterms = frappe.get_all("Incoterm", pluck="name", order_by="name asc") if frappe.db.exists("DocType", "Incoterm") else []
	context.gst_categories = [o for o in (so.meta.get_field("gst_category").options or "").split("\n") if o]
	context.upload_fields = UPLOAD_FIELDS
	return context


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=20, seconds=60 * 60)
def submit_onboarding(token, data):
	so = _get_onboarding(token)
	if not so or not _is_open(so):
		frappe.throw(_("This onboarding link is invalid or has expired."), frappe.PermissionError)
	if so.status == "Pending Approval":
		frappe.throw(_("This form has already been submitted and is under review."))

	data = frappe.parse_json(data) if isinstance(data, str) else (data or {})
	for field, label in (("supplier_group", _("Supplier Group")), ("email", _("Email")), ("address_line1", _("Address Line 1")),
			("city", _("City")), ("bank_name", _("Bank Name")), ("bank_account_no", _("Account Number"))):
		if not (data.get(field) or "").strip():
			frappe.throw(_("{0} is required.").format(label))

	so.apply_portal_submission(data)
	notify_purchase_team(so)
	return {"status": "submitted", "name": so.name}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=40, seconds=60 * 60)
def upload_onboarding_document(token, fieldname, filename, filedata):
	"""Guest-safe upload: only onboarding attach fields, PDF / image, max 5 MB, stored private."""
	so = _get_onboarding(token)
	if not so or not _is_open(so):
		frappe.throw(_("This onboarding link is invalid or has expired."), frappe.PermissionError)
	if fieldname not in UPLOAD_FIELDS:
		frappe.throw(_("Upload not allowed for this field."))
	filename = (filename or "").strip().replace("/", "_").replace("\\", "_")
	if not filename.lower().endswith(ALLOWED_EXTENSIONS):
		frappe.throw(_("Only PDF, JPG and PNG files are allowed."))
	if "," in (filedata or "")[:100]:
		filedata = filedata.split(",", 1)[1]
	try:
		content = base64.b64decode(filedata or "", validate=True)
	except Exception:
		frappe.throw(_("The file could not be read."))
	if not content or len(content) > MAX_UPLOAD_BYTES:
		frappe.throw(_("The file must be smaller than 5 MB."))

	file_doc = frappe.get_doc({
		"doctype": "File",
		"file_name": filename,
		"attached_to_doctype": "Supplier Onboarding",
		"attached_to_name": so.name,
		"attached_to_field": fieldname,
		"is_private": 1,
		"content": content,
	})
	file_doc.flags.ignore_permissions = True
	file_doc.save()
	frappe.db.set_value("Supplier Onboarding", so.name, fieldname, file_doc.file_url)
	return {"fieldname": fieldname, "file_name": filename}


def notify_purchase_team(so):
	"""A-3.1: tell Purchase Manager and Purchase User that the supplier has filled the form."""
	from universal_buying.universal_buying.utils import notify_users, users_with_role

	users = users_with_role("Purchase Manager") + users_with_role("Purchase User")
	link = frappe.utils.get_url(f"/app/supplier-onboarding/{so.name}")
	esc = frappe.utils.escape_html
	message = _(
		"<p>Supplier <b>{0}</b> has completed the onboarding form and it is ready for review.</p>"
		"<p>Email: {1}<br>Onboarding: {2}</p>"
		'<p><a href="{3}">Review Supplier Onboarding</a></p>'
	).format(esc(so.supplier_name or ""), esc(so.email or "-"), so.name, link)
	notify_users(users, _("Supplier Onboarding Submitted: {0}").format(so.supplier_name), message, "Supplier Onboarding", so.name)
