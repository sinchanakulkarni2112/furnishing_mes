# -*- coding: utf-8 -*-
"""Phase 14: the security test suite (docs/04-security-model.md section 6).

This is a release gate, not an ordinary phase test file: every check here
asserts the expected `AccessError` (or an empty recordset, or an HTTP
redirect) against a user genuinely created in that group — never `sudo()`,
which would bypass the very thing under test.

T8 (database manager blocked by `list_db = False` in production) and T9
(no published PostgreSQL port) are configuration facts about a production
deployment, not runtime behaviour this dev container can meaningfully
assert without contradicting its own intentionally permissive dev
settings (`list_db = True`, per docs/04 section 5.1's own table) — both
are verified instead by reading `docker-compose.yml` and the production
config template, and recorded as such in docs/10-testing-qa.md rather than
forced into a test that would either always pass vacuously or fail against
a setting this project deliberately keeps different in dev.
"""

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged

from .common import FmesTestCase


class SecurityCase(FmesTestCase):
    """A pair of users per role, scoped exactly the way a real plant would
    scope them, so "another work center" / "another department" mean
    something concrete rather than an untested hypothetical."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.operator = cls._create_user(
            'sec_operator', 'furnishing_mes.group_fmes_operator')
        cls.operator.fmes_workcenter_ids = [(6, 0, [cls.wc_saw.id])]

        cls.other_operator = cls._create_user(
            'sec_other_operator', 'furnishing_mes.group_fmes_operator')
        cls.other_operator.fmes_workcenter_ids = [(6, 0, [cls.wc_spray.id])]

        cls.supervisor = cls._create_user(
            'sec_supervisor', 'furnishing_mes.group_fmes_supervisor')
        cls.supervisor.fmes_department_ids = [(6, 0, [cls.dept_cutting.id])]

        cls.manager = cls._create_user(
            'sec_manager', 'furnishing_mes.group_fmes_manager')

    def _entry(self, workcenter, **vals):
        base = {
            'date': self.reference_date, 'shift_id': self.shift_a.id,
            'workcenter_id': workcenter.id,
            'product_id': self.product_wardrobe.id, 'planned_qty': 10.0,
            'actual_qty': 8.0,
        }
        base.update(vals)
        return self.env['fmes.production.entry'].create(base)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase14')
class TestT1OperatorOwnWorkcenterOnly(SecurityCase):
    """T1: Operator opens a production entry from another work center by
    URL id -> AccessError."""

    def test_operator_cannot_read_entry_on_an_unallocated_workcenter(self):
        entry = self._entry(self.wc_spray)  # operator is scoped to wc_saw
        with self.assertRaises(AccessError):
            entry.with_user(self.operator).check_access('read')

    def test_operator_can_read_their_own_allocated_workcenter(self):
        entry = self._entry(self.wc_saw)
        entry.with_user(self.operator).check_access('read')  # must not raise

    def test_operator_cannot_write_another_operators_draft_on_a_different_machine(self):
        # Phase 14 audit finding: this specific case used to succeed --
        # the write rule had no workcenter scope at all before this phase.
        # Created AS other_operator (on their own allocated machine) so
        # create_uid is genuinely theirs, not just re-labelled afterwards.
        entry = self.env['fmes.production.entry'].with_user(
            self.other_operator).create({
                'date': self.reference_date, 'shift_id': self.shift_a.id,
                'workcenter_id': self.wc_spray.id,
                'product_id': self.product_wardrobe.id, 'planned_qty': 10.0,
            })
        with self.assertRaises(AccessError):
            entry.with_user(self.operator).write({'actual_qty': 1.0})


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase14')
class TestT2OperatorCannotEditApproved(SecurityCase):
    """T2: Operator edits an approved entry -> AccessError."""

    def test_operator_cannot_write_an_approved_entry(self):
        entry = self._entry(self.wc_saw)
        entry.action_submit()
        entry.action_approve()
        with self.assertRaises(AccessError):
            entry.with_user(self.operator).write({'actual_qty': 5.0})

    def test_operator_can_still_write_their_own_draft(self):
        entry = self._entry(self.wc_saw)
        entry.with_user(self.operator).write({'actual_qty': 3.0})  # must not raise


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase14')
class TestT3SupervisorDepartmentScope(SecurityCase):
    """T3: Supervisor reads a plan(-related record) from another
    department -> empty recordset. Demonstrated on fmes.backlog.snapshot,
    the model docs/04 section 3.4's department-scoping pattern is actually
    implemented on (fmes.production.plan/.line carry no department scope
    at all -- a deliberate, documented choice, not this gap: planning is
    inherently cross-department capacity balancing, see docs/06-build-
    plan.md Phase 14's own audit notes)."""

    def test_supervisor_sees_own_department_snapshot(self):
        snapshot = self.env['fmes.backlog.snapshot'].create({
            'snapshot_date': self.reference_date,
            'product_id': self.product_wardrobe.id,
            'department_id': self.dept_cutting.id,
            'pending_qty': 5.0, 'status': 'pending',
            'company_id': self.company.id,
        })
        found = self.env['fmes.backlog.snapshot'].with_user(
            self.supervisor).search([('id', '=', snapshot.id)])
        self.assertEqual(found, snapshot)

    def test_supervisor_does_not_see_another_departments_snapshot(self):
        snapshot = self.env['fmes.backlog.snapshot'].create({
            'snapshot_date': self.reference_date,
            'product_id': self.product_wardrobe.id,
            'department_id': self.dept_finishing.id,  # not the supervisor's own
            'pending_qty': 5.0, 'status': 'pending',
            'company_id': self.company.id,
        })
        found = self.env['fmes.backlog.snapshot'].with_user(
            self.supervisor).search([('id', '=', snapshot.id)])
        self.assertFalse(found)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase14')
class TestT6FieldLevelRestrictions(SecurityCase):
    """T6: Operator reads mrp.workcenter.costs_hour -> field absent from
    read(). Also covers the two other field-level restrictions this phase
    added (fmes_production_entry.submitted_by, maintenance.request.
    fmes_cost) with the same pattern."""

    def test_costs_hour_absent_for_operator(self):
        # Odoo's field-level groups= restriction has two faces: an
        # unqualified read() silently drops a field the user has no
        # rights to (what T6 literally describes, "field absent from
        # read()" -- exercised on the two simpler models below, which do
        # not cascade into an unrelated model's own ACL the way mrp.
        # workcenter's full field set does); explicitly naming the
        # restricted field in read([...]) instead raises AccessError
        # outright -- the sharper, unambiguous half of the same guarantee,
        # and the one asserted here.
        self.wc_saw.costs_hour = 42.0
        with self.assertRaises(AccessError):
            self.wc_saw.with_user(self.operator).read(['costs_hour'])

    def test_costs_hour_present_for_manager(self):
        self.wc_saw.costs_hour = 42.0
        data = self.wc_saw.with_user(self.manager).read(['costs_hour'])[0]
        self.assertEqual(data['costs_hour'], 42.0)

    def test_submitted_by_absent_for_operator(self):
        entry = self._entry(self.wc_saw)
        entry.action_submit()
        data = entry.with_user(self.operator).read()[0]
        self.assertIn('name', data)
        self.assertNotIn('submitted_by', data)

    def test_maintenance_cost_absent_for_supervisor(self):
        request = self.env['maintenance.request'].create({
            'name': 'Audit request', 'equipment_id': self.equipment_saw.id,
            'fmes_cost': 500.0,
        })
        data = request.with_user(self.supervisor).read()[0]
        self.assertNotIn('fmes_cost', data)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase14')
class TestT7BacklogSnapshotNeverWritable(SecurityCase):
    """T7: Any user writes to fmes.backlog.snapshot -> AccessError, not
    even the Plant Manager (docs/04's own note: this preserves the
    integrity of the trend series -- it is cron-written only)."""

    def _snapshot(self):
        return self.env['fmes.backlog.snapshot'].create({
            'snapshot_date': self.reference_date,
            'product_id': self.product_wardrobe.id,
            'department_id': self.dept_cutting.id,
            'pending_qty': 5.0, 'status': 'pending',
            'company_id': self.company.id,
        })

    def test_supervisor_cannot_write(self):
        snapshot = self._snapshot()
        with self.assertRaises(AccessError):
            snapshot.with_user(self.supervisor).write({'pending_qty': 1.0})

    def test_manager_cannot_write_either(self):
        snapshot = self._snapshot()
        with self.assertRaises(AccessError):
            snapshot.with_user(self.manager).write({'pending_qty': 1.0})


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase14')
class TestT10MultiCompanyIsolation(SecurityCase):
    """T10: Company A user reads Company B records -> empty recordset."""

    def test_company_b_shift_invisible_to_company_a_user(self):
        company_b = self.env['res.company'].create({'name': 'Audit Co B'})
        shift_b = self.env['fmes.shift'].create({
            'name': 'Company B Shift', 'code': 'CB', 'sequence': 10,
            'start_time': 6.0, 'end_time': 14.0, 'break_minutes': 30,
            'company_id': company_b.id,
        })
        company_a_user = self._create_user(
            'sec_company_a', 'furnishing_mes.group_fmes_manager')
        company_a_user.company_ids = [(6, 0, [self.company.id])]
        company_a_user.company_id = self.company.id

        found = self.env['fmes.shift'].with_user(company_a_user).search(
            [('id', '=', shift_b.id)])
        self.assertFalse(found)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase14')
class TestPortalSecurityHttp(HttpCase):
    """T4 and T5, over real HTTP -- an ORM-only test cannot catch a
    controller that forgets to check ownership before rendering (Phase
    13's own D13.3 finding is exactly this class of bug)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_a = cls.env['res.partner'].create({
            'name': 'Sec Portal Customer A', 'is_company': True,
            'customer_rank': 1})
        cls.user_a = cls.env['res.users'].create({
            'name': 'Sec Portal A', 'login': 'sec_portal_a@example.com',
            'email': 'sec_portal_a@example.com', 'password': 'demo12345',
            'partner_id': cls.partner_a.id,
            'groups_id': [(6, 0, [cls.env.ref('base.group_portal').id])],
        })
        cls.partner_b = cls.env['res.partner'].create({
            'name': 'Sec Portal Customer B', 'is_company': True,
            'customer_rank': 1})
        cls.order_b = cls.env['sale.order'].create({
            'partner_id': cls.partner_b.id})

    def test_t4_portal_customer_denied_another_partners_sale_order(self):
        self.authenticate('sec_portal_a@example.com', 'demo12345')
        response = self.url_open('/my/orders/%d' % self.order_b.id)
        # sale's own controller redirects to /my on AccessError/MissingError
        # rather than a bare 404 -- either way, the order's own content
        # must never appear for a customer who does not own it.
        self.assertNotIn(self.order_b.name.encode(), response.content)

    def test_t5_portal_customer_redirected_away_from_the_backend(self):
        self.authenticate('sec_portal_a@example.com', 'demo12345')
        response = self.url_open('/odoo')
        self.assertIn('/my', response.url)

    def test_t5_portal_customer_redirected_from_web_too(self):
        self.authenticate('sec_portal_a@example.com', 'demo12345')
        response = self.url_open('/web')
        self.assertIn('/my', response.url)
