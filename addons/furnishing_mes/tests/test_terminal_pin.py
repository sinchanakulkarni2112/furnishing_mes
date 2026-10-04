# -*- coding: utf-8 -*-
"""The shop-floor terminal's PIN gate, over real HTTP.

What this file exists to protect: on a shared tablet the gate is an
*operator switch* on top of the Odoo login the tablet already holds — the
shared account stays logged in, and a successful PIN entry switches which
employee the terminal is recording for. That switch must (a) accept any
active employee's PIN, (b) carry the switched employee id/name back to the
tablet, (c) never leak a stored PIN, and (d) stay bounded by the attempt
lockout. Those properties are what the tests below assert, over HTTP,
because that is where a shared-tablet bug would actually live.
"""

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import HttpCase, tagged

ROUTE = '/fmes/terminal/pin_verify'
MACHINES_ROUTE = '/fmes/terminal/machines'

# Every response — ok or not — carries this key set. Success adds the
# switched operator's employee_id / employee_name / user_id on top.
BASE_KEYS = {'ok', 'provisioned', 'pin_provisioned', 'locked',
             'remaining_attempts', 'error'}
OK_KEYS = BASE_KEYS | {'employee_id', 'employee_name', 'user_id'}


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase15')
class TestTerminalPinGate(HttpCase):
    """`/fmes/terminal/pin_verify` as an operator, over a logged-in session."""

    def setUp(self):
        super().setUp()
        self.operator = self.env['res.users'].create({
            'name': 'PIN Terminal Operator',
            'login': 'fmes_pin_terminal_op',
            'password': 'fmes_pin_terminal_op',
            'groups_id': [(6, 0, [
                self.env.ref('furnishing_mes.group_fmes_operator').id])],
        })
        self.employee = self.env['hr.employee'].create({
            'name': 'PIN Terminal Operator',
            'pin': '4417',
            'user_id': self.operator.id,
        })
        self.colleague = self.env['hr.employee'].create({
            'name': 'PIN Terminal Colleague',
            'pin': '9134',
        })
        self.authenticate('fmes_pin_terminal_op', 'fmes_pin_terminal_op')
        # Every successful verification clears the attempt counter, so
        # calling it once here gives each test a known-clean session instead
        # of inheriting whatever the previous test failed. It also leaves the
        # session switched to the operator's OWN employee, which is the
        # pre-switch baseline every test assumes.
        self.assertTrue(self.verify('4417')['ok'])

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def verify(self, pin):
        return self.make_jsonrpc_request(ROUTE, {'pin': pin})

    def machines(self):
        return self.make_jsonrpc_request(MACHINES_ROUTE, {})

    def _json_payload(self, params):
        import json
        return json.dumps({
            'jsonrpc': '2.0', 'method': 'call', 'id': 1, 'params': params})

    # ------------------------------------------------------------------
    # the happy path
    # ------------------------------------------------------------------
    def test_own_employee_pin_is_accepted(self):
        result = self.verify('4417')
        self.assertTrue(result['ok'], result.get('error'))
        self.assertTrue(result['provisioned'])
        self.assertTrue(result['pin_provisioned'])
        self.assertFalse(result['locked'])
        self.assertEqual(result['employee_id'], self.employee.id)
        self.assertEqual(result['employee_name'], self.employee.name)
        self.assertEqual(result['user_id'], self.operator.id)

    def test_the_user_pin_is_a_passthrough_of_the_employee_pin(self):
        # `hr` defines res.users.pin as related='employee_id.pin', so there
        # is exactly one stored PIN and the user field is only a view of it.
        # Locking that down here is what stops a future "add a second PIN
        # source" change from silently widening who can satisfy the gate.
        self.assertEqual(
            self.operator._fields['pin'].related, 'employee_id.pin')
        self.operator.pin = '7702'
        self.assertEqual(self.employee.pin, '7702')
        result = self.verify('7702')
        self.assertTrue(result['ok'], result.get('error'))

    def test_a_supervisor_may_set_the_pin_from_the_user_form(self):
        self.operator.pin = '3325'
        self.assertEqual(self.employee.pin, '3325')
        self.assertTrue(self.verify('3325')['ok'])
        self.assertFalse(self.verify('4417')['ok'])

    # ------------------------------------------------------------------
    # the security property: a signed-in operator may switch operators
    # ------------------------------------------------------------------
    def test_pin_verify_switches_active_operator_on_shared_tablet(self):
        # The whole point of the gate. A colleague's PIN switches the
        # tablet's active operator without logging the session out, and the
        # answer carries who the tablet is now recording for.
        other = self.env['res.users'].create({
            'name': 'PIN Terminal Worker 2',
            'login': 'fmes_pin_terminal_worker2',
            'password': 'fmes_pin_terminal_worker2',
            'groups_id': [(6, 0, [
                self.env.ref('furnishing_mes.group_fmes_operator').id])],
        })
        other_emp = self.env['hr.employee'].create({
            'name': 'PIN Terminal Worker 2',
            'pin': '1234',
            'user_id': other.id,
        })
        result = self.verify('1234')
        self.assertTrue(result['ok'], result.get('error'))
        self.assertEqual(result['employee_id'], other_emp.id)
        self.assertEqual(result['employee_name'], other_emp.name)
        self.assertEqual(result['user_id'], other.id)
        # The switch sticks server-side: the machine picker now reads as the
        # switched operator, not the Odoo login that held the session.
        machines = self.machines()
        self.assertEqual(machines['user'], other_emp.name)

    def test_a_stranger_pin_is_refused(self):
        self.assertFalse(self.verify('0000')['ok'])

    def test_surrounding_whitespace_does_not_block_a_valid_pin(self):
        result = self.verify('  4417  ')
        self.assertTrue(result['ok'], result.get('error'))

    def test_an_empty_pin_is_refused(self):
        self.assertFalse(self.verify('')['ok'])
        self.assertFalse(self.verify(None)['ok'])
        self.assertFalse(self.verify('   ')['ok'])

    def test_an_unprovisioned_plant_is_told_so(self):
        # With NO active employee carrying a PIN there is nothing to compare
        # against, so nothing was verified. ok stays False — the route must
        # never claim a check it did not perform — and the tablet decides to
        # carry on with a visible notice instead.
        self.employee.pin = False
        self.colleague.pin = False
        result = self.verify('4417')
        self.assertFalse(result['ok'])
        self.assertFalse(result['provisioned'])
        self.assertFalse(result['pin_provisioned'])
        self.assertIn('No PIN is set', result['error'])

    def test_ok_is_never_true_without_a_real_comparison(self):
        # The invariant any future caller depends on: ok=True implies a PIN
        # was actually compared against a provisioned profile.
        self.employee.pin = False
        self.colleague.pin = False
        for pin in ('', '  ', '0000', '4417', '9134', 'x' * 500):
            result = self.verify(pin)
            self.assertFalse(result['ok'],
                             "answered %r for %r" % (result, pin))
            self.assertFalse(result['provisioned'])

    def test_an_unprovisioned_plant_is_not_locked_out(self):
        # There is no secret to guess, so the attempt counter must not
        # creep toward a lockout and brick the terminal for the shift.
        self.employee.pin = False
        self.colleague.pin = False
        for _ in range(8):
            self.assertFalse(self.verify('0000')['ok'])
        self.employee.pin = '4417'
        self.colleague.pin = '9134'
        self.assertTrue(self.verify('4417')['ok'])

    def test_a_non_digit_pin_is_refused_by_odoo_itself(self):
        # hr validates the stored value as digits-only. Worth pinning: it is
        # Odoo's constraint, not ours, and it is what makes the 5-attempt
        # lockout meaningful (a 4-6 digit space is ~10^4 at worst).
        with self.assertRaises(ValidationError):
            self.employee.pin = 'abcd'
        with self.assertRaises(ValidationError):
            self.employee.pin = '12 34'

    # ------------------------------------------------------------------
    # the PIN never leaves the server
    # ------------------------------------------------------------------
    def test_the_response_never_echoes_the_stored_pin(self):
        result = self.verify('4417')
        serialised = repr(result)
        self.assertNotIn('4417', serialised)
        # The response DOES carry the switched operator's name now — that is
        # what tells the tablet whose screen is showing — but never a PIN,
        # and never a name the PIN did not match.
        self.assertEqual(result['employee_name'], self.employee.name)
        self.assertNotIn(self.colleague.name, serialised)

    def test_an_operator_cannot_read_the_pin_through_the_orm(self):
        # Documents *why* the route needs sudo(): the native field is
        # group-restricted, so the comparison happens with elevated read
        # rights and the value stays on the server.
        with self.assertRaises(AccessError):
            self.employee.with_user(self.operator).read(['pin'])

    def test_an_operator_cannot_read_a_colleagues_pin(self):
        # The related res.users.pin passthrough does NOT deny an operator
        # their own PIN, but res.users record rules must still stop them
        # reading anyone else's -- otherwise the field is a shared secret.
        self.assertEqual(
            self.operator.with_user(self.operator).read(['pin'])[0]['pin'],
            '4417')
        other = self.env['res.users'].create({
            'name': 'PIN Terminal Colleague User',
            'login': 'fmes_pin_terminal_other',
            'password': 'fmes_pin_terminal_other',
            'groups_id': [(6, 0, [
                self.env.ref('furnishing_mes.group_fmes_operator').id])],
            'employee_id': self.colleague.id,
        })
        with self.assertRaises(AccessError):
            other.with_user(self.operator).read(['pin'])

    # ------------------------------------------------------------------
    # response shape
    # ------------------------------------------------------------------
    def test_every_answer_has_the_same_keys(self):
        # A client branching on the response must not have to guess whether
        # a missing key means False or "not checked": the same key set on
        # every failure, and the operator's identity tacked on success.
        cases = [
            {},                                   # no pin at all
            {'pin': ''},                          # nothing typed
            {'pin': '0000'},                      # wrong
            {'pin': '9134'},                      # a match — switched
        ]
        for payload in cases:
            result = self.make_jsonrpc_request(ROUTE, payload)
            ok = result['ok']
            expected = OK_KEYS if ok else BASE_KEYS
            self.assertEqual(set(result), expected,
                             "unexpected shape for %r" % (payload,))
            self.assertIsInstance(result['ok'], bool)
            self.assertIsInstance(result['provisioned'], bool)
            self.assertIsInstance(result['pin_provisioned'], bool)
            self.assertIsInstance(result['locked'], bool)
            self.assertIsInstance(result['remaining_attempts'], int)

    # ------------------------------------------------------------------
    # guessing is bounded
    # ------------------------------------------------------------------
    def test_repeated_wrong_pins_eventually_lock_the_gate(self):
        for _ in range(5):
            result = self.verify('0000')
            self.assertFalse(result['ok'])
            self.assertTrue(result['remaining_attempts'] >= 0)
        # Correct PIN, still refused: a locked gate stays locked, so a
        # four-digit space cannot be walked one guess at a time.
        locked = self.verify('4417')
        self.assertFalse(locked['ok'])
        self.assertTrue(locked['locked'])
        self.assertEqual(locked['remaining_attempts'], 0)
        self.assertIn('Too many', locked['error'])

    def test_wrong_pins_report_remaining_attempts(self):
        self.assertEqual(self.verify('0000')['remaining_attempts'], 4)
        self.assertEqual(self.verify('0000')['remaining_attempts'], 3)

    def test_a_fresh_login_starts_from_a_clean_slate(self):
        for _ in range(5):
            self.verify('0000')
        self.authenticate('fmes_pin_terminal_op', 'fmes_pin_terminal_op')
        self.assertTrue(self.verify('4417')['ok'])

    # ------------------------------------------------------------------
    # authentication is still required
    # ------------------------------------------------------------------
    def test_the_route_requires_a_login(self):
        self.logout()
        response = self.url_open(
            ROUTE,
            data=self._json_payload({'pin': '4417'}),
            headers={'Content-Type': 'application/json'},
            timeout=60)
        self.assertIn('error', response.text)