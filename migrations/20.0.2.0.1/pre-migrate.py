"""Migrace 20.0.2.0.0 → 20.0.2.0.1: Webhook Secret ze Stavu obchůdku do Nastavení.

Stav obchůdku je stránka pro obsluhu, tajný klíč pro Home Assistant patří do Nastavení
→ Web → Otevírací doba (systémový parametr website_opening_hours.webhook_secret).
Skript běží před aktualizací modelů, kdy sloupec opening_hours_status.webhook_secret
ještě existuje, a přenese jeho hodnotu; Home Assistant tak nic měnit nemusí.
"""

import logging

_logger = logging.getLogger(__name__)

PARAM = 'website_opening_hours.webhook_secret'


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'opening_hours_status' AND column_name = 'webhook_secret'
        """
    )
    if not cr.rowcount:
        return
    cr.execute(
        """
        SELECT webhook_secret FROM opening_hours_status
         WHERE COALESCE(webhook_secret, '') <> ''
         ORDER BY id LIMIT 1
        """
    )
    row = cr.fetchone()
    if not row:
        return
    cr.execute(
        """
        INSERT INTO ir_config_parameter (key, value, create_uid, create_date, write_uid, write_date)
        VALUES (%s, %s, 1, now() AT TIME ZONE 'UTC', 1, now() AT TIME ZONE 'UTC')
        ON CONFLICT (key) DO NOTHING
        """,
        (PARAM, row[0]),
    )
    _logger.info('website_opening_hours: Webhook Secret přenesen do systémového parametru %s', PARAM)
