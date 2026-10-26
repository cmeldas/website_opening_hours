"""Migrace 20.0.2.0.1 → 20.0.3.0.0: otevírací doba v hlavičce místo bloku ve stránkách.

Blok „Otevírací doba“ (snippet s_opening_hours) se vkládal do stránek webu a jeho HTML je
uložené přímo v nich (domovská stránka, Sýrárna, obchod). Od 3.0.0 je otevírací doba
v hlavičce každé stránky a blok zmizel z nabídky i jeho JS, takže se z uložených stránek
odstraní, jinak by tam zůstala prázdná lišta a stav by byl na stránce dvakrát.

Mažou se jen sekce s vnitřním .s_opening_hours_widget (vlastní blok core Odoo
website.s_opening_hours se stejnou třídou zůstane), ve všech jazycích arch_db.
"""

import json
import logging

from lxml import etree

_logger = logging.getLogger(__name__)

SNIPPET_XPATH = (
    "//section[contains(concat(' ', normalize-space(@class), ' '), ' s_opening_hours ')]"
    "[.//*[contains(concat(' ', normalize-space(@class), ' '), ' s_opening_hours_widget ')]]"
)


def _strip_snippet(arch):
    """Arch bez bloku otevírací doby a počet odstraněných bloků."""
    root = etree.fromstring(arch)
    sections = root.xpath(SNIPPET_XPATH)
    for section in sections:
        parent = section.getparent()
        if section.tail:
            previous = section.getprevious()
            if previous is not None:
                previous.tail = (previous.tail or '') + section.tail
            else:
                parent.text = (parent.text or '') + section.tail
        parent.remove(section)
    return etree.tostring(root, encoding='unicode'), len(sections)


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        SELECT id, key, arch_db FROM ir_ui_view
         WHERE arch_db::text LIKE '%%s_opening_hours_widget%%'
           AND COALESCE(key, '') NOT LIKE 'website_opening_hours.%%'
        """
    )
    for view_id, key, arch_db in cr.fetchall():
        stripped = {lang: _strip_snippet(arch) for lang, arch in arch_db.items() if arch}
        removed = sum(count for _arch, count in stripped.values())
        if not removed:
            continue
        cr.execute(
            "UPDATE ir_ui_view SET arch_db = %s::jsonb WHERE id = %s",
            (json.dumps({lang: arch for lang, (arch, _count) in stripped.items()}), view_id),
        )
        _logger.info('website_opening_hours: z pohledu %s (%s) odstraněn blok otevírací doby', view_id, key)
