# -*- coding: utf-8 -*-
"""Employee ID login (Requirement 1): the doc's own Login screen wording —
a user signs in with a plant-issued ID number, not necessarily their email.
Email stays the account's real identifier ("Forgot password" always sends
there); fmes_employee_id is a second string res.users._get_login_domain
also accepts.
"""

from psycopg2 import IntegrityError

from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import FmesTestCase


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase1')
class TestEmployeeIdLogin(FmesTestCase):

    def test_login_domain_matches_by_employee_id(self):
        user = self._create_user(
            'fmes_login_emp', 'furnishing_mes.group_fmes_operator')
        user.fmes_employee_id = 'EMP-9001'
        found = self.env['res.users'].search(
            self.env['res.users']._get_login_domain('EMP-9001'))
        self.assertEqual(found, user)

    def test_login_domain_still_matches_by_email(self):
        user = self._create_user(
            'fmes_login_mail', 'furnishing_mes.group_fmes_operator')
        found = self.env['res.users'].search(
            self.env['res.users']._get_login_domain(user.login))
        self.assertEqual(found, user)

    def test_employee_id_must_be_unique(self):
        user_a = self._create_user(
            'fmes_login_dup_a', 'furnishing_mes.group_fmes_operator')
        user_a.fmes_employee_id = 'EMP-DUP'
        user_b = self._create_user(
            'fmes_login_dup_b', 'furnishing_mes.group_fmes_operator')
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            user_b.fmes_employee_id = 'EMP-DUP'
            user_b.flush_recordset()

    def test_employee_id_is_optional(self):
        user = self._create_user(
            'fmes_login_blank', 'furnishing_mes.group_fmes_operator')
        self.assertFalse(user.fmes_employee_id)
