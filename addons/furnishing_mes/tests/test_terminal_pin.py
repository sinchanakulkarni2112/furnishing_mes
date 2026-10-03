# -*- coding: utf-8 -*-
"""The shop-floor terminal's PIN gate, over real HTTP.

What this file exists to protect: the gate is a *re-authentication* step on
top of the individual Odoo login the tablet already has (assumption A16,
revised in Phase 4). It must never be usable to unlock the terminal as
somebody else, and it must never change who an entry is attributed to. Those
two properties are what the tests below assert, over HTTP, because that is
where a shared-tablet bug would actually live.
"""

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import HttpCase, tagged

ROUTE = '/fmes/terminal/pin_verify'


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
        # of inheriting whatever the previous test failed.
        self.assertTrue(self.verify('4417')['ok'])

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def verify(self, pin):
        return self.make_jsonrpc_request(ROUTE, {'pin': pin})

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
    # the security property: own PIN only
    # ------------------------------------------------------------------
    def test_another_employees_pin_is_refused(self):
        # The whole point. An operator holding someone else's PIN must not
        # be able to satisfy the gate -- otherwise the PIN is decorative and
        # the tablet hands over to the next person without a login.
        result = self.verify('9134')
        self.assertFalse(result['ok'])
        self.assertIn('not right', result['error'])

    def test_a_stranger_pin_is_refused(self):
        self.assertFalse(self.verify('0000')['ok'])

    def test_surrounding_whitespace_does_not_block_a_valid_pin(self):
        result = self.verify('  4417  ')
        self.assertTrue(result['ok'], result.get('error'))

    def test_an_empty_pin_is_refused(self):
        self.assertFalse(self.verify('')['ok'])
        self.assertFalse(self.verify(None)['ok'])
        self.assertFalse(self.verify('   ')['ok'])

    def test_a_configured_but_blank_pin_never_verifies(self):
        # An empty PIN must not compare equal to an empty submission.
        self.employee.pin = False
        self.assertEqual(self.operator.pin, False)
        empty = self.verify('')
        none = self.verify(None)
        self.assertEqual((empty, none),
                         ({'ok': False, 'provisioned': False,
                           'error': 'No PIN is set on your profile yet.'},
                          {'ok': False, 'provisioned': False,
                           'error': 'No PIN is set on your profile yet.'}))
        # ...and with nothing provisioned at all, the route reports the gap
        # rather than pretending the check passed a real secret.
        result = self.verify('4417')
        self.assertFalse(result['ok'])

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
    def test_the_response_never_echoes_the_pin_or_any_employee(self):
        result = self.verify('4417')
        serialised = repr(result)
        self.assertNotIn('4417', serialised)
        self.assertNotIn(self.employee.name, serialised)
        self.assertNotIn(self.colleague.name, serialised)
        # No field of the response may carry the stored PIN back out, and
        # there is nothing else in the payload either.
        self.assertEqual(set(result), {'ok', 'provisioned', 'error'})

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
    # unprovisioned accounts stay usable
    # ------------------------------------------------------------------
    def test_an_unprovisioned_account_is_told_so(self):
        # ok stays False: the route must never claim it verified something
        # it did not. The client is the one that decides to carry on with a
        # visible notice instead of trapping the operator in a keypad that
        # can never succeed.
        self.employee.pin = False
        result = self.verify('4417')
        self.assertFalse(result['ok'])
        self.assertFalse(result['provisioned'])
        self.assertIn('No PIN is set', result['error'])

    def test_ok_is_never_true_without_a_real_comparison(self):
        # The invariant any future caller depends on: ok=True implies a PIN
        # was actually compared.
        self.employee.pin = False
        for pin in ('', '  ', '0000', '4417', '9134', 'x' * 500):
            result = self.verify(pin)
            self.assertFalse(result['ok'],
                             "answered %r for %r" % (result, pin))
            self.assertFalse(result['provisioned'])

    def test_an_unprovisioned_account_is_not_locked_out(self):
        # There is no secret to guess, so the attempt counter must not
        # creep toward a lockout and brick the terminal for the shift.
        self.employee.pin = False
        for _ in range(8):
            self.assertFalse(self.verify('0000')['ok'])
        self.employee.pin = '4417'
        self.assertTrue(self.verify('4417')['ok'])

    def test_every_answer_has_the_same_keys(self):
        # A client branching on `provisioned` must not have to guess whether
        # a missing key means False or "not checked".
        cases = [
            {},                                   # no pin at all
            {'pin': ''},                          # nothing typed
            {'pin': '0000'},                      # wrong
            {'pin': '4417'},                      # right
        ]
        for payload in cases:
            result = self.make_jsonrpc_request(ROUTE, payload)
            self.assertEqual(set(result), {'ok', 'provisioned', 'error'},
                             "unexpected shape for %r" % (payload,))
            self.assertIsInstance(result['ok'], bool)
            self.assertIsInstance(result['provisioned'], bool)

    # ------------------------------------------------------------------
    # guessing is bounded
    # ------------------------------------------------------------------
    def test_repeated_wrong_pins_eventually_lock_the_gate(self):
        for _ in range(5):
            self.assertFalse(self.verify('0000')['ok'])
        # Correct PIN, still refused: a locked gate stays locked, so a
        # four-digit space cannot be walked one guess at a time.
        locked = self.verify('4417')
        self.assertFalse(locked['ok'])
        self.assertIn('Too many', locked['error'])

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
