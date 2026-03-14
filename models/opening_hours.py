from odoo import models, fields, api


class OpeningHours(models.Model):
    _name = 'opening.hours'
    _description = 'Opening Hours'
    _order = 'day_of_week'
    _rec_name = 'day_of_week'

    DAY_SELECTION = [
        ('0', 'Pondělí'),
        ('1', 'Úterý'),
        ('2', 'Středa'),
        ('3', 'Čtvrtek'),
        ('4', 'Pátek'),
        ('5', 'Sobota'),
        ('6', 'Neděle'),
    ]

    day_of_week = fields.Selection(
        DAY_SELECTION,
        string='Den v týdnu',
        required=True,
    )
    is_open = fields.Boolean(
        string='Otevřeno',
        default=True,
        help='Zda je v tento den obvykle otevřeno.',
    )
    open_time = fields.Float(
        string='Otevírací čas',
        default=14.0,
        help='Hodina otevření (např. 14.0 = 14:00)',
    )
    close_time = fields.Float(
        string='Zavírací čas',
        default=18.0,
        help='Hodina zavření (např. 18.0 = 18:00)',
    )

    _sql_constraints = [
        ('day_unique', 'UNIQUE(day_of_week)', 'Každý den v týdnu může mít pouze jeden záznam.'),
    ]

    @api.constrains('open_time', 'close_time')
    def _check_times(self):
        for rec in self:
            if rec.is_open and rec.open_time >= rec.close_time:
                raise models.ValidationError(
                    'Zavírací čas musí být pozdější než otevírací čas.'
                )

    def name_get(self):
        day_map = dict(self.DAY_SELECTION)
        return [(rec.id, day_map.get(rec.day_of_week, rec.day_of_week)) for rec in self]
