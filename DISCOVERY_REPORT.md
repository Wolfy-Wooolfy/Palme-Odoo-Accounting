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

## AREA 2 — Visa Bank-Confirmation Mechanics (focused follow-up, 2026-06-23)

> Focused follow-up to Area 2. Traced **3 real Visa collections end-to-end** on the live prod DB to pin
> the EXACT field/relationship that marks *"the accountant confirmed this Visa money actually hit the bank"*.
> 100% read-only (`search_read`/`read_group`/`read` with small limits on the ~41-account holding set; never an
> unbounded `account.move.line` scan). Gather scripts: `src/visa_confirm_discovery.py`, `src/visa_confirm_trace2.py`.

### Verdict (TL;DR)
**The confirmation signal is (b): a manual journal entry that CREDITS the Visa holding account, counterpart
`63001 Liquidity Transfer`, posted when the acquirer (جيديا / *Geidea*) settles the branch's card takings to the bank.**
- Signal **(a)** — reconciling the holding-account lines (`reconciled`/`full_reconcile_id`/`matching_number`) — is
  **structurally impossible** here: every Visa holding account is `reconcile = False`, `account_type = asset_cash`.
  Odoo never sets `full_reconcile_id` on these lines. **Do not use any reconciliation flag.**
- Signal **(c)** — the `121100` auto-reconcile at session close — is POS-internal and is **ruled out**.
- Because the accounts are non-reconcilable, the monitor must measure confirmation by the **net balance of the
  holding account per branch journal** (collected debits − confirmed credits) — not by a reconciliation flag and
  **not by line age** (non-reconcilable accounts have no FIFO matching).

### End-to-end flow — traced on 3 real closed sessions
| Session | Config / branch (co) | Visa amount | Per-session `account.payment` | Visa journal | Holding acct |
|---------|----------------------|-------------|-------------------------------|--------------|--------------|
| `POS/16355` | البنفسج تحصيل 2 (co3) | **32,854.26** | `BNK8/2026/0707` | `638 VIS02 فيزا فرع البنفسج` | `17495` |
| `POS/16353` | ارابيسك كافية تحصيل 2 (co3) | **3,243.96** | `BNK14/2026/0786` | `686 VIS06 فيزا اربيسك كافية` | `17495` |
| `POS/16357` | التجمع الاول تحصيل (co3) | **7,763.37** | `BNK7/2026/1144` | `637 VIS01 فيزا فرع التجمع الاول` | `17495` |

Walking `POS/16355` (Visa = 32,854.26 EGP):
1. **Collect** — card swipes are `pos.payment` on method `427 فيزا فرع البنفسج 2` (no per-payment JE).
2. **Close** — `POSS/2026/3172` debits **`121100` Accounts Receivable (PoS)** 32,854.26 (line `POS/16355 - فيزا فرع البنفسج 2`).
3. **Card payment** — `account.payment BNK8/2026/0707` (journal `638`, method `427`) posts **DR `17495 12035 فيزا الفروع` 32,854.26 / CR `121100` 32,854.26**. (`outstanding_account_id = 17495`, `destination_account_id = 16409 = 121100`.)
4. The two `121100` legs **auto-reconcile** (`full_reconcile_id = 257828`) → POS-internal clearing, **not** bank. `account.payment.is_matched = is_reconciled = True` reflect THIS leg, so they are useless as a bank signal.
5. The **DR on holding `17495` stays `reconciled = False`** — the Visa cash now sits in the holding account awaiting confirmation.
6. **Confirm** — when Geidea deposits the settlement, the accountant posts e.g. `BNK7/2026/1137` *"تحويل جيديا فيزا فرع التجمع الاول"*: **CR `17495` (holding) / DR `63001 Liquidity Transfer`** for the net, plus a fee entry **DR `31030` عمولة مكن الفيزا / CR `17495`**. `63001` (`asset_current`, `reconcile = True`) is then matched to the real bank move. **This credit to the holding account is the per-branch/day "money confirmed received" event.**

### Which signal marks "confirmed in bank"
| Candidate | What it checks | Verdict | Evidence |
|-----------|----------------|---------|----------|
| **(a)** holding-line reconciliation | `account.move.line.full_reconcile_id` / `reconciled` / `matching_number` on the holding acct | ❌ **Impossible** | All 41 Visa holding accts are `reconcile=False, asset_cash`. Of 9,611 lines only 28 show `reconciled=True`, and **all 28 are zero-amount combine-payment artifacts** (D 0 / C 0, `full_reconcile_id=False`, no partials). Genuine reconciliations = **0**. |
| **(b)** transfer-out credit | a JE crediting the holding acct, counterpart `63001 Liquidity Transfer` (ref جيديا/transfer) | ✅ **THE SIGNAL** | Real entries: `BNK7/2026/1137` etc. CR `17495` / DR `63001`; companion fee CR `17495` / DR `31030`. This is the per-branch action that moves the money toward the bank. |
| **(c)** `121100` auto-reconcile | `full_reconcile_id` on the `121100` session/payment legs | ❌ **Ruled out** | Auto-set at close (`257814–257828`); clears POS receivable only, fires for every session regardless of bank settlement. |

### The monitoring screen — exact fields & domains
**Holding-account set** (branch Visa "outstanding" accounts): `outstanding_account_id` of every
`pos.payment.method` where `is_cash_count = False AND name like 'فيزا'` → **41 accounts**
(ids `85-90, 316, 365-385, 394-400, 961, 962, 16823, 17412, 17416, 17495`).

All KPIs read `account.move.line`, domain `account_id in <holding set> AND parent_state = 'posted'`,
grouped by **`journal_id`** (branch) and **`date`** (day):
- **Expected Visa collected** (branch/day) = `SUM(debit)` where `debit > 0`.
- **Confirmed received** (branch/day) = `SUM(credit)` where `credit > 0` (the Geidea/transfer + fee entries). To isolate the true bank-bound amount, restrict to credits whose move has a `63001 Liquidity Transfer` leg (excludes the `31030` commission).
- **Pending / not-yet-confirmed** (running, per branch) = `SUM(balance)` = `SUM(amount_residual)` (identical here — nothing reconciles). Positive = collected-but-not-confirmed.
- **Late flag** = branch has a positive holding balance **and** no confirmation credit within N days (track the latest credit `date` per `journal_id`). **Do not age individual debit lines** — the oldest unreconciled line date (e.g. 2024-06-01) is meaningless on a non-reconcilable account.
- *Collection-side cross-check (optional):* `account.payment` where `pos_payment_method_id in <Visa methods> AND pos_session_id != False`, grouped by `pos_payment_method_id` + `date`.

### Branch/day attribution
- **Branch = `account.move.line.journal_id`** (stored, groupable) — the per-branch Visa bank journal
  (`BNK10 فيزا فرع التجمع الاول`, `VIS02 فيزا فرع البنفسج`, …). **Never `account_id`**: company 3 funnels 6+ branch
  journals (`VIS01-07`) into the single shared holding account `17495`. Collection-side equivalent: `pos.payment.method` (→ its `journal_id`).
- **Day = `date`** (stored). Sub-channels are separate journals/accounts per branch: in-store POS plus delivery
  aggregators مرسول/*Mrsool*, حاضر/*Hadir*, انستا شوب, طلبات/*Talabat* (`BNK18-44`) — group/label by journal.

### Backlog (as of 2026-06-23)
Net unconfirmed across all 41 Visa holding accounts: **108.0M EGP** (debit 149.0M − credit 41.0M; 9,611 lines).
Two distinct eras:

| Era | Accounts | Lines | Collected (DR) | Confirmed (CR) | **Net pending** | Collection span | Last confirmation |
|-----|----------|-------|----------------|----------------|-----------------|-----------------|-------------------|
| **Legacy — Company 1** per-branch | 85-90, 316, 961, 962, … (39) | 7,205 | 124.2M | 17.0M | **107.1M** | 2024-06-05 → 2025-11-26 | **2025-09-25 (stalled)** |
| **Active — Company 3** shared | `17495`, `16823` | 2,406 | 24.85M | 23.93M | **0.92M** | 2025-01-31 → 2026-06-23 | **2026-06-21 (current)** |

Read: POS Visa migrated onto the company-3 shared journals (`VIS01-07 → 17495`) in early 2025, where Geidea
confirmations are posted regularly and the account nets ~0 (only **0.92M** outstanding, ≤2 days old). The
**company-1 per-branch holding accounts are a frozen ~107M unconfirmed pile** — confirmations stopped on
**2025-09-25** and never resumed. So the monitor's headline backlog is dominated by legacy accounts (an
accounting-cleanup / migration question), while the **live daily-ops gap to watch is the small, fast-moving
company-3 balance** ("did each branch's Geidea transfer get posted today?").

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

---

## Area 2 — Session→Geidea Linkage & Late Rule (company #بالميه#.)

> Final pre-build discovery (2026-06-23), **company `#بالميه#.` = company_id 3 only**, 100% read-only.
> Gather script: `src/visa_linkage_discovery.py`. Scope = the two active co-3 Visa holding accounts
> `17495 "12035 فيزا الفروع"` and `16823 "120307 فيزا فرع ارابيسك"` (both `asset_cash`, `reconcile=False`).
> Legacy company-1 per-branch pile is excluded simply by `account_id in (17495,16823) AND company_id=3`.

### 1. Confirmed linkage model — **periodic LUMP per branch, NOT per session → use a running balance**
The Geidea confirmation is **not** posted per session and **cannot** be line-matched to a session (accounts are
`reconcile=False`). Per branch it arrives as a **batch (typically grouped by settlement day) that covers many prior
sessions' takings at once**, and it is split into **two separate moves**, each with exactly **one** credit line on the
holding account:

| Move (branch journal) | ref / line name | Holding leg | Counterpart | Meaning |
|---|---|---|---|---|
| `BNK7/2026/1139` (VIS01 التجمع الاول) | `"…جيديا"` / `Transfer from فيزا فرع التجمع الاول` | **CR `17495` 38,964.61** | **DR `63001` Liquidity Transfer** (id 16572) | **the bank-bound settlement — THE confirmation signal** |
| `BNK7/2026/1140-1141` (same branch) | `"عموله تحويل جيديا التجمع الاول"` | CR `17495` 254.93 + 1.33 | DR `31030` عمولة مكن الفيزا (id 17213) | acquirer commission (companion, **not** bank receipt) |

The `38,964.61` transfer matches **no single session** (same-branch session debits that day were e.g. 7,763.37,
33,938.82, …) — it is a **lump**. Confirmed across all 7 active branches on 2026-06-21: every branch got exactly one
`63001` transfer credit + one `31030` commission credit. ⇒ **Confirmation granularity = per branch, per settlement
batch.** The holding account only nets back to ~0 once **both** legs post; the **`63001` leg is the “money confirmed
to bank” event**, the `31030` leg is just the fee.

**Debit (collection) side — IS per session.** Each closed session's Visa total posts one `account.payment` "combine"
entry on the **branch VIS journal**: **DR holding `17495` / CR `121100`**. That debit line carries
`payment_id → account.payment.pos_session_id → pos.session` (and thus `stop_at`). So every holding **debit** is
attributable to one session; every holding **credit** (confirmation) is a lump over several. Examples:

| Session | `stop_at` | Holding DR line date | Branch journal | Visa DR |
|---|---|---|---|---|
| `POS/16355` | 2026-06-23 06:07 | 2026-06-23 | VIS02 البنفسج | 32,854.26 |
| `POS/16357` | 2026-06-23 05:38 | 2026-06-23 | VIS01 التجمع الاول | 7,763.37 |
| `POS/16343` | **2026-06-22** 21:15 | **2026-06-23** | VIS01 التجمع الاول | 33,938.82 |

⚠ The debit line's **accounting date ≈ close date but can roll to the next day** for late-evening closes (`POS/16343`
closed 22nd 21:15, debit dated 23rd). **Anchor the late clock to `pos.session.stop_at`, never to the holding line `date`.**

### 2. The "collected vs confirmed vs late" compute — recommended approach
Because confirmations are lumps, **do running-balance-by-branch-and-day, with FIFO**:
1. **Collected stream** (per branch journal) = holding **debit** lines, each tagged with its session `stop_at`
   (via `payment_id`). Domain: `account_id in (17495,16823) AND parent_state='posted' AND debit>0`, group by `journal_id`.
2. **Confirmed stream** = holding **credit** lines whose move has a **`63001` leg** (excludes the `31030` commission).
   Same domain with `credit>0`; classify a credit as "confirmation" iff a sibling line on its `move_id` hits acct `63001` (id 16572).
3. **FIFO settle**: per branch, consume oldest collections (by `stop_at`) with incoming confirmation credits.
   The **oldest still-unconsumed collection** defines exposure.
4. **Late** = that oldest unconsumed collection's **`stop_at` + 2 working days < server-today** (Friday-only weekend,
   see §3). Late amount = sum of unconsumed collections past their due date. Net pending per branch = `Σdebit − Σcredit`
   (= `Σbalance`, identical since nothing reconciles).

This gives both a per-branch/day grid (collected vs confirmed) **and** a precise "which day's money is overdue", without
needing a (structurally impossible) per-session match.

### 3. 2-working-day due dates verified on REAL `stop_at` (Friday = ONLY weekend; Saturday works)
Clock starts at `stop_at`, counting begins the next day, skip Fridays only. Server today = **2026-06-23 (Tue)**:

| Session | `stop_at` (weekday) | **Due (stop_at + 2 wd)** | Calendar days | Crosses Fri? | Status today |
|---|---|---|---|---|---|
| `POS/16217` | 2026-06-17 (**Wed**) | **2026-06-20 (Sat)** | +3 | ✅ skips Fri 06-19 | PAST DUE (5 wd) |
| `POS/16246` | 2026-06-18 (**Thu**) | **2026-06-21 (Sun)** | +3 | ✅ skips Fri 06-19 | PAST DUE (4 wd) |
| `POS/16275` | 2026-06-19 (**Fri**) | **2026-06-21 (Sun)** | +2 | n/a (closed on weekend; clock starts next working day) | PAST DUE (4 wd) |
| `POS/16326` | 2026-06-21 (**Sun**) | **2026-06-23 (Tue)** | +2 | ❌ | within window (due today) |
| `POS/16355` | 2026-06-23 (**Tue**) | **2026-06-25 (Thu)** | +2 | ❌ | within window |

### 4. Company-3 scoping & branch working set
- **Scope sessions** with the dot-walk domain `('config_id.company_id','=',3)` (searchable even though session
  `company_id` isn't groupable) — verified 200 closed co-3 sessions since 06-13. Attribution still goes
  `pos.session → config_id → company`, never `session.company_id`.
- **Branches = `journal_id` on the holding lines.** Active co-3 Visa branch journals (the screen's live set):

| journal_id | code | Branch | Net pending (DR−CR) | Last confirm | Status (today) |
|---|---|---|---|---|---|
| 638 | VIS02 | فيزا فرع البنفسج | **371,532.34** | 2026-06-21 | within (2 wd) |
| 637 | VIS01 | فيزا فرع التجمع الاول | **174,714.53** | 2026-06-21 | within (2 wd) |
| 643 | VIS05 | 1 فيزا فرع ساوث بارك | **137,291.58** | 2026-06-21 | within (2 wd) |
| 639 | VIS04 | فيزا فرع سفن ستار | **72,498.79** | 2026-06-21 | within (2 wd) |
| 640 | VIS03 | فيزا فرع التسعين | **69,508.27** | 2026-06-21 | within (2 wd) |
| 709 | VIS07 | فيزا فرع الشروق | **49,513.72** | 2026-06-21 | within (2 wd) |
| 686 | VIS06 | فيزا اربيسك كافية | **40,681.12** | 2026-06-21 | within (2 wd) |
| 645 | VIS99 | فيزا فرع ارابيسك *(acct 16823)* | −52,516.35 *(over-credited)* | — | n/a |

- **Active co-3 net pending (VIS01-07) ≈ 0.92M** (915,740) — exactly matches the Area-2 backlog figure; last
  confirmation 2026-06-21 = **2 working days ago**, so **all branches are at/within window, none past due** ⇒ confirms
  "company-3 confirmations are current". Each branch's pending is just the **un-confirmed 06-21→06-23 tail**.
- **Exclude as noise** (manual/treasury, not the per-session POS flow): `240 MISC` Miscellaneous Operations
  (net ~0), `629 CSH99 خزينة ارابيسك` (+184k cash, no Geidea credit), `641 CSH=1` الخزينة الرئيسية (nets 0),
  `249 POSS` Point of Sale (+50k). The arabisck pair (`645 VIS99` −52.5k / `629 CSH99` +184k on acct `16823`) is a
  secondary, manually-handled branch — flag it separately, don't run the 2-wd rule on it.

### Screen recommendation (one line)
Drive the monitor off the **holding running balance per branch journal**, collections tagged by session `stop_at`,
confirmations = holding credits whose move has a **`63001`** leg; FIFO the two streams and raise **Late** when the
oldest unconfirmed collection's `stop_at + 2 working days (skip Fridays) < server-today`.
