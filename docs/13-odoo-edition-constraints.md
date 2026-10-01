# 13 — Odoo 18 Community: Capability Audit & Constraints

The project targets **Odoo 18.0 Community Edition**. Several capabilities named
in the customer requirements and in the *"Odoo Manufacturing"* solution note are
**Enterprise-only**. This document records what was verified, what the gaps are,
and how each is closed.

**Verification method.** Module presence was checked directly against the
`odoo/odoo` repository on the `18.0` branch — the Community source tree — by
testing for `addons/<module>/__manifest__.py`. This is authoritative; blog posts
and forum answers on this topic contradict each other.

---

## 1. Audit Results

### Available in Community — we build on these

| Module | What it gives us | Used for |
|---|---|---|
| `mrp` | `mrp.bom`, `mrp.production`, `mrp.workcenter`, `mrp.workorder`, `mrp.routing.workcenter`, `mrp.workcenter.productivity`, `mrp.workcenter.productivity.loss`, `mrp.workcenter.capacity` | The entire manufacturing backbone |
| `mrp` — OEE | `mrp.workcenter.oee`, `oee_target`, `time_efficiency`, `_compute_oee()` from productive vs blocked time | Requirement 5 |
| `maintenance` | `maintenance.equipment`, `maintenance.request`, `maintenance.team`, `maintenance.stage`, plus native `mtbf`, `mttr`, `expected_mtbf`, `latest_failure_date`, `estimated_next_failure`, and preventive recurrence (`repeat_interval`, `repeat_unit`, `repeat_until`) | Requirement 7 |
| `hr` | `hr.employee`, `hr.department` | Requirements 3.2, 8 |
| `resource` | `resource.calendar`, working time | Shift capacity |
| `stock`, `product`, `uom` | Inventory, item master, units | Masters |
| `sale_management` | `sale.order` | Mock ERP orders |
| `portal` | Portal users, `portal.mixin`, `/my` | Customer persona |
| `base_automation` | Rule-driven triggers | Requirement 10 |
| `base_import` | CSV/XLSX import | Excel migration |
| `spreadsheet_dashboard` | Management spreadsheets | Requirement 9 |
| `mail` | Chatter, activities, templates, tracking | Audit trail, alerts |
| `mrp_account` | Manufacturing costing | Plant Manager costing view |
| `mrp_subcontracting` | Subcontracted operations | Available if needed |

### Not in Community — gaps we must close

| Enterprise module | What it would have given us | Requirement affected |
|---|---|---|
| `mrp_workorder` | The **Shop Floor app** — tablet work-order terminal | Operator persona, R2.2, R3.5 |
| `web_gantt` | **Gantt views** — timeline scheduling | R1.5, R1.6 scheduling UI |
| `mrp_maintenance` | The **work center ↔ equipment bridge**, and maintenance blocking of work centers | R7.1 |
| `quality_control` | Quality checks and control points | Not requested — out of scope |
| `documents_spreadsheet` | Spreadsheet document management | Not required |

---

## 2. Gap Closures

### G1 — Shop Floor app → custom OWL terminal *(ADR-002, Phase 4)*

**Built instead:** `fmes_shopfloor_terminal`, an OWL client action at
`/fmes/terminal`.

Design in [`05-ui-ux-design.md`](05-ui-ux-design.md) section 3.1.

This is not purely a workaround. The stock Shop Floor app does not capture
downtime reason, manpower and output in a single flow, which is exactly what this
customer's process needs. Building our own gives:

- One screen for output, rejects, downtime and shift submission
- Operator scoping driven by the daily allocation roster
- Optimistic writes with retry, tolerant of shop-floor Wi-Fi
- A layout tuned to a wall-mounted 10" tablet

**Cost:** roughly 3–4 days of OWL work, and we own its maintenance.

### G2 — Gantt views → custom scheduling board *(ADR-003, Phase 3)*

**Built instead:** `fmes_scheduling_board`, an OWL grid of machines × date-shift
cells, colour-coded by load, with drag-to-reassign and a live capacity check.

**Why not an OCA backport.** Community Gantt substitutes exist, but taking a
third-party dependency for a core screen means inheriting its 18.0 compatibility
risk and its upgrade timeline. A purpose-built board is roughly the same effort,
has no external dependency, and shows exactly what a planner needs — load against
capacity — which a generic Gantt does not.

**Cost:** roughly 3 days.

### G3 — `mrp_maintenance` bridge → implemented directly *(Phase 2)*

**Built instead:** `mrp.workcenter.equipment_id` ↔
`maintenance.equipment.workcenter_id`, kept consistent in both directions, plus:

- Maintenance windows derate machine availability in the planning engine (Phase 3)
- A downtime event flagged `fmes_requires_maintenance` auto-raises a
  `maintenance.request` against the linked equipment (Phase 5)
- Equipment health feeds the machine kanban state (Phase 7)

This is a small amount of code and gives tighter integration than the Enterprise
bridge, because the linkage is designed around this plant's workflow.

**Cost:** under a day.

### G4 — Quality control

Not in the customer requirements. `rejected_qty` on the production entry captures
what is needed for the quality factor of OEE. If formal quality control is
requested later, it is a new phase, not a retrofit — `fmes.production.entry`
already carries the reject data a quality module would build on.

---

## 3. Other Community Considerations

| Area | Community position | Our approach |
|---|---|---|
| **Studio** | Enterprise only | All customisation is code in `furnishing_mes` — which is better practice anyway: reviewable, testable, version-controlled |
| **Odoo.sh hosting** | Enterprise only | Self-hosted Docker on-prem, as agreed |
| **Odoo support contract** | Enterprise only | Community edition, self-supported; the customer owns the code |
| **Automated upgrade service** | Enterprise only | Manual upgrade runbook in [`08-deployment-operations.md`](08-deployment-operations.md) |
| **IoT Box** | Enterprise only | Not required — data capture is manual plus Excel import, by agreement |
| **Mobile app** | Enterprise only | The terminal and portal are responsive web; a tablet browser in kiosk mode is the shop-floor client |
| **Field Service, Helpdesk, PLM, Sign** | Enterprise only | Not in scope. Support tickets use a lightweight `fmes.support.ticket` model (Phase 13) rather than Helpdesk |

---

## 4. Licensing

- Odoo 18 Community is **LGPL-3**
- `furnishing_mes` is declared **LGPL-3** in its manifest, consistent with the
  platform, and may be distributed freely
- No Enterprise code, module or asset is copied into this project
- The official `odoo:18.0` Docker image is Community and is used unmodified

---

## 5. Risk and Mitigation Summary

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| E1 | Custom terminal is less polished than the Enterprise app | Medium | Medium | Tablet-first design brief, operator UAT each phase, iterate on real feedback |
| E2 | Scheduling board lacks Gantt features planners expect | Medium | Medium | Board is scoped to load-vs-capacity, the actual planning question. Manual override always available |
| E3 | An Odoo 18.x point release changes an extended core model | Low | Medium | Extensions are additive only; upgrade rehearsed on staging first |
| E4 | Customer later buys Enterprise, duplicating our custom screens | Low | Low | Our models extend native ones, so Enterprise modules could be installed alongside; the custom screens would simply be retired |
| E5 | Missing quality module blocks a future requirement | Low | Low | Reject data is already captured; a quality phase can be added cleanly |

---

## 6. Verification Record

| Checked | Result | Date |
|---|---|---|
| `addons/mrp` in `odoo/odoo@18.0` | Present | 2026-09-06 |
| `addons/maintenance` | Present | 2026-09-06 |
| `addons/mrp_workorder` | **Absent** (Enterprise) | 2026-09-06 |
| `addons/web_gantt` | **Absent** (Enterprise) | 2026-09-06 |
| `addons/mrp_maintenance` | **Absent** (Enterprise) | 2026-09-06 |
| `addons/quality_control` | **Absent** (Enterprise) | 2026-09-06 |
| `addons/spreadsheet_dashboard` | Present | 2026-09-06 |
| `addons/portal`, `base_automation`, `base_import`, `hr`, `resource`, `sale_management` | Present | 2026-09-06 |
| `mrp.workcenter` has `oee`, `oee_target`, `time_efficiency` | Confirmed in source | 2026-09-06 |
| `maintenance.equipment` has `mtbf`, `mttr`, `expected_mtbf`, `estimated_next_failure` | Confirmed in source | 2026-09-06 |

Re-verify this table if the project ever moves to a different Odoo version.
