# Findus Internet-OPAC für Home Assistant

**Deutsch** | [English](README.en.md)

Zeigt die Ausleihen eines Bibliotheksausweises in Home Assistant an – Bücher, Tonies,
CDs, Filme – mit Rückgabefristen, überfälligen Medien und einem Button zum Verlängern.
Funktioniert mit allen Büchereien, die [Findus Internet-OPAC](https://www.findus-internet-opac.de/go)
nutzen (über 230, z. B. `alzey.findus-internet-opac.de`).

> Kein offizielles Produkt. Dieses Projekt steht in keiner Verbindung zu Findus oder den Büchereien.

## Wie es funktioniert

- Findus hat **keine öffentliche API**. Die Integration meldet sich wie ein Browser im
  Leserkonto an (Formular mit Ausweisnummer und Geburtsdatum/Passwort) und liest die
  HTML-Seite aus. Ändert Findus das Seitenlayout, muss der Parser (`client.py`) angepasst werden.
- Findus ist ein gehosteter Spiegel des eigentlichen Büchereiprogramms (Bibliotheca von OCLC
  oder Winbiap). Die Bücherei lädt ihre Daten **mehrmals täglich** hoch – die Daten in
  Home Assistant können also einige Stunden alt sein. Häufigeres Abfragen bringt nichts.
- Verlängern ist bei Findus ein **Verlängerungsantrag**. Die neue Leihfrist erscheint
  eventuell erst nach dem nächsten Abgleich der Bücherei. Die Integration meldet deshalb
  pro Medium entweder `renewed` (neue Frist schon sichtbar) oder `requested` (Antrag gestellt)
  und prüft nach 30 Minuten erneut.
- Verlängern ist nur möglich, wenn die Bücherei es zulässt – typischerweise erst
  **14 Tage vor der Rückgabefrist**, nicht bei vorbestellten Medien und nicht nach der
  maximalen Anzahl an Verlängerungen. Der Grund steht im Attribut `note` des Mediums.
- Die Leihfrist hängt von der Medienart ab (Tonies und CDs meist kürzer als Bücher).
  Jedes Medium hat seine eigene Frist; Verlängern und Auto-Verlängern behandeln jedes
  Medium einzeln nach seinem eigenen Rückgabedatum.

## Installation

### HACS (benutzerdefiniertes Repository)

1. HACS öffnen → Menü (⋮) → **Benutzerdefinierte Repositories**.
2. `https://github.com/OWNER/REPO` eintragen, Kategorie **Integration**.
3. **Findus Internet-OPAC** herunterladen und Home Assistant neu starten.

HACS funktioniert nur mit GitHub. Wird das Projekt woanders entwickelt (z. B. Forgejo),
reicht ein Push-Mirror nach GitHub.

### Manuell

`custom_components/findus_opac` in den Ordner `config/custom_components/` von Home Assistant
kopieren und neu starten.

## Einrichtung

**Einstellungen → Geräte & Dienste → Integration hinzufügen → Findus Internet-OPAC**

| Feld | Beispiel | Hinweis |
|---|---|---|
| Kontoname | `Lena` | Freier Anzeigename, z. B. pro Familienmitglied |
| Bücherei-Subdomain | `alzey` | Teil vor `.findus-internet-opac.de`; eine komplette URL geht auch |
| Ausweisnummer | `12345678` | Nummer neben dem Barcode auf dem Ausweis |
| Geburtsdatum oder Passwort | `01.01.2015` | Wie auf der Webseite der Bücherei |

Mehrere Ausweise = mehrere Einträge. Lehnt die Bücherei die Zugangsdaten später ab,
fragt Home Assistant automatisch nach dem neuen Passwort.

### Optionen

| Option | Standard | Bedeutung |
|---|---|---|
| Aktualisierungsintervall | 6 h | Stunden zwischen zwei Abfragen (1–24) |
| Zeitraum für „bald fällig“ | 3 Tage | Medien, die innerhalb dieser Tage fällig sind |
| Automatisch verlängern | aus | Verlängerbare Medien automatisch beantragen, wenn sie bald fällig sind |
| Zeitraum für automatisches Verlängern | 2 Tage | Medien, die innerhalb dieser Tage fällig sind (0 = erst am Rückgabetag) |
| Nur automatisch verlängern | alle | Auf Medienarten beschränken, z. B. nur Tonies und CDs |
| Benachrichtigen | – | Notify-Dienste, z. B. `mobile_app_mein_handy`; leer = keine Benachrichtigungen |
| Uhrzeit der Benachrichtigung | 08:00 | Wann die tägliche Fristen-Übersicht kommt |
| Benachrichtigen bei | alle | Bald fällig, heute fällig, überfällig, Verlängerung, Ausweis läuft ab |

### Automatisch verlängern

Ist die Option aktiv, prüft die Integration bei jeder Aktualisierung, welche Medien
verlängerbar sind und innerhalb des eingestellten Zeitraums fällig werden, und stellt für
genau diese den Verlängerungsantrag. Pro Medium und Rückgabedatum wird nur **einmal**
beantragt – ein noch nicht verarbeiteter Antrag wird nicht bei jeder Abfrage erneut gestellt.
Ändert sich die Frist (verlängert), beginnt das Spiel beim nächsten Mal von vorn.

Hinweise:

- Die Bücherei öffnet die Verlängerung erst kurz vor Fristende (oft **14 Tage**
  vorher). Ein Zeitraum größer als dieses Fenster bringt nichts.
- Weil Tonies/CDs kürzere Leihfristen als Bücher haben, werden sie meist zu anderen
  Zeitpunkten verlängert – das passiert automatisch, jedes Medium für sich.
- Fehler beim automatischen Verlängern brechen die Aktualisierung nicht ab, sie landen
  als Warnung im Log. Jeder Versuch löst das Ereignis `findus_opac_renewal` mit
  `trigger: auto` aus – ideal für eine Benachrichtigung.

## Entitäten

Pro Konto ein Gerät mit diesen Entitäten (Entity-IDs beginnen mit dem Kontonamen):

| Entität | Typ | Inhalt |
|---|---|---|
| Ausleihen | Sensor | Anzahl aller Ausleihen; Attribut `items` mit allen Medien |
| Bücher, Tonies, CDs, Filme, Spiele | Sensor | Anzahl je Medienart (inkl. `items`) |
| Nächste Rückgabe | Sensor (Datum) | Frühestes Rückgabedatum |
| Tage bis zur Rückgabe | Sensor | Tage bis zur nächsten Rückgabe (negativ = überfällig) |
| Heute fällig / Bald fällig / Überfällig | Sensor | Anzahl Medien |
| Verlängerbar | Sensor | Anzahl aktuell verlängerbarer Medien |
| Ausweis gültig bis | Sensor | Ablaufdatum aus dem Hinweis im Leserkonto („Ihr Ausweis ist gültig bis …“); Attribut `days_left` |
| Ausweis läuft bald ab | Binärsensor | An ab 30 Tagen vor Ablauf; unbekannt, wenn die Seite kein Datum zeigt |
| Überfällige Medien | Binärsensor | an, wenn etwas überfällig ist |
| Verlängerung möglich | Binärsensor | an, wenn mindestens ein Medium verlängert werden kann |
| Alle verlängern | Button | Stellt den Verlängerungsantrag für alle verlängerbaren Medien |
| Jetzt abgleichen | Button (Diagnose) | Liest das Leserkonto sofort neu ein |

„Jetzt abgleichen“ fragt Findus sofort ab. Findus selbst hat aber nur den Stand, den die
Bücherei zuletzt hochgeladen hat – eine gerade am Tresen zurückgegebene Tonie-Box kann
also noch ein paar Stunden in der Liste stehen.

Jedes Element in `items` hat: `mednr`, `title`, `author`, `media_type`, `category`
(`book`, `tonie`, `cd`, `video`, `game`), `due`, `days_left`, `renewable`, `note`, `cover` (Cover-URL oder leer).
`cover` ist das Coverbild, das Findus selbst anzeigt (Tonies über den mycover-Dienst per EAN,
Bücher über den Buchhandels-Coverdienst per ISBN).
Die Medienart kommt von der Bücherei (z. B. „Kinder- und Jugendliteratur“) und wird
per Stichwort einer Kategorie zugeordnet; alles Unbekannte zählt als Buch.

## Dienst und Ereignis

### `findus_opac.renew`

```yaml
action: findus_opac.renew
data:
  config_entry_id: 0123456789abcdef0123456789abcdef
  media_ids:            # optional; leer = alles Verlängerbare
    - "0900000101"
```

Nur bestimmte Medienarten verlängern (`book`, `tonie`, `cd`, `video`, `game`):

```yaml
action: findus_opac.renew
data:
  config_entry_id: 0123456789abcdef0123456789abcdef
  categories:
    - tonie
    - cd
```

Werden `media_ids` und `categories` zusammen angegeben, gilt beides. Nicht verlängerbare
Medien werden immer übersprungen. Mit `response_variable` liefert der Dienst die Ergebnisse
zurück (gleiche `items` wie im Ereignis).

### Ereignis `findus_opac_renewal`

Wird nach jedem Verlängerungsversuch ausgelöst – über Button, Dienst, Karte
(`trigger: manual`) oder das automatische Verlängern (`trigger: auto`):

```json
{
  "config_entry_id": "0123456789abcdef0123456789abcdef",
  "account_name": "Lena",
  "trigger": "auto",
  "items": [
    {"mednr": "0900000101", "title": "Der kleine Drache", "old_due": "2026-11-06",
     "new_due": "2026-12-04", "status": "renewed"},
    {"mednr": "0900000102", "title": "Lieder zum Mitsingen", "old_due": "2026-11-08",
     "new_due": "2026-11-08", "status": "requested"}
  ]
}
```

## Benachrichtigungen

Die Integration benachrichtigt selbst – ohne eigene Automation. Einschalten unter
**Einstellungen → Geräte & Dienste → Findus → Konfigurieren**: bei „Benachrichtigen“ einen
oder mehrere Notify-Dienste wählen (z. B. `mobile_app_mein_handy` der Companion-App), eine
Uhrzeit und die gewünschten Anlässe.

Jeden Tag zur eingestellten Uhrzeit gleicht die Integration das Konto ab und schickt **eine**
Nachricht pro Konto – nur wenn es etwas Neues gibt. War Home Assistant zur Uhrzeit aus oder
im Neustart, kommt die Übersicht gleich nach dem Start nach (einmal pro Tag):

| Anlass | Wann | Wie oft |
|---|---|---|
| Bald fällig | innerhalb des Zeitraums „bald fällig“ (Standard 3 Tage) | einmal je Medium und Rückgabedatum |
| Heute fällig | am Rückgabetag | einmal je Medium und Rückgabedatum |
| Überfällig | nach dem Rückgabetag | täglich, bis das Medium zurück ist |
| Verlängerung | sofort nach einer (auch automatischen) Verlängerung | jedes Mal |
| Ausweis läuft ab | 30 und 7 Tage vor Ablauf des Ausweises | je einmal |

Beispiel:

```text
Bücherei: Kinder
Überfällig seit 2 Tagen: Wieso? Weshalb? Warum? – Wale & Delfine
Heute fällig: Der kleine Drache (verlängerbar)
Fällig am So., 8.11.: Lieder zum Mitsingen (verlängerbar)
```

Wird ein Medium verlängert und bekommt dadurch ein neues Rückgabedatum, wird es zum neuen
Datum wieder gemeldet. Was schon gemeldet wurde, merkt sich die Integration auch über
Neustarts hinweg.

**Knopf „Verlängern“ in der Benachrichtigung:** an Companion-App-Geräte
(`mobile_app_…`, Android und iOS) kommt die Nachricht mit einem Knopf „Verlängern“, wenn
darin verlängerbare Medien stehen. Ein Tipp darauf beantragt die Verlängerung für alle
gerade verlängerbaren Medien; das Ergebnis kommt als eigene Nachricht. Andere Notify-Dienste
(E-Mail, Telegram, …) bekommen nur den Text.

## Automationen

Für Fristen und Verlängerungen braucht es keine Automation mehr: siehe
[Benachrichtigungen](#benachrichtigungen) und [Automatisch verlängern](#automatisch-verlängern).
Für eigene Abläufe stehen alle Sensoren und das Ereignis `findus_opac_renewal` bereit, z. B.
eine Sprachansage am Vorabend:

```yaml
automation:
  - alias: Bücherei – morgen fällig ansagen
    triggers:
      - trigger: time
        at: "18:30:00"
    conditions:
      - condition: numeric_state
        entity_id: sensor.lena_tage_bis_zur_ruckgabe
        below: 2
    actions:
      - action: tts.speak
        target:
          entity_id: tts.home_assistant_cloud
        data:
          media_player_entity_id: media_player.kueche
          message: >
            Morgen müssen {{ states('sensor.lena_bald_fallig') }} Medien zur Bücherei.
```

Die Entity-IDs hängen vom Kontonamen und der Systemsprache ab – auf der Geräteseite nachsehen.

## Dashboard-Karte

Die Integration bringt eine eigene Karte mit und registriert sie selbst – keine
Ressource eintragen, kein extra HACS-Frontend-Paket. Nach dem Neustart taucht sie im
Karten-Dialog als **„Findus Bibliothek“** auf und wählt den Ausleihen-Sensor automatisch.

- Coverbild je Medium (fehlt es, erscheint das Symbol der Medienart)
- Rückgabedatum mit „heute“, „in 2 Tagen“, rot bei überfälligen, orange bei bald fälligen Medien
- Abzeichen „verlängerbar“ und ein Verlängern-Symbol **pro Medium**
- Knopf „N verlängern“ für alle verlängerbaren Medien
- Abgleich-Symbol im Kopf („Jetzt abgleichen“)

```yaml
type: custom:findus-opac-card
entity: sensor.lena_ausleihen
title: Lenas Bücherei     # optional, Standard: Kontoname
show_renew: true          # Verlängern-Knöpfe anzeigen
show_covers: true         # Coverbilder anzeigen
max_items: 0              # 0 = alle
warn_days: 3              # orange ab so vielen Tagen vor der Rückgabe
group_by: due             # due (Rückgabedatum) | category (Medienart) | none – aufklappbare Gruppen
max_height: 400           # Listenhöhe in px, darüber scrollbar; 0 = keine Begrenzung
```

Die Cover lädt der Browser des Betrachters direkt von den Cover-Servern von Findus
(`mycover.findus-internet-opac.de`, `covers-buchhandel-de.findus-internet-opac.de`);
Zugangsdaten werden dabei nicht übertragen. Wer das nicht möchte: `show_covers: false`.

Nach einem Update der Integration ggf. den Browser-Cache leeren (Strg+Umschalt+R).

## Ausleihliste als Markdown-Karte

Alternativ ohne eigene Karte, nur mit Bordmitteln:

```yaml
type: markdown
title: Bücherei
content: >
  {% set items = state_attr('sensor.lena_ausleihen', 'items') or [] %}
  {% if not items %}Keine Ausleihen. 🎉{% endif %}
  {% for i in items %}
  {% if i.days_left < 0 %}<font color="red">**{{ i.title }}**</font>
  {% else %}**{{ i.title }}**{% endif %} · {{ i.media_type }}<br>
  fällig {{ as_timestamp(i.due) | timestamp_custom('%d.%m.%Y') }}
  ({% if i.days_left < 0 %}<font color="red">{{ -i.days_left }} Tage überfällig</font>
  {% elif i.days_left == 0 %}heute{% else %}in {{ i.days_left }} Tagen{% endif %})
  {% if i.renewable %} · 🔄 verlängerbar{% elif i.note %} · <small>{{ i.note }}</small>{% endif %}

  {% endfor %}
```

## Symbol

Das Fuchs-Symbol ist eine eigene Zeichnung (`images/fox.svg`) und **nicht** das Logo von
Findus. Neuere Home-Assistant-Versionen zeigen es automatisch an (Ordner `brand/`).

## Datenschutz

- Ausweisnummer und Geburtsdatum/Passwort liegen im Konfigurationseintrag von Home Assistant
  (`.storage/core.config_entries`), wie bei anderen Integrationen auch.
- Es werden nur die Findus-Server der eingestellten Bücherei abgefragt.
- Die Diagnose-Datei (Gerät → Diagnose herunterladen) schwärzt Zugangsdaten und Formularfelder.

## Lizenz

MIT – siehe [LICENSE](LICENSE).
