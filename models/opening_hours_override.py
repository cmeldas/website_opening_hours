from odoo import models, fields, api


class OpeningHoursOverride(models.Model):
    _name = 'opening.hours.override'
    _description = 'Opening Hours Override'
    _order = 'date'
    _rec_name = 'date'

    date = fields.Date(
        string='Datum',
        required=True,
        index=True,
    )
    is_open = fields.Boolean(
        string='Otevřeno',
        default=False,
        help='Přepsat zda je v tento den otevřeno.',
    )
    open_time = fields.Float(
        string='Otevírací čas',
        default=14.0,
    )
    close_time = fields.Float(
        string='Zavírací čas',
        default=18.0,
    )
    reason = fields.Char(
        string='Důvod',
        help='Např. svátek, dovolená, speciální akce...',
    )

    _sql_constraints = [
        ('date_unique', 'UNIQUE(date)', 'Pro každý den může existovat pouze jeden přepis.'),
    ]

    @api.onchange('date')
    def _onchange_date(self):
        if self.date:
            regular = self.env['opening.hours'].search([
                ('day_of_week', '=', str(self.date.weekday())),
            ], limit=1)
            if regular:
                self.is_open = regular.is_open
                self.open_time = regular.open_time
                self.close_time = regular.close_time

    @api.constrains('open_time', 'close_time')
    def _check_times(self):
        for rec in self:
            if rec.is_open and rec.open_time >= rec.close_time:
                raise models.ValidationError(
                    'Zavírací čas musí být pozdější než otevírací čas.'
                )
