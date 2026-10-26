from odoo import models, fields, api
from odoo.exceptions import ValidationError


class OpeningHoursOverride(models.Model):
    """Výjimka na konkrétní den (svátek, dovolená, akce), má přednost před rozvrhy."""
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

    _date_unique = models.Constraint(
        'UNIQUE(date)',
        'Pro každý den může existovat pouze jeden přepis.',
    )

    @api.onchange('date')
    def _onchange_date(self):
        """Předvyplnit podle rozvrhu platného pro ten den (výchozí nebo sezónní)."""
        if self.date:
            [info] = self.env['opening.hours.schedule']._days(self.date, 1, exclude_override=self._origin)
            if info['source'] == 'schedule':
                self.is_open = info['is_open']
                if info['is_open']:
                    self.open_time = info['open_time']
                    self.close_time = info['close_time']

    @api.constrains('is_open', 'open_time', 'close_time')
    def _check_times(self):
        for rec in self:
            if rec.is_open and rec.open_time >= rec.close_time:
                raise ValidationError(
                    'Zavírací čas musí být pozdější než otevírací čas.'
                )
