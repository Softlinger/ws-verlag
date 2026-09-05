# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Zuständigkeits-Trennung:** Architektur-Grenzen, Modul-Landkarte,
> Architektur-Invarianzen, DB-/Schema-Regeln und die Arbeitsprotokolle sind in
> **`AGENTS.md`** definiert (Single Source of Truth dafür). Diese `CLAUDE.md`
> enthält die fachlichen Entscheidungen und den Geschäftskontext. Bei einem
> Konflikt zu Architektur/Grenzen gilt `AGENTS.md`.

## Auftrag

Individualsoftware für einen Verlagskunden (österreichischer Rechtsraum). Rollen: Softwarearchitekt, der einfaches, klares, strukturiertes Coding umsetzt; ein Agententeam führt Anweisungen präzise aus. **Bei inhaltlichen Unklarheiten sofort Rückfragen stellen – wichtige Entscheidungen nie eigenständig treffen.** (Diese Vorgabe gilt weiterhin für neue, nicht bereits geklärte fachliche Fragen.)

## Befehle

```powershell
poetry install                              # Abhaengigkeiten installieren
poetry run python scripts/seed.py           # Admin + Grundkonfiguration (erfordert MariaDB). Demo-Daten nur mit SEED_DEMO=1
poetry run uvicorn app.main:app --reload    # Dev-Server auf Port 8000, nur Host (setzt MariaDB-DATABASE_URL voraus; sonst via docker compose)
poetry run pytest                           # Tests (DB-Tests brauchen eine erreichbare MariaDB, sonst skipped)
$env:TEST_DATABASE_URL = "mysql+pymysql://root@127.0.0.1:3307/ws_verlag_test"  # vor `poetry run pytest`
poetry run pytest tests/test_tax.py -q      # Einzelne Testdatei (test_tax laeuft ohne DB)
```

Datenbank ist ausschließlich MariaDB (kein SQLite). Für Tests kurz eine Instanz starten,
z. B. `docker run -d -p 3307:3306 -e MARIADB_ALLOW_EMPTY_ROOT_PASSWORD=1 mariadb:11`.

Poetry ist unter `%APPDATA%\Python\Python314\Scripts` installiert (nicht global im PATH) – ggf. Pfad ergänzen. Die Poetry-venv nutzt Python 3.11 (`poetry env use`), da einige Abhängigkeiten mit 3.14 noch nicht kompatibel sind.

**Bekannte Falle**: `passlib[bcrypt]` ist mit `bcrypt>=4.1` inkompatibel (löst beim Hashen `ValueError: password cannot be longer than 72 bytes` aus, unabhängig von der tatsächlichen Passwortlänge). `bcrypt` ist deshalb in `pyproject.toml` explizit auf `==4.0.1` gepinnt – bei Dependency-Updates nicht versehentlich lösen.

## Architektur

FastAPI-App mit serverseitig gerenderten Jinja2-Templates (kein SPA, minimales Vanilla-JS nur für dynamische Positionszeilen in Formularen). SQLAlchemy-Modelle in `app/models.py`, Business-Logik in `app/services/` getrennt von den Routern:

- `app/services/numbering.py` – erzeugt fortlaufende Belegnummern je `DocumentType` (Auftrag/Rechnung/Gutschrift) aus `NumberRange`-Konfiguration (Präfix/Suffix/Start/Stellenanzahl).
- `app/services/tax.py` – zentrale Steuerberechnung: 10 %/20 % USt., Reverse-Charge (0 % USt.), Werbesteuer (Werbeabgabe) 5 % pauschal auf Rechnungs-Nettosumme. **Berechnungsreihenfolge:** `Netto + 5 % Werbeabgabe = USt-Bemessungsgrundlage`, darauf USt, d. h. `Netto → ×1,05 → ×(1+Satz) → Brutto` — die Werbeabgabe IST Teil der USt-Basis (mit Steuerberater bestätigt). Einzige Stelle, die Summen berechnet – Rechnungs-, Gutschrift- und PDF-Rendering sowie die USt-Voranmeldung (`reporting.py`) nutzen ausschließlich `calculate_totals` (die UVA meldet pro Satz `TaxTotals.base_by_rate` = Netto inkl. anteiliger Werbeabgabe, damit `USt = Satz × Netto` aufgeht).
- `app/services/pdf.py` – Belege (Rechnung/Gutschrift/Mahnung) als PDF via reportlab.
- `app/services/mailer.py` – SMTP-Versand + Protokollierung in `MailLog`.
- `app/services/dunning.py` – Mahnstufen-Logik (nächste fällige Stufe, Text-Platzhalter-Rendering).
- `app/services/payments.py` – erfasst Zahlungen zu einer Rechnung und leitet daraus den Zahlungsstatus ab (offen/teilbezahlt/bezahlt), basierend auf `calculate_totals`.
- `app/services/reporting.py` – Aggregationslogik für die Buchhaltungs-Berichte (Saldenliste, USt.-Voranmeldung inkl. CSV-/PDF-Export), baut ebenfalls auf `calculate_totals` auf; Gutschriften mindern die jeweilige Periode/den jeweiligen Kundensaldo.
- `app/services/update_check.py` – ruft das Update-Manifest ab und vergleicht Versionen (Details siehe Update-Funktion unten).

Auth ist Session-Cookie-basiert (`app/auth.py`, `itsdangerous`-signierte Tokens), kein JWT/OAuth. Rollen (`admin`/`sachbearbeiter`) werden per FastAPI-Dependency (`require_login`/`require_admin`) durchgesetzt. `app/main.py` enthält Middleware, die den eingeloggten User als `request.state.user` für die Templates (Navigation) verfügbar macht.

Reverse-Charge wird nicht manuell gesetzt, sondern ergibt sich automatisch aus `Customer.reverse_charge_applicable` (EU-Land + UID vorhanden) und wird bei Rechnungserstellung auf `Invoice.reverse_charge` eingefroren.

DB: ausschließlich MariaDB via `mysql+pymysql://...` (SQLite wird nicht mehr unterstützt; `app/config.py` verlangt zwingend eine MariaDB-`DATABASE_URL` und bricht sonst beim Start ab — im Docker-Betrieb injiziert `docker-compose.yml` sie). Tabellen werden beim Start automatisch erzeugt (`Base.metadata.create_all` + additive `ensure_new_columns`); für spätere Schemaänderungen (Umbenennen/Löschen/Umtypisieren) ist Alembic unter `alembic/` vorbereitet, aber noch keine Migration erzeugt. Die Unit-Tests laufen gegen eine echte MariaDB (via `TEST_DATABASE_URL`, ohne erreichbare DB werden DB-Tests übersprungen).

## Fachliche Anforderungen (aus ws-verlag.txt)

- **Kundenmanagement**: Zahlungsbedingungen und Bankkonto individuell aus Stammdaten zuweisbar; ausländische EU-Kunden mit UID unterliegen dem Reverse-Charge-Verfahren.
- **Artikelmanagement**: Artikel mit 10 % und 20 % MwSt.
- **Auftrags- und Rechnungsmanagement**: Zuordnungsmöglichkeit von 5 % Werbesteuer.
- **Buchhaltung**: Zahlungs- und Mahnungsmanagement mit 3 Mahnstufen, manuell ausgelöst.
- **Firmenstammdaten-Verwaltung**: 6 Bankkonten, SMTP-Server, Zahlungsbedingungen, Belegnummernkreise.
- **Belegversand**: PDF-Versand per E-Mail (SMTP), Verwaltung/Management versendeter Mails inkl. Vorschau.
- **Nummernkreise**: Auftrags- und Rechnungsnummern fortlaufend, mit individuell konfigurierbarer Startnummer, Präfix und Suffix.

## Geklärte fachliche Entscheidungen

- **Gutschriften**: eigener Belegtyp mit eigenem Nummernkreis (Präfix/Suffix/Start), referenziert die Original-Rechnung.
- **Werbesteuer (5 %)**: wird pauschal pro Auftrag/Rechnung zugeordnet (nicht pro Position).
- **Mahntexte**: pro Mahnstufe (1./2./3.) frei editierbare Vorlage in den Firmenstammdaten, mit Platzhaltern (`{kunde}`, `{rechnungsnummer}`, `{rechnungsdatum}`, `{betrag}`, `{faelligkeitsdatum}`).
- **Mahngebühren/-fristen**: Frist (Tage) und Gebühr je Mahnstufe konfigurierbar in den Firmenstammdaten; Erstellung der Mahnung bleibt manuell ausgelöst. **Mahngebühren sind umsatzsteuerfrei** (Kostenersatz, keine steuerpflichtige Leistung): verbucht als USt-freie Position in Saldenliste + offenem Rechnungsbetrag (`payments.total_open`), nie in USt-Basis/UVA; geforderter Mahnbetrag = offener Rechnungsrest + aufgelaufene Gebühren.
- **Rollenmodell**: Admin (Stammdaten, Benutzer, Konfiguration) und Sachbearbeiter (Tagesgeschäft: Kunden, Aufträge, Rechnungen, Mahnungen).
- **Tech-Stack**: Python/FastAPI, MariaDB/SQLAlchemy (ausschließlich MariaDB, kein SQLite mehr — auch Entwicklung via Docker), Server-Rendered Jinja2 (kein SPA), lokale Session-Auth, Poetry als Paketmanager, Port 8000, Demo-Seed-Daten aktiv. **Update (2026-08-30)**: Produktivbetrieb läuft doch über Docker (App + MariaDB + privilegierter Updater-Sidecar, drei Container), nicht native Installation — Grund: automatischer Selbst-Update-Mechanismus (siehe unten) braucht sauberen Container-Austausch/Rollback, dafür ist Docker der robustere Weg.
- **Update-Funktion**: App prüft (Admin-Login + alle 24h) `https://www.weidlinger-soft.at/apps/ws-verlag/version.json` (Format: `docs/update-manifest-format.md`) und zeigt bei neuerer Version "Soll ich das Update installieren?" (Dashboard + `/updates`). Nach Bestätigung übernimmt NICHT der App-Prozess die Installation, sondern ein separater, privilegierter `ws-verlag-updater`-Sidecar-Container (einziger Container mit Docker-Socket-Zugriff — der App-Container hat bewusst keinen), der per gemeinsamem Volume-Signal (`app/routers/updates.py` → `/update-signal/update_request.json`) informiert wird: Backup (MariaDB-Dump), Pull per Digest, Container-Austausch (alter Container wird umbenannt, nicht gelöscht), Health-Check gegen `/healthz`, bei Fehlschlag automatischer Rollback. Siehe `README-DEPLOYMENT.md` für Details/Sicherheitshinweise (Docker-Socket = Root-äquivalent) und `updater/updater.py` für die Kernlogik. Lokal mit Docker Desktop end-to-end getestet (Update- und Rollback-Pfad beide verifiziert).
- **Datensicherung**: der Updater-Container legt automatisch (Standard alle 24h, konfigurierbar) eine DB-Sicherung unter `./backups` an und behält nur die letzten N Dateien (Retention konfigurierbar); Admins können unter „Hilfe“ zusätzlich jederzeit manuell sichern, vorhandene Sicherungen einsehen und eine davon wiederherstellen (der bisherige Stand wird davor automatisch nochmal gesichert). Läuft wie das Update über ein Signal ans gemeinsame Volume, ausgeführt vom privilegierten Updater-Container.
- **Zielserver (Update 2026-09-01)**: beim aktuellen Kunden **kein Synology-NAS mehr** (zu wenig Kapazität für die Docker-Installation), sondern ein leistungsfähiger, durchgehend laufender Windows-PC vor Ort. Die Docker-Architektur (App/DB/Updater, Update-Mechanismus) ist identisch, nur der Docker-Host ändert sich. Laieninstallationsanleitungen: `install-pc.md` (aktuell, Windows-PC) und `SYNOLOGY-Install.md` (als Referenz erhalten, falls künftig doch wieder eine NAS zum Einsatz kommt). Nicht verwechseln mit der **Image-Registry**: Docker-Images werden unabhängig vom Zielserver immer nach `ghcr.io` (GitHub Container Registry) gepusht/von dort gezogen (`deploy/release.py`, `README-DEPLOYMENT.md`) — "GitHub" bezieht sich hier nur auf die Registry, nicht auf die Laufzeitumgebung.

## Technische Rahmenbedingungen

- Mehrplatzfähigkeit (Netzwerk-Mehrbenutzerbetrieb) ist Pflicht.
- UI/UX: einfache, klare, ruhige Benutzerführung; moderne, aufgeräumte Oberfläche; einfache Integration ins lokale Netzwerk.

## Rechtlicher Rahmen (immer beachten)

- Österreichisches/EU-Recht ist maßgeblich (nicht z. B. deutsches Recht) – u. a. Reverse-Charge bei EU-B2B-Kunden mit UID, Werbesteuer (5 %), Mahnstufen.
- DSGVO-Konformität und Datenschutz haben Vorrang vor schneller Umsetzung (siehe globale Anweisungen).
