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
| Überfällige Medien | Binärsensor | an, wenn etwas überfällig ist |
| Verlängerung möglich | Binärsensor | an, wenn mindestens ein Medium verlängert werden kann |
| Alle verlängern | Button | Stellt den Verlängerungsantrag für alle verlängerbaren Medien |

Jedes Element in `items` hat: `mednr`, `title`, `author`, `media_type`, `category`
(`book`, `tonie`, `cd`, `video`, `game`), `due`, `days_left`, `renewable`, `note`, `cover` (Cover-URL oder leer).
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

### Ereignis `findus_opac_renewal`

Wird nach jedem Verlängerungsversuch (Button oder Dienst) ausgelöst:

```json
{
  "config_entry_id": "0123456789abcdef0123456789abcdef",
  "account_name": "Lena",
  "items": [
    {"mednr": "0900000101", "title": "Der kleine Drache", "old_due": "2026-11-06",
     "new_due": "2026-12-04", "status": "renewed"},
    {"mednr": "0900000102", "title": "Lieder zum Mitsingen", "old_due": "2026-11-08",
     "new_due": "2026-11-08", "status": "requested"}
  ]
}
```

## Automationen

**Erinnerung 2 Tage vor der Rückgabe:**

```yaml
automation:
  - alias: Bücherei – Rückgabe in 2 Tagen
    triggers:
      - trigger: numeric_state
        entity_id: sensor.lena_tage_bis_zur_ruckgabe
        below: 3
    actions:
      - action: notify.mobile_app_handy
        data:
          title: Bücherei
          message: >
            {{ states('sensor.lena_ausleihen') }} Medien, nächste Rückgabe am
            {{ states('sensor.lena_nachste_ruckgabe') }}.
```

**Automatisch verlängern, sobald es möglich ist:**

```yaml
automation:
  - alias: Bücherei – automatisch verlängern
    triggers:
      - trigger: state
        entity_id: binary_sensor.lena_verlangerung_moglich
        to: "on"
    actions:
      - action: button.press
        target:
          entity_id: button.lena_alle_verlangern
```

**Benachrichtigung nach dem Verlängern:**

```yaml
automation:
  - alias: Bücherei – Verlängerung gemeldet
    triggers:
      - trigger: event
        event_type: findus_opac_renewal
    actions:
      - action: notify.mobile_app_handy
        data:
          title: "Bücherei: {{ trigger.event.data.account_name }}"
          message: >
            {% for i in trigger.event.data['items'] %}
            {{ i.title }}: {{ 'verlängert bis ' ~ i.new_due if i.status == 'renewed'
               else 'Antrag gestellt' }}
            {% endfor %}
```

Die Entity-IDs hängen vom Kontonamen und der Systemsprache ab – auf der Geräteseite nachsehen.

## Ausleihliste als Markdown-Karte

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

## Datenschutz

- Ausweisnummer und Geburtsdatum/Passwort liegen im Konfigurationseintrag von Home Assistant
  (`.storage/core.config_entries`), wie bei anderen Integrationen auch.
- Es werden nur die Findus-Server der eingestellten Bücherei abgefragt.
- Die Diagnose-Datei (Gerät → Diagnose herunterladen) schwärzt Zugangsdaten und Formularfelder.

## Lizenz

MIT – siehe [LICENSE](LICENSE).
