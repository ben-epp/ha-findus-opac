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
- Loan periods depend on the media type (Tonies and CDs are usually shorter than books).
  Every item has its own due date; renewing and auto-renew handle each item on its own date.

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
| Auto-renew | off | Automatically request renewal for renewable items that are due soon |
| Auto-renew window | 2 days | Items due within this many days (0 = only on the due date) |
| Auto-renew only | all | Restrict to media types, e.g. only Tonies and CDs |

### Auto-renew

When enabled, every update checks which items are renewable and due within the window, and
submits the renewal request for exactly those. Each item is requested **once per due date** –
a request the library hasn't processed yet is not resent on every poll. Once the due date
moves, the item is eligible again next time.

Notes:

- The library only opens renewal shortly before the due date (often **14 days** before).
  A window larger than that gains nothing.
- Tonies/CDs have shorter loan periods than books, so they are usually renewed at different
  times – that happens automatically, item by item.
- Auto-renew errors never fail the update; they are logged as warnings. Every attempt fires
  `findus_opac_renewal` with `trigger: auto` – handy for a notification.

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
| Library card valid until | Sensor | Expiry date from the account banner ("Ihr Ausweis ist gültig bis …"); attribute `days_left` |
| Library card expires soon | Binary sensor | On 30 days before the card expires; unknown if the page shows no expiry |
| Overdue items | Binary sensor | on when anything is overdue |
| Renewal possible | Binary sensor | on when at least one item can be renewed |
| Renew all | Button | Submits the renewal request for all renewable items |
| Sync now | Button (diagnostic) | Re-reads the reader account immediately |

"Sync now" queries Findus right away. Findus itself only has what the library last uploaded,
so a Tonie just returned at the desk may stay in the list for a few more hours.

Each entry in `items` has: `mednr`, `title`, `author`, `media_type`, `category`
(`book`, `tonie`, `cd`, `video`, `game`), `due`, `days_left`, `renewable`, `note`, `cover` (cover image URL or empty).
`cover` is the cover image Findus itself shows (Tonies via the mycover service by EAN, books via
the book trade cover service by ISBN).
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

Renew only certain media types (`book`, `tonie`, `cd`, `video`, `game`):

```yaml
action: findus_opac.renew
data:
  config_entry_id: 0123456789abcdef0123456789abcdef
  categories:
    - tonie
    - cd
```

If both `media_ids` and `categories` are given, both apply. Non-renewable items are always
skipped. With `response_variable` the service returns the results (same `items` as the event).

### Event `findus_opac_renewal`

Fired after every renewal attempt – from the button, service or card (`trigger: manual`)
or from auto-renew (`trigger: auto`):

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

**Renew automatically:** no automation needed any more – enable the "Auto-renew" option
(integration → Configure), see [Auto-renew](#auto-renew).

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
          title: >
            Library {{ trigger.event.data.account_name }}
            {{ '(auto)' if trigger.event.data.trigger == 'auto' else '' }}
          message: >
            {% for i in trigger.event.data['items'] %}
            {{ i.title }}: {{ 'renewed until ' ~ i.new_due if i.status == 'renewed'
               else 'request submitted' }}
            {% endfor %}
```

Entity IDs depend on the account name and system language – check the device page.

## Dashboard card

The integration ships its own card and registers it itself – no resource to add, no extra
HACS frontend package. After a restart it appears in the card picker as **"Findus Bibliothek"**
and picks the loans sensor automatically.

- Cover image per item (falls back to the media type icon)
- Due date with "today", "in 2 days"; red when overdue, orange when due soon
- "renewable" badge and a renew icon **per item**
- "Renew N" button for all renewable items
- Sync icon in the header ("Sync now")

```yaml
type: custom:findus-opac-card
entity: sensor.lena_loans
title: Lena's library    # optional, default: account name
show_renew: true         # show renew buttons
show_covers: true        # show cover images
max_items: 0             # 0 = all
warn_days: 3             # orange from this many days before due
group_by: due            # due | category | none – collapsible groups
max_height: 400          # list height in px, scrolls beyond; 0 = no limit
```

Covers are loaded by the viewer's browser directly from Findus' cover servers
(`mycover.findus-internet-opac.de`, `covers-buchhandel-de.findus-internet-opac.de`); no
credentials are sent. To avoid that: `show_covers: false`.

After updating the integration you may need to clear the browser cache (Ctrl+Shift+R).

## Loan list as a Markdown card

Alternatively, without the custom card, using built-in cards only:

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

## Icon

The fox icon is an original drawing (`images/fox.svg`) and **not** the Findus logo. Recent
Home Assistant versions pick it up automatically (folder `brand/`).

## Privacy

- Card number and birth date/password are stored in Home Assistant's config entry
  (`.storage/core.config_entries`), like any other integration's credentials.
- Only the Findus servers of the configured library are contacted.
- The diagnostics download (device → Download diagnostics) redacts credentials and form fields.

## License

MIT – see [LICENSE](LICENSE).
