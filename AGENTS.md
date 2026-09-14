# AGENTS.md — Betriebsanleitung für Coding-Agenten

<!--
Zweck dieser Datei: Einem KI-Agenten in JEDEDER Session stabil den Überblick über
dieses Warenwirtschaft-/ERP-Projekt geben, damit er vorhandenen Code nicht
unabsichtlich zerstört. Diese Datei ist die operative Leitplanke;
fachliche Detailentscheidungen stehen in CLAUDE.md. Bei Widerspruch gilt:
CLAUDE.md für FACHLICHES, diese Datei für ARCHITEKTUR/GRENZEN/ARBEITSWEISE.
-->

Dieses Projekt ist Individualsoftware für einen Verlagskunden (österreichischer
Rechtsraum): Kunden-, Artikel-, Auftrags-, Rechnungs-, Gutschrifts-, Zahlungs-
und Mahnwesen mit Beleg-PDF und E-Mail-Versand.

**Größtes Risiko in diesem Repo:** Ein Agent umbaut „aus Versehen" kritische
Kernlogik oder das Datenmodell und zerstört damit produktive Installationen mit
echten Kundendaten. Halte dich deshalb an die Grenzen und Invarianzen unten.

---

## 1. Arbeitsprotokolle (gegen „Agent verliert Überblick")

1. **Vor jeder Änderung lesen, nicht raten.** Öffne die betroffene Datei und die
   davon abhängigen Stellen, bevor du Code schreibst. Kein Umbau auf Basis von
   Vermutungen über Dateinamen.
2. **Kleine, abgeschlossene Schritte.** Eine Session = ein klar abgegrenztes
   Änderungsziel = ein kleiner Diff. Keine großflächigen Refactors über mehrere
   Fachdomänen „zur Aufräumung".
3. **Git-Sicherheitsnetz.** Arbeite nur bei sauberem Arbeitsstand; erstelle vor
  risikoträchtigen Änderungen einen Commit bzw. Branch. Fasse fremde/ungewollte
   Änderungen nie mit ein. Vor Abschluss `git diff` selbst gegenlesen.
4. **Verifizieren statt behaupten.** Nach jeder Änderung die passenden Tests
   ausführen (Abschnitt 6) und das Ergebnis prüfen, bevor du „fertig" meldest.
   Ein nicht ausgeführter Test gilt als nicht getestet.
5. **Bei fachlicher Unklarheit rückfragen** — wichtige/nicht geklärte
   Fachentscheidungen nie eigenständig treffen (gilt auch aus CLAUDE.md).
6. **Nur eine Wahrheit pro Fakt.** Zahlen werden nie an zwei Stellen berechnet,
   Konfiguration nicht an zwei Stellen gelesen (siehe Invarianzen, Abschnitt 4).

---

## 2. Stack (Kurzfassung)

- Python 3.11 (venv bewusst auf 3.11, NICHT 3.14 — `poetry env use`), FastAPI
- SQLAlchemy-Modelle + Jinja2 serverseitig gerendert (kein SPA, minimales Vanilla-JS)
- DB: ausschließlich MariaDB via `mysql+pymysql://…` (SQLite wird nicht mehr unterstützt; `config.py` verlangt zwingend eine MariaDB-`DATABASE_URL`). Auch Dev/Tests laufen gegen MariaDB (Tests via `TEST_DATABASE_URL`).
- Auth: Session-Cookie, `itsdangerous`-signierte Tokens, bcrypt-Hashing (kein JWT/OAuth)
- PDF: reportlab · Paketmanagement: Poetry · Dev-Port 8000
- Produktivbetrieb: Docker (App + MariaDB + privilegierter `ws-verlag-updater`-Sidecar)

## 3. Modul-Landkarte & Zuständigkeitsgrenzen

**Schichtentrennung — daran halten:**
`app/routers/*` (HTTP/Forms/Redirects) → `app/services/*` (Business-Logik) →
`app/models.py` (Daten) → Templates/`app/static`. Router enthalten keine
Business-Formeln; Services kennen kein HTTP.

Router (je eine Fachdomain, inkl. gleichnamigem Template-Ordner unter `app/templates/`):

| Router | Domain |
|---|---|
| `auth` | Login/Logout, Session |
| `account` | eigener Account / Passwort des angemeldeten Users |
| `accounting` | Buchhaltungs-Übersicht/Zahlungen |
| `customers` · `articles` | Stammdaten Kunde / Artikel |
| `orders` · `invoices` · `credit_notes` | Belege (Auftrag/Rechnung/Gutschrift) |
| `dunning` | Mahnwesen (3 Stufen, manuell ausgelöst) |
| `reports` | Berichte / USt.-Voranmeldung / CSV-/PDF-Export |
| `company` | Firmenstammdaten, Bankkonten, Zahlungsbedingungen, Nummernkreise, Mahnstufen, SMTP |
| `users` | Benutzerverwaltung (Rollen) |
| `mail_log` | protokollierter Belegversand, Mail-Vorschau |
| `updates` | Update-/Backup-Signale an den Updater-Sidecar |
| `help` | Hilfe/Datensicherung-UI |

Services (Business-Logik, Fachdomäne → Datei):

- `tax.py` — **einzige** Stelle, die Summen berechnet (10 %/20 % USt.,
  Reverse-Charge 0 %, Werbesteuer pauschal). Kernfunktion `calculate_totals`.
- `numbering.py` — **einzige** Stelle für fortlaufende Belegnummern je
  `DocumentType` aus `NumberRange` (Präfix/Suffix/Start/Stellen).
- `payments.py` — Zahlungsstatus (offen/teilbezahlt/bezahlt) aus `calculate_totals`.
- `dunning.py` — Mahnstufen-Logik + Platzhalter-Rendering.
- `reporting.py` — Aggregation für Berichte (Saldenliste, USt.-Voranmeldung);
  Gutschriften mindern Periode/Kundensaldo; baut auf `calculate_totals` auf.
- `pdf.py` — Beleg-PDF (Rechnung/Gutschrift/Mahnung).
- `mailer.py` — SMTP-Versand + `MailLog`.
- `update_check.py` — Manifest abrufen/Versionsvergleich.

Modelle (`app/models.py`) — Tabellen:
`users`, `company`, `bank_accounts`, `payment_terms`, `number_ranges`,
`dunning_level_settings`, `customers`, `articles`, `orders`, `order_items`,
`invoices`, `invoice_items`, `credit_notes`, `credit_note_items`, `payments`,
`dunnings`, `update_state`, `mail_log`.
Enums: `UserRole`, `DocumentType`, `InvoiceStatus`, `VatRate`, `MailStatus`,
`UpdateApplyStatus`.

Zentrale Infra-Dateien: `app/config.py` (Settings, einzige Konfig-Quelle),
`app/database.py` (Engine/Session/`Base` + additive Spalten-Migration),
`app/auth.py` (Session + `require_login`/`require_admin`),
`app/main.py` (App, Middleware `request.state.user`, Router-Registrierung,
Startup `create_all` + `ensure_new_columns`, `/healthz`),
`app/templating.py`, `app/version.py` (`__version__`).

## 4. Architektur-Invarianzen (NICHT verletzen)

Diese Punkte sind die häufigsten stillen Zerstörer. Nicht umgehen, nicht
duplizieren, nicht „einfach schnell" neu implementieren:

1. **Summen nur über `calculate_totals`.** Rechnung, Gutschrift, PDF,
   Zahlungen und Reports rechnen niemals selbst. Neue Summen-/Steuerlogik gehört
   in `tax.py`, nicht in Router/Template. Geld immer als `Decimal` mit
   `ROUND_HALF_UP` (nie `float`) — Rundung nur über `_round()` in `tax.py`.
2. **Nummernkreise nur über `numbering.py`.** Keine Belegnummer per Hand bzw.
   `max(id)+1` irgendwo sonst erzeugen.
3. **Konfiguration nur über `app/config.py` (`settings`).** Keine `os.getenv`
   verstreut, keine Secrets hartkodiert, `.env` nicht einsehen/committen.
4. **Auth nur über die bestehenden Dependencies.** Geschützte Routen brauchen
   `require_login`/`require_admin`; Rollen (`admin`/`sachbearbeiter`) nie
   umgehen oder aufweichen.
5. **Reverse-Charge ist eingefroren, nicht live.** `Invoice.reverse_charge`
   wird bei Rechnungserstellung aus `Customer.reverse_charge_applicable`
   (EU-Ausland + UID) gesetzt und danach nicht mehr nachberechnet.
6. **Österreichisches/EU-Recht.** USt 10 %/20 %, Reverse-Charge EU-B2B mit UID,
   Werbesteuer (Werbeabgabe) 5 % pauschal je Beleg (nicht pro Position), 3 Mahnstufen.
   DSGVO/Datenschutz schlägt schnelle Umsetzung.
   - **Berechnungsreihenfolge (mit Steuerberater bestätigt, NICHT „fixen"):**
     Werbeabgabe = 5 % auf den Schaltungs-Netto, und **die Werbeabgabe ist Teil der
     USt-Bemessungsgrundlage**: `Netto → ×1,05 = Summe vor USt → ×(1+Satz) = Brutto`
     (z. B. 100 → 105 → 126 bei 20 %). `tax.py` (`calculate_totals`) macht genau das;
     die anteilige Basis je USt-Satz liefert `TaxTotals.base_by_rate`.
   - **UVA-Berichte müssen tragen diese Basis:** In `reporting.py` ist das
     „Netto" je Satz = `base_by_rate` (inkl. Werbeabgabe), damit gilt
     `USt = Satz × gemeldetes Netto` und `Netto + USt = Brutto`. Werbeabgabe wird
     separat nur informativ ausgewiesen („davon Werbesteuer …"), NIEMALS zusätzlich
     zur Netto-Basis aufaddieren (sonst Doppelzählung/Übererhebung).
   - **Annahme:** als werbesteuerpflichtig markierte Belege enthalten nur die
     direkte Schaltung (kein Kreation/Produktions-Entgelt). Bei Mischbelegen müsste
     die 5 %-Basis je Position getrennt erfasst werden (aktuell nicht abgebildet).
7. **Privilegierte Operationen bleiben im Updater-Sidecar.** Update/Backup/
   Restore laufen NUR im separaten Container mit Docker-Socket; die App
   schreibt ausschließlich ein Signal ins gemeinsame Volume (`update_signal_dir`).
   Nie Docker-Socket/Root-Rechte in den App-Container holen.
8. **Zahlungsstatus nur über `recompute_invoice_status` (payments.py).** Keine zweite
   Stelle, die `Invoice.status` setzt. Muss nach Zahlung, Rechnungs-Edit UND
   Gutschrift aufgerufen werden; berücksichtigt gezahlt **und** gutgeschrieben und
   sperrt die Rechnungszeile (`FOR UPDATE`) gegen Lost-Updates. `open_amount()` ist
   die einzige Quelle für „noch offen".
9. **Wartungsfenster während Updates (main.py-Middleware).** Solange
   `UpdateState.apply_status` in {ANGEFORDERT, WIRD_INSTALLIERT} (und nicht älter als
   `update_maintenance_timeout_seconds`), antwortet die App auf alles außer
   `/healthz`, `/login`, `/logout`, `/static`, `/updates…` mit 503 — damit niemand
   während Backup/Container-Tausch auf App/DB schreibt. Beim Umbau der Middleware die
   Allowlist NICHT verkleinern (sonst kann der Updater nicht mehr reporten/healthchecken).
   `update_check.clear_stale_apply_status()` (in `check_for_update` + beim Öffnen von
   `/updates` aufgerufen) setzt einen verwaisten ANGEFORDERT/WIRD_INSTALLIERT auf NONE
   zurück, wenn seit `apply_requested_at` mehr als das Wartungsfenster vergangen ist —
   sonst hängt die UI dauerhaft auf „Installation läuft" (z. B. nach fehlgeschlagenem
   Report oder einer zurückgespielten alten DB). NICHT entfernen.
10. **Session = `password_version`-gebunden.** Der Cookie trägt `password_version`;
   Passwortwechsel/Deaktivierung (`account.py`, `users.py`) müssen ihn erhöhen, sonst
   bleiben gestohlene Cookies gültig. `/updates/report` verlangt Header
   `X-Updater-Token == settings.updater_token` (Updater sendet ihn, docker-compose
   gibt dasselbe `UPDATER_TOKEN` an beide Container).
11. **CSRF ist Pflicht in jedem POST-Formular.** `app/csrf.py` (signierter Double-
   Submit-Token) + Middleware setzt Cookie und `request.state.csrf_token`; jedes
   `APIRouter` haengt `Depends(require_csrf)` an. Ein neues `<form method="post">`
    MUSS `{{ csrf_field(request) }}` enthalten, sonst 403. Server-zu-Server-POST
   (`/updates/report`) ist in `_SERVER_TO_SERVER_PATHS` ausgenommen.
12. **SMTP-Passwort at-rest verschluesselt** (`app/crypto.py`, Fernet-Schluessel aus
   SECRET_KEY). Beim Speichern `encrypt_secret`, im Mailer `decrypt_secret`. SECRET_KEY
   rotieren macht gespeicherte SMTP-Passwoerter unlesbar. Bestehende Klartextwerte
   laufen als Fallback weiter.
13. **Manifest-Signatur optional** (`app/services/update_signing.py`, Ed25519, nur bei
   gesetztem `UPDATE_MANIFEST_PUBLIC_KEY` aktiv; kanonische Bytes = canonical_fields
   sortiert/compact — Release-Side und App MUESSEN dieselbe Funktion nutzen).
14. **Mahngebühren = umsatzsteuerfrei.** `payments.accrued_dunning_fees`/`total_open`
   und `reporting.get_balance_list` verbuchen Mahngebühren als eigene USt-freie
   Position (`kind="mahngebuehr"`) in Saldenliste + offenem Rechnungsbetrag. Sie
   dürfen NIEMALS in `calculate_totals`, die USt-Basis oder die UVA (`get_vat_summary`)
   einfließen. Gutschriften-Cap und Zahlungsvergleich bleiben auf dem reinen
   Rechnungsbetrag ohne Gebühren.

## 5. Datenbank & Schema-Änderungen (kritischer Bereich)

- Tables werden beim Start per `Base.metadata.create_all()` angelegt. Diese
  Funktion legt **fehlende Tabellen** an, ändert aber **niemals bestehende**.
- **Neue Spalte** an bestehender Tabelle → additiv in `app/database.py`
  (`_NEW_COLUMNS`-Liste, wird via `ensure_new_columns()` bei Startup nachgezogen).
  Nur `ADD COLUMN`. Damit produktive Installationen ohne manuelles Alembic laufen.
- **Umbenennen/Löschen/Umtypisieren** von Spalten/Tabellen → **Alembic**
  (`alembic/` ist vorbereitet, erste Migration erst nach produktivem Erststart
  nötig). Nie per `create_all` erzwingen wollen.
- Neue Spalten immer mit sicherem Default für Bestandsdaten versehen.
- **Nur MariaDB** (kein SQLite mehr). `SELECT ... FOR UPDATE`, Transaktions-Isolation
  und Fremdschlüssel-Enforcement funktionieren dadurch überall zuverlässig — genau
  deshalb wurde SQLite entfernt. Keine SQLite-Sonderfälle mehr berücksichtigen/annehmen.
- `backups/` enthält echte Kundendaten (MariaDB-Dumps) — nicht committen, nicht löschen.

## 6. Verifikation (Befehle)

```powershell
poetry install                              # Abhängigkeiten
poetry run python scripts/seed.py           # Tabellen anlegen + Admin + Demo-Daten (erfordert MariaDB)
poetry run uvicorn app.main:app --reload    # Dev-Server, Port 8000 (nur Host; setzt MariaDB-DB voraus)
docker compose --profile test run --rm test # KOMPLETTE Testsuite über Docker (baut test-Stage + Wegwerf-MariaDB db-test) - empfohlen
$env:TEST_DATABASE_URL = "mysql+pymysql://root@127.0.0.1:3307/ws_verlag_test"  # nur für Host-pytest
poetry run pytest                           # alle Tests (Host; braucht MariaDB via TEST_DATABASE_URL)
poetry run pytest tests/test_tax.py -q      # einzelne Datei
```

Tests laufen gegen eine echte MariaDB (kurz hochziehen: `docker run -d -p 3307:3306
-e MARIADB_ALLOW_EMPTY_ROOT_PASSWORD=1 mariadb:11`). Ohne erreichbare DB werden die
DB-Tests übersprungen (nur `test_tax.py` läuft ohne DB). Sessions werden im Test-Helper
`tests/_db.py` vor jedem Schema-Reset geschlossen, damit kein DDL auf einem Meta-Lock hängt.

Poetry liegt unter `%APPDATA%\Python\Python314\Scripts` (nicht global im PATH; in Git
Bash nicht per `$APPDATA` erreichbar → vollen Pfad zu `poetry.exe` verwenden).

**Testabdeckung (kritische Pfade):** `test_tax.py` (USt/Reverse-Charge/
Werbesteuer), `test_numbering.py` (Nummernkreise), `test_reporting.py`
(Buchhaltung/Aggregation), `test_update_check.py` + `test_updates_router.py`
(Update-Mechanik), `test_release.py` (Versionierung).

Regel: **Änderung an `tax`/`numbering`/`payments`/`reporting` oder am Schema →
mindestens die zugehörigen Tests + `pytest` komplett ausführen.** Fehlt für eine
risikoreiche Änderung ein Test, vorher einen kleinen Regressionstest ergänzen.

## 7. Bekannte Fallen / Do-not-touch

- `bcrypt` ist in `pyproject.toml` auf `==4.0.1` **gepinnt** (`passlib[bcrypt]`
  ist mit `bcrypt>=4.1` inkompatibel → `ValueError: password cannot be longer
  than 72 bytes`). Bei Dependency-Updates nicht versehentlich lösen.
- Python-venv auf **3.11** belassen (Abhängigkeiten mit 3.14 teils inkompatibel).
- `.env`, `GHCR_TOKEN`, `MARIADB_*_PASSWORD`, `SECRET_KEY`: Secrets — nicht
  auslesen/ausgeben/committen; Werte nur über `.env.example`-Platzhalter dokumentieren.
- `alembic/versions` (noch leer) nicht von Hand mit erfundenen Migrationen füllen.
- Deployment-Ziel ist ein durchgehend laufender **Windows-PC** vor Ort (kein NAS);
  Images laufen unabhängig davon immer über **ghcr.io** — „GitHub" = Registry,
  nicht Laufzeitumgebung. Veraltetes in `SYNOLOGY-Install.md` nicht als Grundlage nehmen.

## 8. Abschluss-Checkliste vor „fertig"

- [ ] betroffene Dateien + Abhängigkeiten gelesen, nicht geraten
- [ ] nur das vereinbarte, kleine Änderungsziel umgesetzt (kein Fremd-Diff)
- [ ] Invarianzen aus Abschnitt 4 unverletzt
- [ ] Schemaänderung additiv bzw. per Alembic korrekt (§5)
- [ ] `pytest` ausgeführt und grün (relevante Tests explizit)
- [ ] `git diff` selbst gegenlesen; Secrets unverändert/geheim gehalten
- [ ] bei ungeklärter Fachfrage: Rückfrage statt Eigenentscheidung

---

Fachliche Entscheidungen und Begründungen im Detail: siehe **CLAUDE.md**. Deployment/
Update-Mechanik: **README-DEPLOYMENT.md**, **updater/updater.py**. Update-Manifest:
**docs/update-manifest-format.md**.
