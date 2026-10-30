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

# Loan.category values -> count sensor keys
CATEGORIES = ("book", "tonie", "cd", "video", "game")

# Renewal
SERVICE_RENEW = "renew"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_MEDIA_IDS = "media_ids"
EVENT_RENEWAL = "findus_opac_renewal"
# Findus applies renewal requests on the library's next sync; re-check after this delay.
RENEW_RECHECK_MINUTES = 30
