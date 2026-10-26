"""Migrace na 20.0.3.1.0: rozvrhy dostávají „Platí“ (letní/zimní čas, rozmezí dat, výchozí).

Nový sloupec validity Odoo při aktualizaci vyplní výchozí hodnotou „dates“ všem řádkům;
tady se opraví podle dosavadního významu: rozvrh bez dat byl výchozí, s daty na rozmezí dat.
Letní a zimní čas si uživatel nastaví sám (stávající rozvrhy se nemění).
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        UPDATE opening_hours_schedule
           SET validity = CASE WHEN date_from IS NULL AND date_to IS NULL THEN 'default' ELSE 'dates' END,
               is_default = (date_from IS NULL AND date_to IS NULL)
        """
    )
    _logger.info('website_opening_hours: platnost doplněna u %s rozvrhů', cr.rowcount)
