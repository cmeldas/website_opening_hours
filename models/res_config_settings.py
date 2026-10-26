from odoo import fields, models

WEBHOOK_SECRET_PARAM = 'website_opening_hours.webhook_secret'


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    opening_hours_webhook_secret = fields.Char(
        string='Webhook Secret',
        config_parameter=WEBHOOK_SECRET_PARAM,
        help='Tajný klíč, který Home Assistant posílá s hlášením o otevření/zavření obchůdku. '
             'Prázdný = webhook přijme cokoli.',
    )
