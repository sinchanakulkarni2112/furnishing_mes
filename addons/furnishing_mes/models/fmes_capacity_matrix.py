# -*- coding: utf-8 -*-
"""Machine capacity matrix.

The heart of Requirement 1.2: what each machine can produce, how fast, and with
how many operators. Automated planning is only ever as good as this table, so it
is modelled explicitly rather than being buried in product or work-center fields.

One row answers: "on this machine, for this item, what is the standard output?"

Resolution order when the planning engine asks for a rate is deliberate and
tested: an exact product row wins, then a product-category row (walking up the
category tree), and otherwise nothing.
"""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Hours assumed per basis when a rate is quoted per shift or per day.
# Derived from assumption A1 (three 8-hour shifts, 30 minutes break each).
DEFAULT_BASIS_HOURS = {
    'per_hour': 1.0,
    'per_shift': 7.5,
    'per_day': 22.5,
}


class FmesCapacityMatrix(models.Model):
    _name = 'fmes.capacity.matrix'
    _description = 'Machine Capacity Matrix'
    _order = 'workcenter_id, priority, product_id, id'
    _check_company_auto = True

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    workcenter_id = fields.Many2one(
        'mrp.workcenter', string='Machine', required=True, index=True,
        ondelete='cascade', check_company=True)
    department_id = fields.Many2one(
        related='workcenter_id.department_id', store=True, readonly=True,
        string='Department')

    product_id = fields.Many2one(
        'product.product', string='Product', index=True,
        domain="[('type', '!=', 'service')]",
        help="Leave empty to define a rate for a whole product category.")
    product_category_id = fields.Many2one(
        'product.category', string='Product Category', index=True,
        help="Used when no rate is defined for the specific product. "
             "Categories are matched up the tree, so a rate on a parent "
             "category covers its children.")
    scope = fields.Selection(
        [('product', 'Specific Product'),
         ('category', 'Product Category')],
        compute='_compute_scope', store=True, index=True,
        help="Whether this row applies to one product or to a whole category.")

    # ------------------------------------------------------------------
    # Standard output
    # ------------------------------------------------------------------
    std_output_qty = fields.Float(
        string='Standard Output', required=True, default=0.0,
        digits='Product Unit of Measure',
        help="Quantity this machine produces of this item in the chosen "
             "time basis, under normal conditions.")
    std_output_uom_id = fields.Many2one(
        'uom.uom', string='Unit',
        help="Unit the standard output is expressed in. Defaults to the "
             "product's own unit of measure.")
    time_basis = fields.Selection(
        [('per_hour', 'Per Hour'),
         ('per_shift', 'Per Shift'),
         ('per_day', 'Per Day')],
        string='Time Basis', required=True, default='per_hour',
        help="Plants usually quote rates per shift or per day. The system "
             "normalises everything to an hourly rate for planning.")
    basis_hours = fields.Float(
        string='Basis Hours', default=1.0, required=True,
        help="Productive hours in one unit of the chosen time basis. Only "
             "used to normalise per-shift and per-day rates.")
    std_output_per_hour = fields.Float(
        string='Standard / Hour', compute='_compute_std_output_per_hour',
        store=True, digits='Product Unit of Measure',
        help="Normalised standard rate. This is what the planning engine reads.")

    efficiency_factor = fields.Float(
        string='Efficiency Factor', default=1.0, required=True,
        groups='furnishing_mes.group_fmes_manager',
        help="Derating for this machine and item, for example 0.85 for an "
             "older machine that does not reach the book rate.")
    effective_output_per_hour = fields.Float(
        string='Effective / Hour', compute='_compute_std_output_per_hour',
        store=True, digits='Product Unit of Measure',
        help="Standard rate after the efficiency factor. Planning uses this "
             "when the factor is not 1.")

    # ------------------------------------------------------------------
    # Resources and setup
    # ------------------------------------------------------------------
    std_manpower = fields.Float(
        string='Standard Manpower', default=1.0,
        help="Operators required to run this machine on this item. Planning "
             "scales capacity down when fewer are rostered.")
    changeover_minutes = fields.Integer(
        string='Changeover (minutes)', default=15,
        help="Setup time lost when the machine switches to this product.")

    # ------------------------------------------------------------------
    # Validity and preference
    # ------------------------------------------------------------------
    date_from = fields.Date(
        string='Valid From',
        help="Leave empty for no start limit.")
    date_to = fields.Date(
        string='Valid To',
        help="Leave empty for no end limit.")
    priority = fields.Integer(
        string='Preference', default=10,
        help="When several machines can make the same item, the lowest "
             "number is preferred.")

    company_id = fields.Many2one(
        'res.company', required=True, index=True,
        default=lambda self: self.env.company)
    active = fields.Boolean(default=True)
    note = fields.Text(string='Notes')

    _sql_constraints = [
        ('fmes_capacity_output_positive',
         'CHECK(std_output_qty > 0)',
         'The standard output must be greater than zero.'),
        ('fmes_capacity_basis_positive',
         'CHECK(basis_hours > 0)',
         'Basis hours must be greater than zero.'),
        ('fmes_capacity_manpower_positive',
         'CHECK(std_manpower >= 0)',
         'Standard manpower cannot be negative.'),
        ('fmes_capacity_changeover_positive',
         'CHECK(changeover_minutes >= 0)',
         'Changeover time cannot be negative.'),
        # Backstop for the Python constraint above: Odoo only validates
        # constraints whose fields appear in the create values, so a row
        # written with neither target would otherwise slip through.
        ('fmes_capacity_target_required',
         'CHECK(product_id IS NOT NULL OR product_category_id IS NOT NULL)',
         'A capacity row must target a product or a product category.'),
    ]

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends('product_id', 'product_category_id')
    def _compute_scope(self):
        for rec in self:
            rec.scope = 'product' if rec.product_id else 'category'

    @api.depends('std_output_qty', 'time_basis', 'basis_hours',
                 'efficiency_factor')
    def _compute_std_output_per_hour(self):
        for rec in self:
            hours = rec.basis_hours or DEFAULT_BASIS_HOURS.get(
                rec.time_basis, 1.0)
            per_hour = rec.std_output_qty / hours if hours else 0.0
            rec.std_output_per_hour = per_hour
            rec.effective_output_per_hour = per_hour * (
                rec.efficiency_factor or 1.0)

    @api.depends('workcenter_id', 'product_id', 'product_category_id')
    def _compute_display_name(self):
        for rec in self:
            target = rec.product_id.display_name or \
                rec.product_category_id.display_name or _('Unspecified')
            rec.display_name = '%s / %s' % (
                rec.workcenter_id.display_name or '', target)

    # ------------------------------------------------------------------
    # Onchanges
    # ------------------------------------------------------------------
    @api.onchange('time_basis')
    def _onchange_time_basis(self):
        """Offer the conventional hours for the chosen basis."""
        for rec in self:
            rec.basis_hours = DEFAULT_BASIS_HOURS.get(rec.time_basis, 1.0)

    @api.onchange('product_id')
    def _onchange_product_id(self):
        for rec in self:
            if rec.product_id:
                rec.product_category_id = rec.product_id.categ_id
                if not rec.std_output_uom_id:
                    rec.std_output_uom_id = rec.product_id.uom_id

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------
    @api.constrains('workcenter_id', 'product_id', 'product_category_id')
    def _check_target_defined(self):
        for rec in self:
            if not rec.product_id and not rec.product_category_id:
                raise ValidationError(_(
                    "A capacity row must target either a product or a product "
                    "category, otherwise the planning engine cannot match it."))

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_from > rec.date_to:
                raise ValidationError(_(
                    "Valid From must not be later than Valid To on the "
                    "capacity row for %s.", rec.display_name))

    @api.constrains('workcenter_id', 'product_id', 'product_category_id',
                    'date_from', 'date_to', 'active', 'company_id')
    def _check_no_overlap(self):
        """Two rows for the same machine and item must not both be valid.

        Without this the resolution order would be ambiguous and plans would
        silently depend on record ids.
        """
        for rec in self.filtered('active'):
            domain = [
                ('id', '!=', rec.id),
                ('workcenter_id', '=', rec.workcenter_id.id),
                ('company_id', '=', rec.company_id.id),
                ('active', '=', True),
            ]
            if rec.product_id:
                domain.append(('product_id', '=', rec.product_id.id))
            else:
                domain += [('product_id', '=', False),
                           ('product_category_id', '=',
                            rec.product_category_id.id)]

            for other in self.search(domain):
                if rec._periods_overlap(other):
                    raise ValidationError(_(
                        "Machine %(wc)s already has a capacity rate for "
                        "%(target)s covering an overlapping period. Close the "
                        "existing row with a 'Valid To' date before adding a "
                        "new rate.",
                        wc=rec.workcenter_id.display_name,
                        target=(rec.product_id or rec.product_category_id
                                ).display_name))

    def _periods_overlap(self, other):
        """True when two validity windows intersect. Empty dates are open."""
        self.ensure_one()
        starts_after_other_ends = (
            self.date_from and other.date_to and self.date_from > other.date_to)
        ends_before_other_starts = (
            self.date_to and other.date_from and self.date_to < other.date_from)
        return not (starts_after_other_ends or ends_before_other_starts)

    # ------------------------------------------------------------------
    # Resolution — the API the planning engine will call
    # ------------------------------------------------------------------
    @api.model
    def _resolve(self, workcenter, product, date=None):
        """Return the capacity row governing `product` on `workcenter`.

        Resolution order:
          1. a row for that exact product
          2. a row for the product's category, then each parent category
          3. an empty recordset

        :param workcenter: ``mrp.workcenter`` record
        :param product: ``product.product`` record
        :param date: date the rate must be valid on, defaults to today
        :return: a single ``fmes.capacity.matrix`` record, or empty
        """
        if not workcenter or not product:
            return self.browse()
        date = date or fields.Date.context_today(self)

        base = [
            ('workcenter_id', '=', workcenter.id),
            ('active', '=', True),
            '|', ('date_from', '=', False), ('date_from', '<=', date),
            '|', ('date_to', '=', False), ('date_to', '>=', date),
        ]

        exact = self.search(base + [('product_id', '=', product.id)],
                            order='priority, id', limit=1)
        if exact:
            return exact

        # Walk up the category tree so a rate set on a parent category covers
        # everything beneath it.
        category = product.categ_id
        while category:
            row = self.search(
                base + [('product_id', '=', False),
                        ('product_category_id', '=', category.id)],
                order='priority, id', limit=1)
            if row:
                return row
            category = category.parent_id

        return self.browse()

    @api.model
    def _get_rate(self, workcenter, product, date=None):
        """Effective hourly output for a machine and product.

        Returns 0.0 when no rate is defined. That is deliberate: a missing
        rate must be visible to the planner rather than silently substituted
        with an unrelated number, which would produce plausible-looking but
        wrong plans.
        """
        row = self._resolve(workcenter, product, date=date)
        return row.effective_output_per_hour if row else 0.0
