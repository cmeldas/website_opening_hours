from datetime import date, datetime, timedelta

import pytz

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import Form, HttpCase, TransactionCase, tagged

from odoo.addons.website_opening_hours.models.opening_hours_schedule import format_hours_short, season_range

PRAGUE = pytz.timezone('Europe/Prague')

# 2030-06-03 pondělí, 2030-06-05 středa
MONDAY = date(2030, 6, 3)
WEDNESDAY = date(2030, 6, 5)


def utc(day, hour, minute=0):
    """Místní čas v Praze jako naivní UTC (jak ho Odoo ukládá)."""
    local = PRAGUE.localize(datetime.combine(day, datetime.min.time()) + timedelta(hours=hour, minutes=minute))
    return local.astimezone(pytz.utc).replace(tzinfo=None)


def week_lines(open_time=15.0, close_time=19.0, closed_days=('0', '1')):
    return [
        fields.Command.create({
            'day_of_week': str(day),
            'is_open': str(day) not in closed_days,
            'open_time': open_time,
            'close_time': close_time,
        })
        for day in range(7)
    ]


@tagged('post_install', '-at_install')
class TestOpeningHoursModels(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.partner_id.tz = 'Europe/Prague'
        cls.Schedule = cls.env['opening.hours.schedule']
        cls.Schedule.search([]).action_archive()
        cls.env['opening.hours.override'].search([]).unlink()
        # po a út zavřeno, jinak 15–19
        cls.default = cls.Schedule.create({'name': 'Test výchozí', 'validity': 'default', 'line_ids': week_lines()})
        cls.status = cls.env['opening.hours.status']._get_status()
        cls.status._clear_manual()

    def _day(self, day):
        [info] = self.Schedule._days(day, 1)
        return info

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

    def test_default_schedule_from_data(self):
        """Dny z dat modulu patří k rozvrhu Celoročně (po instalaci výchozí, uživatel ho může
        přepnout třeba na letní čas)."""
        default = self.env.ref('website_opening_hours.opening_hours_schedule_default')
        self.assertEqual(self.env.ref('website_opening_hours.opening_hours_monday').schedule_id, default)
        self.assertEqual(len(default.line_ids), 7)
        self.assertEqual(default.is_default, default.validity == 'default')

    def test_schedule_period_constraints(self):
        with self.assertRaises(ValidationError):
            self.Schedule.create({'name': 'Jen od', 'date_from': '2030-01-01'})
        with self.assertRaises(ValidationError):
            self.Schedule.create({'name': 'Obráceně', 'date_from': '2030-03-01', 'date_to': '2030-01-01'})
        with self.assertRaises(ValidationError):
            self.Schedule.create({'name': 'Druhý výchozí', 'validity': 'default'})
        # každý rok smí přecházet přes Nový rok
        self.Schedule.create({'name': 'Zima', 'date_from': '2030-11-01', 'date_to': '2030-03-31', 'repeat_yearly': True})

    def test_form_partial_period(self):
        """Nový rozvrh ve formuláři: po zadání jen „Platí od“ (3.0.0 tu padalo na prázdném „do“)."""
        with Form(self.Schedule.with_context(opening_hours_prefill=True)) as form:
            form.name = 'Zima'
            form.date_from = date(2026, 10, 31)
            self.assertEqual(form.period_display, '31. 10. 2026 – …')
            form.date_to = date(2027, 3, 31)
            self.assertEqual(form.period_display, '31. 10. 2026 – 31. 3. 2027')
            form.repeat_yearly = True
            self.assertEqual(form.period_display, 'každý rok 31. 10. – 31. 3.')
            # přepnutí na zimní čas data smaže, platnost ukáže nejbližší zimní období
            form.validity = 'winter_time'
            self.assertFalse(form.date_from)
            self.assertTrue(form.period_display.startswith('Zimní čas: '))
            form.validity = 'dates'
            form.date_from = date(2026, 10, 31)
            form.date_to = date(2027, 3, 31)
            form.repeat_yearly = True
        winter = self.Schedule.search([('name', '=', 'Zima')])
        self.assertEqual(len(winter.line_ids), 7)
        self.assertEqual(self._day(date(2026, 12, 2))['schedule'], 'Zima')

    def test_prefill_from_default(self):
        """Nový rozvrh z menu začíná kopií dnů výchozího rozvrhu."""
        new = self.Schedule.with_context(opening_hours_prefill=True).create({
            'name': 'Léto', 'date_from': '2030-07-01', 'date_to': '2030-08-31',
        })
        self.assertEqual(len(new.line_ids), 7)
        self.assertEqual(
            sorted(new.line_ids.mapped(lambda line: (line.day_of_week, line.is_open, line.open_time))),
            sorted(self.default.line_ids.mapped(lambda line: (line.day_of_week, line.is_open, line.open_time))),
        )
        self.assertEqual(len(self.default.line_ids), 7)

    def test_seasonal_schedules(self):
        winter = self.Schedule.create({
            'name': 'Zima', 'date_from': '2020-11-01', 'date_to': '2021-03-31', 'repeat_yearly': True,
            'line_ids': week_lines(14.0, 16.0),
        })
        christmas = self.Schedule.create({
            'name': 'Vánoce', 'date_from': '2030-12-20', 'date_to': '2030-12-31',
            'line_ids': week_lines(closed_days=tuple(str(day) for day in range(7))),
        })
        summer_day = self._day(WEDNESDAY)
        self.assertEqual(summer_day['schedule'], 'Test výchozí')
        self.assertEqual((summer_day['open_time'], summer_day['close_time']), (15.0, 19.0))

        for winter_wednesday in (date(2030, 12, 4), date(2031, 1, 8)):
            info = self._day(winter_wednesday)
            self.assertEqual(info['schedule'], winter.name, winter_wednesday)
            self.assertEqual((info['open_time'], info['close_time']), (14.0, 16.0))

        # kratší rozmezí (Vánoce) má přednost před zimou
        info = self._day(date(2030, 12, 25))
        self.assertEqual(info['schedule'], christmas.name)
        self.assertFalse(info['is_open'])

        # výjimka na den má přednost před vším
        self.env['opening.hours.override'].create({
            'date': '2030-12-25', 'is_open': True, 'open_time': 10.0, 'close_time': 12.0, 'reason': 'Trhy',
        })
        info = self._day(date(2030, 12, 25))
        self.assertEqual((info['source'], info['is_open'], info['open_time'], info['reason']), ('override', True, 10.0, 'Trhy'))

    def test_summer_and_winter_time(self):
        """Rozvrh pro letní a zimní čas se přepíná s posunem hodin, rozmezí dat má přednost.

        2030: letní čas od neděle 31. 3., zimní od neděle 27. 10. (den přechodu patří novému).
        """
        summer = self.Schedule.create({'name': 'Léto', 'validity': 'summer_time', 'line_ids': week_lines(15.0, 19.0)})
        winter = self.Schedule.create({'name': 'Zima', 'validity': 'winter_time', 'line_ids': week_lines(15.0, 18.0)})
        cases = {
            date(2030, 3, 30): 'Zima',
            date(2030, 3, 31): 'Léto',
            date(2030, 7, 3): 'Léto',
            date(2030, 10, 26): 'Léto',
            date(2030, 10, 27): 'Zima',
            date(2030, 12, 4): 'Zima',
        }
        for day, name in cases.items():
            self.assertEqual(self._day(day)['schedule'], name, day)
        self.assertEqual(self._day(date(2030, 12, 4))['close_time'], 18.0)
        self.assertEqual(self._day(date(2030, 7, 3))['close_time'], 19.0)

        # rozmezí dat má přednost před letním/zimním časem
        self.Schedule.create({
            'name': 'Vánoce', 'validity': 'dates', 'date_from': '2030-12-20', 'date_to': '2030-12-31',
            'line_ids': week_lines(10.0, 12.0),
        })
        self.assertEqual(self._day(date(2030, 12, 25))['schedule'], 'Vánoce')
        self.assertEqual(self._day(date(2031, 1, 8))['schedule'], 'Zima')

        with self.assertRaises(ValidationError):
            self.Schedule.create({'name': 'Léto 2', 'validity': 'summer_time'})
        self.assertTrue(summer.period_display.startswith('Letní čas: '))
        self.assertTrue(winter.period_display.startswith('Zimní čas: '))

    def test_season_range(self):
        """Právě běžící nebo příští období letního/zimního času."""
        self.assertEqual(season_range(PRAGUE, date(2030, 6, 1), True), (date(2030, 3, 31), date(2030, 10, 26)))
        self.assertEqual(season_range(PRAGUE, date(2030, 6, 1), False), (date(2030, 10, 27), date(2031, 3, 29)))
        self.assertEqual(season_range(PRAGUE, date(2030, 12, 4), False), (date(2030, 10, 27), date(2031, 3, 29)))
        self.assertEqual(season_range(PRAGUE, date(2030, 12, 4), True), (date(2031, 3, 30), date(2031, 10, 25)))

    def test_override_onchange_uses_valid_schedule(self):
        self.Schedule.create({
            'name': 'Zima', 'date_from': '2030-11-01', 'date_to': '2031-03-31', 'line_ids': week_lines(14.0, 16.0),
        })
        override = self.env['opening.hours.override'].new({'date': date(2030, 12, 4)})
        override._onchange_date()
        self.assertEqual((override.is_open, override.open_time, override.close_time), (True, 14.0, 16.0))

    def test_intervals_across_dst_change(self):
        """Neděle 27. 10. 2030 (konec letního času): 15:00 místního času je 14:00 UTC."""
        days = self.Schedule._days(date(2030, 10, 27), 1)
        [(start, end)] = self.Schedule._open_intervals(days, PRAGUE)
        self.assertEqual(start.astimezone(pytz.utc).replace(tzinfo=None), datetime(2030, 10, 27, 14, 0))
        self.assertEqual(end.astimezone(pytz.utc).replace(tzinfo=None), datetime(2030, 10, 27, 18, 0))

    # -------------------------------------------------------------------------
    # Ruční otevření a zavření
    # -------------------------------------------------------------------------

    def _state(self, day, hour, minute=0):
        return self.status._state(utc(day, hour, minute))

    def test_schedule_state_and_next_change(self):
        state = self._state(WEDNESDAY, 10)
        self.assertFalse(state['is_open'])
        self.assertEqual(state['next_change'], PRAGUE.localize(datetime(2030, 6, 5, 15, 0)))
        state = self._state(WEDNESDAY, 16)
        self.assertTrue(state['is_open'])
        self.assertEqual(state['next_change'], PRAGUE.localize(datetime(2030, 6, 5, 19, 0)))

    def test_open_early_lasts_until_schedule_opens(self):
        self.status._set_manual(True, 'odoo', utc(WEDNESDAY, 10))
        state = self._state(WEDNESDAY, 10, 1)
        self.assertTrue(state['is_open'])
        self.assertTrue(state['manual'])
        self.assertEqual(state['manual_until'], PRAGUE.localize(datetime(2030, 6, 5, 15, 0)))
        # otevřeno nepřetržitě, zavře se podle rozvrhu v 19:00
        self.assertEqual(state['next_change'], PRAGUE.localize(datetime(2030, 6, 5, 19, 0)))
        self.assertTrue(self._state(WEDNESDAY, 16)['is_open'])
        self.assertFalse(self._state(WEDNESDAY, 19, 30)['is_open'])

    def test_close_during_hours_and_back_to_schedule(self):
        self.status._set_manual(False, 'odoo', utc(WEDNESDAY, 16))
        state = self._state(WEDNESDAY, 16, 1)
        self.assertFalse(state['is_open'])
        self.assertEqual(state['manual_until'], PRAGUE.localize(datetime(2030, 6, 5, 19, 0)))
        # znovu otevřít během otevírací doby = zpět podle rozvrhu
        self.status._set_manual(True, 'odoo', utc(WEDNESDAY, 17))
        state = self._state(WEDNESDAY, 17, 1)
        self.assertTrue(state['is_open'])
        self.assertFalse(state['manual'])
        self.assertFalse(self.status.manual_state)

    def test_close_before_opening_means_closed_today(self):
        """Dnes už neotevírat: zavřít ve 14:00 platí i pro otevírací dobu 15–19."""
        self.status._set_manual(False, 'odoo', utc(WEDNESDAY, 14))
        self.assertFalse(self._state(WEDNESDAY, 16)['is_open'])
        self.assertEqual(self._state(WEDNESDAY, 16)['manual_until'], PRAGUE.localize(datetime(2030, 6, 5, 19, 0)))
        # další den zase podle rozvrhu
        self.assertTrue(self._state(WEDNESDAY + timedelta(days=1), 16)['is_open'])

    def test_open_on_closed_day_until_midnight(self):
        self.status._set_manual(True, 'odoo', utc(MONDAY, 10))
        state = self._state(MONDAY, 22)
        self.assertTrue(state['is_open'])
        self.assertEqual(state['manual_until'], PRAGUE.localize(datetime(2030, 6, 4, 0, 0)))
        self.assertFalse(self._state(MONDAY + timedelta(days=1), 0, 30)['is_open'])

    def test_website_header_hours_label(self):
        """Předpokládaná doba v hlavičce: dnes do zavření, pak nejbližší otevření."""
        status_model = self.env['opening.hours.status']
        header = status_model._website_header(utc(WEDNESDAY, 10))
        self.assertEqual(header['hours_label'], '15 – 19 h')
        self.assertEqual([day['label'] for day in header['days'][:3]], ['Dnes', 'Zítra', 'Pátek'])
        self.assertTrue(header['days'][0]['is_today'])
        self.assertEqual(header['days'][0]['hours'], '15:00 – 19:00')
        # po zavření zítřek
        self.assertEqual(status_model._website_header(utc(WEDNESDAY, 19, 30))['hours_label'], 'zítra 15 – 19 h')
        # neděle večer: po a út zavřeno, další otevření ve středu
        sunday = WEDNESDAY + timedelta(days=4)
        header = status_model._website_header(utc(sunday, 20))
        self.assertEqual(header['hours_label'], 've středu 15 – 19 h')
        self.assertEqual(header['days'][1]['hours'], 'Zavřeno')
        # celý týden zavřeno
        self.default.line_ids.write({'is_open': False})
        self.assertEqual(status_model._website_header(utc(WEDNESDAY, 10))['hours_label'], 'Tento týden zavřeno')
        # krátce jako na ceduli, minuty jen když nejsou nulové
        self.assertEqual(format_hours_short(15.5, 18.0), '15:30 – 18 h')
        self.assertEqual(format_hours_short(9.0, 24.0), '9 – 24 h')

    def test_ha_report_fields_readonly(self):
        """Co hlásí HA, se v Odoo ručně nemění (jen webhook)."""
        fields_info = self.env['opening.hours.status'].fields_get(['ha_is_open', 'last_update'], ['readonly'])
        self.assertTrue(fields_info['ha_is_open']['readonly'])
        self.assertTrue(fields_info['last_update']['readonly'])

    def test_live_fields(self):
        self.status._set_manual(True, 'odoo')
        self.assertTrue(self.status.is_open_now)
        self.assertTrue(self.status.manual_active)
        self.assertEqual(self.status.state_label, 'Otevřeno')
        self.assertIn('Ručně (Odoo', self.status.state_detail)
        self.status.action_follow_schedule()
        self.assertFalse(self.status.manual_state)

    # -------------------------------------------------------------------------
    # Home Assistant
    # -------------------------------------------------------------------------

    def _open_all_day(self):
        """Výjimka 0–24 včera, dnes a zítra: teď je podle rozvrhu otevřeno (v každé zóně)."""
        today = fields.Date.today()
        for delta in (-1, 0, 1):
            self.env['opening.hours.override'].create({
                'date': today + timedelta(days=delta), 'is_open': True, 'open_time': 0.0, 'close_time': 24.0,
            })

    def test_ha_report_manual_and_confirm(self):
        self._open_all_day()
        status_model = self.env['opening.hours.status']
        # HA ručně zavřel: Odoo převezme jako ručně zavřeno
        self.assertEqual(status_model.update_ha_status(False), 'manual')
        self.assertFalse(self.status._state()['is_open'])
        self.assertEqual(self.status.manual_source, 'ha')
        self.assertFalse(self.status.ha_is_open)
        # HA zase otevřel: zpět podle rozvrhu
        self.assertEqual(status_model.update_ha_status(True), 'manual')
        self.assertTrue(self.status._state()['is_open'])
        self.assertFalse(self.status.manual_state)
        # HA se jen přepnul podle Odoo: potvrzení
        self.assertEqual(status_model.update_ha_status(True), 'confirmed')
        self.assertEqual(len(status_model.search([])), 1)

    def test_ha_stale_report_ignored(self):
        self._open_all_day()
        old = fields.Datetime.now() - timedelta(minutes=20)
        self.assertEqual(self.env['opening.hours.status'].update_ha_status(False, old), 'stale')
        self.assertTrue(self.status._state()['is_open'])
        self.assertFalse(self.status.manual_state)

    def test_ha_state_payload(self):
        self._open_all_day()
        payload = self.status._ha_state()
        self.assertTrue(payload['is_open'])
        self.assertFalse(payload['manual'])
        self.status._set_manual(False, 'odoo')
        payload = self.status._ha_state()
        self.assertFalse(payload['is_open'])
        self.assertTrue(payload['manual_until'].endswith('Z'))


@tagged('post_install', '-at_install')
class TestOpeningHoursHttp(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.status = cls.env.ref('website_opening_hours.opening_hours_status_default')
        cls.env['ir.config_parameter'].sudo().set_str('website_opening_hours.webhook_secret', 'tajne-heslo')
        cls.status._clear_manual()

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
        data = self._get_json('/opening-hours/status')
        self.assertEqual(data['display_status'], 'open')
        self.assertTrue(data['is_open'])
        self.assertTrue(data['today']['is_open'])
        self.assertEqual(data['today']['open_time'], '0:00')
        self.assertEqual(data['today']['close_time'], '24:00')
        self.assertTrue(data['today']['is_override'])
        self.assertIsNone(data['message'])

    def test_status_closed_unexpected(self):
        self._set_today(True)
        self.status._set_manual(False, 'odoo')
        data = self._get_json('/opening-hours/status')
        self.assertEqual(data['display_status'], 'closed_unexpected')
        self.assertEqual(data['scheduled_hours'], '0:00 – 24:00')
        self.assertTrue(data['message'])

    def test_status_open_early(self):
        self._set_today(False, reason='Dovolená')
        self.status._set_manual(True, 'odoo')
        data = self._get_json('/opening-hours/status')
        self.assertEqual(data['display_status'], 'open_early')
        self.assertEqual(data['message'], 'Mimořádně máme otevřeno')
        self.assertEqual(data['today']['reason'], 'Dovolená')

    def test_status_closed(self):
        self._set_today(False)
        data = self._get_json('/opening-hours/status')
        self.assertEqual(data['display_status'], 'closed')
        self.assertIsNone(data['today']['open_time'])

    def test_schedule(self):
        self._set_today(True)
        self.status._set_manual(False, 'odoo')
        schedule = self._get_json('/opening-hours/schedule')
        self.assertEqual(len(schedule), 7)
        dates = [fields.Date.from_string(day['date']) for day in schedule]
        self.assertEqual(dates, [dates[0] + timedelta(days=i) for i in range(7)])
        self.assertEqual(schedule[0]['display_status'], 'closed_unexpected')
        for day in schedule[2:]:
            # bez výjimky platí rozvrh
            self.assertFalse(day['is_override'])
            self.assertIn(day['day_name'], ('Pondělí', 'Úterý', 'Středa', 'Čtvrtek', 'Pátek', 'Sobota', 'Neděle'))

    def test_ha_state(self):
        self._set_today(True)
        result = self.make_jsonrpc_request('/opening-hours/ha-state', {})
        self.assertTrue(result['is_open'])
        self.assertFalse(result['manual'])

    def test_webhook(self):
        self._set_today(True)
        result = self.make_jsonrpc_request('/opening-hours/webhook', {'secret': 'spatne', 'is_open': False})
        self.assertEqual(result['status'], 'error')
        self.status.invalidate_recordset()
        self.assertFalse(self.status.manual_state)

        # ruční zavření v HA převezme Odoo
        result = self.make_jsonrpc_request('/opening-hours/webhook', {
            'secret': 'tajne-heslo', 'is_open': False, 'changed_at': datetime.now(pytz.utc).isoformat(),
        })
        self.assertEqual(result, {'status': 'ok', 'is_open': False, 'result': 'manual'})
        self.status.invalidate_recordset()
        self.assertEqual(self.status.manual_state, 'closed')
        self.assertFalse(self.make_jsonrpc_request('/opening-hours/ha-state', {})['is_open'])

    def test_webhook_secret_in_settings(self):
        """Webhook Secret se nastavuje v Nastavení → Web, ukládá se jako systémový parametr."""
        settings = self.env['res.config.settings'].create({'opening_hours_webhook_secret': 'nove-heslo'})
        settings.execute()
        self.assertEqual(
            self.env['ir.config_parameter'].sudo().get_str('website_opening_hours.webhook_secret'), 'nove-heslo',
        )
        result = self.make_jsonrpc_request('/opening-hours/webhook', {'secret': 'tajne-heslo', 'is_open': True})
        self.assertEqual(result['status'], 'error')

    def test_header_on_every_page(self):
        """Otevírací doba je v hlavičce (v liště i pod ní) s předpokládanou dobou, bez stavu.

        Stav Otevřeno/Zavřeno doplní až JS z /opening-hours/status, server ho nevykreslí.
        """
        self._set_today(True, 10.0, 18.0)
        response = self.url_open('/')
        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn('o_oh_at_nav', html)
        self.assertIn('o_oh_at_strip', html)
        self.assertEqual(html.count('class="o_oh_bar"'), 2)
        self.assertIn('class="o_oh_status_text"></span>', html)
        self.assertNotIn('Otevřeno</span>', html)
        self.assertIn('o_oh_day_today', html)

    def test_snippet_removed(self):
        """Blok pro vkládání do stránek už v nabídce editoru není."""
        arch = self.env.ref('website.snippets').get_combined_arch()
        self.assertNotIn('website_opening_hours.s_opening_hours', arch)
        self.assertFalse(self.env.ref('website_opening_hours.s_opening_hours', raise_if_not_found=False))
