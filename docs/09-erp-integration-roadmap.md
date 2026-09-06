# 09 — ERP 10.8 Integration Roadmap

> **Status: deferred by customer decision.** No connector is built during Phases
> 1–15. This document specifies the seam so the connector can be added later
> **without changing the domain model** — which is the whole point of writing it now.

Requirement 11 of `customer_requirements.txt` asks the MES to exchange data
automatically with ERP 10.8. Until that work is authorised, all upstream master
data is seeded as mock records inside Odoo (Phase 2, `demo/`).

---

## 1. Why Design It Now

Retrofitting external identity onto records that already exist in production is a
data-migration exercise: every manufacturing order, product and partner would
need to be matched to its ERP counterpart by hand. Reserving the columns and the
adapter interface up front costs one mixin and a log model, and eliminates that
migration entirely.

Three things are therefore built during Phase 1 and left dormant:

1. `fmes.erp.sync.mixin` — external id and sync state fields
2. `fmes.sync.log` — an audit trail model, unused until a connector writes to it
3. The `services/integration/` package with an abstract adapter and no implementations

Nothing else in the codebase knows or cares that ERP 10.8 exists.

---

## 2. Data Contract

### 2.1 Inbound — ERP 10.8 to MES

| ERP entity | Odoo target | Key | Direction | Frequency |
|---|---|---|---|---|
| Customer Master | `res.partner` | `erp_external_id` | Inbound only | Daily, or on change |
| Item Master | `product.template` / `product.product` | `erp_external_id` | Inbound only | Daily |
| BOM | `mrp.bom` + `mrp.bom.line` | `erp_external_id` | Inbound only | On change |
| Sales Orders | `sale.order` + `sale.order.line` | `erp_external_id` | Inbound only | Every 15 min |
| Work Orders | `mrp.production` | `erp_external_id` | Inbound, MES may update status | Every 15 min |

Inbound records are **read-mostly in the MES**. Fields owned by the ERP are set
`readonly` in the MES UI once `erp_sync_state = 'synced'`, so a local edit cannot
silently diverge and then be overwritten by the next sync.

### 2.2 Outbound — MES to ERP 10.8

| MES source | ERP entity | Trigger | Frequency |
|---|---|---|---|
| `fmes.production.entry` (approved) | Production output | On approval | Every 15 min, batched |
| `mrp.production.state` | Production completion status | On state change | Every 15 min |
| `fmes.backlog.snapshot` | Order progress | Nightly | Daily |
| `maintenance.request` (closed) | Maintenance information | On close | Daily |

Only **approved** production entries are eligible for outbound sync. Draft and
submitted data never leaves the MES — the ERP must never see a figure the
supervisor has not signed off.

### 2.3 Field mapping (to be completed when ERP access is granted)

The mapping table is deliberately left as a skeleton. It cannot be finalised
without the ERP 10.8 schema, and guessing at it would be worse than leaving it blank.

| ERP field | Odoo field | Transform | Required | Notes |
|---|---|---|---|---|
| *(to be filled)* | | | | |

What must be resolved at that time:
- Unit-of-measure code mapping between the two systems
- Date/timezone convention (ERP local time vs Odoo UTC)
- Numeric precision and rounding rules for quantities
- Partner hierarchy — does ERP model ship-to separately from bill-to?
- Which system owns the item master if both can create items

---

## 3. Architecture

```
        ERP 10.8
           ▲ │
           │ ▼   (REST / SOAP / DB view / file drop — TBD)
  ┌────────────────────────────────────┐
  │  fmes.erp.adapter                  │   concrete transport
  │   implements fmes.integration.     │
  │   adapter (abstract)               │
  └────────────────┬───────────────────┘
                   │
  ┌────────────────▼───────────────────┐
  │  fmes.sync.service                 │
  │   · fetch / push orchestration     │
  │   · mapping + transformation       │
  │   · idempotent upsert by           │
  │     erp_external_id                │
  │   · conflict resolution            │
  │   · error capture + retry          │
  └────────────────┬───────────────────┘
                   │
       ┌───────────┴───────────┐
       ▼                       ▼
  Domain models          fmes.sync.log
  (unchanged)            (audit trail)
```

The domain models are untouched by integration. The adapter is swappable: if ERP
10.8 turns out to expose a REST API, a SOAP endpoint, a read-only database view
or a nightly CSV drop, only the adapter class changes.

### 3.1 `fmes.integration.adapter` — AbstractModel

```python
class IntegrationAdapter(models.AbstractModel):
    _name = 'fmes.integration.adapter'
    _description = 'ERP Integration Adapter Interface'

    def fetch(self, entity, since=None, limit=None):
        """Return a list of dicts of external records for `entity`."""
        raise NotImplementedError

    def push(self, entity, payload):
        """Send `payload` to the ERP. Return an ack dict."""
        raise NotImplementedError

    def test_connection(self):
        """Return (ok: bool, message: str)."""
        raise NotImplementedError
```

### 3.2 Sync mixin — built in Phase 1

Fields per [`03-data-model.md`](03-data-model.md) section 10.1:
`erp_external_id`, `erp_source_system`, `erp_last_sync`, `erp_sync_state`,
`erp_sync_message`.

Mixed into `res.partner`, `product.template`, `mrp.bom`, `sale.order`,
`mrp.production`. `erp_external_id` is indexed and unique per
`(erp_source_system, model)`.

---

## 4. Synchronisation Rules

| Concern | Rule |
|---|---|
| **Idempotency** | Every inbound write is an upsert keyed on `erp_external_id`. Replaying a batch must produce no duplicates. |
| **Ordering** | Masters before transactions: partners → items → BOMs → sales orders → work orders. A batch that arrives out of order is queued, not partially applied. |
| **Atomicity** | One entity batch, one transaction. A failed record marks itself `error` and the batch continues; a failed *batch* rolls back. |
| **Conflict** | ERP wins for ERP-owned fields; MES wins for MES-owned fields (production output, downtime, maintenance). No field is owned by both. |
| **Deletion** | The ERP never deletes through the connector. It marks records inactive; the MES archives rather than unlinks, preserving history. |
| **Retry** | Exponential backoff, capped at 5 attempts, then the record is parked in `error` for human review. |
| **Idle safety** | If the ERP is unreachable, the MES continues to operate on its own data. Integration is never on the critical path of a shift. |
| **Audit** | Every batch writes a `fmes.sync.log` row: direction, entity, counts, duration, outcome. |

---

## 5. Security Considerations

- ERP credentials live in `.env` and are read into `ir.config_parameter` at
  startup, never committed and never displayed in the UI
- Outbound calls use TLS; certificate verification is never disabled
- The ERP service account has the minimum rights required for the listed entities
- Inbound payloads are validated against expected types and ranges before any
  write — an ERP is an external system and its data is untrusted input
- Sync runs as a dedicated technical user, not `admin`, so its actions are
  distinguishable in the audit trail
- Rate limiting and a circuit breaker prevent a misbehaving ERP from exhausting
  Odoo's workers

---

## 6. Delivery Plan (when authorised)

| Stage | Work | Estimate |
|---|---|---|
| I1 | Discovery: obtain ERP 10.8 API/schema docs, credentials, sandbox; complete the field mapping table | 1 week |
| I2 | Adapter implementation and connection test against the sandbox | 1 week |
| I3 | Inbound masters — partners, items, BOMs; reconciliation report | 1.5 weeks |
| I4 | Inbound transactions — sales orders, work orders | 1 week |
| I5 | Outbound — production output, completion status, order progress, maintenance | 1.5 weeks |
| I6 | Monitoring, retry, alerting on sync failure; sync dashboard | 0.5 week |
| I7 | UAT with the customer against real ERP data; cutover plan | 1 week |
| | **Total** | **~7.5 weeks** |

Prerequisite before I1 can start: **ERP 10.8 sandbox access with documented
API and a named technical contact on the customer side.** Without it, the
estimate is not meaningful.

---

## 7. Interim Position

Until then, Phase 2's mock dataset stands in for the ERP. It is deliberately
placed in `demo/` rather than `data/`, so a production install
(`--without-demo=all`) gets none of it, and real master data can be loaded by
import instead. The MES is fully functional on its own data — the integration
adds automation, not capability.
