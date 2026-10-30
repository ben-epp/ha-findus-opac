# Findus Internet-OPAC for Home Assistant

[Deutsch](README.md) | **English**

Shows the loans of a library card in Home Assistant – books, Tonies, CDs, films – with
due dates, overdue items and a renew button. Works with every library that uses
[Findus Internet-OPAC](https://www.findus-internet-opac.de/go) (230+, e.g.
`alzey.findus-internet-opac.de`).

> Unofficial. This project is not affiliated with Findus or any library.

## How it works

- Findus has **no public API**. The integration logs in to the reader account like a browser
  (form with card number and birth date/password) and parses the HTML page. If Findus changes
  its page layout, the parser (`client.py`) needs an update.
- Findus is a hosted mirror of the library's actual system (OCLC Bibliotheca or Winbiap).
  The library uploads its data **several times a day**, so data in Home Assistant can be a few
  hours old. Polling more often gains nothing.
- Renewing is a **renewal request** ("Verlängerungsantrag") in Findus. The new due date may
  only appear after the library's next sync. The integration therefore reports each item as
  `renewed` (new date already visible) or `requested` (request submitted) and checks again
  after 30 minutes.
- Renewal only works when the library allows it – usually **from 14 days before the due date**,
  not for reserved items and not after the maximum number of renewals. The reason is in the
  item's `note` attribute.

## Installation

### HACS (custom repository)

1. Open HACS → menu (⋮) → **Custom repositories**.
2. Add `https://github.com/OWNER/REPO`, category **Integration**.
3. Download **Findus Internet-OPAC** and restart Home Assistant.

HACS only works with GitHub. If you develop elsewhere (e.g. Forgejo), a push mirror to GitHub is enough.

### Manual

Copy `custom_components/findus_opac` into Home Assistant's `config/custom_components/` and restart.

## Setup

**Settings → Devices & services → Add integration → Findus Internet-OPAC**

| Field | Example | Note |
|---|---|---|
| Account name | `Lena` | Free display name, e.g. one per family member |
| Library subdomain | `alzey` | Part before `.findus-internet-opac.de`; a full URL works too |
| Card number | `12345678` | Number next to the barcode on the card |
| Birth date or password | `01.01.2015` | As on the library website |

Several cards = several entries. If the library later rejects the credentials, Home Assistant
asks for the new password.

### Options

| Option | Default | Meaning |
|---|---|---|
| Update interval | 6 h | Hours between checks (1–24) |
| Due soon window | 3 days | Items due within this many days |

## Entities

One device per account with these entities (entity IDs start with the account name):

| Entity | Type | Content |
|---|---|---|
| Loans | Sensor | Number of loans; attribute `items` with all items |
| Books, Tonies, CDs, Videos, Games | Sensor | Count per category (incl. `items`) |
| Next due date | Sensor (date) | Earliest due date |
| Days until next due | Sensor | Days until the next due date (negative = overdue) |
| Due today / Due soon / Overdue | Sensor | Number of items |
| Renewable | Sensor | Number of items renewable right now |
| Overdue items | Binary sensor | on when anything is overdue |
| Renewal possible | Binary sensor | on when at least one item can be renewed |
| Renew all | Button | Submits the renewal request for all renewable items |

Each entry in `items` has: `mednr`, `title`, `author`, `media_type`, `category`
(`book`, `tonie`, `cd`, `video`, `game`), `due`, `days_left`, `renewable`, `note`.
The media type comes from the library (e.g. "Kinder- und Jugendliteratur") and is mapped to a
category by keyword; anything unknown counts as a book.

## Service and event

### `findus_opac.renew`

```yaml
action: findus_opac.renew
data:
  config_entry_id: 0123456789abcdef0123456789abcdef
  media_ids:            # optional; empty = everything renewable
    - "0900000101"
```

### Event `findus_opac_renewal`

Fired after every renewal attempt (button or service):

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

## Automations

**Reminder 2 days before the due date:**

```yaml
automation:
  - alias: Library – due in 2 days
    triggers:
      - trigger: numeric_state
        entity_id: sensor.lena_days_until_next_due
        below: 3
    actions:
      - action: notify.mobile_app_phone
        data:
          title: Library
          message: >
            {{ states('sensor.lena_loans') }} items, next due
            {{ states('sensor.lena_next_due_date') }}.
```

**Renew automatically as soon as possible:**

```yaml
automation:
  - alias: Library – auto renew
    triggers:
      - trigger: state
        entity_id: binary_sensor.lena_renewal_possible
        to: "on"
    actions:
      - action: button.press
        target:
          entity_id: button.lena_renew_all
```

**Notify after renewing:**

```yaml
automation:
  - alias: Library – renewal reported
    triggers:
      - trigger: event
        event_type: findus_opac_renewal
    actions:
      - action: notify.mobile_app_phone
        data:
          title: "Library: {{ trigger.event.data.account_name }}"
          message: >
            {% for i in trigger.event.data['items'] %}
            {{ i.title }}: {{ 'renewed until ' ~ i.new_due if i.status == 'renewed'
               else 'request submitted' }}
            {% endfor %}
```

Entity IDs depend on the account name and system language – check the device page.

## Loan list as a Markdown card

```yaml
type: markdown
title: Library
content: >
  {% set items = state_attr('sensor.lena_loans', 'items') or [] %}
  {% if not items %}No loans. 🎉{% endif %}
  {% for i in items %}
  {% if i.days_left < 0 %}<font color="red">**{{ i.title }}**</font>
  {% else %}**{{ i.title }}**{% endif %} · {{ i.media_type }}<br>
  due {{ as_timestamp(i.due) | timestamp_custom('%d.%m.%Y') }}
  ({% if i.days_left < 0 %}<font color="red">{{ -i.days_left }} days overdue</font>
  {% elif i.days_left == 0 %}today{% else %}in {{ i.days_left }} days{% endif %})
  {% if i.renewable %} · 🔄 renewable{% elif i.note %} · <small>{{ i.note }}</small>{% endif %}

  {% endfor %}
```

## Privacy

- Card number and birth date/password are stored in Home Assistant's config entry
  (`.storage/core.config_entries`), like any other integration's credentials.
- Only the Findus servers of the configured library are contacted.
- The diagnostics download (device → Download diagnostics) redacts credentials and form fields.

## License

MIT – see [LICENSE](LICENSE).
