# Website Opening Hours

Otevírací doba obchůdku na webu ranče se živým stavem otevřeno/zavřeno z Home Assistantu.

## Co modul umí

- **Týdenní rozvrh** (`opening.hours`, menu Otevírací doba → Týdenní rozvrh): pro každý den
  otevřeno ano/ne a časy.
- **Výjimky** (`opening.hours.override`, kalendář): svátky, dovolená, akce; přepisují rozvrh na
  konkrétní den, volitelně s důvodem.
- **Stav z Home Assistantu** (`opening.hours.status`, jeden záznam): HA volá webhook při změně
  `input_boolean.obchudek_otevren`.
- **Snippet webu „Otevírací doba“** (blok v editoru webu ve skupině Obsah): lišta se stavem,
  dnešními hodinami a hláškou, po najetí myší nebo kliknutí rozvrh na 7 dní.

Stav na webu kombinuje rozvrh a HA: `open` (otevřeno v otevírací době), `open_early` (HA otevřeno
mimo otevírací dobu, „Už jsme otevřeli dříve“), `closed_unexpected` (v otevírací době HA zavřeno,
omluva a plánované hodiny), `closed`.

## Rozhraní

| cesta | typ | k čemu |
|---|---|---|
| `/opening-hours/status` | GET, JSON | aktuální stav, snippet se ptá každou minutu |
| `/opening-hours/schedule` | GET, JSON | rozvrh na 7 dní od dneška včetně výjimek |
| `/opening-hours/webhook` | POST JSON-RPC, `auth='none'` | HA: `{"secret": "...", "is_open": true/false}` |

Tajný klíč webhooku se nastavuje v menu Otevírací doba → Stav HA. Dokud je prázdný, webhook
přijme cokoli.

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
