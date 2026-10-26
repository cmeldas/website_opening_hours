{
    'name': 'Website Opening Hours',
    'version': '20.0.2.0.1',
    'author': 'Matouš Čmelík',
    'category': 'Website',
    'summary': 'Opening hours of the shop with seasonal schedules, manual open/close and Home Assistant sync',
    'description': """
        Otevírací doba obchůdku: výchozí a sezónní rozvrhy (rozmezí dat, i každý rok),
        výjimky na dny, ruční Otevřít / Zavřít. Odoo je zdroj pravdy, Home Assistant
        se podle něj přepíná (input_boolean.obchudek_otevren) a ruční přepnutí v HA
        posílá zpět. Snippet webu se stavem a rozvrhem na 7 dní.
    """,
    'depends': ['website'],
    'data': [
        'security/ir.access.csv',
        'data/opening_hours_data.xml',
        'views/opening_hours_views.xml',
        'views/opening_hours_menus.xml',
        'views/res_config_settings_views.xml',
        'views/snippets/snippets.xml',
        'views/snippets/s_opening_hours.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'website_opening_hours/static/src/scss/opening_hours.scss',
            'website_opening_hours/static/src/snippets/s_opening_hours/opening_hours.js',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
