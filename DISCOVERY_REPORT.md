# Discovery Report — POS Sessions, Card Reconciliation, Bank Movements & Purchase Cycle

**Project:** Palme Odoo financial reporting · **Generated:** 2026-06-22 (server time)
**Mode:** READ-ONLY discovery (no writes). Data gathered via the existing `OdooReadOnlyClient`
(`odoo-financial-reports/src/odoo_client.py`) using only `fields_get` / `search_count` /
`read_group` / `search_read`.

## Connection
| Item | Value |
|------|-------|
| URL / DB | `kamahtech-palme-prod-13407418` (production) |
| Odoo version | **17.0+e** (Enterprise) |
| API method | XML-RPC (JSON-RPC auth returns *Access Denied* — falls back to XML-RPC, uid 49) |
| Companies | **3** (multi-company — always filter by `company_id`) |
| Localization | `l10n_eg`, currency EGP |

> Raw dump of everything below: `odoo-financial-reports/output/area_discovery_raw.json`.
> Gathering script (read-only, re-runnable): `odoo-financial-reports/src/area_discovery.py`
> → `python -m src.area_discovery`.
>
> **As-of caveat:** counts are a point-in-time snapshot taken **2026-06-22**. This is a *live* prod DB —
> POS cash/purchase volumes drift by a few records per minute, so totals like statement-line and
> `invoice_status` counts will move by ±a handful. All figures below were independently re-derived by a
> separate verification pass; the substantive conclusions hold exactly. **Tooling note:** call
> `client.fields_get(model)` *without* a field-name list — passing field names returns empty attribute dicts;
> and `search_read` defaults to `limit=80`, so use `search_count` / explicit limits when counting.

---

## AREA 1 — POS Sessions (open / close behaviour)

### Models & exact fields
**`pos.session`**
- `state` *(selection)* — values: `opening_control`, `opened` ("In Progress"), `closing_control` ("Closing Control"), `closed` ("Closed & Posted")
- `start_at` *(datetime, stored)* — opening time · `stop_at` *(datetime, stored)* — closing time
- `config_id` *(m2o → `pos.config`)* · `user_id` *(m2o → `res.users`, "Opened By")* · `name` *(char, "Session ID")*
- `cash_register_balance_start` *(monetary, **stored**)* · `cash_register_balance_end_real` *(monetary, **stored**, "Ending Balance")*
- `cash_register_balance_end` *(monetary, **NOT stored** — theoretical)* · `cash_register_difference` *(monetary, **NOT stored**)*
- `move_id` *(m2o → `account.move`)* — the session journal entry (posted at close)
- `bank_payment_ids` *(o2m → `account.payment`)* — auto-created card/bank payments (see Area 2)
- `statement_line_ids` *(o2m → `account.bank.statement.line`, "Cash Lines")*
- `order_count`, `total_payments_amount` *(both computed, not stored)* · `rescue` *(bool — recovery session)*

**`pos.config`** — `name`, `active`, `current_session_id` *(m2o → `pos.session`)*, `current_session_state` *(char)*,
`journal_id` *(POS sales journal)*, `invoice_journal_id`, `payment_method_ids` *(m2m → `pos.payment.method`)*, `company_id`.

### Linkage
`pos.session.config_id → pos.config` · `pos.config.current_session_id → pos.session` (the live one) ·
`pos.session.move_id → account.move` (accounting) · `pos.session.bank_payment_ids → account.payment` ·
`pos.session.statement_line_ids → account.bank.statement.line`.

### Counts
| Metric | Value |
|--------|-------|
| Sessions total | **15,225** |
| By state | `closed` 15,196 · `opened` **29** · `closing_control` 0 · `opening_control` 0 |
| `pos.config` records | **46** total = **45 active + 1 archived** |
| Open sessions older than 30 days | **12 of 29** |
| Oldest open session | `POS/02459` — open **613 days**, 1,360 orders, `rescue=True`, config "1 South Park تحصيل" |
| Rescue sessions | **2,673 of 15,225 (~18%)** have `rescue=True` |

### Data-quality surprises
- **29 sessions stuck `opened`**, 12 of them stale >30 days; one rescue session has been open ~1.7 years with 1,360 orders. These distort "current cash on hand" and block period close.
- Most chronically-open sessions belong to **"تحصيل" (collection) POS configs** — registers used to settle credit customers, left perpetually open.
- `cash_register_balance_end` and `cash_register_difference` are **computed (not stored)** → cannot be filtered/sorted server-side; only `*_start` and `*_end_real` are stored.
- **~18% of all sessions are `rescue` (recovery duplicates)** — `POS/xxxxx (RESCUE FOR POS/yyyyy)` — they distort open/close and cash-difference reporting and should be flagged/excluded.
- ⚠ **`pos.session.company_id` is NOT SQL-groupable** (a `read_group` on it raises *"Cannot convert field pos.session.company_id to SQL"*). Filter/group sessions by company via `config_id.company_id` instead.

### Recommendation
Build the open/close monitor on `pos.session` with domain `state in ('opened','closing_control')`, join `config_id`
for the branch and `user_id` for the operator. Compute age client-side as `now − start_at` (`start_at` is stored and
sortable). Flag stale sessions (threshold e.g. >1 business day). Use presence of `move_id` to confirm a *closed*
session actually posted its journal entry.

---

## AREA 2 — POS Card / Visa payments & reconciliation

### Models & exact fields
**`pos.payment.method`** — `name`, `is_cash_count` *(bool: **True = cash drawer**, False = card/bank/credit)*,
`journal_id` *(m2o → `account.journal`)*, `outstanding_account_id` *(m2o → `account.account` — the **card holding account**)*,
`receivable_account_id` *(m2o, "Intermediary Account" — **empty on every method here**)*, `split_transactions`,
`use_payment_terminal` *(selection — `none` on all)*, `company_id`. (`type` is a computed, non-stored selection.)

**`pos.payment`** — `pos_order_id` *(→ `pos.order`)*, `payment_method_id` *(→ `pos.payment.method`)*, `amount`,
`payment_date`, `session_id` *(→ `pos.session`)*, `account_move_id` *(→ `account.move` — **empty on all but 78 of 3.7M records**: not posted per-payment)*,
`card_type` / `transaction_id` / `cardholder_name` *(present but **blank**)*, `is_change`.

> ⚠ **`card_type` filtering trap:** the values are **empty strings**, not `False`. `('card_type','!=',False)` matches
> **3.65M rows** (looks fully populated) but `('card_type','!=','')` matches **0**. Same for `transaction_id` /
> `cardholder_name`. There is no usable card metadata — `use_payment_terminal` is `false`/`none` on all 117 methods
> (no terminal integration), so card reconciliation is purely manual at the holding-account level.

**`account.payment`** — `is_reconciled` *(bool — counterpart/receivable leg cleared)*, `is_matched` *(bool, "Matched With a Bank Statement" — **unreliable here**, see below)*, `outstanding_account_id`, `destination_account_id`, `move_id`, `pos_session_id`, `pos_payment_method_id`, `journal_id`, `state`.

**`account.move.line` (reconciliation fields)** — `reconciled` *(bool)*, `full_reconcile_id` *(m2o → `account.full.reconcile`)*,
`matched_debit_ids` / `matched_credit_ids` *(→ `account.partial.reconcile`)*, `amount_residual`, `matching_number` *(char)*,
`account_id`, `payment_id` *(→ `account.payment`)*, `statement_line_id` *(→ `account.bank.statement.line`)*.

### How a card payment becomes an accounting entry (traced on session `POS/16334`)
1. Each card swipe is a **`pos.payment`** (method with `is_cash_count=False`). It carries **no** journal entry of its own (`account_move_id` empty).
2. **At session close**, `pos.session.move_id` (`POSS/…`) is posted: credits sales income (`4443xx`), debits COGS (`500xxx`), and **debits POS receivable `121100` "Accounts Receivable (PoS)"** for the card total (line label `POS/xxxxx - <method name>`). Because every method's `receivable_account_id` is empty, **all** collections (cash, card, credit) fall back to the company-default POS receivable `121100`.
3. For each non-cash method, POS also creates an **`account.payment`** (`pos.session.bank_payment_ids`), posted in the method's **bank journal** (e.g. `VIS01`, type `bank`, `default_account_id = 12035 "فيزا الفروع"`): **debit holding account `12035`, credit `121100`**.
4. The two `121100` lines (session debit + payment credit) are **auto-reconciled at close** → `full_reconcile_id` set, `reconciled=True`, `amount_residual=0`, `matching_number` set. **This clears the POS receivable only — it is NOT the bank match.**
5. The card money now sits as an unreconciled **debit in the holding account `12035`**. The final leg — matching that holding-account balance against the acquirer's actual bank deposit — is the real "card-in-bank" reconciliation, and **it is essentially not being done** (see counts).

### Which field(s) mark "card collection reconciled / matched with bank"
- ✅ **Authoritative:** reconciliation of the **holding-account move line** — `account.move.line.reconciled` / `full_reconcile_id` / `amount_residual = 0` on the method's `outstanding_account_id`.
- ✅ POS-receivable clearing leg (POS-internal, not bank): `account.payment.is_reconciled = True` / `full_reconcile_id` on the `121100` lines.
- ❌ **Do NOT use `account.payment.is_matched`** — it is `True` for ~98% of payments even though the holding accounts are unreconciled (compute quirk: outstanding/liquidity residual check doesn't reflect actual settlement in this config).

### Counts
| Metric | Value |
|--------|-------|
| `pos.payment.method` total | **117** (30 cash, 87 non-cash: Visa "فيزا", Bank/InstaPay "بنك انستاباي", Credit "عملاء أجل") |
| `pos.payment` total | **3,704,575** |
| `account.payment` total | **41,313** (14,583 originate from POS sessions) |
| `account.payment.is_reconciled` | True 36,876 · False 4,437 |
| `account.payment.is_matched` | True 40,576 · False 737 *(unreliable)* |
| POS receivable `121100` move lines | 20,441 total · **19,636 reconciled (~96%)** |
| **Card holding accounts** (43 distinct `outstanding_account_id`) | 15,488 lines · **only 93 reconciled · 15,395 NOT reconciled (≈99.4%)** |
| Methods with `receivable_account_id` set | **0** |
| Methods with `outstanding_account_id` set | **56 of 117** (31 non-cash methods have **no** holding account configured) |

### Data-quality surprises
- **Card holding accounts are ~99.4% unreconciled** — the card-to-bank settlement reconciliation is effectively not performed; the "وسيط فيزا" holding accounts keep accumulating.
- ⚠ **A holding account does NOT identify a branch.** In **company 3 (#بالميه#.)** 14 different branch-Visa methods all post to the **single** shared holding account `17495` ("12035 فيزا الفروع") — only 3 distinct holding accounts for 16 methods. In **company 1 (Palme)** it is 1:1 (40 methods → 40 accounts). So branch attribution must use the **stored** `journal_id` or the source `account.payment.pos_payment_method_id` / `pos_session_id` — **never** the account — and the logic differs per company.
- **Cash, card, and credit all post to the same `121100`** (no per-method `receivable_account_id`). You cannot separate them by account — use the source `pos.payment.payment_method_id` / `account.payment.pos_payment_method_id` or the move-line label.
- `is_matched` **and** `is_reconciled` on `account.payment` track the bank/liquidity leg, not the holding-account leg — both are almost always True and neither proves the card holding account was cleared. Rely on the holding-account move-line reconciliation instead.

### Recommendation
"Card collected but not yet in the bank" = sum of **unreconciled** (`reconciled=False` / `amount_residual≠0`)
`account.move.line` over the **43 card `outstanding_account_id` accounts** (from `pos.payment.method` where
`is_cash_count=False`). Attribute to branch/method via `account.payment.pos_session_id` + `pos_payment_method_id`.
Use `full_reconcile_id` / `matching_number` to show what *has* settled. Treat the `121100` clearing (step 4) as
POS-internal, not as proof of bank receipt.

---

## AREA 3 — Bank movements & gaps

### Models & exact fields
**`account.journal`** — `name`, `code`, `type` *(selection: `bank`, `cash`, …)*, `default_account_id`,
`suspense_account_id`, `bank_account_id` *(→ `res.partner.bank`)*, `currency_id`, `company_id`, `bank_statements_source`.

**`account.bank.statement.line`** — `is_reconciled` *(bool — **THE matched flag**)*, `amount`, `payment_ref` *(char, "Label")*,
`partner_id`, `move_id` *(→ `account.move` — the JE)*, `statement_id` *(→ `account.bank.statement` — mostly empty)*,
`amount_residual`, `transaction_type`, `account_number`. ⚠ `date` and `journal_id` are **computed (not stored)** — they
resolve from the move.

**`account.bank.statement`** — exists but holds **0 records** (Odoo 17 statement-less reconciliation).
**`account.payment`** — bank side via `is_matched`, `is_reconciled`, `journal_id`, `move_id`, `state`.

### Linkage
`account.bank.statement.line.move_id → account.move → account.move.line`; the line is matched when its bank/suspense
move line is reconciled (`reconciled` / `full_reconcile_id`). Group by `journal_id` for the bank/cash account.

### Counts
| Metric | Value |
|--------|-------|
| Journals total | 179 (**83 type=`bank`**, 58 type=`cash`) — "bank" includes the many per-branch VISA journals |
| `account.bank.statement` records | **0** |
| `account.bank.statement.line` total | **27,413** — reconciled **25,674** · not reconciled **1,739** |
| …in **bank**-type journals | 938 total · **938 reconciled · 0 open** |
| …in **cash**-type journals | 26,474 total · 24,736 reconciled · **1,738 open** |
| `account.payment` total | 41,313 — **is_reconciled False: 4,457 · is_matched False: 737 · cancelled: 1,587 · draft: 10** |

### Data-quality surprises
- **`account.bank.statement` is entirely unused (0 rows)** — do not model statements; work from statement *lines* directly (`statement_id` is empty).
- **~96.6% of statement lines are CASH-register lines** (POS cash drawers), only **938 are true bank-account lines**. The "bank movements" dataset is dominated by POS cash, not bank imports.
- All 938 true bank lines are reconciled → the statement-line open gap (1,738) is **entirely in cash journals**.
- **The statement-line gap understates the real exposure.** The more material bank/cash reconciliation gap lives in `account.payment`: **4,457 unreconciled** + **737 unmatched** (plus 1,587 cancelled / 10 draft inside the 41,313 total — exclude those from cash-flow counts). Report on `account.payment` health, not just statement lines.
- Card settlements **do not flow through statement lines** at all — they sit on the Area-2 holding accounts. A complete "money not yet in bank" view must combine *three* universes: cash statement lines, `account.payment`, and card holding accounts.
- 2 bank journals are archived (`active=False`) on top of the 83 active ones.
- `date` / `journal_id` on the statement line are non-stored (computed) — filter via the line's domain (search is delegated) but sort/group on `move_id`'s date where possible.

### Recommendation
"Bank gaps" report = `account.bank.statement.line` where `is_reconciled = False`, grouped by `journal_id` and date,
**split by `journal.type`** (cash vs bank). Then layer in the Area-2 holding-account exposure to get the true
unsettled-funds total. Don't expect bank statements; iterate statement lines.

---

## AREA 4 — Purchase cycle (PO → Receipt → Bill)

### Models & exact fields
**`purchase.order`** — `name`, `state` *(selection: `draft`/`sent`/`purchase`/`done`/`cancel`)*, `partner_id` *(vendor)*,
`picking_ids` *(m2m → `stock.picking`, "Receptions")*, `invoice_ids` *(m2m → `account.move`, "Bills")*,
`invoice_count` *(integer, **STORED** — usable in domain/`read_group`)*, `invoice_status` *(selection: `no`/`to invoice`/`invoiced`)*,
`amount_total`, `order_line` *(o2m → `purchase.order.line`)*, `company_id`, `date_order`. *(`picking_count` not exposed → use `len(picking_ids)`.)*

**`stock.picking`** — `name`, `origin` *(char = **PO name**, stored)*, `purchase_id` *(m2o → `purchase.order`, **computed / NOT stored**)*,
`state`, `picking_type_id`, `picking_type_code` *(selection: `incoming`/`outgoing`/`internal`, non-stored)*, `partner_id`, `date_done`.

**`account.move` (bill)** — `move_type` *(`in_invoice` = Vendor Bill, `in_refund` = Vendor Credit Note)*,
`invoice_origin` *(char = **PO name**, **stored**)*, `purchase_id` *(m2o, **computed / NOT stored**)*, `purchase_order_count`,
`partner_id`, `state`, `amount_total`, `invoice_date`, `ref`.
**`account.move.line`** — `purchase_line_id` *(m2o → `purchase.order.line`, **STORED** — the precise line-level link)*,
`purchase_order_id` *(computed)*, `product_id`.

### Linkage
- **PO → receipts:** `purchase.order.picking_ids` (authoritative, m2m). Reverse: `stock.picking.origin = PO.name` (stored) — preferred — or `stock.picking.purchase_id` (computed).
- **PO → bills:** `purchase.order.invoice_ids` (authoritative, m2m) + `invoice_count` + `invoice_status`.
- **Bill → PO:** `account.move.invoice_origin` (= PO name, stored, searchable) or `account.move.purchase_id` (computed). **Most precise:** `account.move.line.purchase_line_id → purchase.order.line.order_id`.

### Counts
| Metric | Value |
|--------|-------|
| Purchase orders total | **25,219** |
| By `state` | `purchase` 22,598 · `draft` 1,614 · `cancel` 982 · `sent` 15 · `done` 10 |
| By `invoice_status` | `invoiced` 17,318 · `to invoice` **4,552** · `no` 3,349 |
| POs with **0** bills | **5,270** (== `invoice_count=0`) · with ≥1 bill: 19,949 |
| Bill-count distribution | 1 bill → 19,674 · **>1 bill → 275** (2→206, 3→27, 4→16, 5→6, 6→2, long tail up to **133 bills on one PO**) |
| Vendor bills (`in_invoice`) | **20,928** · with `invoice_origin` set: 19,826 |
| Vendor credit notes (`in_refund`) | 115 |
| Pickings total / incoming | 118,223 / 24,732 |
| Pickings with `purchase_id` set | 24,082 *(see caveat)* |

### Data-quality surprises
- **4,552 POs are `to invoice`** (received but not yet billed) — the GR/IR / accrual exposure list. (3,349 are `no` = not to be billed.)
- A few POs have **absurd bill counts** (one with 133, one 105, one 63) → likely blanket/standing orders or mis-linked bills — worth flagging.
- `invoice_origin` is **free-text char** (can be edited or hold multiple refs) → for exact matching prefer `purchase_line_id`; for header-level use `purchase.order.invoice_ids`.
- ⚠ **`purchase_id` (on both `stock.picking` and `account.move`) and `picking_type_code` are computed / non-stored.** Searching them is *broken*: `purchase_id != False` returns 24,082 pickings, but `purchase_id = False` returns **0 across the entire 118,223-row table** — the ORM cannot build a correct SQL filter for the empty case on this related field. **Use the stored `origin` field or the PO-side `picking_ids` / `invoice_ids`, never these computed fields, in a domain.**
- `move_type` `in_receipt` / `out_receipt` are valid options but **unused** (0 records each) — the purchase cycle is purely PO → `in_invoice` (20,928) / `in_refund` (115).

### Recommendation
Three-way match driven from `purchase.order`: use `invoice_status` + `invoice_count` for billing state and `picking_ids`
for receipt state. "**Received not billed**" = `invoice_status = 'to invoice'` (4,552) → the accrual list. For exact
PO↔Bill reconciliation, join at line level via `account.move.line.purchase_line_id → purchase.order.line`; for
header level use `purchase.order.invoice_ids` (authoritative) rather than `bill.invoice_origin`. Flag anomalies
(`invoice_count > 2`, incoming receipts not tied to a PO via `origin`).

---

## Cross-area summary (how to build the 4 analyses cleanly)

| # | Analysis | Drive from | Key field(s) | Watch out for |
|---|----------|-----------|--------------|---------------|
| 1 | POS open/close monitor | `pos.session` `state in (opened, closing_control)` | `start_at`, `config_id`, `move_id` | 29 stuck-open sessions; computed balance fields |
| 2 | Card-in-bank reconciliation | `account.move.line` on the 43 card `outstanding_account_id` | `reconciled`/`full_reconcile_id`/`amount_residual` | `is_matched` unreliable; all collections share `121100`; holding acct ≠ branch (co. 3 shares one) — attribute via `journal_id`/`payment_method_id` |
| 3 | Bank gaps | `account.bank.statement.line` `is_reconciled=False` | `is_reconciled`, `journal_id`, `journal.type` | no `account.bank.statement`; 96% are cash; cards bypass lines |
| 4 | Purchase 3-way match | `purchase.order` | `invoice_status`, `invoice_count`, `picking_ids`, `invoice_ids`, `purchase_line_id` | computed `purchase_id`/`picking_type_code` search is inconsistent |

> **Multi-company (3 companies) — they are NOT interchangeable:**
> - **Company 1 "Palme"** — POS-heavy, card holding accounts mapped **1:1** to branches (40 methods → 40 accounts). POS payments ≈ 2.57M.
> - **Company 3 "#بالميه#."** — POS-heavy, but branch-Visa methods **share** holding accounts (14 methods → 1 account `17495`). POS payments ≈ 1.13M; vendor bills concentrate here (≈13,966).
> - **Company 2 "##Manufacture Palme##"** — purchase/manufacturing only: has POS configs/sessions but **zero `pos.payment`** records; ~3,638 POs / ~3,448 bills.
>
> Every analysis must filter/group by `company_id` — and the **card branch-attribution logic differs per company** (Area 2). For POS *sessions*, group via `config_id.company_id` (session `company_id` is not SQL-groupable).
