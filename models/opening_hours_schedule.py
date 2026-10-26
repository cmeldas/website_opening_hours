from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models
from odoo.exceptions import ValidationError

DEFAULT_TZ = 'Europe/Prague'
DAY_NAMES_CZ = ('Pondělí', 'Úterý', 'Středa', 'Čtvrtek', 'Pátek', 'Sobota', 'Neděle')


def float_to_hm(value):
    """14.5 → (14, 30), 24.0 → (24, 0)."""
    return divmod(round(value * 60), 60)


def format_time(value):
    hours, minutes = float_to_hm(value)
    return f'{hours}:{minutes:02d}'


def local_datetime(tz, day, hours):
    """Čas `hours` (float, i 24.0) dne `day` v pásmu `tz` jako aware datetime."""
    hour, minute = float_to_hm(hours)
    return tz.localize(datetime.combine(day, time()) + timedelta(hours=hour, minutes=minute))


def _same_day_in_year(day, year):
    """Datum `day` v roce `year`; 29. 2. v nepřestupném roce je 28. 2."""
    try:
        return day.replace(year=year)
    except ValueError:
        return day.replace(year=year, day=28)


class OpeningHoursSchedule(models.Model):
    """Rozvrh otevírací doby: výchozí (bez dat) a sezónní na rozmezí dat.

    Pro každý den platí nejdřív výjimka (`opening.hours.override`), jinak sezónní rozvrh,
    do jehož rozmezí den spadá (při překryvu ten s kratším rozmezím, tedy konkrétnější),
    jinak výchozí rozvrh.
    """
    _name = 'opening.hours.schedule'
    _description = 'Opening Hours Schedule'
    _order = 'is_default desc, date_from, id'

    name = fields.Char(string='Název', required=True)
    active = fields.Boolean(default=True)
    date_from = fields.Date(string='Platí od')
    date_to = fields.Date(string='Platí do')
    repeat_yearly = fields.Boolean(
        string='Každý rok',
        help='Rozmezí platí každý rok, rok v datech se nebere v úvahu. Může přecházet '
             'přes Nový rok, třeba zima od 1. 11. do 31. 3.',
    )
    is_default = fields.Boolean(
        string='Výchozí',
        compute='_compute_is_default',
        store=True,
        help='Rozvrh bez dat platí vždy, když neplatí žádný sezónní.',
    )
    line_ids = fields.One2many(
        'opening.hours',
        'schedule_id',
        string='Dny',
        copy=True,
        default=lambda self: self._default_line_commands(),
    )
    period_display = fields.Char(string='Platnost', compute='_compute_period_display')

    @api.depends('date_from', 'date_to')
    def _compute_is_default(self):
        for rec in self:
            rec.is_default = not rec.date_from and not rec.date_to

    @api.depends('date_from', 'date_to', 'repeat_yearly')
    def _compute_period_display(self):
        for rec in self:
            if rec.is_default:
                rec.period_display = 'Výchozí (když neplatí jiný)'
            elif rec.repeat_yearly:
                rec.period_display = (f'každý rok {rec.date_from.day}. {rec.date_from.month}. – '
                                      f'{rec.date_to.day}. {rec.date_to.month}.')
            else:
                rec.period_display = (f'{rec.date_from.day}. {rec.date_from.month}. {rec.date_from.year} – '
                                      f'{rec.date_to.day}. {rec.date_to.month}. {rec.date_to.year}')

    def _default_line_commands(self):
        """Nový rozvrh z formuláře začíná kopií dnů výchozího rozvrhu (kontext z akce)."""
        if not self.env.context.get('opening_hours_prefill'):
            return []
        default = self.search([('is_default', '=', True)], limit=1)
        if default.line_ids:
            return [fields.Command.create(line.copy_data({'schedule_id': False})[0]) for line in default.line_ids]
        return [fields.Command.create({'day_of_week': str(day), 'is_open': False}) for day in range(7)]

    @api.constrains('date_from', 'date_to', 'repeat_yearly', 'active')
    def _check_period(self):
        for rec in self:
            if bool(rec.date_from) != bool(rec.date_to):
                raise ValidationError('Vyplňte obě data (od i do), nebo žádné pro výchozí rozvrh.')
            if rec.date_from and not rec.repeat_yearly and rec.date_from > rec.date_to:
                raise ValidationError('Datum „Platí do“ musí být stejné nebo pozdější než „Platí od“.')
        if self.search_count([('is_default', '=', True)]) > 1:
            raise ValidationError('Výchozí rozvrh (bez dat) může být jen jeden.')

    def _period_for(self, day):
        """Rozmezí (od, do) tohoto sezónního rozvrhu, do kterého spadá `day`, jinak None."""
        self.ensure_one()
        if self.is_default:
            return None
        if not self.repeat_yearly:
            return (self.date_from, self.date_to) if self.date_from <= day <= self.date_to else None
        start = _same_day_in_year(self.date_from, day.year)
        end = _same_day_in_year(self.date_to, day.year)
        if start <= end:
            return (start, end) if start <= day <= end else None
        # rozmezí přes Nový rok
        if day >= start:
            return start, _same_day_in_year(self.date_to, day.year + 1)
        if day <= end:
            return _same_day_in_year(self.date_from, day.year - 1), end
        return None

    @api.model
    def _schedule_for(self, day, schedules):
        """Rozvrh platný pro `day` z načtených `schedules`."""
        matches = [(period, rec) for rec in schedules if (period := rec._period_for(day))]
        if matches:
            # nejkratší rozmezí vyhrává, při shodě novější začátek
            return min(
                matches,
                key=lambda match: ((match[0][1] - match[0][0]).days, -match[0][0].toordinal(), -match[1].id),
            )[1]
        return next((rec for rec in schedules if rec.is_default), self.browse())

    @api.model
    def _days(self, first_day, count, exclude_override=None):
        """Otevírací doba `count` dnů od `first_day`: výjimka, jinak platný rozvrh.

        Vrací seznam slovníků s klíči date, is_open, open_time, close_time (float nebo None),
        reason, source ('override'/'schedule'/'none') a schedule (název rozvrhu).
        """
        last_day = first_day + timedelta(days=count - 1)
        schedules = self.sudo().search([])
        overrides = {
            override.date: override
            for override in self.env['opening.hours.override'].sudo().search([
                ('date', '>=', first_day), ('date', '<=', last_day),
            ])
            if override != exclude_override
        }

        def day_info(day):
            override = overrides.get(day)
            if override:
                source, is_open, line_open, line_close = 'override', override.is_open, override.open_time, override.close_time
                schedule_name, reason = None, override.reason or None
            else:
                schedule = self._schedule_for(day, schedules)
                line = schedule.line_ids.filtered(lambda rec: rec.day_of_week == str(day.weekday()))[:1]
                source = 'schedule' if schedule else 'none'
                is_open, line_open, line_close = line.is_open, line.open_time, line.close_time
                schedule_name, reason = schedule.name or None, None
            return {
                'date': day,
                'is_open': bool(is_open),
                'open_time': line_open if is_open else None,
                'close_time': line_close if is_open else None,
                'reason': reason,
                'source': source,
                'schedule': schedule_name,
            }

        return [day_info(first_day + timedelta(days=offset)) for offset in range(count)]

    @api.model
    def _open_intervals(self, days, tz):
        """Otevřené úseky dnů z `_days` jako (začátek, konec) aware datetime, navazující sloučené."""
        intervals = []
        for info in days:
            if not info['is_open']:
                continue
            start = local_datetime(tz, info['date'], info['open_time'])
            end = local_datetime(tz, info['date'], info['close_time'])
            if intervals and intervals[-1][1] >= start:
                intervals[-1] = (intervals[-1][0], max(intervals[-1][1], end))
            else:
                intervals.append((start, end))
        return intervals

    @api.model
    def _format_day(self, info):
        """Den z `_days` pro web: časy jako text, název dne česky."""
        return {
            'date': str(info['date']),
            'day_name': DAY_NAMES_CZ[info['date'].weekday()],
            'is_open': info['is_open'],
            'open_time': format_time(info['open_time']) if info['is_open'] else None,
            'close_time': format_time(info['close_time']) if info['is_open'] else None,
            'reason': info['reason'],
            'is_override': info['source'] == 'override',
            'schedule': info['schedule'],
        }

    @api.model
    def _tz(self):
        return pytz.timezone(self.env.company.partner_id.tz or DEFAULT_TZ)
