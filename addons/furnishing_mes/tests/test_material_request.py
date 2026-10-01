# -*- coding: utf-8 -*-
"""Material request (Requirement 6): a supervisor reviewing a downtime
report can request more materials, which needs Plant Manager approval —
the same draft-then-approve shape as downtime review itself, just with the
Plant Manager as the approver instead of the Supervisor.
"""

from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import FmesTestCase


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase6')
class TestMaterialRequestApproval(FmesTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.operator = cls._create_user(
            'fmes_matreq_op', 'furnishing_mes.group_fmes_operator')
        cls.supervisor = cls._create_user(
            'fmes_matreq_sup', 'furnishing_mes.group_fmes_supervisor')
        cls.manager = cls._create_user(
            'fmes_matreq_mgr', 'furnishing_mes.group_fmes_manager')

    def _create_request(self, user):
        return self.env['fmes.material.request'].with_user(user).create({
            'product_id': self.product_wardrobe.id,
            'qty_requested': 20.0,
        })

    def test_supervisor_can_create_a_request(self):
        request = self._create_request(self.supervisor)
        self.assertEqual(request.state, 'new')

    def test_operator_cannot_create_a_request(self):
        with self.assertRaises(AccessError):
            self._create_request(self.operator)

    def test_supervisor_cannot_approve(self):
        request = self._create_request(self.supervisor)
        with self.assertRaises(AccessError):
            request.with_user(self.supervisor).action_approve()

    def test_manager_can_approve(self):
        request = self._create_request(self.supervisor)
        request.with_user(self.manager).action_approve()
        self.assertEqual(request.state, 'approved')
        self.assertEqual(request.approved_by, self.manager)
        self.assertTrue(request.approved_on)

    def test_manager_can_reject(self):
        request = self._create_request(self.supervisor)
        request.with_user(self.manager).action_reject()
        self.assertEqual(request.state, 'rejected')

    def test_workcenter_follows_the_linked_downtime_event(self):
        event = self.env['mrp.workcenter.productivity'].create({
            'workcenter_id': self.wc_saw.id,
            'loss_id': self.env.ref('mrp.block_reason1').id,
        })
        request = self.env['fmes.material.request'].with_user(
            self.supervisor).create({
                'product_id': self.product_wardrobe.id,
                'qty_requested': 5.0,
                'downtime_event_id': event.id,
            })
        self.assertEqual(request.workcenter_id, self.wc_saw)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase10')
class TestMaterialRequestAlert(FmesTestCase):
    """Event-driven alert (Requirement 10) — same base_automation +
    fmes.alert.engine._on_event pattern as new_order_received."""

    def test_material_request_event_raises_an_alert(self):
        rule = self.env.ref('furnishing_mes.alert_rule_material_request_raised')
        request = self.env['fmes.material.request'].create({
            'product_id': self.product_wardrobe.id,
            'qty_requested': 15.0,
        })
        alert = self.env['fmes.alert'].search([
            ('rule_id', '=', rule.id), ('res_model', '=', 'fmes.material.request'),
            ('res_id', '=', request.id)])
        self.assertTrue(alert)
