# -*- coding: utf-8 -*-
"""ERP 10.8 integration adapter interface (dormant — no implementations).

Completes the third piece of the seam docs/09-erp-integration-roadmap.md
section 1 describes as built in Phase 1: `fmes.erp.sync.mixin` (models/
mixins.py) and `fmes.sync.log` (models/fmes_sync_log.py) existed; this
abstract adapter did not, until Phase 15's own readiness review found the
gap between what that document claimed and what the codebase actually
contained.

A concrete transport (REST, SOAP, a read-only database view, a nightly
file drop — genuinely unknown until ERP 10.8 access is granted, docs/09
section 6) implements this interface by inheriting `fmes.integration.
adapter` and overriding all three methods. `fmes.sync.service`
(docs/09 section 3 — fetch/push orchestration, idempotent upsert by
`erp_external_id`, conflict resolution) is the only intended caller, and
is itself not built until the connector work is authorised. Nothing else
in the codebase depends on this class existing.
"""

from odoo import models


class FmesIntegrationAdapter(models.AbstractModel):
    _name = 'fmes.integration.adapter'
    _description = 'ERP Integration Adapter Interface'

    def fetch(self, entity, since=None, limit=None):
        """Return a list of dicts of external records for `entity`.

        :param str entity: the ERP-side entity name (docs/09 section 2.1's
            "ERP entity" column, e.g. "Customer Master").
        :param since: only records changed since this datetime, or None
            for a full fetch.
        :param int limit: batch size, or None for the adapter's own
            default batching.
        """
        raise NotImplementedError

    def push(self, entity, payload):
        """Send `payload` to the ERP for `entity`. Return an ack dict.

        :param str entity: the ERP-side entity name being written.
        :param list payload: records to push, already mapped to the
            ERP's own field names.
        """
        raise NotImplementedError

    def test_connection(self):
        """Verify connectivity and credentials without side effects.

        :rtype: tuple
        :returns: ``(ok, message)`` — `ok` is a bool, `message` is a
            human-readable diagnostic for the Plant Manager's own
            integration status screen (not yet built).
        """
        raise NotImplementedError
