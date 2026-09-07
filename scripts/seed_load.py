# -*- coding: utf-8 -*-
"""Performance dataset generator (Phase 14, docs/06-build-plan.md deliverable 4).

Run inside the running container, against the DEV database only:

    docker compose run --rm web odoo shell -d furnishing_mes < scripts/seed_load.py

Produces the volumes docs/10-testing-qa.md section 6 names — ~100,000
`fmes.production.entry` rows, ~50,000 `mrp.workcenter.productivity`
(downtime) rows, ~40,000 `fmes.backlog.snapshot` rows, ~5,000
`maintenance.request` rows — via bulk `INSERT ... SELECT` against the
demo/fixture master data (workcenters, shifts, products) already in the
database, not the ORM's own `create()`. At six-figure row counts, ORM
`create()` (per-record validation, computed fields, mail-thread tracking)
would take on the order of hours; a set-based SQL insert does the same
job in seconds, which is the entire point of this script — it exists ONLY
to give the dashboard/report timing benchmarks a realistic volume to run
against, never to be run against a real plant's database, and never
mistaken for a fixture real business logic should be tested against
(`tests/common.py`'s own small, deterministic plant remains that).

Every derived column this script fills in (`achievement_pct`, `ok_qty`,
`variance_qty`, `efficiency_pct`, `utilization_pct`, downtime `duration`)
uses the exact same formula the model's own compute methods use — see the
comments inline — so a dashboard tile or report figure computed FROM this
data is a genuine, meaningful number, not noise; only the values feeding
those formulas are synthetic, not the arithmetic itself.

Idempotent: running it twice does not double the data — it deletes any
prior synthetic rows (identified by `note`/`description` markers this
script itself writes) before regenerating.
"""

import logging
import random
from datetime import date, timedelta

_logger = logging.getLogger('seed_load')

MARKER = 'seed_load synthetic row'

TARGET_ENTRIES = 100_000
TARGET_DOWNTIME = 50_000
TARGET_BACKLOG = 40_000
TARGET_MAINTENANCE = 5_000

random.seed(42)  # reproducible volumes/distributions run to run

company = env.company
workcenters = env['mrp.workcenter'].search([('company_id', 'in', (company.id, False))])
shifts = env['fmes.shift'].search([('company_id', 'in', (company.id, False))])
products = env['product.product'].search(
    [('type', '!=', 'service'), ('categ_id', '!=', False)], limit=50)
departments = env['hr.department'].search([('company_id', '=', company.id)])
equipment = env['maintenance.equipment'].search(
    [('company_id', 'in', (company.id, False))])
teams = env['maintenance.team'].search([('company_id', 'in', (company.id, False))])

if not (workcenters and shifts and products and equipment and teams):
    raise RuntimeError(
        'Master data missing (workcenters/shifts/products/equipment/'
        'maintenance teams). Install with demo data first: '
        '`docker compose run --rm web odoo -d furnishing_mes -i furnishing_mes`')

cr = env.cr

_logger.info('Clearing any previous synthetic rows...')
cr.execute("DELETE FROM fmes_production_entry WHERE note = %s", (MARKER,))
cr.execute("DELETE FROM mrp_workcenter_productivity WHERE description = %s", (MARKER,))
cr.execute("DELETE FROM fmes_backlog_snapshot WHERE block_note = %s", (MARKER,))
cr.execute("DELETE FROM maintenance_request WHERE name = %s", ('Seed load synthetic request',))

wc_ids = workcenters.ids
shift_ids = shifts.ids
product_ids = products.ids
dept_by_wc = {wc.id: wc.department_id.id or None for wc in workcenters}
company_id = company.id
admin_uid = env.uid


def daterange(n_days, end=None):
    end = end or date.today()
    return [end - timedelta(days=i) for i in range(n_days)]


# ======================================================================
# 1. Production entries (~100k): date x shift x workcenter, one product
#    per slot, spread across ~3 years so week/month/year trend tiles have
#    something real to aggregate.
# ======================================================================
_logger.info('Generating ~%s production entries...', TARGET_ENTRIES)
n_days = max(1, TARGET_ENTRIES // max(1, len(shift_ids) * len(wc_ids)))
days = daterange(n_days)

rows = []
seq = 1
for day in days:
    for shift_id in shift_ids:
        for wc_id in wc_ids:
            product_id = random.choice(product_ids)
            planned = round(random.uniform(50, 400), 2)
            # A realistic achievement spread: mostly close to target, a
            # long tail of bad shifts, matching what the alert thresholds
            # (A29, 95%) are meant to actually catch some of.
            achievement_fraction = min(1.35, max(0.10, random.gauss(0.92, 0.15)))
            actual = round(planned * achievement_fraction, 2)
            rejected = round(actual * random.uniform(0, 0.05), 2)
            ok_qty = round(actual - rejected, 2)
            run_hours = round(random.uniform(4, 7.5), 2)
            downtime_hours = round(random.uniform(0, 2.5), 2)
            available_hours = round(run_hours + downtime_hours, 2)
            std_manpower = round(random.uniform(1, 4), 2)
            actual_manpower = round(
                std_manpower * random.uniform(0.7, 1.1), 2)
            rows.append((
                'PE/SEED/%07d' % seq, 'approved', day, shift_id, wc_id,
                dept_by_wc.get(wc_id), product_id, planned, actual,
                rejected, ok_qty, actual - planned, planned, True,
                run_hours, downtime_hours, available_hours, std_manpower,
                actual_manpower, company_id, admin_uid, MARKER,
            ))
            seq += 1

_logger.info('Inserting %s production entry rows...', len(rows))
cr.executemany(
    """
    INSERT INTO fmes_production_entry (
        name, state, date, shift_id, workcenter_id, department_id,
        product_id, planned_qty, actual_qty, rejected_qty, ok_qty,
        variance_qty, std_output_qty, has_target, run_hours,
        downtime_hours, available_hours, std_manpower, actual_manpower,
        company_id, create_uid, write_uid, create_date, write_date, note,
        achievement_pct, efficiency_pct, utilization_pct
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
        %s, %s, %s, %s, %s, %s, now(), now(), %s,
        CASE WHEN %s > 0 THEN %s / %s * 100.0 ELSE 0 END,
        CASE WHEN %s > 0 THEN %s / %s * 100.0 ELSE 0 END,
        CASE WHEN %s > 0 THEN %s / %s * 100.0 ELSE 0 END
    )
    """,
    [
        (r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9],
         r[10], r[11], r[12], r[13], r[14], r[15], r[16], r[17], r[18],
         r[19], r[20], r[20], r[21],
         r[7], r[8], r[7],       # achievement_pct = actual/planned*100
         r[12], r[8], r[12],     # efficiency_pct = actual/std_output*100
         r[16], r[14], r[16])    # utilization_pct = run/available*100
        for r in rows
    ],
)
env.cr.commit()
_logger.info('Production entries done.')

# ======================================================================
# 2. Downtime events (~50k): unplanned-weighted loss reasons, duration in
#    minutes matching (date_end - date_start) exactly, so the report's
#    own SUM(duration) and a hand check against the timestamps agree.
# ======================================================================
_logger.info('Generating ~%s downtime events...', TARGET_DOWNTIME)
loss_reasons = env['mrp.workcenter.productivity.loss'].search(
    [('loss_type', '!=', 'productive')])
if not loss_reasons:
    raise RuntimeError('No non-productive loss reasons found.')
loss_ids = loss_reasons.ids

n_events = TARGET_DOWNTIME
event_days = daterange(n_days)
rows = []
for _i in range(n_events):
    day = random.choice(event_days)
    shift_id = random.choice(shift_ids)
    wc_id = random.choice(wc_ids)
    loss_id = random.choice(loss_ids)
    start_hour = random.uniform(0, 22)
    duration_minutes = round(random.uniform(5, 90), 2)
    date_start = f"{day.isoformat()} {int(start_hour):02d}:{int((start_hour % 1) * 60):02d}:00"
    rows.append((
        wc_id, company_id, loss_id, date_start, duration_minutes,
        shift_id, company_id, MARKER,
    ))

_logger.info('Inserting %s downtime rows...', len(rows))
cr.executemany(
    """
    INSERT INTO mrp_workcenter_productivity (
        workcenter_id, company_id, loss_id, loss_type,
        date_start, date_end, duration, fmes_shift_id, fmes_state,
        create_uid, write_uid, create_date, write_date, description
    )
    SELECT %s, %s, %s, l.loss_type,
           %s::timestamp,
           %s::timestamp + make_interval(secs => %s),
           %s, %s, 'approved',
           %s, %s, now(), now(), %s
    FROM mrp_workcenter_productivity_loss l WHERE l.id = %s
    """,
    [
        # duration (r[4]) is stored in MINUTES, matching the native
        # mrp.workcenter.productivity field (confirmed against this
        # module's own SQL views, e.g. downtime_report.py's
        # `SUM(p.duration) / 60.0 AS downtime_hours`); the interval added
        # to date_start needs SECONDS, hence r[4] * 60 only for that one.
        (r[0], r[1], r[2], r[3], r[3], r[4] * 60, r[4], r[5],
         admin_uid, admin_uid, r[7], r[2])
        for r in rows
    ],
)
env.cr.commit()
_logger.info('Downtime events done.')

# ======================================================================
# 3. Backlog snapshots (~40k): plain fields only (Phase 9's own "photo,
#    not a live view" model) -- every value written directly, no derived
#    column to get wrong.
# ======================================================================
_logger.info('Generating ~%s backlog snapshots...', TARGET_BACKLOG)
snapshot_days = daterange(max(1, TARGET_BACKLOG // 200))
statuses = ['pending', 'blocked', 'delayed', 'at_risk', 'completed']
rows = []
per_day = max(1, TARGET_BACKLOG // max(1, len(snapshot_days)))
for day in snapshot_days:
    for _i in range(per_day):
        product_id = random.choice(product_ids)
        dept_id = random.choice(departments.ids) if departments else None
        wc_id = random.choice(wc_ids)
        ordered = round(random.uniform(20, 500), 2)
        produced = round(ordered * random.uniform(0, 1), 2)
        pending = round(max(ordered - produced, 0), 2)
        days_delayed = random.choice([0, 0, 0, 1, 3, 8, 16, 25])
        status = random.choice(statuses)
        is_critical = days_delayed > 15
        deadline = day + timedelta(days=random.randint(-20, 20))
        rows.append((
            day, product_id, dept_id, wc_id, ordered, produced, pending,
            round(produced / ordered * 100.0 if ordered else 0, 2),
            deadline, days_delayed, status, is_critical, company_id,
            MARKER,
        ))

_logger.info('Inserting %s backlog snapshot rows...', len(rows))
cr.executemany(
    """
    INSERT INTO fmes_backlog_snapshot (
        snapshot_date, product_id, department_id, workcenter_id,
        ordered_qty, produced_qty, pending_qty, completion_pct,
        date_deadline, days_delayed, status, is_critical, company_id,
        create_uid, write_uid, create_date, write_date, block_note
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
        %s, %s, now(), now(), %s
    )
    """,
    [r[:13] + (admin_uid, admin_uid, r[13]) for r in rows],
)
env.cr.commit()
_logger.info('Backlog snapshots done.')

# ======================================================================
# 4. Maintenance requests (~5k): spread across the last ~2 years.
# ======================================================================
_logger.info('Generating ~%s maintenance requests...', TARGET_MAINTENANCE)
stage = env['maintenance.stage'].search([], limit=1)
maintenance_days = daterange(730)
rows = []
for i in range(TARGET_MAINTENANCE):
    eq = random.choice(equipment.ids)
    team = random.choice(teams.ids)
    req_date = random.choice(maintenance_days)
    mtype = random.choice(['preventive', 'corrective'])
    closed = random.random() < 0.85
    close_date = req_date + timedelta(days=random.randint(0, 10)) if closed else None
    cost = round(random.uniform(200, 5000), 2) if random.random() < 0.6 else None
    rows.append((
        'Seed load synthetic request', company_id, eq, team, stage.id,
        mtype, req_date, close_date, cost, admin_uid, admin_uid,
    ))

_logger.info('Inserting %s maintenance request rows...', len(rows))
cr.executemany(
    """
    INSERT INTO maintenance_request (
        name, company_id, equipment_id, maintenance_team_id, stage_id,
        maintenance_type, request_date, close_date, fmes_cost,
        create_uid, write_uid, create_date, write_date, kanban_state
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now(), 'normal')
    """,
    rows,
)
env.cr.commit()
_logger.info('Maintenance requests done.')

_logger.info('Seed load complete. Refreshing SQL-view-dependent stats...')
cr.execute('ANALYZE fmes_production_entry, mrp_workcenter_productivity, '
          'fmes_backlog_snapshot, maintenance_request')
env.cr.commit()
_logger.info('Done.')
