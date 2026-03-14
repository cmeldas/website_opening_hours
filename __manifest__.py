{
    'name': 'Website Opening Hours',
    'version': '18.0.1.0.0',
    'category': 'Website',
    'summary': 'Display opening hours widget on website with live open/closed status from Home Assistant',
    'description': """
        Configurable opening hours per day of week with calendar overrides.
        Live open/closed status synced from Home Assistant.
        Website snippet with hover tooltip showing 7-day schedule.
    """,
    'depends': ['website'],
    'data': [
        'security/ir.model.access.csv',
        'data/opening_hours_data.xml',
        'views/opening_hours_views.xml',
        'views/opening_hours_menus.xml',
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
