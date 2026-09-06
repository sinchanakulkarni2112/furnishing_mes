# 14 — Glossary

## Manufacturing & MES Terms

| Term | Meaning |
|---|---|
| **MES** | Manufacturing Execution System. Sits between planning (ERP) and the machines; tracks what is actually produced, when, on what, by whom |
| **Work center** | A machine or station where an operation is performed. Odoo model `mrp.workcenter`. In this project, "machine" and "work center" are the same thing |
| **Work order** | One operation of a manufacturing order at one work center. `mrp.workorder` |
| **Manufacturing order (MO)** | An instruction to produce a quantity of an item. `mrp.production` |
| **BOM** | Bill of Materials — the components and operations needed to make an item |
| **Routing** | The ordered sequence of operations, each at a work center |
| **Capacity matrix** | The standard output rate of each machine for each item. The basis of automated planning (Requirement 1.2) |
| **Standard output** | The expected quantity a machine should produce per hour or per shift for a given item, under normal conditions |
| **Shift** | A defined working period (A 06:00–14:00, B 14:00–22:00, C 22:00–06:00) |
| **Changeover** | Setup time lost when a machine switches from one product to another |
| **Bottleneck** | The machine whose capacity constrains the whole line's throughput |
| **Backlog** | Ordered quantity not yet produced |
| **Carry forward** | Quantity planned for a day but not produced, rolled into the next day's plan |
| **Blocked order** | An order that cannot proceed — missing material, machine down, awaiting customer |
| **Downtime** | Time a machine was available to run but did not |
| **Planned downtime** | Scheduled stoppage (maintenance, changeover). Excluded from availability loss |
| **Unplanned downtime** | Unscheduled stoppage (breakdown, power failure, material shortage) |
| **Loss reason** | The coded cause of downtime. `mrp.workcenter.productivity.loss` |
| **Manpower deployment** | How many operators are actually assigned and present, versus the standard requirement |

## Performance Metrics

| Term | Meaning |
|---|---|
| **OEE** | Overall Equipment Effectiveness = Availability × Performance × Quality. The standard measure of how well a machine is really used |
| **Availability** | Share of planned production time the machine was actually running |
| **Performance** | Actual output as a share of what the standard rate would have produced in the run time |
| **Quality** | Good units as a share of total units produced |
| **Utilisation %** | Run hours ÷ available hours. Simpler than OEE — it ignores speed and quality |
| **Capacity utilisation %** | Planned load ÷ available capacity. A planning metric, not an execution one |
| **Achievement %** | Actual output ÷ planned output |
| **Efficiency %** | Actual output ÷ standard output |
| **Productivity** | Good units per manpower-hour |
| **MTBF** | Mean Time Between Failures — how long a machine typically runs before breaking |
| **MTTR** | Mean Time To Repair — how long a repair typically takes |
| **PM compliance %** | Preventive maintenance jobs completed on time ÷ jobs due |
| **MIS** | Management Information System. Here, the monthly management report pack |

## Odoo Terms

| Term | Meaning |
|---|---|
| **Addon / module** | A packaged unit of Odoo functionality. Ours is `furnishing_mes` |
| **Model** | A Python class backed by a database table. Roughly, a domain entity |
| **ORM** | Odoo's Object-Relational Mapper — the API for defining and querying models |
| **View** | An XML definition of how a model is displayed: list, form, kanban, pivot, graph, calendar, search |
| **Record rule** (`ir.rule`) | A row-level filter automatically applied to a group's queries. Real access control |
| **ACL** (`ir.model.access`) | Model-level create/read/write/delete permissions per group |
| **`res.groups`** | A security group. Membership grants ACLs and record rules |
| **`implied_ids`** | Group inheritance — holding a group implies holding the groups it implies |
| **Portal user** | An external user (a customer) with access only to `/my`, never the backoffice |
| **Internal user** | An employee with backoffice access, subject to their groups |
| **Chatter** | The message and activity thread on a record, from `mail.thread`. Our audit trail |
| **Tracking** | Field-level change logging into the chatter (`tracking=True`) |
| **`ir.cron`** | A scheduled action. Odoo's built-in job scheduler — why this project needs no Celery |
| **OWL** | Odoo Web Library, the frontend framework (version 2 in Odoo 18). Used for our three custom screens |
| **QWeb** | Odoo's XML templating engine, used for PDF reports and portal pages |
| **Client action** | A full-screen custom UI registered as an action — how the terminal, board and dashboard are delivered |
| **`_auto = False`** | A model backed by a SQL view rather than a table. Used for all report models |
| **Wizard** (`TransientModel`) | A short-lived model used for dialogs, like the plan generator |
| **Demo data** | Sample records loaded only when demo mode is on. Never present in production |
| **Developer mode** | Odoo's debug mode, exposing the Technical menu |
| **Filestore** | Where Odoo stores attachments on disk, separate from the database. Must be backed up together with it |
| **Community / Enterprise** | Odoo's two editions. This project targets Community — see [`13-odoo-edition-constraints.md`](13-odoo-edition-constraints.md) |

## Project Terms

| Term | Meaning |
|---|---|
| **`fmes`** | The project's namespace prefix — Furnishing MES |
| **Phase** | One increment of the build plan, ending in a commit and push |
| **ERP 10.8** | The customer's existing ERP. Integration is deferred; the seam is designed |
| **Integration seam** | The dormant fields and adapter interface that let ERP integration be added later without touching the domain model |
| **Read model** | A SQL-view model built for reporting, never written to by the application |
| **Mock ERP data** | Demo records standing in for what ERP 10.8 will eventually supply |
| **DAY WISE OUTPUT** | The customer's existing Excel workbook, and the format the XLSX importer targets |
