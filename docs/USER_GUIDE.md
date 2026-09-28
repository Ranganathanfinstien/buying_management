# Universal Buying – Learn-by-Doing Guide

You will enter your own small dataset and walk it from **Sales Order to Payment**, screen by screen. Every step says **where to click**, **what to fill**, and **what you should see**. Use the example values or your own.

- Open: **http://127.0.0.1:8011/desk** → click **Universal Buying**. The left sidebar has every screen used below.
- To open any screen by name, press **Ctrl+K** and type it (e.g. "Auto PO Run").
- Mandatory fields have a red star. **Save** = Ctrl+S. **Submit** appears after saving.

---

## Part 0 – Before you start (10 minutes, once)

### 0.1 Who does which step

Some steps must be done by a **different user** from the one who created the document (you cannot approve your own RFQ). The site already has demo users, all with password **Demo@12345**:

| User (…@buying.local) | Use for |
|---|---|
| Administrator (you) | Setup, masters, most data entry |
| demo.depthead, demo.scm, demo.ops, demo.ceo | RFQ approval tiers; demo.ceo also awards quotations |
| demo.purchase | PO approval (Purchase Executive, orders up to ₹5 lakh) |
| demo.pm | PO Amendment approval (Purchase Manager) |
| demo.suppliera | Supplier portal user of *DEMO Supplier A* |

Open an **Incognito window** (Ctrl+Shift+N) for the second user, so both stay logged in.

> Tip: for PO approval you can instead give yourself the role: **User** → Administrator → Roles → tick **Purchase Executive** → Save.

### 0.2 Check the company setup

| Screen | What to check |
|---|---|
| **Company** → Universal Buying Demo | Has an **Address** (Company form → Address & Contact). POs need supplier, billing and shipping addresses. |
| **Purchase Taxes and Charges Template** | At least one template for the company (e.g. *DEMO GST In State*). |
| **Warehouse** | *Stores - UBD* and *Rejected Goods - UBD* exist. |
| **Buying Control Settings** | Read through the tabs once. Leave defaults. Every rule used below lives here. |

---

## Part A – Supplier and Item setup

### A1. Create a supplier (two ways)

**Way 1 – Onboarding (the full process)**

1. **Prospective Supplier** → New.
   - Supplier Name: `LRN Components Pvt Ltd`
   - Email: `lrn.components@example.com`
   - PAN: `AABCL1234M`, GSTIN: `33AABCL1234M1Z5` (characters 3–12 of GSTIN must equal the PAN)
   - Save.
2. Click **Create Onboarding**. A *Supplier Onboarding* opens pre-filled.
3. On the onboarding fill:
   - Supplier Group: `Raw Material`, Supplier Type: `Company`, Country: `India`
   - Address Line 1, City (mandatory on submit)
   - Bank Name, Bank Account No (mandatory on submit)
   - Risk / Evaluation tabs: fill every row (question text is already filled). If a risk row's RPN is 27 or more, also fill Mitigation Plan, Owner, Target Date and Status.
   - Save → **Submit**.
4. **You should see:** a new **Supplier** `LRN Components Pvt Ltd` with address, contact, bank account and a portal user. The Prospective Supplier status becomes *Onboarded*.

> The supplier can also fill the form themselves: button **Send Onboarding Link** (needs outgoing email) or the public page `/supplier-onboarding-form`.

**Way 2 – Direct supplier (faster)**

**Supplier** → New → Name `LRN Metals`, Supplier Group `Raw Material`, Country India → open the **Buying** tab → set **Incoterms** (e.g. EXW), **Bank**, **Bank Account No**, **IFSC** → Save. Add an Address (Address & Contact section).

### A2. Approve the supplier

Open the supplier. Top right shows **Approval Status: Draft** and an **Actions** menu.

| Click (Actions) | Result status | Role needed |
|---|---|---|
| Send for Approval | Pending Purchase Approval | Purchase User |
| Approve | Pending Quality Approval | Purchase Manager |
| Approve | Pending Finance Approval | Quality Manager |
| Approve | **Enabled** | Finance Manager |

Administrator has these roles, so you can click through all four. *Raw Material* uses the full chain, *Services* goes straight to Finance, other groups approve in one step (set in Buying Control Settings → Supplier tab).

**You should see:** Approval Status **Enabled**. RFQs and POs are blocked for suppliers that are not Enabled.

Common errors: *"Set the Incoterms…"* → fill Incoterms on the Buying tab. *"needs an active Bank Account"* → fill Bank + Account No.

### A3. Supplier Line Card (optional but useful)

**Supplier Line Card** → New → Supplier `LRN Metals`, Company → rows: Manufacturer Part No `LRN-MPN-PCB-01`, Lead Time 14, MOQ 100, SPQ 50 → Save.

Used by Auto PO Run in *Lead-time Mode* and as the fallback supplier.

### A4. Items

Create these with **Item** → New (Item Group: create *Raw Material* / *Products* if missing, UOM `Nos`, **Maintain Stock** ticked):

| Item Code | Is Purchase Item | Min Order Qty (MOQ) | Standard Packing Qty (SPQ) | Notes |
|---|---|---|---|---|
| LRN-FG-01 | No | – | – | Finished good you sell |
| LRN-PCB | Yes | 100 | 50 | Will get a price → auto ordered |
| LRN-IC | Yes | 100 | 100 | Default supplier but no price → *No Price* exception |
| LRN-RES | Yes | 10000 | 5000 | Price, but shortage too small vs MOQ → MOQ exception |

- MOQ is the standard field *Minimum Order Qty*; SPQ is **Standard Packing Qty (SPQ)** just below it.
- **Built Type**: Standard (leave).
- For LRN-PCB, open *Quality* section → tick **Inspection Required before Purchase** and pick a **Quality Inspection Template** (create one with one parameter, e.g. "Visual").
- Check the **Item Defaults** table has a row for *Universal Buying Demo* (ERPNext adds it).
- For LRN-IC set **Default Supplier** = `LRN Metals` in that Item Defaults row (but do **not** give it a price). An item with no default supplier at all shows as *No Supplier* instead.

**Item Manufacturer** → New → Item `LRN-PCB`, Manufacturer (create one, e.g. `LRN Mfr`), Manufacturer Part No `LRN-MPN-PCB-01` → Save. Repeat for LRN-RES with `LRN-MPN-RES-01`.

**BOM** → New → Item `LRN-FG-01`, rows: LRN-PCB qty 1, LRN-IC qty 2, LRN-RES qty 4 → Save → **Submit** (it becomes the default BOM).

### A5. Item Price Request – give items an approved source

**Item Price Request** → New (or on the Item form: **Create → Item Price Request**).

- Company: Universal Buying Demo, Type: **Buying**
- Row 1: Item `LRN-PCB`, UOM Nos, Supplier `LRN Metals`, Price List `Standard Buying`, Rate `120`, MOQ 100, SPQ 50, Lead Time Days 14, Valid From today, Valid Upto +1 year, Manufacturer Part No `LRN-MPN-PCB-01`
- Row 2: `LRN-RES`, same supplier, Rate `0.50`, MOQ 10000, SPQ 5000, lead time 7
- Save → **Submit**.

**You should see:** an **Item Price** for each row (supplier + validity), MOQ/SPQ written on the items, **Default Supplier** = LRN Metals in Item Defaults, and the MPN marked default.

> An item can have only one *open* Buying request. Later price changes: raise a new request after the first is submitted, or edit Item Price directly.

---

## Part B – Demand and automatic ordering

### B1. Sales Order

**Sales Order** → New → Customer (create `LRN Customer`), Delivery Date +45 days, Item `LRN-FG-01`, Qty **200**, Rate any → Save → **Submit**.

### B2. Run the shortage calculation

The Requirement Engine runs every night at 03:00. To run it now: **Requirement Rebuild** list → button **Rebuild Now** → Company: Universal Buying Demo → **Queue**. Wait ~10 seconds and refresh.

**You should see:** a Requirement Rebuild row with status *Completed*. Open **Requirement Log** (or the report **Manufacturing Shortage Summary**) → Shortage rows:

| Item | Shortage |
|---|---|
| LRN-PCB | 200 |
| LRN-IC | 400 |
| LRN-RES | 800 |

(Stock and open POs are subtracted first; with no stock, shortage = SO qty × BOM qty.)

### B3. Auto PO Run

**Auto PO Run** → New → Company, **To Date** = +90 days (must cover the SO delivery date) → Save → **Submit**. It runs in the background; refresh after a few seconds until Status = *Completed*.

**You should see:**
- Button **Purchase Orders** → one **draft PO** for LRN Metals: LRN-PCB qty 200 (rounded to SPQ 50, at least MOQ 100) at ₹120.
- Button **Auto PO Exception** → the items that could not be ordered:

| Item | Exception Type | Why |
|---|---|---|
| LRN-IC | No Price | Has a default supplier but no Item Price |
| LRN-RES | MOQ Exception | 800 needed, MOQ 10000 (below the 70% class-C threshold) |

### B4. Handle the exceptions (manual – there is no Recommendation Note)

Open the **Auto PO Exception** and **Submit** it (the Create buttons appear only on the submitted exception; it stays editable for the Follow-up column).

- **LRN-IC (No Price):** **Create → Item Price Request** (it offers the No Price rows). Complete it (supplier, rate, etc.) and submit. Next Auto PO Run will order it. — *or* get quotes first with an RFQ (Part C).
- **LRN-RES (MOQ Exception):** choose one:
  - **Create → Purchase Order for MOQ Items** – only allowed when the shortage is within 5% of MOQ (here it is not, so it will be refused – that is correct);
  - order the full MOQ with a manual PO; or
  - wait until more demand comes.
  Type your decision in the **Follow-up** column (e.g. "RFQ PUR-RFQ-…" or "wait") and Update – rows with Follow-up are not repeated on the next run.
- **No Supplier rows** (items without any default supplier): raise an RFQ by hand (Part C) or an Item Price Request by hand.

---

## Part C – Sourcing with RFQ (for LRN-IC)

### C1. Request for Quotation

**Request for Quotation** → New:
- Company, **PO Type** `3-Way`
- Suppliers: `LRN Metals` and `LRN Components Pvt Ltd` (you can also add a *Prospective Supplier* instead of a Supplier)
- Items: `LRN-IC`, Qty 400, Required By date
- **Bid Deadline**: set it **15–20 minutes from now** for practice
- Save → **Submit**.

**You should see:** state *Open*, Bid Status *Open*. Invitations are queued as emails (they will not be delivered until real SMTP is configured on Email Account *DEMO Outgoing*).

### C2. Enter the quotations

Either way works:

- **As the buyer (simplest):** RFQ → **Create → Supplier Quotation** → pick the supplier → enter Rate (e.g. ₹8.00 for one, ₹7.50 for the other), Lead Time, terms → Save. Do this for both suppliers.
- **As the supplier:** in the Incognito window log in as a supplier portal user → **/supplier_portal** → RFQs → Quote. (Prospective suppliers get a link `/rfq-portal?token=…` by email.)

A supplier can re-quote; the older quotation is marked *Revised*. The buyer can press **Mark for Revision** on a quotation to ask for a new one.

### C3. Close bidding and approve

After the Bid Deadline passes (the scheduler closes it within 15 minutes, or check Bid Status), the RFQ **Actions** menu shows **Send for Approval**. Then each tier approves from **Actions**, logged in as that user (not the RFQ creator):

| Step | User | State after |
|---|---|---|
| Send for Approval | you | Pending Dept Head Approval |
| Approve | demo.depthead | Pending SCM Head Approval |
| Approve | demo.scm | Pending Operations Head Approval |
| Approve | demo.ops | Pending Final Approval |

Any tier can **Reject** or **Send Back for Correction** (a comment is required).

### C4. Compare and award

As **demo.ceo**: open the RFQ → button **Quotation Comparison** (page `/quotation-comparison?rfq=…`). You see one column per live quotation: rates, landed total, lead time, MOQ/SPQ, payment terms, specs, supplier approval status, and the current Item Price difference. The lowest total is highlighted. Enter remarks → **Award** the chosen supplier.

**Discussion (chat):** the comparison page has a **Discussion** row with a chat box under every supplier. Type a message and press **Send** (or Ctrl+Enter). Tick **Internal note** to write something only your team sees (yellow). Supplier messages appear in white, buyer messages in blue; the page refreshes every 20 seconds. The supplier reads and replies in the **Messages with the buyer** panel on their RFQ portal page, and the same thread is shown on the Supplier Quotation form (section *Discussion with Supplier*). All messages are kept in **Quotation Message**.

**You should see:** the winning Supplier Quotation *Approved*, the others *Rejected*, RFQ state *Awarded*. If the winner was a Prospective Supplier, an onboarding is created for it automatically.

### C5. Create the PO from the quotation

Open the winning **Supplier Quotation** → **Create → Purchase Order** → check lines → Save.

Optional (make it the approved source for future Auto PO runs): raise an **Item Price Request** for LRN-IC with the awarded supplier and rate.

---

## Part D – Purchase Order, approval, supplier portal

### D1. Check and approve the POs

Open the draft PO from Auto PO Run (Purchase Order list, *Buying Control* tab shows **Origin = Auto PO Run**).

1. Check supplier address, billing and shipping address, taxes. **Rate cannot be changed** – it comes from the Item Price (Price Control = Strict).
2. Click **Send for Approval** → Approval Status *Pending*, the required role is shown.
3. As **demo.purchase** (or yourself if you gave yourself *Purchase Executive*): open the PO → **Approve**.

**You should see:** PO **submitted automatically**, Portal Status *Pending Acceptance*. Bigger POs need more steps (₹5L–1Cr adds Purchase Senior Manager, etc. – see Settings → Purchase Order tab).

Do the same for the PO created from the quotation (Origin = Supplier Quotation).

### D2. Supplier side (optional)

As the supplier's portal user (e.g. demo.suppliera for DEMO Supplier A, or set a password for your supplier's portal user under **User**) open **/supplier_portal** → Purchase Orders → the PO:
- **Acknowledge** with a confirmed delivery date → Portal Status *Accepted*
- **Material Status** updates (In Production, Ready…)
- Upload the invoice document, create a **Shipment** → Dispatched

### D3. Changing a PO after submit – PO Amendment

PO → **Create → PO Amendment** → change New Qty / New Rate / New Date on lines, Reason → Save → **Actions → Send for Approval** → as **demo.pm**: **Approve**. The PO lines, taxes and totals are updated. Rate increase is limited to 5% unless an Item Price supports it; qty cannot go below received qty.

---

## Part E – Receiving and quality

### E1. Gate Entry

**Gate Entry** → New → Entry Type **In**, Party Type Supplier, Party `LRN Metals`, invoice number `INV-LRN-001`, vehicle no, boxes → Save → **Submit** → button **Create → Purchase Receipt**.

### E2. Purchase Receipt

On the new receipt:
1. **Get Items From → Purchase Order (Pending Lines)** → tick the PO line(s) → Get Items. (Rows cannot be typed without a PO.)
2. **Supplier Invoice No** `INV-LRN-001` (+ date). Gate Entry is already filled.
3. Per row: Manufacturer, Manufacturer Part No, **Manufacturer Batch No**, Manufacturing Date (for batch items).
4. Save.
5. Batch-tracked items: **Create → Batches**.
6. Inspection-required items (LRN-PCB): **Create → Inspections by Batch**.

Try **Submit** now – it is **blocked** ("inspection missing") because the IQC gate is *Block*. That is expected.

### E3. Quality Inspection

Open each inspection (from the receipt or **Quality Inspection** list):
- Sample size comes from the template's sampling band. Enter readings, **Sample Taken** = sample size, **Received Manufacturer Part No** = the MPN on the Item Manufacturer.
- Status **Accepted** → Save → **Submit**.

Back on the receipt: **Actions → Check IQC** → **Submit**. Stock goes into *Stores*.

**Rejected path (try once):** on a second small receipt set the inspection to **Rejected** and submit. The rejected qty moves to *Rejected Goods*, and an **Item Non Conformance** is created (or use **Create → Item Non Conformance** on the inspection). Open it → pick a Disposition (Scrap / Return to Supplier / Transfer / Rework / Accept on Deviation), attach a file → Submit → **Create → Stock Entry** or **Create → Purchase Return**.

**Mismatch between invoice and goods:** on a draft receipt create an **Inward Discrepancy** (rows: item, invoice qty, type, remarks; buyer comments required on submit).

---

## Part F – Invoice and payment

### F1. Purchase Invoice (3-way match)

**Purchase Invoice** → New → Supplier `LRN Metals`, **Supplier Invoice No** (Bill No) `INV-LRN-001` → **Get Items From → Receipts by Supplier Invoice No** → rows from every receipt with that invoice number come in → check taxes → Save → **Submit**.

Rules you will meet:
- 3-Way PO Type: invoice without a receipt is refused. 2-Way (services) needs only the PO.
- Invoice total above PO total + tolerance: save is blocked until you enter an **Override Reason**.

### F2. Payment Indent (advance request)

**Payment Indent** → New → Company, Supplier → add Purchase Orders → **Get Items from Purchase Orders** → set indent qty, **Requested Amount** (max 110% of value), proforma details, justification → Save → **Submit**.

**You should see:** a **Payment Request** per PO (buttons under *Payment Requests*). Above ₹5 lakh the submitter needs the Purchase Manager role. Accounts then makes the **Payment Entry** from the Payment Request / invoice.

---

## Part G – Reports to check your work

Sidebar → **Reports**:

| Report | Shows |
|---|---|
| Manufacturing Shortage Summary / PO Shortage Summary / Project Shortage Summary | Shortage by month |
| Auto PO Exception | What Auto PO could not order |
| Excess PO | Ordered beyond requirement |
| RFQ Status, Pending Supplier Quotations | Sourcing progress |
| Purchase Order Open Qty, Delayed PO, Unacknowledged PO | Open orders |
| Purchase Receipt Pending, IQC Pending, IQC Rejection, Inward Discrepancy Register | Receiving |
| Purchase Receipt to be Billed, Invoice Variance | Finance |

---

## Common messages and fixes

| Message | Fix |
|---|---|
| Supplier … is not approved | Take the supplier to *Enabled* (A2). |
| Set the Incoterms … / needs an active Bank Account | Supplier → Buying tab: Incoterms, Bank, Account No. |
| Company … is not present in the Item Master | Item → Item Defaults: add a row for the company. |
| Item already exists in an open Item Price Request | Submit or cancel the earlier request first. |
| Auto PO Run makes no PO | Did you run **Rebuild Now** after the Sales Order? Is To Date after the delivery date? Does the item have default supplier + valid Item Price? |
| Rate is reset on the PO | Price Control is Strict – change the price with an Item Price Request. |
| You cannot approve (PO / RFQ) | Log in as the user holding the step role; the creator cannot approve their own RFQ. |
| Send for Approval not shown on RFQ | Bid Deadline not passed yet. |
| Receipt submit blocked – inspection missing | Submit a Quality Inspection for each inspection-required row, then **Check IQC**. |
| Invoice blocked – exceeds PO | Enter **Override Reason** or correct qty/rate. |
| Emails not arriving | Configure real SMTP in **Email Account → DEMO Outgoing**. |
| Page looks unstyled | Ctrl+Shift+R; if still, restart `bench start`. |

## One-page summary

```
Supplier:  Prospective Supplier → Onboarding → Supplier → Approval (Enabled)
Item:      Item + Item Manufacturer + BOM → Item Price Request (price, supplier, MOQ, SPQ)
Demand:    Sales Order → Requirement Rebuild (Rebuild Now) → Auto PO Run → draft PO + Auto PO Exception
Exception: Item Price Request | PO for MOQ items | RFQ (manual) | wait  (write Follow-up)
RFQ:       RFQ → quotes → deadline → tier approvals → CEO award → PO from quotation
Order:     PO → Send for Approval → Approve (auto submit) → supplier acknowledges → shipment
Inward:    Gate Entry → Purchase Receipt → Batches → Quality Inspection → Check IQC → Submit
Finance:   Purchase Invoice (by supplier invoice no) → Payment Indent → Payment Request → Payment Entry
```
