## Universal Buying

Sales Order driven buying for manufacturing companies on ERPNext v16. It covers:

- **Planning and receiving:** nightly shortage calculation, Auto PO Run, Auto PO Exception, Gate Entry, receipt, inspection.
- **Supplier handling:** supplier registration and approval, RFQ portal, quotation comparison with discussion and award, supplier portal after the PO.

Recommendation Note, Capex and Revex are not part of this app. Items that Auto PO cannot order are handled by the user by hand (RFQ, Item Price Request or a manual PO).

Build notes for developers are in `BUILD_SPEC.md`. The user guide is `docs/USER_GUIDE.md`.

### Install

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch version-16
bench --site <site> install-app universal_buying      # needs erpnext
```

The installer creates roles, custom fields (all prefixed `ub_`), four workflows, default PO Types (2-Way, 3-Way), the onboarding question bank, the audit checklist and default settings. It runs again on every `bench migrate` and is safe to repeat.

### Where things are

Open **Universal Buying** from the desk.

| Stage | Screens |
|---|---|
| Setup | Buying Control Settings, PO Type |
| Supplier | Prospective Supplier, Supplier Onboarding, Supplier (approval workflow), Supplier Audit Log, Supplier Profile Change Request, Supplier Line Card |
| Item and price | Item (buying fields), Item Manufacturer, Item Price Request, Item Classification |
| Planning | Sales Order, Requirement Log (nightly), Auto PO Run, Auto PO Exception, Material Request (consumables) |
| Sourcing | Request for Quotation (approval tiers, bid deadline), Supplier Quotation, `/rfq-portal?token=`, `/quotation-comparison?rfq=` |
| Ordering | Purchase Order (PO Type, price control, value-band approval), PO Amendment, PO Acknowledgement, PO Material Status, PO Shipment, Supplier Channel |
| Supplier portal | `/supplier_portal` for users with the Supplier role, `/supplier-onboarding?token=`, `/supplier-onboarding-form` |
| Inward | Gate Entry, Purchase Receipt, Quality Inspection, Item Non Conformance, Inward Discrepancy, Landed Cost Voucher |
| Finance | Purchase Invoice (2-Way / 3-Way, tolerance, TDS opening balance), Payment Indent (creates Payment Requests) |

### Configuration

Every rule lives in **Buying Control Settings**, for example the planning buffer, the ABC thresholds, the MOQ tolerance, price control mode, the RFQ approval tiers, the PO approval bands, the gate entry and IQC gates, and the shelf life limit. Company Overrides change a value for one company. Saving the settings rebuilds the RFQ and quotation workflows.

### Scheduled jobs

| When | Job |
|---|---|
| 03:00 daily | Requirement Engine rebuild (shortage log) |
| Weekly | ABC Item Classification |
| Daily | Consumables auto PO, draft Auto PO purge, supplier document expiry |
| Every 15 min | RFQ bid reminders and closing |

### Tests

```bash
cd sites
../env/bin/python ../apps/universal_buying/tools/run_tests_rollback.py <site>              # all modules, nothing is saved
../env/bin/python ../apps/universal_buying/tools/run_tests_rollback.py <site> ub_planning  # one module
```

### License

mit
