# universal_buying – Build Spec for the porting workers

Read this whole file before writing code. "BRD" section numbers below refer to the Universal Buying requirements (screens 6.x, settings 7, workflows 8); the user-facing behaviour is described in `docs/USER_GUIDE.md`.

## 1. Environment

| Item | Value |
|---|---|
| Bench | `/home/finstein-emp/frappe-v16` (Frappe 16.30, ERPNext 16.31, Python 3.14) |
| App | `/home/finstein-emp/frappe-v16/apps/universal_buying` (package `universal_buying`) |
| Site | `buying.local`, company **Universal Buying Demo** (abbr `UBD`), currency INR, country India |
| ERPNext v16 source (check signatures here) | `/home/finstein-emp/frappe-v16/apps/erpnext`, `/home/finstein-emp/frappe-v16/apps/frappe` |

**india_compliance is NOT installed.** Never depend on it. GST fields (`gst_hsn_code`, `GST HSN Code` doctype, `gstin` on Address…) may be missing. Guard with `frappe.get_meta(dt).has_field(...)` / `frappe.db.exists("DocType", ...)`.

## 2. What you may and may not do

- DO: read both source apps freely; write ONLY inside your own module folder(s) (section 4) plus `universal_buying/www/` and `universal_buying/templates/` files whose names you own (section 4).
- DO: static checks – `python3 -m py_compile <file>`, `node --check <file.js>`, `python3 -m json.tool <file.json> >/dev/null`.
- DO NOT: run `bench migrate`, `bench install-app`, `bench build`, `bench restart`, `bench start`, or anything that writes to the database. The lead does migration and testing after all modules land.
- DO NOT: edit `hooks.py`, `setup/install.py`, `universal_buying/universal_buying/*` (core), or another worker's module. If you need something from core or another module, use the contracts in section 6; if a contract is missing, say so in your final report.
- DO NOT: `git commit`. The lead commits.

## 3. Conventions

- Tabs for Python/JS indentation (Frappe style), double quotes. JSON 1-space indent is fine (generator output).
- Create doctypes with the generator: `/home/finstein-emp/frappe-v16/apps/universal_buying/tools/make_doctype.py` (read its docstring). Write a small `tools/gen_<module>.py` script that calls it, run it with `/home/finstein-emp/frappe-v16/env/bin/python tools/gen_<module>.py`. The generator never overwrites existing `.py`/`.js`, so regenerate JSON freely.
- Doctype names must not clash with ERPNext/Frappe doctypes. Check `find /home/finstein-emp/frappe-v16/apps/erpnext /home/finstein-emp/frappe-v16/apps/frappe -path '*doctype/<scrubbed_name>'` before creating.
- **Every custom field on a standard doctype starts with `ub_`.** Declare them in your module's `install.py` → `CUSTOM_FIELDS = {"Purchase Order": [ {fieldname, label, fieldtype, insert_after, ...}, ... ]}`. Also `ROLES = [...]`, `PROPERTY_SETTERS = [...]` and an idempotent `def setup():` (workflows, master records). The core installer (`setup/install.py`) merges all modules. Read it.
- Hooks: write `<module>/hooks_contrib.py` as PURE DATA (no imports). Allowed keys are listed at the top of `universal_buying/hooks.py`. Keys like OVERRIDE_DOCTYPE_CLASS / DOCTYPE_JS are single-owner – only the owner in section 5 may set them for that doctype. Everybody may add DOC_EVENTS for any doctype.
- Every rule number, role list, threshold, day count: read from settings, never hard-code:
  `from universal_buying.universal_buying.settings import get_setting, get_list, get_lines, apply_mode, has_any_role, abc_threshold`. Field names are in `universal_buying/universal_buying/doctype/buying_control_settings/buying_control_settings.json`. If you need a new setting, list it in your final report (the lead adds it) and read it with a safe default: `get_setting("x", default=...)`.
- Shared helpers: `universal_buying.universal_buying.utils` → `set_po_origin`, `get_po_origin`, `assert_supplier_enabled`, `supplier_is_enabled`, `autoname_with_company`, `notify_users`, `users_with_role`. PO Type helpers: `universal_buying.universal_buying.doctype.po_type.po_type.get_po_type`.
- Remove everything tied to: Recommendation Note, Capex, Revex, Capital Project, BOQ, WBS / Task budgets, Project Request, Sourcing Batch, subsidy, SEZ, equipment variance/CB Case, burden rollups, `coexistence.is_capex_doc`, legacy freeze (`legacy_frozen`, legacy cutoff), Oracle/legacy IDs.
- Fix the source-app defects the BRD lists for your screens ("Fix from the source app" notes).
- Background work: `frappe.enqueue(..., queue="long")`. Keep request handlers fast.
- Write focused unit tests in `<module>/tests/test_*.py` (FrappeTestCase / `frappe.tests.IntegrationTestCase` in v16) for the main V-/A- rules. The lead runs them.

## 4. Module ownership

| Worker | Module folder (package) | Module name | BRD sections | Also owns |
|---|---|---|---|---|
| A Supplier | `universal_buying/ub_supplier` | UB Supplier | 6.2–6.7, 8.1 | `www/supplier_onboarding.*`, web form `supplier_onboarding_form` (in ub_supplier/web_form) |
| B Planning | `universal_buying/ub_planning` | UB Planning | 6.8–6.12, reports "Planning"/"Exceptions" in §12, consumables job | – |
| C Sourcing | `universal_buying/ub_sourcing` | UB Sourcing | 6.13–6.15, 8.2 | `www/rfq_portal.*`, `www/rfq-portal.*`, `www/quotation_comparison.*`, `templates/includes/rfq_*` |
| D Ordering | `universal_buying/ub_ordering` | UB Ordering | 6.17–6.21, 8.3, 8.4, Ordering reports | `www/supplier_portal/**`, `www/supplier_portal_api.py`, `templates/includes/supplier_portal_*` |
| E Inward | `universal_buying/ub_inward` | UB Inward | 6.22–6.26, Receiving reports | – |
| F Finance | `universal_buying/ub_finance` | UB Finance | 6.27–6.28, Finance reports, TDS | – |

Core (lead, already done): Buying Control Settings, PO Type, UB * link/child tables, settings.py, utils.py, installer, hooks merge.

## 5. Single-owner hooks and doctype JS

| Doctype | OVERRIDE_DOCTYPE_CLASS owner | DOCTYPE_JS owner |
|---|---|---|
| Supplier | – (use DOC_EVENTS) | A |
| Item, Item Price, Item Manufacturer | – | B |
| Material Request | – | B |
| Request for Quotation | C | C |
| Supplier Quotation | C | C |
| Purchase Order | D | D |
| Purchase Receipt | E | E |
| Quality Inspection | – | E |
| Landed Cost Voucher | – | E |
| Purchase Invoice | F | F |

If you need client behaviour on a doctype you don't own, put it in DOC_EVENTS (server side) or describe it in your report.

## 6. Cross-module contracts (implement exactly these names)

### 6.1 Custom fields other modules rely on

| Doctype | Field | Type | Owner | Meaning |
|---|---|---|---|---|
| Supplier | `workflow_state` (standard via Workflow "UB Supplier Approval") | – | A | "Enabled" = approved |
| Supplier | `ub_green_card` | Check | A | trusted supplier, skips IQC |
| Supplier | `ub_moq_per_line` | Check | A | round to MOQ instead of SPQ |
| Supplier | `ub_onboarding` | Link Supplier Onboarding | A | |
| Supplier | `ub_msme`, `ub_msme_category`, `ub_msme_certificate`, `ub_msme_expiry` | | A | |
| Supplier | `ub_tax_withholding_details` (Table "UB Supplier TDS Category"), `ub_tds_opening_balances` (Table "UB Supplier TDS Balance") | | F | TDS opening balance |
| Item | `ub_built_type` (Select Standard/Custom, default Standard) | | B | |
| Item | `ub_standard_packing_qty` (Float) | | B | SPQ (MOQ = standard `min_order_qty`) |
| Item | `ub_revision_no` (Data), `ub_test_certificate_required`, `ub_coc_required`, `ub_fai_required`, `ub_rohs`, `ub_reach` (Check), `ub_ppap_level` (Select \nL1\nL2\nL3\nL4\nL5) | | B | compliance flags copied to PO lines |
| Item Manufacturer | `ub_disabled` (Check) | | B | disabled MPN blocked on PO/QI |
| Item Price | `ub_manufacturer` (Link Manufacturer), `ub_item_manufacturer` (Link Item Manufacturer), `ub_company` (Link Company) | | B | |
| Purchase Order | `ub_po_type` (Link PO Type), `ub_origin_doctype` (Link DocType), `ub_origin_name` (Dynamic Link on ub_origin_doctype), `ub_is_import` (Check) | | D | set_po_origin() writes the origin fields |
| Purchase Order | `ub_approval_status` (Select Draft/Pending/Approved/Rejected), `ub_portal_status` (Select \nPending Acceptance\nAccepted\nPartially Dispatched\nDispatched), `ub_confirmed_delivery_date` (Date) | | D | |
| Purchase Order Item | `ub_skip_moq` (Check, read only), `ub_required_by` (Date), `ub_supplier_delivery_date` (Date) | | D | only Auto PO Exception sets ub_skip_moq |
| Purchase Order Item | `ub_test_certificate_required`, `ub_coc_required`, `ub_fai_required`, `ub_rohs`, `ub_reach`, `ub_ppap_level`, `ub_revision_no` fetched from item | | D | |
| Request for Quotation | `ub_po_type`, `ub_bid_deadline` (Datetime), `ub_bid_status` | | C | |
| Request for Quotation Supplier | `ub_prospective_supplier` (Link Prospective Supplier), `ub_rfq_token` (Data) | | C | supplier may be blank when prospective |
| Supplier Quotation | `ub_prospective_supplier` (Link), `ub_revised` (Check), `ub_lead_time_days` (Int) | | C | |
| Purchase Receipt | `ub_gate_entry` (Link Gate Entry), `ub_supplier_invoice_no` (Data), `ub_supplier_invoice_date` (Date), `ub_boe_no` (Data), `ub_boe_date` (Date), `ub_is_bonded` (Check), `ub_green_card` (Check), `ub_iqc_complete` (Check), `ub_inward_discrepancy` (Link) | | E | F reads supplier invoice no + boe |
| Purchase Receipt Item | `ub_manufacturer_batch_no` (Data), `ub_manufacturing_date` (Date) | | E | |
| Purchase Invoice | `ub_override_reason` (Small Text), `ub_boe_no` (Data), `ub_boe_date` (Date), `ub_is_import` (Check) | | F | |

Standard fields to use instead of new ones: Item `min_order_qty`, `lead_time_days`, `shelf_life_in_days`, `inspection_required_before_purchase`, `quality_inspection_template`, `default_item_manufacturer`, `default_manufacturer_part_no`; PO Item / PR Item `manufacturer`, `manufacturer_part_no`, `material_request`, `material_request_item`, `supplier_quotation`, `supplier_quotation_item`. Verify each exists in ERPNext v16 before use.

### 6.2 Doctypes referenced across modules (names are fixed)

`Prospective Supplier`, `Supplier Onboarding`, `Supplier Line Card` (child `Supplier Line Card Item` with `manufacturer_part_no` Data, `manufacturer` Link Manufacturer, `lead_time_days`, `min_order_qty`, `standard_packing_qty`), `Supplier Profile Change Request` — A.
`Item Price Request`, `Requirement Log`, `Item Classification`, `Auto PO Run`, `Auto PO Exception` — B.
`PO Amendment`, `PO Acknowledgement`, `PO Material Status` — D.
`Gate Entry`, `Item Non Conformance`, `Inward Discrepancy` — E.
`Payment Indent` — F.

Note: this app does not use a separate `Manufacturer Part Number` master; it uses the standard **Item Manufacturer** (item + manufacturer + manufacturer_part_no) plus plain MPN text on the line card. B and A must agree on this (MPN text match on `Item Manufacturer.manufacturer_part_no`).

### 6.3 Functions other modules call

| Function | Owner | Called by | Purpose |
|---|---|---|---|
| `universal_buying.ub_supplier.api.create_onboarding_from_prospective(prospective_supplier, send_email=1) -> str` | A | C (award) | Creates Supplier Onboarding + token, emails link, sets prospective status "Onboarding Sent" |
| `universal_buying.ub_supplier.api.get_supplier_for_prospective(prospective_supplier) -> str or None` | A | C, D | Linked Supplier once onboarded |
| `universal_buying.ub_supplier.api.submit_profile_change_request(supplier, changes: dict)` (whitelisted) | A | D portal | portal profile edits |
| `universal_buying.ub_supplier.api.get_document_vault(supplier)` / `upload_vault_document(...)` / `delete_vault_document(...)` (whitelisted) | A | D portal | document vault |
| `universal_buying.ub_sourcing.api.get_or_create_rfq_token(rfq, supplier) -> str` | C | D portal | logged-in supplier quoting through `/rfq-portal?token=` |
| `universal_buying.ub_ordering.approval.get_approval_state(po_name) -> dict` | D | any | |
| `universal_buying.ub_planning.api.get_current_item_price(item_code, supplier=None, company=None, date=None, uom=None) -> dict or None` | B | C (comparison), D (price control) | winning buying Item Price row: {name, price_list_rate, currency, supplier, ub_item_manufacturer, manufacturer, manufacturer_part_no, valid_from, valid_upto} |
| `universal_buying.ub_planning.api.get_shortage_map(item_codes, company, months=0) -> dict` | B | D, E, F | current (+n months) shortage per item from Requirement Log |
| `universal_buying.ub_inward.api.get_pending_receipt_rows(company, supplier, supplier_invoice_no) -> list` | E | F | receipt rows not yet billed for a supplier invoice number |

## 7. Final report (what to return to the lead)

1. Files created (tree).
2. Every DOC_EVENTS / override / scheduler entry you put in hooks_contrib.py.
3. Custom fields added (per doctype).
4. New settings you needed (name, type, default).
5. What you deliberately left out or could not port, and why.
6. Any contract in section 6 you could not honour.
7. Source-app bugs you fixed.
