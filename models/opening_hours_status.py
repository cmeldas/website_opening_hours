from datetime import datetime, time, timedelta

import pytz

from odoo import fields, models
from odoo.exceptions import AccessError

from .opening_hours_schedule import DAY_AT_CZ, DAY_NAMES_CZ, format_time, local_datetime

LOOKAHEAD_DAYS = 8
STALE_HA_REPORT = timedelta(minutes=10)


def _to_utc_naive(value):
    return value.astimezone(pytz.utc).replace(tzinfo=None)


def _scheduled_open_at(intervals, moment):
    return any(start <= moment < end for start, end in intervals)


def _end_of_disagreement(intervals, moment, want_open, limit):
    """Konec nejbližšího úseku od `moment`, kdy rozvrh říká opak `want_open`, nejpozději `limit`.

    Tak dlouho platí ruční otevření/zavření: otevřít v 10:00 při rozvrhu 15–19 platí do 15:00
    (pak je otevřeno podle rozvrhu), zavřít v 16:00 do 19:00, zavřít ve 14:00 („dnes už
    neotevírat“) taky do 19:00. Vždy nejdéle do konce dne.
    """
    edges = sorted({edge for interval in intervals for edge in interval})
    while moment < limit:
        boundary = next((edge for edge in edges if edge > moment), limit)
        if _scheduled_open_at(intervals, moment) != want_open:
            return min(boundary, limit)
        moment = boundary
    return limit


def _format_moment(moment, today):
    """Čas změny pro lidi: „v 19:00“, „zítra v 15:00“, „ve středu 28. 10. v 15:00“."""
    clock = f'{moment.hour}:{moment.minute:02d}'
    day = moment.date()
    if day == today:
        return f'v {clock}'
    if day == today + timedelta(days=1):
        return f'zítra v {clock}'
    return f'{DAY_NAMES_CZ[day.weekday()].lower()} {day.day}. {day.month}. v {clock}'


class OpeningHoursStatus(models.Model):
    """Stav obchůdku (jeden záznam): ruční otevření/zavření nad rozvrhem a hlášení z HA.

    Pravdu má Odoo: otevřeno je podle rozvrhu (výjimky, sezónní a výchozí rozvrh), pokud ho
    nepřebíjí ruční otevření/zavření (tlačítka tady nebo přepnutí v Home Assistantu).
    Home Assistant se podle `/opening-hours/ha-state` přepíná sám.
    """
    _name = 'opening.hours.status'
    _description = 'Shop Open State'

    ha_is_open = fields.Boolean(
        string='HA hlásí otevřeno',
        default=False,
        readonly=True,
        help='Poslední stav input_boolean.obchudek_otevren, který Home Assistant poslal '
             '(jen hlášení, nastavuje ho webhook).',
    )
    last_update = fields.Datetime(
        string='HA naposledy hlásil',
        default=fields.Datetime.now,
        readonly=True,
    )
    manual_state = fields.Selection(
        [('open', 'Otevřeno'), ('closed', 'Zavřeno')],
        string='Ručně',
    )
    manual_until = fields.Datetime(string='Ručně do')
    manual_source = fields.Selection(
        [('odoo', 'Odoo'), ('ha', 'Home Assistant')],
        string='Ručně z',
    )
    manual_user_id = fields.Many2one('res.users', string='Ručně nastavil')
    manual_date = fields.Datetime(string='Ručně nastaveno kdy')

    # živý stav pro formulář (počítá se při každém čtení)
    is_open_now = fields.Boolean(string='Teď otevřeno', compute='_compute_live_state')
    manual_active = fields.Boolean(string='Platí ruční stav', compute='_compute_live_state')
    opens_later_today = fields.Boolean(compute='_compute_live_state')
    state_label = fields.Char(string='Stav', compute='_compute_live_state')
    state_detail = fields.Char(string='Proč', compute='_compute_live_state')
    today_hours = fields.Char(string='Dnes', compute='_compute_live_state')
    next_change_display = fields.Char(string='Další změna', compute='_compute_live_state')

    def _compute_display_name(self):
        for rec in self:
            rec.display_name = 'Stav obchůdku'

    def _compute_live_state(self):
        for rec in self:
            state = rec._state()
            today = state['today']
            rec.is_open_now = state['is_open']
            rec.manual_active = state['manual']
            rec.opens_later_today = any(
                start > state['now'] and start.date() == state['now'].date() for start, _end in state['intervals']
            )
            rec.state_label = 'Otevřeno' if state['is_open'] else 'Zavřeno'
            if state['manual']:
                until = state['manual_until']
                until_text = ('do konce dne' if until.time() == time() and until.date() > state['now'].date()
                              else f'do {until.hour}:{until.minute:02d}')
                who = dict(rec._fields['manual_source'].selection).get(rec.manual_source, '')
                if rec.manual_user_id:
                    who = f'{who}, {rec.manual_user_id.name}'
                rec.state_detail = f'Ručně ({who}) {until_text}, pak podle rozvrhu'
            elif today['source'] == 'override':
                rec.state_detail = 'Podle výjimky' + (f': {today["reason"]}' if today['reason'] else '')
            elif today['source'] == 'schedule':
                rec.state_detail = f'Podle rozvrhu „{today["schedule"]}“'
            else:
                rec.state_detail = 'Žádný rozvrh, zavřeno'
            if today['is_open']:
                rec.today_hours = f'{format_time(today["open_time"])} – {format_time(today["close_time"])}'
            else:
                rec.today_hours = 'Zavřeno'
            if today['reason']:
                rec.today_hours += f' ({today["reason"]})'
            if state['next_change']:
                verb = 'Zavře se' if state['is_open'] else 'Otevře se'
                rec.next_change_display = f'{verb} {_format_moment(state["next_change"], state["now"].date())}'
            else:
                rec.next_change_display = 'V příštím týdnu beze změny'

    def _get_status(self):
        """Get or create the singleton status record."""
        status = self.sudo().search([], limit=1)
        if not status:
            status = self.sudo().create({'ha_is_open': False})
        return status

    # -------------------------------------------------------------------------
    # Stav
    # -------------------------------------------------------------------------

    def _state(self, now=None):
        """Stav obchůdku v `now` (naivní UTC, výchozí teď) v časovém pásmu obchůdku.

        Klíče: now, today (den z `_days`), intervals (otevřené úseky na týden dopředu),
        scheduled_open (podle rozvrhu), manual (platí ruční stav), manual_until, is_open
        (výsledek), next_change (kdy se výsledek změní, nebo None).
        """
        status = self._get_status()
        schedule_model = self.env['opening.hours.schedule'].sudo()
        tz = schedule_model._tz()
        now = now or fields.Datetime.now()
        now_local = pytz.utc.localize(now).astimezone(tz)
        days = schedule_model._days(now_local.date(), LOOKAHEAD_DAYS)
        intervals = schedule_model._open_intervals(days, tz)
        scheduled_open = _scheduled_open_at(intervals, now_local)
        manual = bool(status.manual_state and status.manual_until and status.manual_until > now)
        manual_open = status.manual_state == 'open'
        manual_until = pytz.utc.localize(status.manual_until).astimezone(tz) if manual else None
        is_open = manual_open if manual else scheduled_open

        def effective_at(moment):
            if manual and moment < manual_until:
                return manual_open
            return _scheduled_open_at(intervals, moment)

        edges = sorted({edge for interval in intervals for edge in interval} | ({manual_until} if manual else set()))
        return {
            'now': now_local,
            'today': days[0],
            'intervals': intervals,
            'scheduled_open': scheduled_open,
            'manual': manual,
            'manual_until': manual_until,
            'is_open': is_open,
            'next_change': next((edge for edge in edges if edge > now_local and effective_at(edge) != is_open), None),
        }

    def _set_manual(self, is_open, source, now=None):
        """Ručně otevřít/zavřít; platí do konce nejbližšího úseku, kdy rozvrh říká opak.

        Když ruční stav platí a nový souhlasí s rozvrhem, ruční stav se zruší (zpět podle
        rozvrhu): ručně zavřeno v 16:00, v 17:00 „Otevřít“ = zase otevřeno do 19:00.
        """
        status = self._get_status()
        now = now or fields.Datetime.now()
        state = status._state(now)
        if state['manual'] and is_open == state['scheduled_open']:
            status._clear_manual()
            return
        tz = state['now'].tzinfo
        end_of_day = tz.localize(datetime.combine(state['now'].date() + timedelta(days=1), time()))
        until = _end_of_disagreement(state['intervals'], state['now'], is_open, end_of_day)
        status.sudo().write({
            'manual_state': 'open' if is_open else 'closed',
            'manual_until': _to_utc_naive(until),
            'manual_source': source,
            'manual_user_id': self.env.user.id if source == 'odoo' else False,
            'manual_date': now,
        })

    def _clear_manual(self):
        self.sudo().write({
            'manual_state': False,
            'manual_until': False,
            'manual_source': False,
            'manual_user_id': False,
            'manual_date': False,
        })

    # -------------------------------------------------------------------------
    # Tlačítka
    # -------------------------------------------------------------------------

    def _check_internal_user(self):
        if not self.env.user._is_internal():
            raise AccessError('Otevřít nebo zavřít obchůdek může jen přihlášený uživatel.')

    def action_open(self):
        self._check_internal_user()
        self._set_manual(True, 'odoo')

    def action_close(self):
        self._check_internal_user()
        self._set_manual(False, 'odoo')

    def action_follow_schedule(self):
        self._check_internal_user()
        self._get_status()._clear_manual()

    # -------------------------------------------------------------------------
    # Home Assistant a web
    # -------------------------------------------------------------------------

    def update_ha_status(self, is_open, changed_at=None):
        """Home Assistant hlásí změnu `input_boolean.obchudek_otevren`.

        Shoda se stavem v Odoo je jen potvrzení (HA se přepnul podle Odoo). Rozdíl je ruční
        přepnutí v HA (aplikace, notifikace „Zavřít obchůdek“): Odoo ho převezme jako ruční
        otevření/zavření, aby ho HA při příštím dotazu nevrátil. Hlášení starší než 10 minut
        (opakované odeslání po výpadku Odoo) se za ruční změnu nepovažuje.

        :param changed_at: kdy se stav v HA změnil (naivní UTC), nebo None
        :return: 'confirmed', 'manual' nebo 'stale'
        """
        status = self._get_status()
        now = fields.Datetime.now()
        status.sudo().write({'ha_is_open': is_open, 'last_update': now})
        if is_open == status._state(now)['is_open']:
            return 'confirmed'
        if changed_at and now - changed_at > STALE_HA_REPORT:
            return 'stale'
        status._set_manual(is_open, 'ha', now)
        return 'manual'

    def _ha_state(self):
        """Stav pro Home Assistant (`/opening-hours/ha-state`)."""
        state = self._state()
        return {
            'is_open': state['is_open'],
            'scheduled_open': state['scheduled_open'],
            'manual': state['manual'],
            'manual_until': _to_utc_naive(state['manual_until']).isoformat() + 'Z' if state['manual'] else None,
            'next_change': _to_utc_naive(state['next_change']).isoformat() + 'Z' if state['next_change'] else None,
        }

    def _website_status(self):
        """Stav pro snippet na webu (`/opening-hours/status`)."""
        status = self._get_status()
        state = status._state()
        today = self.env['opening.hours.schedule']._format_day(state['today'])
        message = scheduled_hours = None
        if state['is_open'] and state['scheduled_open']:
            display_status = 'open'
        elif state['is_open']:
            display_status = 'open_early'
            opens_later = state['today']['is_open'] and any(
                start > state['now'] and start.date() == state['now'].date() for start, _end in state['intervals']
            )
            message = 'Už jsme otevřeli dříve' if opens_later else 'Mimořádně máme otevřeno'
        elif state['scheduled_open']:
            display_status = 'closed_unexpected'
            message = 'Omlouváme se, ale aktuálně máme neplánovaně zavřeno'
            scheduled_hours = f'{today["open_time"]} – {today["close_time"]}'
        else:
            display_status = 'closed'
        return {
            'today': today,
            'is_open': state['is_open'],
            'ha_is_open': status.ha_is_open,
            'ha_last_update': str(status.last_update) if status.last_update else None,
            'display_status': display_status,
            'message': message,
            'scheduled_hours': scheduled_hours,
        }

    def _website_schedule(self):
        """Rozvrh na 7 dní od dneška pro snippet; dnešek s živým stavem."""
        schedule_model = self.env['opening.hours.schedule'].sudo()
        today = fields.Datetime.now().replace(tzinfo=pytz.utc).astimezone(schedule_model._tz()).date()
        days = [schedule_model._format_day(info) for info in schedule_model._days(today, 7)]
        display_status = self._website_status()['display_status']
        if display_status in ('closed_unexpected', 'open_early'):
            days[0]['display_status'] = display_status
        return days

    def _website_header(self, now=None):
        """Otevírací doba v hlavičce webu, jak ji vykreslí server (bez stavu otevřeno/zavřeno).

        Stav doplní JS z `/opening-hours/status`, až ho server potvrdí; tady je jen podle
        rozvrhu předpokládaná doba: dnešní hodiny, a když už dnes neotevře, nejbližší
        otevření („zítra 15:00 – 19:00“, „ve středu 15:00 – 19:00“). A 7 dní pro rozbalení.

        :param now: naivní UTC, výchozí teď
        """
        schedule_model = self.env['opening.hours.schedule'].sudo()
        tz = schedule_model._tz()
        now_local = pytz.utc.localize(now or fields.Datetime.now()).astimezone(tz)
        days = schedule_model._days(now_local.date(), 7)

        def hours(info):
            return f'{format_time(info["open_time"])} – {format_time(info["close_time"])}'

        today = days[0]
        if today['is_open'] and now_local < local_datetime(tz, today['date'], today['close_time']):
            hours_label = hours(today)
        else:
            offset, upcoming = next(
                ((offset, info) for offset, info in enumerate(days[1:], start=1) if info['is_open']),
                (None, None),
            )
            if upcoming is None:
                hours_label = 'Tento týden zavřeno'
            else:
                when = 'zítra' if offset == 1 else DAY_AT_CZ[upcoming['date'].weekday()]
                hours_label = f'{when} {hours(upcoming)}'

        def label(offset, info):
            if offset == 0:
                return 'Dnes'
            if offset == 1:
                return 'Zítra'
            return DAY_NAMES_CZ[info['date'].weekday()]

        return {
            'hours_label': hours_label,
            'days': [
                {
                    'date': str(info['date']),
                    'label': label(offset, info),
                    'is_today': offset == 0,
                    'is_open': info['is_open'],
                    'hours': hours(info) if info['is_open'] else 'Zavřeno',
                    'reason': info['reason'],
                }
                for offset, info in enumerate(days)
            ],
        }
