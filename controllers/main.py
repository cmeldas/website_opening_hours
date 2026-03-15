import hmac
import json
from datetime import timedelta, datetime

from odoo import http, fields
from odoo.http import request, Response


class OpeningHoursController(http.Controller):

    DAY_NAMES_CZ = {
        0: 'Pondělí',
        1: 'Úterý',
        2: 'Středa',
        3: 'Čtvrtek',
        4: 'Pátek',
        5: 'Sobota',
        6: 'Neděle',
    }

    def _format_time(self, float_time):
        """Convert float time (e.g., 14.5) to string '14:30'."""
        hours = int(float_time)
        minutes = int((float_time - hours) * 60)
        return f'{hours}:{minutes:02d}'

    def _get_day_info(self, target_date):
        """Get opening info for a specific date, considering overrides."""
        # Check for override first
        override = request.env['opening.hours.override'].sudo().search([
            ('date', '=', target_date),
        ], limit=1)

        if override:
            return {
                'date': str(target_date),
                'day_name': self.DAY_NAMES_CZ[target_date.weekday()],
                'is_open': override.is_open,
                'open_time': self._format_time(override.open_time) if override.is_open else None,
                'close_time': self._format_time(override.close_time) if override.is_open else None,
                'reason': override.reason or None,
                'is_override': True,
            }

        # Fall back to regular schedule
        day_of_week = str(target_date.weekday())
        regular = request.env['opening.hours'].sudo().search([
            ('day_of_week', '=', day_of_week),
        ], limit=1)

        if regular:
            return {
                'date': str(target_date),
                'day_name': self.DAY_NAMES_CZ[target_date.weekday()],
                'is_open': regular.is_open,
                'open_time': self._format_time(regular.open_time) if regular.is_open else None,
                'close_time': self._format_time(regular.close_time) if regular.is_open else None,
                'reason': None,
                'is_override': False,
            }

        return {
            'date': str(target_date),
            'day_name': self.DAY_NAMES_CZ[target_date.weekday()],
            'is_open': False,
            'open_time': None,
            'close_time': None,
            'reason': None,
            'is_override': False,
        }

    @http.route('/opening-hours/status', type='http', auth='public', website=True, sitemap=False)
    def get_opening_status(self):
        """Return current opening status as JSON — polled by the widget every minute."""
        today = fields.Date.context_today(request.env.user)
        today_info = self._get_day_info(today)

        # Get HA live status
        status_model = request.env['opening.hours.status'].sudo()
        status = status_model.search([], limit=1)
        ha_is_open = status.ha_is_open if status else False
        last_update = str(status.last_update) if status and status.last_update else None

        # Determine display message
        scheduled_open = today_info['is_open']

        # Check if current time is within today's opening hours
        now = datetime.now()
        current_hour = now.hour + now.minute / 60.0
        within_hours = False
        if scheduled_open and today_info['open_time'] and today_info['close_time']:
            open_h, open_m = map(int, today_info['open_time'].split(':'))
            close_h, close_m = map(int, today_info['close_time'].split(':'))
            open_float = open_h + open_m / 60.0
            close_float = close_h + close_m / 60.0
            within_hours = open_float <= current_hour < close_float

        message = None
        display_status = 'closed'

        scheduled_hours = None
        if ha_is_open and within_hours:
            display_status = 'open'
        elif ha_is_open and not within_hours:
            display_status = 'open_early'
            message = 'Už jsme otevřeli dříve'
        elif not ha_is_open and within_hours:
            display_status = 'closed_unexpected'
            message = 'Omlouváme se, ale aktuálně máme neplánovaně zavřeno'
            scheduled_hours = today_info['open_time'] + ' – ' + today_info['close_time']
        else:
            display_status = 'closed'

        result = {
            'today': today_info,
            'ha_is_open': ha_is_open,
            'ha_last_update': last_update,
            'display_status': display_status,
            'message': message,
            'scheduled_hours': scheduled_hours,
        }

        return Response(
            json.dumps(result),
            content_type='application/json',
            status=200,
        )

    @http.route('/opening-hours/schedule', type='http', auth='public', website=True, sitemap=False)
    def get_opening_schedule(self):
        """Return opening hours for the next 7 days as JSON."""
        today = fields.Date.context_today(request.env.user)

        # Get HA status for today's display_status
        status_model = request.env['opening.hours.status'].sudo()
        status = status_model.search([], limit=1)
        ha_is_open = status.ha_is_open if status else False

        schedule = []
        for i in range(7):
            day = today + timedelta(days=i)
            info = self._get_day_info(day)
            # For today, enrich with HA-aware display status (time-aware)
            if i == 0 and info['is_open'] and info['open_time'] and info['close_time']:
                open_h, open_m = map(int, info['open_time'].split(':'))
                close_h, close_m = map(int, info['close_time'].split(':'))
                open_f = open_h + open_m / 60.0
                close_f = close_h + close_m / 60.0
                now = datetime.now()
                cur = now.hour + now.minute / 60.0
                in_hours = open_f <= cur < close_f
                if not ha_is_open and in_hours:
                    info['display_status'] = 'closed_unexpected'
                elif ha_is_open and not in_hours:
                    info['display_status'] = 'open_early'
            schedule.append(info)

        return Response(
            json.dumps(schedule),
            content_type='application/json',
            status=200,
        )

    @http.route('/opening-hours/webhook', type='json', auth='none', methods=['POST'], csrf=False)
    def webhook_ha_status(self, secret='', is_open=False, **kw):
        """Webhook endpoint called by Home Assistant when obchudek_otevren changes.

        Expected JSON-RPC params:
            secret: webhook secret string
            is_open: true/false
        """
        # Validate webhook secret
        status_model = request.env['opening.hours.status'].sudo()
        status = status_model.search([], limit=1)

        if status and status.webhook_secret:
            if not hmac.compare_digest(str(secret), status.webhook_secret):
                return {'status': 'error', 'message': 'Invalid secret'}

        status_model.update_ha_status(is_open)

        return {'status': 'ok', 'is_open': is_open}
