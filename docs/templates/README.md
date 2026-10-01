# Master Data Import Templates

CSV templates for loading the plant's real master data. They exist so the
customer can answer questions **Q1–Q7** in
[`../15-open-questions-and-assumptions.md`](../15-open-questions-and-assumptions.md)
by filling in a spreadsheet rather than writing prose.

Column headers are Odoo field names, so the files import directly through
**Favourites → Import records** on the matching list view, with no column
mapping needed.

---

## Import order

Later files reference earlier ones by name, so load them in sequence.

| # | File | Import into | Answers |
|---|---|---|---|
| 1 | `01_shifts.csv` | Furnishing MES → Configuration → Shifts | Q1 |
| 2 | `02_departments.csv` | Furnishing MES → Configuration → Departments | Q4 |
| 3 | `03_machines.csv` | Furnishing MES → Configuration → Machines | Q3 |
| 4 | `04_products.csv` | Inventory → Products | Q6, Q7 |
| 5 | `05_capacity_matrix.csv` | Furnishing MES → Configuration → Capacity Matrix | **Q5** |

Each file ships with two or three example rows showing the expected format.
Replace them with the real data — do not leave the examples in.

---

## How to import

1. Open the target list view
2. **Favourites → Import records**
3. Upload the CSV, click **Test** first — it validates without writing anything
4. Fix anything it flags, then **Import**

---

## Column notes

### `01_shifts.csv`

| Column | Notes |
|---|---|
| `code` | Short code used in reports. Must be unique |
| `start_time` / `end_time` | Decimal hours on a 24-hour clock: `6.5` is 06:30 |
| `break_minutes` | Deducted from planning capacity |

A shift whose end is earlier than its start is understood as running past
midnight — enter Shift C as `22.0` to `6.0`, not `22.0` to `30.0`.

### `03_machines.csv`

| Column | Notes |
|---|---|
| `department_id` | The department **name**, exactly as imported in step 2 |
| `fmes_criticality` | One of `low`, `medium`, `high`, `critical` |
| `fmes_is_bottleneck` | `1` if this machine constrains overall throughput, else `0` |
| `costs_hour` | Machine hour rate. Leave blank if not tracked |

Machines are Odoo work centers. The maintenance equipment record can be linked
afterwards from the machine form, or created separately and linked from either
side — the two stay in step automatically.

### `05_capacity_matrix.csv` — the important one

This is what makes automated planning possible. One row answers: *on this
machine, for this item, what is the standard output?*

| Column | Notes |
|---|---|
| `workcenter_id` | Machine **name**, as imported in step 3 |
| `product_id` | Product name for an item-specific rate. Leave blank for a category rate |
| `product_category_id` | Category name. Used when no item-specific rate exists |
| `std_output_qty` | The standard output figure |
| `time_basis` | `per_hour`, `per_shift` or `per_day` — quote it however the plant does |
| `basis_hours` | Productive hours in one shift or day. Ignored for `per_hour` |
| `std_manpower` | Operators needed for this machine and item |
| `changeover_minutes` | Setup time lost when switching to this product |
| `priority` | Lower number wins when several machines can make the same item |

**Fill in a category row for every machine and product family first.** That
alone makes planning work. Item-specific rows are only needed where a particular
item runs noticeably faster or slower than its family.

**On rates you are unsure about:** enter the plant's working figure rather than
leaving the row out. A machine with no rate is reported as having no defined
capacity and is skipped by the planner — deliberately, so a missing rate is
visible rather than silently replaced by a guess.

---

## What is loaded before you import anything

Installing with demo data creates a complete mock plant — six departments,
fifteen machines, twenty items, a populated capacity matrix and thirty orders —
so the system can be explored and demonstrated immediately.

None of it is present in a production install. Real data arrives through these
templates.
