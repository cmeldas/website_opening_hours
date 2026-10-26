# Website Opening Hours

Otevírací doba obchůdku ranče: rozvrhy, výjimky a ruční otevření/zavření v Odoo, stav na webu
a v Home Assistantu. **Odoo je zdroj pravdy**, Home Assistant se podle něj přepíná.

## Co modul umí

Menu **Otevírací doba**:

- **Stav obchůdku**: teď otevřeno/zavřeno a proč, dnešní hodiny, další změna, co naposledy
  hlásil Home Assistant. Tlačítka **Otevřít**, **Zavřít**, **Dnes už neotevírat** a **Zpět podle
  rozvrhu** (vidí je každý přihlášený uživatel).
- **Rozvrhy** (`opening.hours.schedule`, jen správce): výchozí rozvrh bez dat („Celoročně“)
  a sezónní rozvrhy na rozmezí dat, volitelně **každý rok** (zima 1. 11. – 31. 3. přes Nový
  rok). Každý rozvrh má 7 dnů s otevřeno ano/ne a časy (`opening.hours`). Nový rozvrh začíná
  kopií dnů výchozího.
- **Výjimky (dny)** (`opening.hours.override`, kalendář): svátky, dovolená, akce na konkrétní den.

Co platí pro den: **výjimka** → **sezónní rozvrh**, do jehož rozmezí den spadá (při překryvu
ten s kratším rozmezím, tedy Vánoce před zimou) → **výchozí rozvrh**. Nad tím **ruční stav**:

| akce | platí do |
|---|---|
| Otevřít v 10:00, rozvrh 15–19 | 15:00, pak podle rozvrhu, tedy otevřeno nepřetržitě do 19:00 |
| Zavřít v 16:00, rozvrh 15–19 | 19:00 |
| Dnes už neotevírat ve 14:00, rozvrh 15–19 | 19:00 (dnes zavřeno) |
| Otevřít ve zavřený den | konec dne |
| Otevřít, když je ručně zavřeno v otevírací době | ruční stav se zruší, zpět podle rozvrhu |

Ruční stav vždy platí nejdéle do konce dne. Časy jsou v pásmu firmy (výchozí Europe/Prague).

**Snippet webu „Otevírací doba“** (blok v editoru webu ve skupině Obsah): lišta se stavem,
dnešními hodinami a hláškou; rozvrh na 7 dní po najetí myší nebo klepnutím na lištu, dalším
klepnutím (i na rozvrh) se schová. Na mobilu se rozvrh ukazuje jen klepnutím (dřív po
klepnutí zůstal viset, protože `:hover` na dotykovém displeji trvá).

Stavy na webu: `open` (otevřeno podle rozvrhu), `open_early` (ručně otevřeno mimo otevírací
dobu: „Už jsme otevřeli dříve“ před dnešním otevřením, jinak „Mimořádně máme otevřeno“),
`closed_unexpected` (ručně zavřeno v otevírací době, omluva a plánované hodiny), `closed`.

## Home Assistant

HA nemá vlastní otevírací dobu (plánovač/scheduler se na obchůdek nepoužívá), řídí ho Odoo:

1. **Odoo → HA**: blueprint `ha_config/blueprints/automation/odoo_opening_hours_follow.yaml`
   se každou minutu ptá na `/opening-hours/ha-state` a přepíná `input_boolean.obchudek_otevren`.
   Změnu udělanou v HA za poslední 3 minuty nechá být, než ji webhook nahlásí Odoo.
2. **HA → Odoo**: blueprint `odoo_opening_hours.yaml` při každé změně `obchudek_otevren`
   volá `/opening-hours/webhook`. Když HA jen následoval Odoo, je to potvrzení. Když někdo
   přepnul obchůdek v HA (dashboard, notifikace „Zavřít obchůdek“), Odoo to převezme jako
   ruční otevření/zavření (stejně jako tlačítka), aby ho HA při příštím dotazu nevrátil.
   Hlášení starší než 10 minut (opakování po výpadku Odoo) se za ruční změnu nepovažuje.

Když Odoo neběží, HA nechá stav, jak je, a obchůdek jde přepínat ručně v HA.

### Přechod z plánovače HA

1. Nasadit modul 20.0.2.0.0 (aktualizace převede týdenní rozvrh na výchozí rozvrh „Celoročně“).
2. V Odoo zkontrolovat Rozvrhy, případně založit sezónní (zima, léto) a výjimky.
3. Do HA nahrát oba blueprinty z `ha_config` (`/config/blueprints/automation/`), znovu
   načíst automatizace. Stávající automatizace „Webhook - Odoo openning hours“ použije nový
   `odoo_opening_hours.yaml` sama (vyplněný Webhook Secret, stejný jako v Odoo).
4. Založit automatizaci z blueprintu „Odoo Opening Hours – follow Odoo“ (Odoo URL
   `http://192.168.100.9:8069`).
5. **Smazat (nebo vypnout) rozvrhy plánovače** pro obchůdek („Otevírací doba obchůdku týden“
   a další), jinak by s Odoo soupeřily.

## Rozhraní

| cesta | typ | k čemu |
|---|---|---|
| `/opening-hours/status` | GET, JSON | aktuální stav, snippet se ptá každou minutu |
| `/opening-hours/schedule` | GET, JSON | rozvrh na 7 dní od dneška včetně výjimek |
| `/opening-hours/ha-state` | POST JSON-RPC, `auth='none'` | HA: `{"is_open", "scheduled_open", "manual", "manual_until", "next_change"}` (UTC) |
| `/opening-hours/webhook` | POST JSON-RPC, `auth='none'` | HA: `{"secret": "...", "is_open": true/false, "changed_at": "ISO"}` → `{"status", "is_open", "result": "confirmed"/"manual"/"stale"}` |

Tajný klíč webhooku se nastavuje v Stav obchůdku (vidí ho jen správce). Dokud je prázdný,
webhook přijme cokoli. `ha-state` klíč nechce, stav je veřejný (ukazuje ho i web).

## Test

```
odoo -d <db> -i website_opening_hours --test-enable --test-tags /website_opening_hours --stop-after-init
```

Modely (rozvrhy, sezóny přes Nový rok, přednosti, přechod na zimní čas, ruční stav a jeho
konec, hlášení z HA včetně starého), JSON trasy, webhook, `ha-state`, registrace snippetu.

## 20.0.2.0.0

Rozvrhy místo jednoho týdenního rozvrhu, ruční otevření/zavření v Odoo, HA řízený z Odoo,
oprava schovávání rozvrhu na mobilu. `migrations/20.0.2.0.0/post-migrate.py` přiřadí stávajících
7 dnů k výchozímu rozvrhu „Celoročně“ (založí ho data modulu); NOT NULL na `schedule_id` doplní
Odoo až po skriptu, unikátnost dne je teď v rámci rozvrhu. Ověřeno na kopii produkce `db20`.

## Odoo 20

Port z 19.0.1.0.0 na **20.0.1.1.0** (větev `20.0`).

- **Práva**: `security/ir.model.access.csv` → `security/ir.access.csv` (Odoo 20 zrušilo
  `ir.model.access` a `ir.rule`, nový model `ir.access` se sloupci `operation` a `domain`).
  XML ID zůstala stejná, práva taky (správce `crud`, veřejnost `r`).
- **JS snippetu**: Odoo 20 už nemá `publicWidget` (`@web/legacy/js/public/public_widget`), skript
  je přepsaný na `Interaction` (`@web/public/interaction`), registrace
  `public.interactions` + `public.interactions.edit`/`preview`. Chování na webu je stejné, třídy
  a HTML snippetu se nezměnily (snippet je uložený přímo ve stránkách webu).
  - Selektor `.s_opening_hours` + `selectorHas: .s_opening_hours_widget`: core Odoo má vlastní
    blok `website.s_opening_hours` se stejnou třídou, ten se teď nechytí.
  - Po načtení stránky se nejdřív vyčistí obsah uložený editorem a ukáže se stav „načítání“, pak
    živá data. V 19 se do stránky ukládal vykreslený stav a po načtení chvíli svítil starý.
  - Při zastavení (vstup do editoru, uložení stránky) interakce vrátí lištu a rozvrh do stavu
    šablony, takže editor ukládá čistý snippet. Ověřeno v prohlížeči: po uložení stránky
    v editoru je v databázi jen kostra snippetu.
  - V editoru webu běží taky (živý stav), ale bez klikání a vykreslené části nejsou editovatelné.
- **Webhook** má `readonly=False`: trasy `auth='none'` jsou v 19 i 20 ve výchozím stavu jen pro
  čtení. Bez repliky databáze (produkce) to nevadí, kurzor je stejně pro zápis, ale v testech
  (a s replikou) zápis stavu končil chybou `cannot execute UPDATE in a read-only transaction`
  a Odoo ho opakovalo s jiným kurzorem.
- **Oprava chyby z 19**: kontrola časů volala `models.ValidationError`, který neexistuje
  (`AttributeError` místo hlášky). Teď `odoo.exceptions.ValidationError` a kontrola hlídá i
  přepnutí `is_open`.
- **Testy** (`tests/`, nové): modely, JSON trasy, webhook, registrace snippetu.

### Migrace dat 19 → 20

Tabulky modulu se nemění (schéma `opening_hours*` v 20 je stejné jako na produkci 19), data
zůstávají. `migrations/20.0.1.1.0/pre-migrate.py` jen smaže z `ir_model_data` stará XML ID práv
tohoto modulu s modelem `ir.model.access`/`ir.rule`, kdyby je nesmazala obecná migrace základu;
jinak by načtení `ir.access.csv` spadlo na „found record of different model“. Ověřeno simulací
aktualizace z 19.0.1.0.0.

Při migraci přes OpenUpgrade (`c:\git_my\openupgrade`, větev 20.0) stará XML ID práv maže už
`base/20.0.1.3/pre-migration.py` (`_ir_access_xmlids`, předtím si je uloží do zálohové tabulky).
Skript modulu pak nic nenajde a nic nedělá; potřebný je jen při aktualizaci bez OpenUpgrade.
Na produkci (dump 6. 10. 2026) jde o 6 XML ID, všechna práva aktivní, žádná vlastní práva ani
pravidla na modelech modulu, takže převod nic neztratí.

Snippety uložené ve stránkách produkce (domovská stránka, Sýrárna, produkty) obsahují vykreslený
stav z 19. Nevadí: interakce ho po načtení přepíše a při příštím uložení stránky v editoru se
uloží čistá kostra.
