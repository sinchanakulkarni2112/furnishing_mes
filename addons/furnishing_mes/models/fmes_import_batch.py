# -*- coding: utf-8 -*-
"""Import batches.

Every spreadsheet import is recorded as a batch, and a batch can be reversed as
a unit. Migrating a year of the customer's DAY WISE OUTPUT workbook is exactly
the kind of operation that goes wrong once before it goes right, and being able
to undo it cleanly is what makes the first attempt safe to try.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class FmesImportBatch(models.Model):
    _name = 'fmes.import.batch'
    _description = 'Production Data Import Batch'
    _order = 'create_date desc, id desc'

    name = fields.Char(
        required=True, copy=False, readonly=True, default=lambda self: _('New'))
    source_filename = fields.Char(string='File', readonly=True)
    imported_by = fields.Many2one(
        'res.users', readonly=True, default=lambda self: self.env.user)
    imported_on = fields.Datetime(
        readonly=True, default=fields.Datetime.now)

    entry_ids = fields.One2many(
        'fmes.production.entry', 'import_batch_id', string='Entries',
        readonly=True)
    entry_count = fields.Integer(compute='_compute_stats', store=True)
    row_count = fields.Integer(
        string='Rows Read', readonly=True,
        help="Data rows found in the file, including any that were skipped.")
    skipped_count = fields.Integer(
        string='Rows Skipped', readonly=True,
        help="Rows that could not be imported. The reasons are in the log.")

    date_from = fields.Date(compute='_compute_stats', store=True)
    date_to = fields.Date(compute='_compute_stats', store=True)
    total_actual_qty = fields.Float(
        compute='_compute_stats', store=True,
        digits='Product Unit of Measure', string='Total Produced')

    state = fields.Selection(
        [('imported', 'Imported'), ('reverted', 'Reverted')],
        default='imported', required=True, readonly=True)
    log = fields.Text(readonly=True, help="Row-level notes and skip reasons.")
    company_id = fields.Many2one(
        'res.company', required=True, index=True,
        default=lambda self: self.env.company)

    @api.depends('entry_ids', 'entry_ids.actual_qty', 'entry_ids.date')
    def _compute_stats(self):
        for batch in self:
            entries = batch.entry_ids
            batch.entry_count = len(entries)
            dates = entries.mapped('date')
            batch.date_from = min(dates) if dates else False
            batch.date_to = max(dates) if dates else False
            batch.total_actual_qty = sum(entries.mapped('actual_qty'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'fmes.import.batch') or _('New')
        return super().create(vals_list)

    def action_revert(self):
        """Delete the entries this batch created.

        Approved entries are left alone: once a supervisor has signed a figure
        off it is part of the record, and an import reversal is not the right
        instrument for retracting it.
        """
        for batch in self:
            if batch.state == 'reverted':
                raise UserError(_("%s has already been reverted.", batch.name))
            approved = batch.entry_ids.filtered(
                lambda e: e.state == 'approved')
            if approved:
                raise UserError(_(
                    "%(count)s of the entries in %(batch)s have been approved "
                    "and cannot be removed by reverting the import. Reopen "
                    "them first if they really need to go.",
                    count=len(approved), batch=batch.name))
            removed = len(batch.entry_ids)
            batch.entry_ids.unlink()
            batch.write({
                'state': 'reverted',
                'log': (batch.log or '') + '\n' + _(
                    "Reverted by %(user)s: %(count)s entries removed.",
                    user=self.env.user.display_name, count=removed),
            })

    def action_open_entries(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Entries: %s', self.name),
            'res_model': 'fmes.production.entry',
            'view_mode': 'list,form',
            'domain': [('import_batch_id', '=', self.id)],
        }
