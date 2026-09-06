# 05 — UI / UX Design

The customer asked for a system that is genuinely nice to use, not just correct.
In Odoo that means three things: a well-organised menu tree, views that answer a
question at a glance, and purpose-built OWL screens where a stock Odoo view would
be the wrong tool.

---

## 1. Design Principles

| # | Principle | In practice |
|---|---|---|
| U1 | **The shop floor is not an office** | The terminal is touch-first: large targets (min 48 px), high contrast, no dropdown hunting, no horizontal scrolling. Readable at arm's length on a wall-mounted tablet. |
| U2 | **One screen, one question** | Every view has a job. The machine kanban answers "what is running right now"; the variance list answers "where did we miss target". Neither tries to do both. |
| U3 | **Colour carries meaning, consistently** | Green = on/above target, amber = at risk, red = below target or blocked, grey = idle, blue = planned/informational. The same five colours mean the same thing everywhere. |
| U4 | **Numbers come with context** | Never a bare figure. Achievement shows target alongside actual and the variance. Utilisation shows the hours behind the percentage. |
| U5 | **Drill-through everywhere** | Every KPI tile and chart segment opens the records behind it. A manager who distrusts a number can reach the raw rows in two clicks. |
| U6 | **Stay native where native is good** | Odoo's list, pivot, graph and search views are excellent and familiar. Custom OWL is reserved for the terminal, the scheduling board and the executive dashboard, where stock views genuinely fall short. |
| U7 | **Accessible by default** | Contrast ratio at least 4.5:1, never colour alone to convey state (always paired with an icon or label), full keyboard navigation in the backoffice. |

---

## 2. Menu Structure

Root application menu: **Furnishing MES** (custom icon, `sequence=10`).

```
Furnishing MES
├── Dashboard                       (Supervisor+)
│   ├── Executive Dashboard
│   └── Live Production Status
├── Planning                        (Supervisor+)
│   ├── Production Plans
│   ├── Scheduling Board
│   ├── Generate Plan               (wizard)
│   └── Carry Forward Lines
├── Production                      (Operator sees only Shop Floor Terminal)
│   ├── Shop Floor Terminal
│   ├── Production Entries
│   ├── Approval Queue              (Supervisor+)
│   ├── Planned vs Actual
│   └── Import Daily Output         (wizard, Supervisor+)
├── Downtime
│   ├── Downtime Events
│   ├── Approval Queue              (Supervisor+)
│   └── Loss Analysis               (Supervisor+)
├── Maintenance
│   ├── Equipment
│   ├── Preventive Schedules
│   ├── Maintenance Requests
│   └── Maintenance Calendar
├── Manpower                        (Supervisor+)
│   ├── Operator Allocation
│   ├── Roster Planning
│   └── Manpower Logs
├── Backlog                         (Supervisor+)
│   ├── Backlog Overview
│   ├── Blocked Orders
│   └── Delayed Orders
├── Alerts
│   ├── Alert Center
│   └── Alert Rules                 (Manager only)
├── Reports                         (Supervisor+)
│   ├── Daily Production
│   ├── Machine Utilisation
│   ├── Downtime
│   ├── Backlog & Carry Forward
│   ├── Maintenance
│   ├── Productivity
│   ├── Exceptions
│   └── Monthly MIS
└── Configuration                   (Manager only)
    ├── Shifts
    ├── Machines / Work Centers
    ├── Capacity Matrix
    ├── Departments
    ├── Downtime Reasons
    ├── Report Schedules
    └── Settings
```

Operators see only **Production → Shop Floor Terminal**. Menu visibility uses
`groups=`, but the real enforcement is the ACLs and record rules in
[`04-security-model.md`](04-security-model.md).

---

## 3. Custom OWL Components

Three screens are built as OWL 2 client actions. Everything else uses native views.

### 3.1 Shop-Floor Terminal — `fmes_shopfloor_terminal` *(Phase 4)*

Full-screen, chrome-free, tablet-first.

```
┌────────────────────────────────────────────────────────────┐
│  CNC PANEL SAW 01        Shift A · 06:00–14:00    ● RUNNING │
├────────────────────────────────────────────────────────────┤
│                                                            │
│   TARGET              PRODUCED            ACHIEVEMENT      │
│     450                 312                   69 %         │
│    units               units             ▓▓▓▓▓▓▓░░░        │
│                                                            │
├────────────────────────────────────────────────────────────┤
│  CURRENT WORK ORDER                                        │
│  WH/MO/00042 · Oak Wardrobe Side Panel · 150 units         │
│  Elapsed 01:47:22                                          │
│                                                            │
│  ┌──────────┐  ┌──────────┐  ┌───────────────┐             │
│  │  PAUSE   │  │  RECORD  │  │ LOG DOWNTIME  │             │
│  │          │  │  OUTPUT  │  │               │             │
│  └──────────┘  └──────────┘  └───────────────┘             │
├────────────────────────────────────────────────────────────┤
│  UP NEXT   WH/MO/00047 · Teak Drawer Front · 200 units     │
├────────────────────────────────────────────────────────────┤
│  Today's downtime: 42 min  ·  3 events        [ SUBMIT ]   │
└────────────────────────────────────────────────────────────┘
```

Behaviour:
- Machine selector on entry, limited to the operator's allocations for today
- Live timer driven client-side, reconciled against the server on every write
- Output entry opens a numeric keypad overlay — no keyboard needed
- Downtime opens a reason grid: large tiles grouped by category, colour-coded,
  free-text remark required for *Other*
- Optimistic UI with a queued retry, so a brief Wi-Fi drop does not lose a
  reading; a persistent banner shows unsynced entries
- Auto-refresh every 30 s via `bus` or polling

### 3.2 Scheduling Board — `fmes_scheduling_board` *(Phase 3)*

The Gantt replacement (ADR-003).

```
             Mon 08      Tue 09      Wed 10      Thu 11
           A  B  C     A  B  C     A  B  C     A  B  C
SAW-01    ███ ███ ▓▓   ███ ███ ░░   ███ ▓▓▓ ░░   ███ ███ ███
EDGE-02   ███ ▓▓▓ ░░   ███ ███ ███  ▒▒▒ ▒▒▒ ░░   ███ ▓▓▓ ░░
DRILL-03  ▓▓▓ ░░░ ░░   ███ ███ ▓▓   ███ ███ ░░   ▓▓▓ ░░░ ░░
                                        ▲
   ███ ≥90% load   ▓▓▓ 60–90%   ░░░ <60%   ▒▒▒ maintenance
```

- Machines on Y, date × shift on X
- Cell colour encodes load against capacity; over-capacity cells get a red border
- Hover shows planned quantity, hours and manpower; click opens the plan lines
- Drag a cell to another machine or shift to reassign, with a live capacity check
  that refuses an infeasible drop and explains why
- Filters: department, product, date range, plan state

### 3.3 Executive Dashboard — `fmes_executive_dashboard` *(Phase 10)*

```
┌───────────────────────────────────────────────────────────────┐
│  Period [This Month ▾]  Department [All ▾]      ⟳ 2 min ago   │
├───────────────────────────────────────────────────────────────┤
│  ACHIEVEMENT  UTILISATION   DOWNTIME    OEE    BACKLOG   PM   │
│    92.4% ▲      78.1% ▼      6.2% ▲    71.3%   1,240    7 due │
├─────────────────────────────────┬─────────────────────────────┤
│  Production Trend (planned vs   │  Downtime Pareto            │
│  actual, daily)                 │  by loss reason             │
├─────────────────────────────────┼─────────────────────────────┤
│  Department Performance         │  Shift Performance          │
├─────────────────────────────────┼─────────────────────────────┤
│  Machine Utilisation ranking    │  Backlog Ageing             │
├─────────────────────────────────┴─────────────────────────────┤
│  Maintenance Performance: MTBF · MTTR · PM compliance         │
└───────────────────────────────────────────────────────────────┘
```

- KPI tiles show value, trend arrow versus the previous period, and target
- Every tile and chart segment drills through to the records
- Supervisor variant is identical but pre-filtered to their departments
- Charts follow one categorical palette, applied consistently across the app

---

## 4. Native View Conventions

| View | Where used | Convention |
|---|---|---|
| **List** | Entries, plan lines, requests | `decoration-danger` below target, `decoration-warning` at risk, `decoration-success` complete. Optional columns hidden by default to keep the default view readable. |
| **Kanban** | Machines, equipment, tickets, alerts | Card shows state colour bar, headline metric, and one action. Grouped by state or department. |
| **Form** | All records | Statusbar top-right, smart buttons for related counts, chatter on every workflow model. Notebook pages rather than long single columns. |
| **Pivot** | All report models | Sensible default row/column grouping so the first render is already useful. |
| **Graph** | Trends and comparisons | Default measure preset; line for trends, bar for comparisons, always with a date axis where time matters. |
| **Calendar** | Maintenance, roster | Colour by type or department. |
| **Search** | All | Named filters for the questions people actually ask ("Below Target", "Blocked", "Overdue PM", "My Department", "This Shift") plus useful group-bys. |

---

## 5. Visual Language

| Token | Value | Meaning |
|---|---|---|
| `--fmes-success` | `#28a745` | On or above target, running, completed |
| `--fmes-warning` | `#f0ad4e` | At risk, approaching threshold |
| `--fmes-danger` | `#dc3545` | Below target, blocked, breakdown, critical alert |
| `--fmes-info` | `#3498db` | Planned, informational |
| `--fmes-idle` | `#95a5a6` | Idle, not started |
| `--fmes-maintenance` | `#9b59b6` | Under maintenance |

State is never conveyed by colour alone — every coloured element also carries an
icon or a text label, for accessibility and for printed reports.

Typography follows Odoo's own scale so the module never looks bolted on. The
terminal overrides only sizing (minimum 18 px body, 48 px touch targets), not the
typeface.

Custom SCSS lives in `static/src/scss/`, split into `fmes_variables.scss`,
`fmes_backend.scss`, `fmes_terminal.scss` and `fmes_portal.scss`. No inline
styles in XML; no `!important` unless overriding Odoo core, and then with a comment.

---

## 6. Responsive Behaviour

| Surface | Target device | Notes |
|---|---|---|
| Shop-Floor Terminal | 10" tablet, landscape | Primary design target; also usable on a 24" wall display |
| Backoffice | Desktop, 1366 px and up | Odoo's own responsive behaviour |
| Executive Dashboard | Desktop and tablet | Tiles reflow from 6 to 3 to 2 columns |
| Customer Portal | Mobile-first | Odoo portal is already responsive; our templates stay within its grid |

---

## 7. Report Layout

All QWeb PDFs share one `fmes_report_layout` template:

- Header: company logo, report title, plant/department, period, generated-on
- Body: summary band of key figures, then the detail table
- Consistent number formatting — quantities to the product's UoM precision,
  percentages to one decimal, hours to two
- Footer: page x of y, and a note when the report is filtered, so a printed page
  is never mistaken for the whole picture
- Print-safe: state is shown as text and shading, never colour alone
