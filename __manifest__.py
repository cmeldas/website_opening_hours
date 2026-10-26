{
    'name': 'Website Opening Hours',
    'version': '20.0.3.1.0',
    'author': 'Matouš Čmelík',
    'category': 'Website',
    'summary': 'Opening hours of the shop with seasonal schedules, manual open/close and Home Assistant sync',
    'description': """
        Otevírací doba obchůdku: rozvrhy pro letní a zimní čas (přepínají se samy s posunem
        hodin), na rozmezí dat (i každý rok) a výchozí,
        výjimky na dny, ruční Otevřít / Zavřít. Odoo je zdroj pravdy, Home Assistant
        se podle něj přepíná (input_boolean.obchudek_otevren) a ruční přepnutí v HA
        posílá zpět. Na webu v hlavičce každé stránky stav a rozvrh na 7 dní.
    """,
    'depends': ['website'],
    'data': [
        'security/ir.access.csv',
        'data/opening_hours_data.xml',
        'views/opening_hours_views.xml',
        'views/opening_hours_menus.xml',
        'views/res_config_settings_views.xml',
        'views/header_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'website_opening_hours/static/src/header/opening_hours_header.scss',
            'website_opening_hours/static/src/header/opening_hours_header.js',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
