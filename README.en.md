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
  `renewed` (new date already visible), `requested` (request submitted, marked as
  "Verlängerung beantragt" in the account) or `failed` (request not accepted) and checks again
  after 30 minutes. Until the library syncs, the item stays listed with its old due date, is no
  longer renewable and has `renew_requested: true`.
- The new loan period counts **from the day of the request**, not from the old due date.
  Renewing early wastes loan time – better shortly before the due date (auto-renew default:
  2 days before).
- Renewal only works when the library allows it – usually **from 14 days before the due date**,
  not for reserved items and not after the maximum number of renewals. The reason is in the
  item's `note` attribute.
- Loan periods depend on the media type (Tonies and CDs are usually shorter than books).
  Every item has its own due date; renewing and auto-renew handle each item on its own date.

## Installation

### HACS (custom repository)

1. Open HACS → menu (⋮) → **Custom repositories**.
2. Add `https://github.com/ben-epp/ha-findus-opac`, category **Integration**.
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
| Notify | – | Notify services, e.g. `mobile_app_my_phone`; empty = no notifications |
| Notification time | 08:00 | When the daily due-date digest is sent |
| Notify about | all | Due soon, due today, overdue, renewal, library card expiry |

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
| Library announcement | Sensor | The library's free-text notice (e.g. holiday closure, event); state = title, attributes `text` (capped at 2000 characters, then `truncated: true` and `url` to the website), `kind` (`closure` if it matches keywords such as "geschlossen", "Urlaub", "Ferien", else `info`), `images`. The card shows it as an expandable banner (`show_announcement`) |
| Library card expires soon | Binary sensor | On 30 days before the card expires; unknown if the page shows no expiry |
| Overdue items | Binary sensor | on when anything is overdue |
| Renewal possible | Binary sensor | on when at least one item can be renewed |
| Renew all | Button | Submits the renewal request for all renewable items |
| Sync now | Button (diagnostic) | Re-reads the reader account immediately |

"Sync now" queries Findus right away. Findus itself only has what the library last uploaded,
so a Tonie just returned at the desk may stay in the list for a few more hours.

Each entry in `items` has: `mednr`, `title`, `author`, `media_type`, `category`
(`book`, `tonie`, `cd`, `video`, `game`), `due`, `days_left`, `renewable`, `renew_requested`, `note`, `cover` (cover image URL or empty).
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

## Notifications

The integration sends notifications itself – no automation needed. Enable them under
**Settings → Devices & services → Findus → Configure**: pick one or more notify services
under "Notify" (e.g. the companion app's `mobile_app_my_phone`), a time and the events.

Every day at that time the integration syncs the account and sends **one** message per
account – only when there is something new. If Home Assistant was off or restarting at that
time, the digest is sent right after startup (once per day):

| Event | When | How often |
|---|---|---|
| Due soon | within the "due soon" window (default 3 days) | once per item and due date |
| Due today | on the due date | once per item and due date |
| Overdue | after the due date | daily until returned |
| Renewal | right after a renewal (also automatic ones) | every time |
| Library card expires | 30 and 7 days before the card expires | once each |

Example:

```text
Library: Kids
Overdue for 2 days: Whales & Dolphins
Due today: The little dragon (renewable)
Due Sun 8 Nov: Sing-along songs (renewable)
```

A renewed item with a new due date is reported again for the new date. What was already
sent is remembered across restarts.

**"Renew" button in the notification:** companion-app targets (`mobile_app_…`, Android and
iOS) get a "Renew" button when the message lists renewable items. Tapping it requests renewal
for everything currently renewable; the result arrives as a separate message. Other notify
services (email, Telegram, …) get the text only.

## Automations

Due dates and renewals no longer need an automation: see [Notifications](#notifications) and
[Auto-renew](#auto-renew). For your own flows all sensors and the `findus_opac_renewal` event
are available, e.g. a spoken reminder the evening before:

```yaml
automation:
  - alias: Library – announce items due tomorrow
    triggers:
      - trigger: time
        at: "18:30:00"
    conditions:
      - condition: numeric_state
        entity_id: sensor.lena_days_until_next_due
        below: 2
    actions:
      - action: tts.speak
        target:
          entity_id: tts.home_assistant_cloud
        data:
          media_player_entity_id: media_player.kitchen
          message: >
            {{ states('sensor.lena_due_soon') }} library items are due tomorrow.
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

## Languages

German and English. Another language needs two files:

1. `custom_components/findus_opac/translations/<lang>.json` – a translated copy of `en.json`:
   setup, options, entities, errors, service **and** notifications (keys `notify_*` under
   `exceptions`). Keep the `{…}` placeholders unchanged. Date formats (`notify_date_short`,
   `notify_date_long`) use `%a` weekday, `%b` month name, `%d`/`%m` day/month, `%D`/`%M`
   two digits, `%Y` year.
2. `frontend/findus-opac-card.js` – one block in `TEXT` for the card.

Missing texts fall back to English. Titles, media types and notes from the library come from
Findus and stay German.

## Privacy

- Card number and birth date/password are stored in Home Assistant's config entry
  (`.storage/core.config_entries`), like any other integration's credentials.
- Only the Findus servers of the configured library are contacted.
- The diagnostics download (device → Download diagnostics) redacts credentials and form fields.

## License

MIT – see [LICENSE](LICENSE).
