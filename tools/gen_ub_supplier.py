"""Generate the UB Supplier module doctypes (BRD v2 sections 6.2 - 6.7).

Run from the app folder: <bench>/env/bin/python tools/gen_ub_supplier.py
Only the .json files are rewritten; hand-written .py / .js controllers are kept.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_doctype import F, make_doctype, perm

M = "UB Supplier"

GST_CATEGORIES = "\nRegistered Regular\nRegistered Composition\nUnregistered\nSEZ\nOverseas\nUIN Holders"
INDUSTRY_TYPES = "\nIndustrial\nAutomotive\nMedical\nRailways\nDefence / Aerospace"
SEVERITY = "\nLoss of Company Reputation\nCustomer dissatisfaction\nTime and cost Overrunning of the Project\nMarginal effect on the project\nNo effect on the project"
OCCURRENCE = "\nVery high chance of occurance\nHigh chance of occurance\nMedium chance of occurance\nLow chance of occurance\nVery low chance of occurance"
PREVENTION = "\nNo control available\nGuide lines not available for design\nMinor changes in proven design\nControl available but not followed\nAlready proven parameters used in the project"


def ro(p):
	"""read-only permission row"""
	return perm(p, write=0, create=0, delete=0)


# ---------------------------------------------------------------------------
# 6.2 Prospective Supplier
# ---------------------------------------------------------------------------
make_doctype(
	M, "Prospective Supplier",
	[
		F("supplier_name", "Data", "Supplier Name", reqd=1, in_list_view=1, in_standard_filter=1, bold=1),
		F("supplier_type", "Select", "Supplier Type", options="Company\nIndividual\nPartnership", default="Company"),
		F("column_break_basic", "Column Break"),
		F("status", "Select", "Status", options="Active\nOnboarding Sent\nOnboarded", default="Active", read_only=1, in_list_view=1, in_standard_filter=1, no_copy=1),
		F("linked_supplier", "Link", "Linked Supplier", options="Supplier", read_only=1, no_copy=1),
		F("supplier_onboarding", "Link", "Supplier Onboarding", options="Supplier Onboarding", read_only=1, no_copy=1),
		F("section_break_contact", "Section Break", "Contact Details"),
		F("contact_person", "Data", "Contact Person", in_list_view=1),
		F("designation", "Data", "Designation"),
		F("email", "Data", "Email", options="Email", reqd=1, in_list_view=1),
		F("column_break_contact", "Column Break"),
		F("phone", "Data", "Phone", options="Phone"),
		F("mobile", "Data", "Mobile", options="Phone"),
		F("website", "Data", "Website"),
		F("section_break_address", "Section Break", "Address"),
		F("address_line1", "Data", "Address Line 1"),
		F("address_line2", "Data", "Address Line 2"),
		F("city", "Data", "City"),
		F("column_break_address", "Column Break"),
		F("state", "Data", "State"),
		F("country", "Link", "Country", options="Country"),
		F("pincode", "Data", "Pincode"),
		F("section_break_tax", "Section Break", "Tax Information"),
		F("gstin", "Data", "GSTIN", description="15 characters; characters 3-12 must equal the PAN."),
		F("gst_category", "Select", "GST Category", options=GST_CATEGORIES),
		F("column_break_tax", "Column Break"),
		F("pan", "Data", "PAN", description="Format AAAAA9999A"),
		F("section_break_notes", "Section Break", "Additional Information"),
		F("notes", "Small Text", "Notes"),
	],
	naming_series="PSUP-.YYYY.-.#####",
	title_field="supplier_name",
	search_fields="supplier_name,email,gstin",
	permissions=[
		perm("System Manager", delete=1),
		perm("Purchase Manager", delete=1),
		perm("Purchase User"),
		ro("Sourcing User"),
		ro("Sourcing Manager"),
	],
	js=True,
	extra={"show_title_field_in_link": 1},
)

# ---------------------------------------------------------------------------
# Question bank (risk / evaluation / ranking questions for the onboarding)
# ---------------------------------------------------------------------------
make_doctype(
	M, "Supplier Onboarding Question Bank Detail",
	[
		F("category", "Select", "Category", options="Risk\nEvaluation\nRanking", reqd=1, in_list_view=1, default="Risk"),
		F("question_no", "Data", "Section Code", in_list_view=1, description="Groups questions, e.g. SR_1, SE_2, RANK"),
		F("main_question", "Small Text", "Section Heading", in_list_view=1),
		F("question", "Small Text", "Question", reqd=1, in_list_view=1),
		F("weightage", "Int", "Weightage"),
		F("ranking_section", "Section Break", "Ranking Options", depends_on="eval:doc.category=='Ranking'"),
		F("option_5", "Data", "Score 5"),
		F("option_4", "Data", "Score 4"),
		F("option_3", "Data", "Score 3"),
		F("column_break_opts", "Column Break"),
		F("option_2", "Data", "Score 2"),
		F("option_1", "Data", "Score 1"),
	],
	istable=1,
)
make_doctype(
	M, "Supplier Onboarding Question Bank",
	[
		F("question_bank_name", "Data", "Question Bank Name", reqd=1, unique=1, in_list_view=1),
		F("is_default", "Check", "Default", default="0", in_list_view=1, description="Used for new Supplier Onboardings."),
		F("description", "Small Text", "Description"),
		F("questions", "Table", "Questions", options="Supplier Onboarding Question Bank Detail"),
	],
	autoname="field:question_bank_name",
	title_field="question_bank_name",
	permissions=[perm("System Manager", delete=1), perm("Purchase Manager", delete=1), ro("Purchase User"), perm("Quality Manager")],
)

# ---------------------------------------------------------------------------
# Onboarding questionnaire child tables
# ---------------------------------------------------------------------------
make_doctype(
	M, "Supplier Risk Analysis",
	[
		F("question_no", "Data", "Section Code", read_only=1, hidden=1),
		F("main_question", "Data", "Risk Area", read_only=1, in_list_view=1, columns=2),
		F("question", "Small Text", "Question", read_only=1, in_list_view=1, columns=3),
		F("effect", "Data", "Effect"),
		F("severity_ranking", "Select", "Severity Evaluation Criteria", options=SEVERITY, in_list_view=1, columns=2),
		F("severity_value", "Int", "Severity Ranking", read_only=1),
		F("probability_of_occurance", "Select", "Occurrence Evaluation Criteria", options=OCCURRENCE, in_list_view=1, columns=1),
		F("occurrence_value", "Int", "Occurrence Ranking", read_only=1),
		F("prevention_control_if_any", "Select", "Prevention Evaluation Criteria", options=PREVENTION, in_list_view=1, columns=1),
		F("prevention_value", "Int", "Prevention Ranking", read_only=1),
		F("risk_priority_no", "Int", "Risk Priority Number", read_only=1, in_list_view=1, columns=1),
		F("mitigation_section", "Section Break", "Mitigation", description="Required when the RPN is at or above the threshold in Buying Control Settings."),
		F("mitigation_plan", "Small Text", "Mitigation Plan"),
		F("responsibility", "Link", "Owner", options="User"),
		F("column_break_mit", "Column Break"),
		F("target_date", "Date", "Target Date"),
		F("status", "Select", "Status", options="\nOpen\nCompleted\nClosed"),
	],
	istable=1,
)
make_doctype(
	M, "Supplier Evaluation",
	[
		F("question_no", "Data", "Section Code", read_only=1, hidden=1),
		F("main_question", "Data", "Section", read_only=1, in_list_view=1, columns=2),
		F("question", "Small Text", "Question", read_only=1, in_list_view=1, columns=4),
		F("response", "Select", "Yes / No", options="\nYes\nNo", in_list_view=1, columns=1),
		F("remarks", "Small Text", "Remarks", in_list_view=1, columns=3),
	],
	istable=1,
)
make_doctype(
	M, "Supplier Evaluation Ranking",
	[
		F("sl_no", "Int", "Sl No", read_only=1, hidden=1),
		F("evaluation_criteria", "Small Text", "Evaluation Criteria", read_only=1, in_list_view=1, columns=5),
		F("option_5", "Data", "Score 5", read_only=1, hidden=1),
		F("option_4", "Data", "Score 4", read_only=1, hidden=1),
		F("option_3", "Data", "Score 3", read_only=1, hidden=1),
		F("option_2", "Data", "Score 2", read_only=1, hidden=1),
		F("option_1", "Data", "Score 1", read_only=1, hidden=1),
		F("ranking_select", "Select", "Ranking", in_list_view=1, columns=3, description="One of the five options of this criterion (options are set per row)."),
		F("rating", "Int", "Rating", read_only=1, in_list_view=1, columns=1),
		F("evidence_remarks", "Small Text", "Evidence / Remarks"),
	],
	istable=1,
)

# ---------------------------------------------------------------------------
# 6.4 Audit checklist + audit log
# ---------------------------------------------------------------------------
make_doctype(
	M, "Supplier Audit Checklist Detail",
	[
		F("group", "Data", "Group", reqd=1, in_list_view=1),
		F("question", "Small Text", "Question", reqd=1, in_list_view=1),
		F("options", "Small Text", "Options", reqd=1, description="One answer per line, lowest score first."),
		F("max_score", "Int", "Max Score", in_list_view=1),
		F("minimum_score_required_section", "Section Break", "Minimum Score Required by Industry"),
		F("industrial", "Int", "Industrial"),
		F("railways", "Int", "Railways"),
		F("column_break_neti", "Column Break"),
		F("automotive", "Int", "Automotive"),
		F("defence_aerospace", "Int", "Defence / Aerospace"),
		F("column_break_hufg", "Column Break"),
		F("medical", "Int", "Medical"),
	],
	istable=1,
)
make_doctype(
	M, "Supplier Audit Checklist",
	[
		F("checklist_name", "Data", "Checklist Name", reqd=1, unique=1, in_list_view=1),
		F("company", "Link", "Company", options="Company", in_list_view=1, description="Blank = all companies"),
		F("column_break_qtqq", "Column Break"),
		F("is_active", "Check", "Is Active", default="1", in_list_view=1),
		F("section_break_rows", "Section Break"),
		F("checklist_detail", "Table", "Checklist Questions", options="Supplier Audit Checklist Detail"),
	],
	autoname="field:checklist_name",
	title_field="checklist_name",
	permissions=[perm("System Manager", delete=1), perm("Quality Manager", delete=1), perm("Purchase Manager"), ro("Purchase User")],
)
make_doctype(
	M, "Supplier Audit Log Detail",
	[
		F("group", "Data", "Group", read_only=1, in_list_view=1, columns=2),
		F("question", "Small Text", "Question", read_only=1, in_list_view=1, columns=3),
		F("option_list", "JSON", "Option List", hidden=1),
		F("answer", "Small Text", "Answer for Rating", read_only=1, description="Checklist option matching the rating (options are listed lowest score first, starting at 0)."),
		F("reference_procedure", "Small Text", "Reference Procedure / WI"),
		F("column_break_hkqc", "Column Break"),
		F("supplier_self_rating", "Int", "Supplier Self Rating", in_list_view=1, columns=1),
		F("company_rating", "Int", "Company Rating", in_list_view=1, columns=1),
		F("audit_finding_category", "Select", "Finding", options="\nO+\nOI\nNC", in_list_view=1, columns=1),
		F("observation", "Small Text", "Audit Observation"),
		F("section_break_scores", "Section Break"),
		F("max_score", "Int", "Max Score", read_only=1, in_list_view=1, columns=1),
		F("min_score", "Int", "Min Score", read_only=1, default="0"),
		F("column_break_scores", "Column Break"),
		F("non_conformance", "Link", "Non Conformance", options="Non Conformance", read_only=1, no_copy=1),
	],
	istable=1,
)
make_doctype(
	M, "Supplier Audit Log",
	[
		F("supplier", "Link", "Supplier", options="Supplier", in_list_view=1, in_standard_filter=1),
		F("supplier_name", "Data", "Supplier Name", fetch_from="supplier.supplier_name", fetch_if_empty=1),
		F("supplier_onboarding", "Link", "Supplier Onboarding", options="Supplier Onboarding", in_standard_filter=1),
		F("company", "Link", "Company", options="Company"),
		F("column_break_kigt", "Column Break"),
		F("audit_type", "Select", "Audit Type", options="New Supplier Qualification\nSupplier Requalification", reqd=1, in_list_view=1, default="New Supplier Qualification"),
		F("audit_date", "Date", "Audit Date", reqd=1, default="Today"),
		F("supplier_audit_checklist", "Link", "Audit Checklist", options="Supplier Audit Checklist", reqd=1),
		F("supplier_audit_type", "Select", "Industry Type", options=INDUSTRY_TYPES, reqd=1),
		F("auditor_section", "Section Break", "Auditor"),
		F("auditor", "Link", "Auditor", options="User", reqd=1, default="__user"),
		F("column_break_oaaa", "Column Break"),
		F("auditor_name", "Data", "Auditor Name", fetch_from="auditor.full_name", read_only=1),
		F("questions_section", "Section Break", "Questions"),
		F("audit_rows", "Table", "Audit Questions", options="Supplier Audit Log Detail"),
		F("score_section", "Section Break", "Score"),
		F("total_score", "Int", "Maximum Score", read_only=1, default="0"),
		F("minimum_score", "Int", "Minimum Score for Industry", read_only=1, default="0"),
		F("column_break_fupj", "Column Break"),
		F("audit_score", "Int", "Audit Score", read_only=1, default="0", in_list_view=1),
		F("audit_score_percent", "Percent", "Audit Score (%)", read_only=1, default="0"),
		F("meets_minimum", "Check", "Meets Minimum Score", read_only=1, default="0", in_list_view=1),
	],
	naming_series="SUP-AUD-.YYYY.-.#####",
	title_field="supplier_name",
	is_submittable=1,
	permissions=[
		perm("System Manager", delete=1, submit=1, cancel=1, amend=1),
		perm("Quality Manager", delete=1, submit=1, cancel=1, amend=1),
		perm("Purchase Manager", submit=1, cancel=1, amend=1),
		perm("Purchase User"),
	],
	js=True,
)

# ---------------------------------------------------------------------------
# 6.3 Supplier Onboarding
# ---------------------------------------------------------------------------
onboarding_fields = [
	# --- Details tab ---
	F("supplier_name", "Data", "Supplier Name", reqd=1, in_list_view=1, bold=1),
	F("supplier_group", "Link", "Supplier Group", options="Supplier Group", reqd=1, in_list_view=1, in_standard_filter=1),
	F("supplier_type", "Select", "Supplier Type", options="Company\nIndividual\nPartnership", default="Company", reqd=1),
	F("country", "Link", "Country", options="Country", reqd=1),
	F("column_break0", "Column Break"),
	F("status", "Select", "Status", options="Draft\nPending Approval\nApproved\nRejected", default="Draft", read_only=1, in_list_view=1, in_standard_filter=1, no_copy=1, allow_on_submit=1),
	F("prospective_supplier", "Link", "Prospective Supplier", options="Prospective Supplier", read_only=1),
	F("supplier", "Link", "Supplier Created", options="Supplier", read_only=1, no_copy=1, allow_on_submit=1),
	F("portal_user", "Link", "Portal User", options="User", read_only=1, no_copy=1, allow_on_submit=1),
	F("commercial_section", "Section Break", "Commercial"),
	F("default_currency", "Link", "Billing Currency", options="Currency"),
	F("default_price_list", "Link", "Price List", options="Price List"),
	F("incoterm", "Link", "Incoterms", options="Incoterm"),
	F("column_break_comm", "Column Break"),
	F("payment_terms", "Link", "Payment Terms Template", options="Payment Terms Template"),
	F("website", "Data", "Website"),
	F("moq_per_line", "Check", "MOQ Applies per Line", default="0"),
	F("tax_section", "Section Break", "Tax and MSME"),
	F("gst_category", "Select", "GST Category", options=GST_CATEGORIES, default="Unregistered"),
	F("gstin", "Data", "GSTIN"),
	F("pan", "Data", "PAN", mandatory_depends_on='eval:doc.country=="India"'),
	F("tax_category", "Link", "Tax Category", options="Tax Category"),
	F("tax_withholding_category", "Link", "Tax Withholding Category", options="Tax Withholding Category"),
	F("column_break_tax", "Column Break"),
	F("msme", "Check", "MSME Registered", default="0"),
	F("msme_category", "Select", "MSME Category", options="\nMicro\nSmall\nMedium", depends_on="msme"),
	F("msme_registration_no", "Data", "Udyam Registration No", depends_on="msme"),
	F("msme_certificate", "Attach", "MSME Certificate", depends_on="msme"),
	F("msme_expiry", "Date", "MSME Certificate Expiry", depends_on="msme"),
	# --- Address & Contact tab ---
	F("address_contact_tab", "Tab Break", "Address & Contact"),
	F("primary_address_section", "Section Break", "Primary Address"),
	F("address_type", "Select", "Address Type", options="Billing\nShipping\nOffice\nPlant\nWarehouse\nOther", default="Billing"),
	F("address_line1", "Data", "Address Line 1"),
	F("address_line2", "Data", "Address Line 2"),
	F("column_break_addr", "Column Break"),
	F("city", "Data", "City/Town"),
	F("state", "Data", "State/Province"),
	F("pincode", "Data", "Postal Code"),
	F("primary_contact_section", "Section Break", "Primary Contact"),
	F("contact_person", "Data", "Contact Person"),
	F("designation", "Data", "Designation"),
	F("column_break_cont", "Column Break"),
	F("email", "Data", "Email", options="Email", reqd=1, description="Used for the Contact and the supplier portal login."),
	F("phone", "Data", "Phone", options="Phone"),
	F("mobile", "Data", "Mobile", options="Phone"),
	F("escalation_section", "Section Break", "Escalation Contact", collapsible=1),
	F("escalation_contact_person", "Data", "Name"),
	F("escalation_designation", "Data", "Designation"),
	F("column_break_esc", "Column Break"),
	F("escalation_email", "Data", "Email", options="Email"),
	F("escalation_phone", "Data", "Phone", options="Phone"),
	# --- Bank tab ---
	F("bank_tab", "Tab Break", "Bank"),
	F("bank_section", "Section Break", "Bank Details"),
	F("bank_name", "Data", "Bank Name", description="A Bank master is created if it does not exist."),
	F("account_holder_name", "Data", "Account Holder Name"),
	F("bank_account_no", "Data", "Account Number"),
	F("column_break_bank", "Column Break"),
	F("ifsc_code", "Data", "IFSC / Branch Code"),
	F("bank_branch", "Data", "Bank Branch"),
	F("iban", "Data", "IBAN"),
	F("swift_code", "Data", "SWIFT Code"),
	# --- Documents tab ---
	F("documents_tab", "Tab Break", "Documents"),
	F("statutory_docs_section", "Section Break", "Statutory Documents"),
	F("gst_certificate", "Attach", "GST Certificate"),
	F("pan_card", "Attach", "PAN Card"),
	F("column_break_docs", "Column Break"),
	F("company_registration", "Attach", "Company Registration"),
	F("qms_section", "Section Break", "QMS Certification Status"),
	F("iso_9001", "Attach", "ISO 9001"),
	F("iso_14001", "Attach", "ISO 14001"),
	F("iso_45001", "Attach", "ISO 45001"),
	F("column_break_qms", "Column Break"),
	F("iatf_16949", "Attach", "IATF 16949"),
	F("iso_ts_22163", "Attach", "ISO / TS 22163"),
	F("as_9100", "Attach", "AS 9100"),
	F("other_docs_section", "Section Break", "Other Documents"),
	F("attach_1", "Attach", "Other Certificate 1"),
	F("attach_2", "Attach", "Other Certificate 2"),
	F("attach_3", "Attach", "Other Certificate 3"),
	F("column_break_other", "Column Break"),
	F("customer_base", "Attach", "Existing Customer Base"),
	F("company_specialize", "Attach", "Principal Areas of Business"),
	F("business_continuity", "Attach", "Business Continuity / Contingency Plan"),
	F("logistics_processes", "Attach", "Logistics Processes"),
	F("notes_section", "Section Break", "Additional Information"),
	F("supplier_notes", "Small Text", "Notes"),
	# --- Questionnaire tabs (switch: settings.onboarding_questionnaire) ---
	F("risk_analysis_tab", "Tab Break", "Risk Analysis", depends_on="eval:doc.questionnaire_enabled"),
	F("questionnaire_enabled", "Check", "Questionnaire Enabled", read_only=1, hidden=1, default="0", no_copy=1),
	F("question_bank", "Link", "Question Bank", options="Supplier Onboarding Question Bank"),
	F("risk_legend", "HTML", "Risk Ranking Legend"),
	F("risk_analysis", "Table", "Risk Analysis", options="Supplier Risk Analysis"),
	F("evaluation_tab", "Tab Break", "Supplier Evaluation", depends_on="eval:doc.questionnaire_enabled"),
	F("evaluation", "Table", "Evaluation Questions", options="Supplier Evaluation"),
	F("evaluation_ranking_section", "Section Break", "Evaluation Ranking"),
	F("evaluation_ranking", "Table", "Evaluation Ranking", options="Supplier Evaluation Ranking"),
	F("evaluation_score", "Int", "Ranking Score", read_only=1),
	# --- Audit tab (required only for groups in audit_required_groups) ---
	F("audit_tab", "Tab Break", "Audit"),
	F("audit_required", "Check", "Audit Required", read_only=1, default="0", no_copy=1, description="Set from Buying Control Settings > Audit Required Groups."),
	F("supplier_audit_type", "Select", "Industry Type", options=INDUSTRY_TYPES, mandatory_depends_on="audit_required"),
	F("column_break_audit", "Column Break"),
	F("supplier_audit_log", "Link", "Supplier Audit Log", options="Supplier Audit Log", read_only=1, no_copy=1),
	F("audit_self_assessment_section", "Section Break", "Supplier Self Assessment", depends_on="audit_required"),
	F("audit_self_assessment", "Table", "Self Assessment", options="Supplier Audit Log Detail"),
	# --- Portal / token ---
	F("portal_tab", "Tab Break", "Portal"),
	F("onboarding_token", "Data", "Onboarding Token", read_only=1, hidden=1, no_copy=1, allow_on_submit=1),
	F("token_expired", "Check", "Link Expired", read_only=1, default="0", no_copy=1, allow_on_submit=1),
	F("portal_submitted_on", "Datetime", "Submitted by Supplier On", read_only=1, no_copy=1),
	F("column_break_portal", "Column Break"),
	F("onboarding_link", "Small Text", "Onboarding Link", read_only=1, no_copy=1, allow_on_submit=1),
]
make_doctype(
	M, "Supplier Onboarding",
	onboarding_fields,
	naming_series="SUP-ONB-.YYYY.-.#####",
	title_field="supplier_name",
	is_submittable=1,
	search_fields="supplier_name,supplier_group,status",
	permissions=[
		perm("System Manager", delete=1, submit=1, cancel=1, amend=1),
		perm("Purchase Manager", delete=1, submit=1, cancel=1, amend=1),
		perm("Purchase Master Manager", submit=1, cancel=1, amend=1),
		perm("Purchase User"),
		ro("Quality Manager"),
		ro("Finance Manager"),
	],
	js=True,
	list_js=True,
	extra={"show_title_field_in_link": 1},
)

# ---------------------------------------------------------------------------
# 6.6 Supplier Profile Change Request
# ---------------------------------------------------------------------------
make_doctype(
	M, "Supplier Profile Contact Request",
	[
		F("is_primary_contact", "Check", "Primary", default="0", in_list_view=1),
		F("first_name", "Data", "First Name", reqd=1, in_list_view=1),
		F("last_name", "Data", "Last Name", in_list_view=1),
		F("designation", "Data", "Designation"),
		F("column_break_c1", "Column Break"),
		F("email", "Data", "Email", options="Email", in_list_view=1),
		F("phone", "Data", "Phone", options="Phone"),
		F("mobile", "Data", "Mobile", options="Phone", in_list_view=1),
		F("existing_contact", "Link", "Existing Contact", options="Contact", read_only=1),
		F("remove", "Check", "Remove", default="0", in_list_view=1),
	],
	istable=1,
)
make_doctype(
	M, "Supplier Profile Address Request",
	[
		F("is_primary_address", "Check", "Primary", default="0", in_list_view=1),
		F("address_type", "Select", "Address Type", options="Billing\nShipping\nOffice\nWarehouse\nPlant\nOther", default="Billing", in_list_view=1),
		F("address_title", "Data", "Address Title"),
		F("column_break_a1", "Column Break"),
		F("address_line1", "Data", "Address Line 1", reqd=1, in_list_view=1),
		F("address_line2", "Data", "Address Line 2"),
		F("city", "Data", "City", reqd=1, in_list_view=1),
		F("state", "Data", "State"),
		F("country", "Link", "Country", options="Country"),
		F("pincode", "Data", "Pincode"),
		F("existing_address", "Link", "Existing Address", options="Address", read_only=1),
		F("remove", "Check", "Remove", default="0", in_list_view=1),
	],
	istable=1,
)
make_doctype(
	M, "Supplier Profile Bank Account Request",
	[
		F("action", "Select", "Action", options="Add\nRemove", default="Add", in_list_view=1),
		F("is_default", "Check", "Default", default="0"),
		F("account_name", "Data", "Account Holder Name", in_list_view=1),
		F("column_break_b1", "Column Break"),
		F("bank", "Link", "Bank", options="Bank", in_list_view=1),
		F("account_type", "Link", "Account Type", options="Bank Account Type"),
		F("bank_account_no", "Data", "Account Number", in_list_view=1),
		F("iban", "Data", "IBAN"),
		F("branch_code", "Data", "Branch Code / IFSC"),
		F("existing_bank_account", "Link", "Existing Bank Account", options="Bank Account", read_only=1),
	],
	istable=1,
)
make_doctype(
	M, "Supplier Profile Change Request",
	[
		F("supplier", "Link", "Supplier", options="Supplier", reqd=1, in_list_view=1, in_standard_filter=1),
		F("supplier_name", "Data", "Supplier Name", fetch_from="supplier.supplier_name", read_only=1, in_list_view=1),
		F("column_break_head", "Column Break"),
		F("requested_by", "Link", "Requested By", options="User", read_only=1),
		F("request_date", "Datetime", "Request Date", read_only=1),
		F("section_break_summary", "Section Break", "Summary of Changes (Current to Requested)"),
		F("changes_summary_html", "HTML", "Changes Summary"),
		F("section_break_contacts", "Section Break", "Contacts"),
		F("contacts", "Table", "Contacts", options="Supplier Profile Contact Request"),
		F("section_break_addresses", "Section Break", "Addresses"),
		F("addresses", "Table", "Addresses", options="Supplier Profile Address Request"),
		F("section_break_bank", "Section Break", "Bank Accounts"),
		F("bank_accounts", "Table", "Bank Accounts", options="Supplier Profile Bank Account Request"),
		F("section_break_tax", "Section Break", "GST / Tax"),
		F("gstin", "Data", "GSTIN / Tax ID"),
		F("column_break_tax", "Column Break"),
		F("gst_certificate", "Attach", "GST Certificate"),
	],
	naming_series="SPCR-.YYYY.-.#####",
	title_field="supplier_name",
	is_submittable=1,
	permissions=[
		perm("System Manager", delete=1, submit=1, cancel=1, amend=1),
		perm("Purchase Manager", delete=1, submit=1, cancel=1, amend=1),
		perm("Purchase User", submit=1, cancel=1),
	],
	js=True,
)

# ---------------------------------------------------------------------------
# Document vault (Supplier.ub_document_vault rows) + document type catalog
# ---------------------------------------------------------------------------
make_doctype(
	M, "Supplier Document Type",
	[
		F("document_key", "Data", "Document Key", reqd=1, unique=1),
		F("label", "Data", "Label", reqd=1, in_list_view=1),
		F("category", "Select", "Category", options="Insurance\nFinancial\nStatutory\nQuality\nLegal\nCustoms\nOther", reqd=1, in_list_view=1),
		F("column_break_cfg", "Column Break"),
		F("is_required", "Check", "Required", default="0", in_list_view=1),
		F("renewal_months", "Int", "Renewal Period (months)", default="0"),
		F("allow_custom_label", "Check", "Allow Uploader to Name It", default="0"),
		F("is_active", "Check", "Active", default="1"),
		F("sort_order", "Int", "Display Order", default="0"),
	],
	autoname="field:document_key",
	title_field="label",
	permissions=[perm("System Manager", delete=1), perm("Purchase Manager", delete=1), ro("Purchase User"), ro("Supplier")],
	extra={"show_title_field_in_link": 1},
)
make_doctype(
	M, "Supplier Document",
	[
		F("document_type", "Link", "Document Type", options="Supplier Document Type", reqd=1, in_list_view=1),
		F("custom_label", "Data", "Custom Label / Title", in_list_view=1),
		F("category", "Data", "Category", fetch_from="document_type.category", read_only=1),
		F("doc_key", "Data", "Key", fetch_from="document_type.document_key", read_only=1, hidden=1),
		F("column_break_d1", "Column Break"),
		F("status", "Select", "Status", options="Not Uploaded\nUploaded\nExpiring\nExpired", default="Not Uploaded", read_only=1, in_list_view=1),
		F("attachment", "Attach", "Attachment", in_list_view=1),
		F("uploaded_on", "Datetime", "Uploaded On", read_only=1),
		F("expires_on", "Date", "Expires On", in_list_view=1),
		F("notes", "Small Text", "Notes"),
	],
	istable=1,
)

# ---------------------------------------------------------------------------
# 6.7 Supplier Line Card (child fields fixed by BUILD_SPEC 6.2)
# ---------------------------------------------------------------------------
make_doctype(
	M, "Supplier Line Card Item",
	[
		F("manufacturer_part_no", "Data", "Manufacturer Part No", reqd=1, in_list_view=1),
		F("manufacturer", "Link", "Manufacturer", options="Manufacturer", in_list_view=1),
		F("lead_time_days", "Int", "Lead Time (Days)", in_list_view=1),
		F("min_order_qty", "Float", "MOQ", in_list_view=1),
		F("standard_packing_qty", "Float", "SPQ", in_list_view=1),
	],
	istable=1,
)
make_doctype(
	M, "Supplier Line Card",
	[
		F("supplier", "Link", "Supplier", options="Supplier", reqd=1, in_list_view=1, in_standard_filter=1),
		F("supplier_name", "Data", "Supplier Name", fetch_from="supplier.supplier_name", read_only=1),
		F("column_break_zjmc", "Column Break"),
		F("company", "Link", "Company", options="Company", reqd=1, in_list_view=1, in_standard_filter=1),
		F("disabled", "Check", "Disabled", default="0"),
		F("section_break_items", "Section Break", "Manufacturer Part Numbers"),
		F("items", "Table", "Line Card Items", options="Supplier Line Card Item"),
	],
	naming_series="SLC-.#####",
	title_field="supplier_name",
	search_fields="supplier,company",
	permissions=[
		perm("System Manager", delete=1),
		perm("Purchase Manager", delete=1),
		perm("Purchase User"),
		perm("Sourcing User"),
		perm("Sourcing Manager", delete=1),
	],
	js=True,
)

print("UB Supplier doctypes generated")
