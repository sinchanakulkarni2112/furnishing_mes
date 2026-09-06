# Documentation Index

Design and delivery documentation for **Furnishing MES** — a Manufacturing
Execution System built as a custom module on Odoo 18 Community.

Start with [`00-project-overview.md`](00-project-overview.md), then
[`06-build-plan.md`](06-build-plan.md).

---

## Reading Order

### Understand the project
| Doc | What it answers |
|---|---|
| [00 — Project Overview](00-project-overview.md) | What are we building, for whom, and why |
| [01 — Requirements Traceability](01-requirements-traceability.md) | How does every customer requirement get delivered |
| [14 — Glossary](14-glossary.md) | What does that term mean |

### Understand the design
| Doc | What it answers |
|---|---|
| [02 — Architecture](02-architecture.md) | How is the system structured, and why those choices (ADRs) |
| [03 — Data Model](03-data-model.md) | What are the models, fields and relations |
| [04 — Security Model](04-security-model.md) | Who can see and do what, and how it is enforced |
| [05 — UI / UX Design](05-ui-ux-design.md) | What does it look like and how does it behave |
| [13 — Odoo Edition Constraints](13-odoo-edition-constraints.md) | What is missing from Community and how we close the gaps |

### Build it
| Doc | What it answers |
|---|---|
| [06 — Build Plan](06-build-plan.md) | **What gets built in which phase** |
| [07 — Development Setup](07-development-setup.md) | How do I run and develop this locally |
| [10 — Testing & QA](10-testing-qa.md) | How do we know it works |
| [12 — Git Workflow](12-git-workflow.md) | How do we commit and push |

### Ship and extend it
| Doc | What it answers |
|---|---|
| [08 — Deployment & Operations](08-deployment-operations.md) | How does it run in the plant |
| [11 — Reporting & Analytics](11-reporting-analytics.md) | What are the reports and how is each metric defined |
| [09 — ERP 10.8 Integration Roadmap](09-erp-integration-roadmap.md) | How will ERP integration be added later |

---

## Quick Answers

| Question | Where |
|---|---|
| How do I run the project? | [Root README](../README.md) |
| What is Phase N? | [06 — Build Plan](06-build-plan.md) |
| Which model holds daily output? | `fmes.production.entry` — [03 — Data Model](03-data-model.md) §4.1 |
| How is a metric calculated? | [11 — Reporting & Analytics](11-reporting-analytics.md) §1 |
| Can an operator see another machine? | No — [04 — Security Model](04-security-model.md) §3.2 |
| Why no React or FastAPI? | Odoo is both backend and frontend — [02 — Architecture](02-architecture.md) §1 |
| Why no Gantt view? | Enterprise-only — [13 — Edition Constraints](13-odoo-edition-constraints.md) §2 |
| When is ERP integration? | Deferred — [09 — ERP Roadmap](09-erp-integration-roadmap.md) |

---

## Document Status

| Doc | Status | Updated at |
|---|---|---|
| 00–14 | Complete | Phase 0 |
| 06 — Build Plan | Living — phase checklist updated each phase | Every phase |
| 01 — Traceability | Living — rows marked as requirements are covered | Every phase |
| 08 — Deployment | Specified now, realised in Phase 15 | Phase 15 |
| 10 — Testing | Living — actual results recorded in Phase 14 | Phase 14 |
