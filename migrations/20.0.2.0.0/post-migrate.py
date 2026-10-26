"""Migrace 20.0.1.1.0 → 20.0.2.0.0: týdenní rozvrh se stává výchozím rozvrhem.

Do 20.0.1.x byl jeden týdenní rozvrh (`opening.hours`, den v týdnu unikátní). Od 2.0.0
patří dny do rozvrhů (`opening.hours.schedule`): výchozí bez dat a sezónní na rozmezí dat.
Výchozí rozvrh „Celoročně“ založí data modulu (nový záznam, i když je blok noupdate),
stávající dny se k němu tady přiřadí. NOT NULL na `schedule_id` doplní Odoo až po tomhle
skriptu (odložená omezení při aktualizaci), unikátnost se mění na (rozvrh, den).
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    default = env.ref('website_opening_hours.opening_hours_schedule_default', raise_if_not_found=False)
    if not default:
        default = env['opening.hours.schedule'].create({'name': 'Celoročně'})
    cr.execute("UPDATE opening_hours SET schedule_id = %s WHERE schedule_id IS NULL", (default.id,))
    _logger.info('website_opening_hours: %s dnů přiřazeno k výchozímu rozvrhu %r', cr.rowcount, default.name)
