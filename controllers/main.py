import hmac
import json
from datetime import datetime

import pytz

from odoo import http
from odoo.http import request, Response

from ..models.res_config_settings import WEBHOOK_SECRET_PARAM


def _json_response(data):
    return Response(json.dumps(data), content_type='application/json', status=200)


def _parse_changed_at(value):
    """ISO čas z Home Assistantu (s časovou zónou) jako naivní UTC, jinak None."""
    try:
        moment = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if moment.tzinfo:
        moment = moment.astimezone(pytz.utc).replace(tzinfo=None)
    return moment


class OpeningHoursController(http.Controller):

    @http.route('/opening-hours/status', type='http', auth='public', website=True, sitemap=False)
    def get_opening_status(self):
        """Return current opening status as JSON — polled by the widget every minute."""
        return _json_response(request.env['opening.hours.status'].sudo()._website_status())

    @http.route('/opening-hours/schedule', type='http', auth='public', website=True, sitemap=False)
    def get_opening_schedule(self):
        """Return opening hours for the next 7 days as JSON."""
        return _json_response(request.env['opening.hours.status'].sudo()._website_schedule())

    @http.route('/opening-hours/ha-state', type='jsonrpc', auth='none', methods=['POST'], csrf=False)
    def ha_state(self, **kw):
        """Home Assistant se ptá každou minutu, jestli má být obchůdek otevřený.

        Stav je veřejný (ukazuje ho i web), tajný klíč se nekontroluje.
        """
        return request.env['opening.hours.status'].sudo()._ha_state()

    @http.route('/opening-hours/webhook', type='jsonrpc', auth='none', methods=['POST'], csrf=False, readonly=False)
    def webhook_ha_status(self, secret='', is_open=False, changed_at=None, **kw):
        """Webhook endpoint called by Home Assistant when obchudek_otevren changes.

        Expected JSON-RPC params:
            secret: webhook secret string
            is_open: true/false
            changed_at: kdy se stav v HA změnil (ISO s časovou zónou), nepovinné
        """
        expected = request.env['ir.config_parameter'].sudo().get_str(WEBHOOK_SECRET_PARAM)
        if expected and not hmac.compare_digest(str(secret), expected):
            return {'status': 'error', 'message': 'Invalid secret'}

        result = request.env['opening.hours.status'].sudo().update_ha_status(bool(is_open), _parse_changed_at(changed_at) if changed_at else None)

        return {'status': 'ok', 'is_open': is_open, 'result': result}
