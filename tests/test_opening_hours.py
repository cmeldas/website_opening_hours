from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import HttpCase, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestOpeningHoursModels(TransactionCase):

    def test_regular_times_constraint(self):
        """Zavírací čas před otevíracím je chyba (v 19 padalo na AttributeError)."""
        monday = self.env.ref('website_opening_hours.opening_hours_monday')
        with self.assertRaises(ValidationError):
            monday.write({'is_open': True, 'open_time': 18.0, 'close_time': 14.0})
        # zavřený den časy nekontroluje
        monday.write({'is_open': False, 'open_time': 18.0, 'close_time': 14.0})

    def test_override_times_constraint(self):
        with self.assertRaises(ValidationError):
            self.env['opening.hours.override'].create({
                'date': '2030-01-01',
                'is_open': True,
                'open_time': 12.0,
                'close_time': 12.0,
            })

    def test_display_name_is_day(self):
        self.assertEqual(self.env.ref('website_opening_hours.opening_hours_sunday').display_name, 'Neděle')

    def test_update_ha_status_singleton(self):
        status_model = self.env['opening.hours.status']
        status_model.update_ha_status(True)
        status_model.update_ha_status(False)
        status_model.update_ha_status(True)
        statuses = status_model.search([])
        self.assertEqual(len(statuses), 1)
        self.assertTrue(statuses.ha_is_open)


@tagged('post_install', '-at_install')
class TestOpeningHoursHttp(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.status = cls.env.ref('website_opening_hours.opening_hours_status_default')
        cls.status.webhook_secret = 'tajne-heslo'

    def _set_today(self, is_open, open_time=0.0, close_time=24.0, reason=False):
        """Výjimka na včera, dnes i zítra, ať test nezávisí na časové zóně serveru."""
        today = fields.Date.today()
        Override = self.env['opening.hours.override']
        Override.search([]).unlink()
        for delta in (-1, 0, 1):
            Override.create({
                'date': today + timedelta(days=delta),
                'is_open': is_open,
                'open_time': open_time,
                'close_time': close_time,
                'reason': reason,
            })

    def _get_json(self, url):
        response = self.url_open(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Type'], 'application/json')
        return response.json()

    def test_status_open(self):
        self._set_today(True)
        self.status.ha_is_open = True
        data = self._get_json('/opening-hours/status')
        self.assertEqual(data['display_status'], 'open')
        self.assertTrue(data['today']['is_open'])
        self.assertEqual(data['today']['open_time'], '0:00')
        self.assertEqual(data['today']['close_time'], '24:00')
        self.assertTrue(data['today']['is_override'])
        self.assertIsNone(data['message'])

    def test_status_closed_unexpected(self):
        self._set_today(True)
        self.status.ha_is_open = False
        data = self._get_json('/opening-hours/status')
        self.assertEqual(data['display_status'], 'closed_unexpected')
        self.assertEqual(data['scheduled_hours'], '0:00 – 24:00')
        self.assertTrue(data['message'])

    def test_status_open_early(self):
        self._set_today(False, reason='Dovolená')
        self.status.ha_is_open = True
        data = self._get_json('/opening-hours/status')
        self.assertEqual(data['display_status'], 'open_early')
        self.assertEqual(data['message'], 'Už jsme otevřeli dříve')
        self.assertEqual(data['today']['reason'], 'Dovolená')

    def test_status_closed(self):
        self._set_today(False)
        self.status.ha_is_open = False
        data = self._get_json('/opening-hours/status')
        self.assertEqual(data['display_status'], 'closed')
        self.assertIsNone(data['today']['open_time'])

    def test_schedule(self):
        self._set_today(True)
        self.status.ha_is_open = False
        schedule = self._get_json('/opening-hours/schedule')
        self.assertEqual(len(schedule), 7)
        dates = [fields.Date.from_string(day['date']) for day in schedule]
        self.assertEqual(dates, [dates[0] + timedelta(days=i) for i in range(7)])
        self.assertEqual(schedule[0]['display_status'], 'closed_unexpected')
        for day in schedule[2:]:
            # bez výjimky platí týdenní rozvrh
            self.assertFalse(day['is_override'])
            self.assertIn(day['day_name'], ('Pondělí', 'Úterý', 'Středa', 'Čtvrtek', 'Pátek', 'Sobota', 'Neděle'))

    def test_webhook(self):
        self.status.ha_is_open = False
        result = self.make_jsonrpc_request('/opening-hours/webhook', {'secret': 'spatne', 'is_open': True})
        self.assertEqual(result['status'], 'error')
        self.status.invalidate_recordset()
        self.assertFalse(self.status.ha_is_open)

        result = self.make_jsonrpc_request('/opening-hours/webhook', {'secret': 'tajne-heslo', 'is_open': True})
        self.assertEqual(result, {'status': 'ok', 'is_open': True})
        self.status.invalidate_recordset()
        self.assertTrue(self.status.ha_is_open)

    def test_snippet_registered(self):
        """Snippet je v panelu stavebních bloků a jeho šablona se vykreslí."""
        arch = self.env.ref('website.snippets').get_combined_arch()
        self.assertIn('t-snippet="website_opening_hours.s_opening_hours"', arch)
        html = str(self.env['ir.qweb']._render('website_opening_hours.s_opening_hours'))
        for css_class in ('s_opening_hours', 's_opening_hours_widget', 's_oh_status_bar', 's_oh_schedule_list'):
            self.assertIn(css_class, html)
