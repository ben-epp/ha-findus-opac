"""Constants for Findus Internet-OPAC."""
from __future__ import annotations

DOMAIN = "findus_opac"

# Config entry data
CONF_ACCOUNT_NAME = "account_name"
CONF_SUBDOMAIN = "subdomain"
CONF_CARD = "card"
CONF_SECRET = "secret"

# Options
CONF_SCAN_HOURS = "scan_hours"
CONF_DUE_SOON_DAYS = "due_soon_days"
DEFAULT_SCAN_HOURS = 6
DEFAULT_DUE_SOON_DAYS = 3
MIN_SCAN_HOURS = 1
MAX_SCAN_HOURS = 24
CONF_AUTO_RENEW = "auto_renew"
CONF_AUTO_RENEW_DAYS = "auto_renew_days"
CONF_AUTO_RENEW_CATEGORIES = "auto_renew_categories"  # empty = all categories
DEFAULT_AUTO_RENEW_DAYS = 2
# Optional; the library mails its confirmation of a renewal request here (Findus "replyto").
CONF_RENEW_EMAIL = "renew_email"

# Notifications (options); empty targets = notifications off
CONF_NOTIFY_TARGETS = "notify_targets"
CONF_NOTIFY_TIME = "notify_time"
CONF_NOTIFY_EVENTS = "notify_events"
CONF_NOTIFY_SHOW_TITLES = "notify_show_titles"  # off: counts only, titles stay off lock screens
DEFAULT_NOTIFY_TIME = "08:00:00"
NOTIFY_EVENTS = ("due_soon", "due_today", "overdue", "last_chance", "renewed", "card_expiry")
# mobile_app action id prefix; the config entry id is appended
NOTIFY_ACTION_PREFIX = "FINDUS_OPAC_RENEW_"
# Sent-notification keys older than this are pruned from storage
NOTIFY_KEEP_DAYS = 60

# Library card expiry: "expires soon" binary sensor turns on this many days before.
CARD_EXPIRY_WARN_DAYS = 30

# Loan.category values -> count sensor keys
CATEGORIES = ("book", "tonie", "cd", "video", "game")

# Renewal
SERVICE_RENEW = "renew"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_MEDIA_IDS = "media_ids"
ATTR_CATEGORIES = "categories"
EVENT_RENEWAL = "findus_opac_renewal"
# Findus applies renewal requests on the library's next sync; re-check after this delay.
RENEW_RECHECK_MINUTES = 30

# Bundled Lovelace card (frontend/findus-opac-card.js); bump CARD_VERSION to bust browser caches.
CARD_FILE = "findus-opac-card.js"
CARD_URL = f"/{DOMAIN}/{CARD_FILE}"
CARD_VERSION = "0.9.1"
