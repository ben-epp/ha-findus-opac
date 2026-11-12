# Glossary

Domain terms used in code, tests and docs. German Findus terms in parentheses.

- **Library**: one Findus Internet-OPAC installation, identified by its subdomain.
- **Account** (Leserkonto): what one library card shows after login: loans, card validity,
  announcement, last sync. One config entry per account.
- **Library card** (Ausweis): card number plus secret (birth date); has a valid-until date.
- **Loan**: one borrowed item, identified by its media number (`mednr`); has a due date,
  a category, a renewable flag and the library's note.
- **Category**: book, tonie, cd, video or game, derived from the Findus media type.
- **Renewal**: extending a loan. Findus either moves the due date at once (renewed) or files
  a renewal request.
- **Renewal request** (Verlängerungsantrag): an email to library staff, applied by hand.
  Findus forgets its mark at the library's next data upload; the integration keeps its own
  record until the due date moves or the item is returned.
- **Pending**: a renewal request still waiting: until the library's second opening day after
  it was sent (three calendar days when opening hours are unknown). Never resent while pending.
- **Renew block**: the library's reason a loan cannot be renewed: limit, reserved, too_early,
  other.
- **Auto-renew**: renewing loans automatically within N days of their due date, optionally
  only some categories; at most one attempt per loan, due date and day.
- **Due status**: overdue, today, soon (within the due-soon days) or later.
- **Digest**: the daily notification for one account, listing only what is new since the
  last one.
- **Last chance**: the last regular opening before a due date on which the library is closed,
  for a loan that cannot be renewed.
- **Announcement** (Veranstaltungshinweis): the library's free-text notice; kind closure or
  info.
- **Opening hours**: regular weekly hours. Conditional days count as open; holidays are
  unknown.
- **Last sync** (Datenstand): when the library last uploaded its data to Findus.
- **Family view**: one card showing several accounts.
