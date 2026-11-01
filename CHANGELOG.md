# Changelog

## 0.5.1 – unreleased

- Neuer Sensor „Mitteilung der Bibliothek“ mit dem Freitext-Hinweis der Bücherei (Titel als
  Zustand; Attribute `text`, `kind`, `images`, `url`). Langer Text
  wird bei 2000 Zeichen mit „…“ gekürzt und verlinkt auf die Webseite. Die Karte zeigt ihn als
  aufklappbaren Banner, abschaltbar mit `show_announcement`. Ob Schließzeit oder Info, ist
  eine Schlüsselwort-Schätzung.

- Benachrichtigungstexte liegen jetzt in `translations/<sprache>.json` (Schlüssel `notify_*`);
  eine neue Sprache braucht nur noch diese Datei plus einen Block in der Karte. Abschnitt
  „Sprachen“ in der README.

## 0.5.0 – unreleased

- Verlängerung mit echtem Konto geprüft: ein einziger Schritt, die Bücherei bestätigt mit
  „OK, Verlängerungsantrag wurde gestellt“.
- Medien mit gestelltem Verlängerungsantrag verschwanden bis zum nächsten Abgleich aus der
  Liste – sie bleiben jetzt gelistet, nicht verlängerbar, mit neuem Attribut
  `renew_requested` und Hinweis „Verlängerung beantragt“ in Karte und Benachrichtigung.
- Neuer Status `failed`, wenn die Bücherei den Antrag nicht annimmt; der Button/Dienst meldet
  dann einen Fehler.
- Doku: neue Leihfrist zählt ab dem Tag des Antrags.

## 0.4.0 – unreleased

- Eingebaute Benachrichtigungen (Optionen „Benachrichtigen“, Uhrzeit, Anlässe): tägliche
  Übersicht zu bald fälligen, heute fälligen und überfälligen Medien, Hinweis vor Ablauf des
  Ausweises (30 und 7 Tage), Meldung nach jeder Verlängerung. Jeder Anlass nur einmal (überfällig
  täglich), auch über Neustarts hinweg. Verpasste Uhrzeit (HA aus/Neustart) wird nach dem
  Start nachgeholt.
- Companion-App: Knopf „Verlängern“ direkt in der Benachrichtigung.

## 0.3.2 – unreleased

- Karte: aufklappbare Gruppen nach Rückgabedatum oder Medienart (`group_by`, Standard
  Rückgabedatum; überfällige und bald fällige Gruppen offen), scrollbare Liste
  (`max_height`, Standard 400 px).
- Karte wird zusätzlich als Dashboard-Ressource registriert (Speicher-Modus), damit die
  Companion-Apps sie laden („Custom element doesn't exist“ behoben).
- Reihentitel: Bandtitel wird mitgelesen („Yakari - Die Rache des Carcajou (Band 26)“ statt
  nur „Yakari“); neues Attribut `series` mit dem Reihennamen.
- Ausweis-Gültigkeit: Sensor „Ausweis gültig bis“ (aus dem Hinweis im Leserkonto) und
  Binärsensor „Ausweis läuft bald ab“ (30 Tage vorher); in der Karte unter dem Titel.

## 0.3.0 – unreleased

- Eigene Dashboard-Karte „Findus Bibliothek“ (`custom:findus-opac-card`), wird automatisch
  registriert: Cover, Fristen farbig, Verlängern pro Medium und für alle, Abgleich-Symbol.
- Coverbilder: neues Attribut `cover` je Medium.
- Automatisches Verlängern (Option): Zeitraum vor der Rückgabe, Beschränkung auf Medienarten,
  ein Antrag pro Medium und Rückgabedatum.
- Dienst `findus_opac.renew`: neues Feld `categories`.
- Ereignis `findus_opac_renewal`: neues Feld `trigger` (`manual` / `auto`).
- Button „Jetzt abgleichen“.
- Eigenes Fuchs-Symbol (`brand/`).
- Anmeldung sendet die versteckten Felder der Login-Seite mit.

## 0.2.0 – unreleased

- Kontoname, Tage bis zur Rückgabe, heute/bald fällig, Optionen, Reauth, Diagnose,
  Übersetzungen, Tests.

## 0.1.0 – unreleased

- Erste Version / first version.
- Einrichtung über die UI: Kontoname, Subdomain, Ausweisnummer, Geburtsdatum/Passwort.
- Erneute Anmeldung (Reauth), wenn die Bücherei die Zugangsdaten ablehnt.
- Optionen: Aktualisierungsintervall, Zeitraum für „bald fällig“.
- Sensoren: Ausleihen gesamt und je Medienart, nächste Rückgabe, Tage bis zur Rückgabe,
  heute/bald fällig, überfällig, verlängerbar; Binärsensoren für überfällig und verlängerbar.
- Button „Alle verlängern“, Dienst `findus_opac.renew`, Ereignis `findus_opac_renewal`.
- Diagnose mit geschwärzten Zugangsdaten.
