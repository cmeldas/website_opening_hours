from odoo import models, fields


class OpeningHoursStatus(models.Model):
    _name = 'opening.hours.status'
    _description = 'Live Opening Status from Home Assistant'

    ha_is_open = fields.Boolean(
        string='HA: Otevřeno',
        default=False,
        help='Aktuální stav z Home Assistant (input_boolean.obchudek_otevren).',
    )
    last_update = fields.Datetime(
        string='Poslední aktualizace',
        default=fields.Datetime.now,
    )
    webhook_secret = fields.Char(
        string='Webhook Secret',
        help='Tajný klíč pro ověření webhook volání z Home Assistant.',
    )

    def _get_status(self):
        """Get or create the singleton status record."""
        status = self.sudo().search([], limit=1)
        if not status:
            status = self.sudo().create({'ha_is_open': False})
        return status

    def update_ha_status(self, is_open):
        """Update the HA open/closed status."""
        status = self._get_status()
        status.sudo().write({
            'ha_is_open': is_open,
            'last_update': fields.Datetime.now(),
        })
        return True
