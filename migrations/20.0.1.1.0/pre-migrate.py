"""Migrace 19.0 → 20.0: práva z ir.model.access na ir.access.

Odoo 20 zrušilo ir.model.access a ir.rule, práva jsou v novém modelu ir.access
(security/ir.access.csv). XML ID záznamů zůstávají stejná (access_opening_hours_*),
jen pod jiným modelem. Kdyby v ir_model_data zůstaly staré řádky s modelem
ir.model.access, načtení ir.access.csv by spadlo na „found record of different model“.

Obecný migrační skript základu (balík A, base) má stará XML ID smazat sám; tohle je
pojistka pro případ, že to neudělal, aby aktualizace modulu prošla. Mažou se jen
odkazy v ir_model_data tohoto modulu, ne data: stará tabulka ir_model_access podle
zvyklostí OpenUpgrade zůstává, nové záznamy ir.access založí načtení CSV.
"""

import logging

_logger = logging.getLogger(__name__)

MODULE = 'website_opening_hours'


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        DELETE FROM ir_model_data
         WHERE module = %s
           AND model IN ('ir.model.access', 'ir.rule')
        """,
        (MODULE,),
    )
    if cr.rowcount:
        _logger.info('%s: smazáno %s starých XML ID práv (ir.model.access/ir.rule)', MODULE, cr.rowcount)
