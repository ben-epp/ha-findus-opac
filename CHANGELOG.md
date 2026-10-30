# Changelog

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
