# WS-Verlag Verwaltung

Individualsoftware für einen Verlagskunden: Kunden-, Artikel-, Auftrags- und Rechnungsmanagement,
Buchhaltung mit Zahlungs- und Mahnungsmanagement (3 Mahnstufen), Firmenstammdaten-Verwaltung und
Belegversand per E-Mail.

## Stack

- Backend: Python 3.11, FastAPI
- DB: SQLAlchemy, MariaDB (produktiv) / SQLite (lokale Entwicklung, Standard)
- Frontend: Server-Rendered Jinja2-Templates + minimalem Vanilla-JS (keine SPA)
- Auth: Session-Cookie, Passwort-Hashing mit bcrypt
- PDF: reportlab
- Paketmanagement: Poetry

## Einrichtung

```powershell
# Poetry installieren, falls noch nicht vorhanden
python -m pip install --user poetry

# Abhaengigkeiten installieren
poetry install

# Optional: .env aus Vorlage anlegen und Werte anpassen (SECRET_KEY unbedingt setzen!)
copy .env.example .env

# Datenbank initialisieren + Admin-Benutzer + Demo-Daten anlegen
poetry run python scripts/seed.py
```

Das Seed-Skript gibt beim ersten Lauf ein generiertes Admin-Passwort aus. **Nach dem ersten Login
sofort ändern.**

## Starten

```powershell
.\run.ps1
```

oder direkt:

```powershell
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Anwendung erreichbar unter `http://localhost:8000` (im lokalen Netzwerk: `http://<Server-IP>:8000`).

## Tests

```powershell
poetry run pytest
```

Getestet werden insbesondere die steuerlich kritische Logik (Berechnung 10 %/20 % USt.,
Reverse-Charge, Werbesteuer) und die Nummernkreis-Logik (fortlaufende, konfigurierbare
Belegnummern).

## Produktivbetrieb mit MariaDB

`DATABASE_URL` in `.env` setzen, z. B.:

```
DATABASE_URL=mysql+pymysql://ws_verlag_user:CHANGE_ME@localhost:3306/ws_verlag
```

Datenbank und Benutzer vorher in MariaDB anlegen. Tabellen werden beim Start automatisch erzeugt
(`Base.metadata.create_all`); für spätere Schemaänderungen ist Alembic (`alembic/`) vorbereitet.

## Rollen

- **Admin**: Firmenstammdaten, Bankkonten, Zahlungsbedingungen, Belegnummernkreise, Mahnstufen,
  SMTP-Konfiguration, Benutzerverwaltung.
- **Sachbearbeiter**: Tagesgeschäft — Kunden, Artikel, Aufträge, Rechnungen, Gutschriften, Zahlungen,
  Mahnungen.

## Fachliche Kernregeln

- **Reverse-Charge**: gilt automatisch, wenn ein Kunde als EU-Ausland markiert ist und eine
  UID-Nummer hinterlegt hat — auf Rechnungen wird dann keine USt. ausgewiesen.
- **Werbesteuer (5 %, konfigurierbar)**: wird pauschal auf den Nettobetrag der gesamten Rechnung
  aufgeschlagen, wenn auf dem Beleg zugeordnet.
- **Gutschriften**: eigener Belegtyp mit eigenem Nummernkreis, referenzieren die Original-Rechnung.
- **Mahnwesen**: 3 Mahnstufen, jeweils mit editierbarem Text, Frist und Gebühr in den
  Firmenstammdaten konfigurierbar; Erstellung erfolgt manuell je Rechnung.
- **Belegnummern**: je Belegtyp (Auftrag/Rechnung/Gutschrift) eigener Nummernkreis mit
  konfigurierbarem Präfix, Suffix, Startnummer und Stellenanzahl.

## Offene Punkte / mögliche Erweiterungen

- Automatisierter Lauf für fällige Mahnungen (aktuell bewusst manuell ausgelöst).
- Export/Reporting für die Buchhaltung (z. B. Saldenlisten, USt.-Voranmeldung).
- Mehrsprachigkeit der Belege (aktuell nur Deutsch).
- Feingranularere Berechtigungen (z. B. read-only Buchhaltungsrolle).
