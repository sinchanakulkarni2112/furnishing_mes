# 15 — Open Questions & Assumptions Register

Two things live in this document:

- **Part A — Questions** for the manager, and through them the customer. Each is
  phrased so it can be copied straight into an email or a meeting agenda.
- **Part B — Assumptions** we are proceeding on *right now*, so that no phase is
  blocked waiting for an answer.

**The working method.** Where an answer is unknown, we adopt the industry-standard
default, record it here with an ID (`A1`, `A2`, …), and implement it as a
**configuration record**, not as hard-coded logic. When the real answer arrives,
it is a data edit by the Plant Manager — not a code change, not a migration, not
a redeploy. This is how manufacturing software is normally delivered when the
customer's process discovery runs in parallel with the build, and it is why the
build can start today.

Every assumption below is traceable: the model or config record that carries it
is named, so a reviewer can see exactly where a guess lives.

---

# Part A — Questions for the Manager / Customer

Ordered by when we need the answer. Each states the impact if the eventual
answer differs from our assumption.

## A.1 — Needed before Phase 2 (Master Data)

| # | Question | Assumed meanwhile | Impact if different |
|---|---|---|---|
| Q1 | What are the actual **shift timings and break durations**? Is there a permanent night shift? | 3 × 8 h, 30 min break (`A1`) | Low — shift records are data. Capacity figures shift proportionally |
| Q2 | What is the **working week and holiday calendar**? Weekly off day? | 6 days, Sunday off (`A2`) | Low — a `resource.calendar` edit |
| Q3 | Please share the **machine list**: name, code, department, and what each does | 15 machines across 6 departments, typical panel-furniture line (`A4`) | **Medium** — real machine count changes plan volumes and dashboard layout. Import template provided |
| Q4 | What is the **department structure** on the shop floor? | Cutting, Edge Banding, CNC/Drilling, Assembly, Finishing, Packing (`A3`) | Medium — affects grouping in every report |
| Q5 | What are the **standard output rates** per machine per item (or item family)? This is the single most important input to automated planning | Derived plausible rates per machine type (`A5`) | **High** — this *is* the capacity matrix. Plans are only as good as these numbers. A CSV import template is provided so the customer can fill it in directly |
| Q6 | What **unit of measure** is production reported in — pieces, sq. ft., running metres? Does it differ by department? | Units (pieces), with UoM per product (`A6`) | Medium — Odoo handles multiple UoMs, but reports must agree on one for totals |
| Q7 | How many **items / SKUs** are in active production? Are they grouped into families? | ~20 representative items in 4 families (`A7`) | Low — masters are imported |

## A.2 — Needed before Phase 4 (Daily Tracking & Terminal)

| # | Question | Assumed meanwhile | Impact if different |
|---|---|---|---|
| Q8 | Please share a **sample of the actual "DAY WISE OUTPUT" Excel file** (a real month, with headers intact) | A representative layout modelled on the requirements (`A12`) | **High** — the importer is built to a column map. A real sample means it works first time instead of needing rework |
| Q9 | How much **historical Excel data** should be migrated, and from when? | Last 12 months, if available (`A13`) | Medium — determines whether trend charts are useful at go-live or only after months of use |
| Q10 | Who physically **enters production data**, and when? Operator during the shift, or supervisor at shift end? | Operator during shift, supervisor approves at shift end (`A14`) | **High** — determines whether the terminal is the primary surface or a secondary one |
| Q11 | Will **tablets or terminals be available on the shop floor**? How many, and is there reliable Wi-Fi? | One shared tablet per department, intermittent Wi-Fi assumed (`A15`) | **High** — drives the offline-tolerance design. We are building for unreliable Wi-Fi regardless, which is the safe direction |
| Q12 | Do operators get **individual logins**, or is a shared machine account with a PIN acceptable? | Individual Odoo logins, no PIN (`A16`, revised in Phase 4) | Low now — a PIN layer can still be added on top of individual logins later if the plant wants shared-tablet handover; nothing in the terminal design blocks it |
| Q13 | Is **rejection / rework quantity** currently recorded? At what stage? | Captured per production entry (`A17`) | Medium — needed for the Quality factor of OEE. Without it, OEE overstates |

## A.3 — Needed before Phase 5 & 7 (Downtime, Maintenance)

| # | Question | Assumed meanwhile | Impact if different |
|---|---|---|---|
| Q14 | Please **confirm or correct the downtime reason list**. The requirements name nine; are there others the supervisors use? | The nine from the brief, plus Changeover and Other (`A18`) | Low — reasons are configuration records |
| Q15 | What is the **minimum downtime worth logging**? Is a 3-minute stoppage recorded? | 5 minutes (`A19`) | Low — a threshold setting |
| Q16 | Are there **existing preventive maintenance schedules**? What intervals, per machine type? | Monthly PM, quarterly major service, per machine type (`A20`) | Medium — real intervals matter for compliance reporting |
| Q17 | Is there a **maintenance team structure**? In-house, contracted, or both? | One in-house team (`A21`) | Low |
| Q18 | Should **spare parts and maintenance cost** be tracked? | Cost field present but optional (`A22`) | Low — the field exists either way |

## A.4 — Needed before Phase 8, 9, 11 (Manpower, Backlog, Alerts)

| # | Question | Assumed meanwhile | Impact if different |
|---|---|---|---|
| Q19 | How is the **operator roster** currently planned, and by whom? | Supervisor plans weekly, adjusts daily (`A23`) | Medium |
| Q20 | Is there an **existing attendance / biometric system** we should read from? | No; manpower is entered per shift (`A24`) | Medium — an integration would remove double entry. Worth asking early |
| Q21 | What is the **standard manpower** per machine? | Per machine type in the capacity matrix (`A25`) | Medium |
| Q22 | When is an order considered **delayed** — past the promised date, or past an internal buffer? | Past `date_deadline`, no buffer (`A26`) | Medium — changes what the Backlog Report flags |
| Q23 | What are the real **blocking reasons** for orders? | Material, machine, manpower, quality, customer hold, other (`A27`) | Low |
| Q24 | What **alert thresholds** are meaningful? At what point does a manager want to be told? | Industry defaults (`A28`–`A33`) | Medium — thresholds are tunable records. Wrong ones cause alert fatigue, which is the main reason alert systems get ignored |
| Q25 | **Who should receive which alerts**, and through which channel — in-app, email, or both? | In-app for all; email for critical only (`A34`) | Low |
| Q26 | Are there **quiet hours**, or should night-shift alerts reach managers immediately? | Critical alerts always; others queue to 08:00 (`A35`) | Low |

## A.5 — Needed before Phase 12, 13, 15 (Reports, Portal, Deployment)

| # | Question | Assumed meanwhile | Impact if different |
|---|---|---|---|
| Q27 | **Who receives which report**, at what time, in what format? | Defaults in `A36` | Low — schedules are records |
| Q28 | Are there **existing report formats** management is attached to? Please share samples | Our own clean layout (`A37`) | Medium — matching a familiar layout speeds adoption significantly |
| Q29 | Should **customers really get portal access** at go-live, or is that a later phase for the business? | Built in Phase 13, enabled at the customer's discretion (`A38`) | Low — it is a switch |
| Q30 | What should a customer **be allowed to see** — order progress only, or expected dates too? | Progress %, status and expected completion; no internal data (`A39`) | Medium |
| Q31 | What is the **server** the system will run on? Spec, OS, who administers it? | 8-core / 16 GB / 250 GB SSD, Ubuntu 22.04 (`A40`) | Medium |
| Q32 | Is there an **SMTP server / email account** the system may send from? | Required at Phase 11; a placeholder until then (`A41`) | **High at Phase 11** — no email means no scheduled reports and no email alerts |
| Q33 | What is the customer's **backup policy and off-site storage**? | Nightly, 30/12/3 retention, off-server copy (`A42`) | Medium |
| Q34 | How many **users** of each role? | 30 internal, 10 tablets, portal customers TBD (`A43`) | Low |
| Q35 | Is the system **internet-facing** or LAN-only? | LAN-only, TLS via internal CA (`A44`) | Medium — changes the security posture and certificate approach |

## A.6 — ERP 10.8 (deferred, but ask early — lead time is long)

| # | Question | Why ask now |
|---|---|---|
| Q36 | What **product is "ERP 10.8"** — vendor and full name? | "10.8" is a version, not a product. We cannot scope anything without the name |
| Q37 | Does it expose an **API** (REST / SOAP), a database view, or only file export? | Determines the adapter type and the entire integration estimate |
| Q38 | Can we get **API documentation and a sandbox instance**? | This is the gating prerequisite. The 7.5-week estimate in `09-erp-integration-roadmap.md` is not meaningful without it |
| Q39 | Who is the **technical contact** on the ERP side? | Integration projects stall on this more than on anything technical |
| Q40 | Which system is the **master** for the item list — ERP or MES? | Decides conflict-resolution direction before any data flows |

These six should go to the manager now even though the work is deferred, because
obtaining sandbox access and a named contact typically takes longer than building
the connector.

---

# Part B — Assumptions Register

Every assumption below is implemented as configuration, not code. The "Where it
lives" column names the record or field to change.

## B.1 Plant, Calendar & Shifts

| ID | Assumption | Basis | Where it lives |
|---|---|---|---|
| `A1` | Three 8-hour shifts: **A 06:00–14:00, B 14:00–22:00, C 22:00–06:00**, each with a 30-minute break → **7.5 net hours** | The standard three-shift pattern in Indian discrete manufacturing | `fmes.shift` records (`demo/`) |
| `A2` | Six-day week, **Sunday weekly off**; public holidays configurable | Standard for the sector | `resource.calendar` |
| `A3` | Six departments: **Cutting · Edge Banding · CNC / Drilling · Assembly · Finishing · Packing** | The conventional panel-furniture production sequence | `hr.department` records |
| `A44` | LAN-only deployment; no internet exposure at go-live | Typical for a single-plant on-prem MES | Deployment config |

## B.2 Machines & Capacity

| ID | Assumption | Basis | Where it lives |
|---|---|---|---|
| `A4` | **15 machines** across the six departments: panel saw ×2, beam saw, edge bander ×2, CNC router ×2, multi-boring, assembly line ×2, hot press, sander, spray booth ×2, packing station | A representative small-to-mid furnishing plant | `mrp.workcenter` (`demo/`) |
| `A5` | Standard output rates assigned per machine type and product family, with a 0.85 efficiency factor on older machines | Plausible rates for the machine classes above; **explicitly flagged for customer correction** | `fmes.capacity.matrix` |
| `A6` | Production reported in **units (pieces)**, with each product carrying its own UoM | Simplest consistent basis; Odoo supports per-product UoM natively | `product.uom_id` |
| `A7` | ~20 items in 4 families (wardrobe, kitchen unit, office desk, bed) | Enough variety to exercise the capacity matrix meaningfully | `product.template` (`demo/`) |
| `A25` | Standard manpower defined per machine type — 1 for automated, 2–3 for assembly and finishing | Conventional staffing for the machine classes | `fmes.capacity.matrix.std_manpower` |
| `A49` | Every machine is treated as fully staffed until the roster exists (Phase 8). The planning engine applies a manpower factor of 1.0 | Matches how the plant plans today; a half-real constraint against a model that does not exist yet would be worse than an honest placeholder | `fmes.planning.engine._get_manpower_factor` |
| `A8` | One machine may run several items; one item may run on several machines, with a preference order | Standard flexible-routing assumption | `fmes.capacity.matrix.priority` |
| `A9` | Changeover time applies when a machine switches product: **15 min** default, 30 min for finishing | Standard setup-time modelling | `fmes.capacity.matrix.changeover_minutes` |
| `A10` | Machine availability derated by **planned maintenance windows and 90-day historical unplanned downtime** | Standard finite-capacity practice — planning on 100% availability is the most common cause of unachievable plans | Planning engine |
| `A11` | Plans generated **weekly, rolling**, with daily re-planning available | Common MES planning cadence | `fmes.production.plan.plan_type` |

## B.3 Data Capture

| ID | Assumption | Basis | Where it lives |
|---|---|---|---|
| `A12` | The DAY WISE OUTPUT importer uses a **configurable column map**, not a fixed layout | Guarantees the importer adapts to the real file rather than requiring rework | `wizards/production_import.py` |
| `A13` | 12 months of history migrated if available | Enough for year-on-year trend at go-live | Import batch |
| `A14` | Operator enters output during the shift; **supervisor approves at shift end** | Standard two-step MES control — capture at source, verify before it becomes reportable | `fmes.production.entry.state` |
| `A15` | Shop-floor Wi-Fi is **assumed unreliable**; the terminal queues writes and retries | Designing for the worse case costs little and cannot backfire | Terminal OWL component |
| `A16` | **Revised in Phase 4.** Operators authenticate with a normal individual Odoo login, no PIN. Machine scoping is done separately via `res.users.fmes_workcenter_ids` | A PIN is a second authentication mechanism to build and secure; individual logins give a stronger audit trail (`fmes.production.entry.create_uid`/`submitted_by` are then meaningful) and Odoo's own login is already fast on a saved/kiosk browser. If the plant insists on shared-tablet handover, a PIN can be layered on top without changing the terminal | Terminal auth (`controllers/shopfloor.py`) |
| `A17` | **Rejected quantity captured per entry**, feeding the Quality factor of OEE | Without it OEE is overstated and meaningless | `fmes.production.entry.rejected_qty` |
| `A19` | Minimum loggable downtime **5 minutes** | Below this, logging costs more than the data is worth | Config parameter |

## B.4 Downtime & Maintenance

| ID | Assumption | Basis | Where it lives |
|---|---|---|---|
| `A18` | Downtime taxonomy = the nine reasons in the brief **plus Changeover and Other**; each classified `planned` or `unplanned` | The brief's list is already close to standard TPM loss categories | `mrp.workcenter.productivity.loss` |
| `A20` | Preventive maintenance: **monthly routine, quarterly major**, per machine type; raised **7 days** before due | Common interval structure for this machine class | `fmes.maintenance.schedule` |
| `A21` | One in-house maintenance team | Simplest structure; more teams are just more records | `maintenance.team` |
| `A22` | Maintenance cost tracked but optional | Present without forcing data entry the customer may not have | `maintenance.request.fmes_cost` |

## B.5 Targets & Thresholds

These are the numbers that decide when someone gets told something. They are the
most likely to need tuning, and the easiest to tune.

| ID | Assumption | Basis | Where it lives |
|---|---|---|---|
| `A28` | **OEE target 75 %** | The Nakajima world-class benchmark is 85 % (90 × 95 × 99.9); typical discrete manufacturing runs near 60 %. 75 % is a realistic first-year target for a plant introducing an MES — a target nobody can hit is a target everyone ignores | `mrp.workcenter.oee_target` |
| `A29` | **Achievement target 95 %** of daily plan | Standard plan-adherence expectation | Alert rule |
| `A30` | Machine flagged **under-utilised below 60 %** | Consistent with typical baseline OEE | Alert rule / dashboard |
| `A31` | **Excess downtime** alert at > 60 min unplanned in one shift, or > 10 % of shift time | Roughly one-eighth of a shift — material enough to warrant a look | Alert rule |
| `A32` | **Critical backlog** at > 15 days aged, or an order > 7 days past deadline | Conventional ageing buckets | Alert rule |
| `A33` | **Maintenance due** alert 7 days ahead; overdue alert on the due date | Gives a week to schedule around production | Alert rule |
| `A34` | In-app alerts for all; **email for critical only** | Prevents alert fatigue, the main reason alert systems get switched off | `fmes.alert.rule` channels |
| `A35` | Critical alerts sent immediately at any hour; others queue to **08:00** | Respects night shift without suppressing genuine emergencies | Alert rule |
| `A45` | Alert **cooldown 60 minutes** per rule per subject | Prevents one stuck machine generating a hundred alerts | `fmes.alert.rule.cooldown_minutes` |
| `A26` | An order is **delayed** when past `date_deadline`, with no internal buffer | The strictest reading; a buffer can be added but not retroactively removed | Backlog service |
| `A27` | Blocking reasons: material · machine · manpower · quality · customer hold · other | Covers the standard causes | `fmes.backlog.snapshot.block_reason` |

## B.6 Reporting & Users

| ID | Assumption | Basis | Where it lives |
|---|---|---|---|
| `A36` | Default schedules: **Daily Production 07:00 daily** · **Downtime Monday 08:00** · **Backlog 18:00 daily** · **Monthly MIS 1st at 09:00** | Reports arrive before the decisions they inform — the morning report lands before the morning meeting | `fmes.report.schedule` |
| `A37` | Our own clean report layout until customer samples arrive | Neutral and professional; matching their existing format later is a template edit | QWeb layout |
| `A38` | Customer portal **built but disabled** until the business decides to expose it | Ready when wanted, invisible until then | Portal group assignment |
| `A39` | Customers see progress %, status and expected completion — **never** machine, cost, downtime or other customers' data | Standard customer-portal boundary | Portal record rules |
| `A41` | SMTP configured via environment; a console backend until real credentials arrive | Development proceeds; nothing is silently lost | `.env` / `ir.mail_server` |
| `A43` | 30 internal users, 10 tablets, portal customers TBD | Sizes the worker configuration | `odoo.conf` |
| `A42` | Nightly backup; **30 daily / 12 monthly / 3 yearly** retention, copied off-server | Conventional and defensible | `scripts/backup.sh` |
| `A46` | **3 years** of online data retention | Matches the trend-analysis requirement | No purge cron |

## B.7 Language & Locale

| ID | Assumption | Basis | Where it lives |
|---|---|---|---|
| `A47` | English UI; Indian date format (DD/MM/YYYY), IST timezone, INR currency | The brief is in English; the plant context is Indian | `res.company`, `res.lang` |
| `A48` | Multi-company structure **provisioned but unused** — one plant at go-live | Costs nothing now; a second plant later needs no refactor | `company_id` on every model |

---

# Part C — How to Use This Document

**For the manager / customer conversation.** Part A is ordered by deadline. The
highest-value asks, in order, are:

1. **Q5** — standard output rates (the capacity matrix). Nothing about automated
   planning is better than this input
2. **Q8** — a real DAY WISE OUTPUT sample
3. **Q3 / Q4** — the real machine and department list
4. **Q36–Q40** — the ERP questions, because their lead time is the longest
5. **Q32** — SMTP access, needed by Phase 11

Import templates for Q1, Q3, Q4, Q5, Q6 and Q7 are **available now** in
[`templates/`](templates/), so the customer can answer by filling in a
spreadsheet rather than writing prose. Column headers are Odoo field names, so
the files import directly with no mapping step.

**For the build.** No phase is blocked. Every assumption is a record. When an
answer arrives:

1. Update the row in Part B with the confirmed value, and strike the question in Part A
2. Change the configuration record — not the code
3. Note it in `MEMORY.md` under the current phase
4. If it invalidates a design decision, update the affected doc in the same commit

**Review cadence.** This document is reviewed at the start of every phase. Any
assumption that turned out wrong is corrected before the phase that depends on it.
