# Universal Buying – Demo Script

A screen-by-screen walkthrough of one complete purchase, using the **LRN** demo data on buying.local. For each screen: **what to show**, and **what the system does behind it** (tables, rules, settings, jobs).

Open http://127.0.0.1:8011/desk → **Universal Buying**. Ask the administrator for the demo and supplier portal passwords.

**The story:** a customer orders 200 controller boards (LRN-FG-01). Each board needs one PCB, one IC and one resistor. The system works out what is short, orders the PCB automatically, flags the IC (no supplier) and the resistor (too small for MOQ). The buyer gets IC quotes with an RFQ, the CEO awards it, and the goods are received, inspected, invoiced and paid.

## Demo documents on buying.local (open them with Ctrl+K)

| Step | Screen | Document | Status / values |
|---|---|---|---|
| 1 | Supplier | LRN Metals Pvt Ltd, LRN Electro Components | Enabled; portal users portal@lrnmetals.example, sales@lrnelectro.example |
| 2 | Item / BOM | LRN-FG-01, LRN-PCB, LRN-IC, LRN-RES; BOM-LRN-FG-01-001 | MOQ / SPQ / lead time set |
| 3 | Item Price Request | IPR-2026-00003 (PCB 120, RES 0.50), IPR-2026-00004 (IC 7.50) | Submitted, Item Prices created |
| 4 | Sales Order | SAL-ORD-2026-00002 | 200 × LRN-FG-01, delivery 25-Oct-2026 |
| 5 | Auto PO Run | APO-2026-00002, APO-2026-00003 | Completed |
| 6 | Auto PO Exception | APE-2026-00002 | LRN-RES MOQ Exception, LRN-IC No Supplier, Follow-ups filled |
| 7 | Purchase Order (auto) | PUR-UBD-2026-00004 | LRN Metals, 200 × LRN-PCB @ 120, ₹28,320, Approved, Portal: Dispatched |
| 8 | Supplier Portal | PO-ACK-2026-00003, PO-MS-2026-00003/4/5, SHP-2026-00002 | Acknowledged → In Production → Ready → Dispatched |
| 9 | RFQ | PUR-RFQ-2026-00002 | 4 approvals, Awarded |
| 10 | Supplier Quotation | PUR-SQTN-2026-00005 (LRN Metals 7.50) / PUR-SQTN-2026-00004 (LRN Electro 8.00) | Approved / Rejected |
| 11 | Quotation Comparison | /quotation-comparison?rfq=PUR-RFQ-2026-00002 | Discussion with both suppliers + internal note |
| 12 | Purchase Order (from quote) | PUR-UBD-2026-00005 | 200 × LRN-IC @ 7.50, ₹1,770, Approved |
| 13 | PO Amendment | POA-2026-00002 | Delivery 21-Oct → 28-Oct, approved by demo.pm |
| 14 | Gate Entry | GE-UBD-2026-00003, GE-UBD-2026-00004 | INV-LRN-001 / INV-LRN-002 |
| 15 | Purchase Receipt | MAT-PRE-2026-00003 (150 accepted), MAT-PRE-2026-00004 (50 rejected) | Completed / Return Issued |
| 16 | Quality Inspection | MAT-QA-2026-00003 Accepted, MAT-QA-2026-00004 Rejected | IQC gate blocked submit before inspection |
| 17 | Item Non Conformance | INC-2026-00002 | Return to Supplier → Purchase Return MAT-PRE-2026-00005 |
| 18 | Inward Discrepancy | ID-2026-00001 | Invoice 55 vs received 50 (Short Supply) |
| 19 | Purchase Invoice | ACC-PINV-2026-00002 | INV-LRN-001, 150 × 120 + IGST = ₹21,240 |
| 20 | Payment Indent → Payment Request | PAY-IND-2026-00002 → ACC-PRQ-2026-00002 | ₹1,650 advance for PUR-UBD-2026-00005 |

Demo users: demo.depthead, demo.scm, demo.ops, demo.ceo (RFQ tiers and award), demo.purchase (PO approval), demo.pm (PO Amendment), demo.quality (inspection).

---

## 1. Buying Control Settings – the rulebook

**Show:** the tabs Planning, Supplier, RFQ, Purchase Order, Inward, Finance, Company Overrides. Point at the ABC thresholds, the MOQ tolerance, the RFQ approval tiers and the PO approval bands.

**Behind it:** a single settings record. Every module reads it through one helper (`get_setting`), with company overrides applied first, so no rule is hard-coded. Saving it rebuilds the RFQ approval workflow from the tier table.

## 2. Supplier – onboarding and approval

**Show:** Prospective Supplier → Supplier Onboarding (risk and evaluation tabs) → the created Supplier with Approval Status **Enabled**. Open the Supplier's **Buying** tab (Incoterms, MSME, green card, bank) and **Portal Users** tab.

**Behind it:**
- PAN and GSTIN are checked: format, GSTIN matches PAN, no duplicates across suppliers and prospective suppliers.
- Onboarding submit creates, in one transaction, the **Supplier + Address + Contact + Bank Account + portal User** (role *Supplier*). It then marks the prospective supplier Onboarded and moves any RFQ or quotation rows to the new supplier.
- The risk score (RPN) is Severity × Occurrence × Prevention. At or above the threshold (27), a mitigation plan is mandatory.
- The **UB Supplier Approval** workflow routes by supplier group: Raw Material goes Purchase → Quality → Finance; Services goes to Finance only; others take one step. Only **Enabled** suppliers can receive RFQs and POs.

## 3. Item, Item Manufacturer, BOM

**Show:** LRN-PCB with Minimum Order Qty 100, SPQ 50, Lead Time 14, Inspection Required + template; its **Item Manufacturer** (part number LRN-MPN-PCB-01); the BOM of LRN-FG-01.

**Behind it:** MOQ, SPQ and lead time drive ordering quantities. The approved part numbers are checked on POs and at inspection, and a disabled part number is blocked. The BOM is what the requirement engine explodes.

## 4. Item Price Request – the approved source

**Show:** the submitted request for LRN-PCB and LRN-RES (supplier LRN Metals), then the resulting **Item Price** records. Also show the request for LRN-IC raised after the award.

**Behind it:**
- Submit expires the old price and creates the new **Item Price**, with supplier, validity, manufacturer and part number.
- It also writes MOQ and SPQ onto the Item, sets the **Default Supplier** in Item Defaults, and marks the default part number.
- An item with default supplier + valid price + MOQ + SPQ is an *approved source*, and Auto PO can order it without a human.

## 5. Sales Order – the demand

**Show:** SAL-ORD-2026-00002, 200 × LRN-FG-01, delivery 25-Oct.

**Behind it:** only submitted, open Sales Orders count. Excluded order types (Maintenance) and closed or on-hold orders are skipped.

## 6. Requirement Rebuild → Requirement Log – what is short

**Show:** Requirement Rebuild list (**Rebuild Now**), then the report **Manufacturing Shortage Summary**, with PCB, IC and resistor shortages by month.

**Behind it:** a nightly job (03:00), or run on demand. For every pending Sales Order line, in delivery-date order:
1. reserve stock (excluded warehouses like Rejected Goods are ignored);
2. reserve open Purchase Order quantity;
3. explode the BOM and repeat for each component, down to raw material;
4. write what's still uncovered as **Shortage** rows in the Requirement Log.

The same log feeds Auto PO, the exceptions, the Payment Indent shortage columns and the shortage reports.

## 7. Auto PO Run – automatic ordering

**Show:** the run (Company, To Date), status **Completed**, buttons **View → Purchase Orders / Auto PO Exception**.

**Behind it** (background job):
1. Take Shortage rows up to the To Date, pull them earlier by the planning buffer, and group by month.
2. Net off open POs not yet reserved, including drafts, so a second run doesn't order twice.
3. Supplier = Item Default supplier (or the Supplier Line Card). Price and part number = the valid Item Price.
4. **ABC test:** the shortage must reach 90% / 80% / 70% of MOQ (class A / B / C); otherwise the row becomes an exception.
5. Round up to SPQ and top up to MOQ.
6. One **draft PO per supplier**, origin "Auto PO Run". The tax template is chosen by address (same state = In State, other state = Out State); import is detected from the supplier country.
7. Everything else goes to one **Auto PO Exception**. A supplier whose PO can't be built is shown as *Completed with Errors* with the reason.

## 8. Auto PO Exception – the human decisions

**Show:** APE-2026-00002 with LRN-RES (**MOQ Exception**: 200 vs MOQ 10,000) and LRN-IC (**No Supplier**), and the **Follow-up** column.

**Behind it:**
- Create → Item Price Request works for *No Price* rows.
- Create → PO for MOQ Items is allowed only within the MOQ tolerance (5%).
- Everything else is handled manually (RFQ, manual PO or wait). There is no Recommendation Note.
- A row with a Follow-up is not repeated on the next run, and an item already on an open exception is not duplicated.

## 9. Purchase Order – approval by value

**Show:** PUR-UBD-2026-00004 (LRN Metals, 200 × LRN-PCB @ 120, **Out State** tax), the **Buying Control** tab (Origin, Approval Status, Portal Status, approval history), and **Send for Approval → Approve**.

**Behind it:**
- **Price control Strict:** the rate must equal the approved Item Price, or the linked quotation. The buyer can't change it.
- MOQ is checked unless the line came from an MOQ exception. The UOM conversion must exist. No negative taxes.
- The **approval engine** matches the PO's base grand total (and origin and company) to a band in the rule table and builds the chain of roles. Each step needs its own role; System Manager doesn't bypass. The final approval submits the PO automatically.
- On submit, Portal Status becomes **Pending Acceptance** and the supplier's portal users are notified.

## 10. Supplier Portal – supplier side after the PO

**Show** (Incognito, portal user of LRN Metals): /supplier_portal → Purchase Orders → the PO:
- **Acknowledge** with a confirmed delivery date;
- **Material Status** updates;
- **Invoice upload**;
- **Shipment**, then **Dispatched**.

**Behind it:**
- The supplier only sees its own records (row-level permission rules).
- Acknowledgement and material status are **append-only logs**: the latest one wins, and a status can't go backwards.
- **Dispatched** needs an uploaded invoice and a submitted shipment. Over-shipping is blocked.

## 11. RFQ – getting prices for the IC

**Show:** PUR-RFQ-2026-00002: PO Type, **Bid Deadline**, Bid Status, two suppliers, item LRN-IC × 200. The two quotations: LRN Electro 8.00 (entered by the supplier on the portal) and LRN Metals 7.50 (entered by the buyer).

**Behind it:**
- Submit opens bidding. Registered suppliers are told to use the portal; prospective suppliers get a one-time **token link**.
- A job every 15 minutes sends a reminder 24 hours before the deadline and closes bidding after it.
- A supplier can re-quote; the older quote is marked *Revised*, and only one quote per supplier is live.
- The approval chain is the **UB RFQ Approval** workflow, built from the tier table in settings: Dept Head → SCM Head → Operations Head → CEO. The RFQ creator can't approve their own RFQ, and Send Back needs a comment.

## 12. Quotation Comparison – discussion and award

**Show** (as demo.ceo): the Discussion row, with the buyer ↔ supplier messages and the yellow internal note; the side-by-side comparison of rates, landed total (lowest in green), lead time, current price difference and supplier status; then **Award**.

**Behind it:**
- Each thread belongs to the RFQ's supplier row, so it survives revisions and onboarding.
- Internal notes are never sent to suppliers. Suppliers reply from their RFQ portal page.
- Only the **award role** (CEO), at the final approval state, can award. Award approves and submits the winning quote, rejects the others and sets the RFQ to **Awarded**. If the winner were a prospective supplier, its onboarding would start automatically.

## 13. PO from the quotation, and PO Amendment

**Show:** the PO created from PUR-SQTN-2026-00005 (origin *Supplier Quotation*), approved and submitted; then a **PO Amendment** moving the date by one week, approved by demo.pm.

**Behind it:**
- The PO keeps the quotation's rate; price control accepts a rate that comes from the linked quotation.
- The amendment caps rate increases (5%) and never goes below the received quantity. On approval it updates the PO lines through ERPNext's standard method, so **taxes and totals are recalculated**.

## 14. Gate Entry → Purchase Receipt – receiving

**Show:** the Gate Entry (vehicle, invoice, boxes), then **Create → Purchase Receipt**, **Get Items From → Purchase Order (Pending Lines)**, the manufacturer batch / date, and **Create → Batches**.

**Behind it:**
- A Gate Entry is required for every normal receipt.
- Rows can only come from a PO. The picker nets off quantity on other draft receipts and warns about double receipt.
- Over-receipt is checked when you save.
- Batch creation groups rows by item + manufacturing date + manufacturer batch, requires the part number for standard items, and refuses material with less than 75% of its shelf life left.

## 15. Quality Inspection – the IQC gate

**Show:** submitting the receipt **before** inspection, which is blocked. Then the inspection (sample size from the template band, received part number), **Accepted**, and the receipt submitted.

**Behind it:**
- Items marked *Inspection Required* can't be received into stock without a submitted inspection (setting *IQC gate = Block*).
- The received part number must be an approved Item Manufacturer.
- Green-card suppliers can skip inspection.

## 16. Rejected goods – Item Non Conformance

**Show:** the second receipt (50 pcs) with a **Rejected** inspection. The quantity moved to *Rejected Goods*; the auto-created **Item Non Conformance**, disposition *Return to Supplier*; the **Purchase Return**.

**Behind it:** rejection rewrites the draft receipt row (rejected qty goes to the rejected warehouse) and creates the INC with supplier, invoice, batch and receipt rate. Each disposition creates a standard ERPNext document, valued at the receipt rate, and links it back to the INC.

## 17. Purchase Invoice – 3-way match

**Show:** Purchase Invoice → **Get Items From → Receipts by Supplier Invoice No** (INV-LRN-001) → submitted.

**Behind it:**
- The PO Type decides the match: 3-Way needs a PO and a receipt, 2-Way needs only a PO.
- An invoice total above the PO total plus tolerance needs an override reason.
- The creditor account's currency must match the invoice. TDS can use the supplier's opening balance.

## 18. Payment Indent → Payment Request

**Show:** the indent for the IC PO (PO lines, MOQ, SPQ and shortage columns, requested amount), submitted; then its **Payment Request**.

**Behind it:** the requested amount is capped at 110% of value. Above ₹5 lakh the submitter needs an approver role. Submit creates the Payment Request(s), split across the POs.

## 19. Reports – the control room

**Show:** Manufacturing / PO / Project Shortage Summary, Auto PO Exception, Excess PO, RFQ Status, Pending Supplier Quotations, Purchase Order Open Qty, Delayed PO, Unacknowledged PO, Purchase Receipt Pending, IQC Pending, IQC Rejection, Inward Discrepancy Register, Purchase Receipt to be Billed, Invoice Variance.

**Behind it:** all are live queries on the same documents; the shortage reports read the Requirement Log.

---

## Scheduled jobs running in the background

| When | Job |
|---|---|
| 03:00 daily | Requirement Engine rebuild |
| Weekly | ABC item classification |
| Daily | Consumables auto PO (if enabled), draft Auto PO purge (if set), supplier document expiry |
| Every 15 min | RFQ reminders and bid closing |
