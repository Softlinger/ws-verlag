# Produktiv-Deployment auf Synology NAS (Docker/Container Manager)

Dieses Dokument beschreibt den produktiven Betrieb mit automatischem Update-Mechanismus.
Für lokale Entwicklung siehe `README.md` (Poetry + SQLite, ohne Docker).

## Architektur

Drei Container, ein internes Docker-Netzwerk:

- **`ws-verlag-app`** — die Anwendung selbst. Kein Docker-Socket-Zugriff, keine erhöhten
  Rechte, läuft als Nicht-root-Benutzer im Container.
- **`ws-verlag-db`** — MariaDB.
- **`ws-verlag-updater`** — einziger Container mit Zugriff auf den Docker-Socket des Hosts.
  Führt Backup, Image-Pull, Container-Austausch, Health-Check und ggf. automatischen
  Rollback aus, wenn ein Update über die App bestätigt wurde. **Nicht nach außen exponieren.**

Ablauf: Die App prüft periodisch (Standard alle 24h) sowie bei jedem Admin-Login das
Manifest unter `https://www.weidlinger-soft.at/apps/ws-verlag/version.json`. Ist eine neuere
Version verfügbar, erscheint im Dashboard/unter „Updates“ die Frage *„Soll ich das Update
installieren?“*. Nach Bestätigung schreibt die App ein Signal auf ein gemeinsames Volume;
der Updater-Container liest dieses Signal, legt ein Backup an, tauscht den App-Container
gegen die neue Version aus, prüft `/healthz` und rollt bei Fehlschlag automatisch auf die
vorherige (aufbewahrte, nicht gelöschte) Version zurück.

## Wichtiger Sicherheitshinweis: Docker-Socket

`ws-verlag-updater` hat über `/var/run/docker.sock` faktisch Root-Rechte auf dem NAS-Host
(kann beliebige Container starten/stoppen, auf den Host zugreifen). Das ist für den
automatischen Selbst-Update-Mechanismus ohne Vor-Ort-Support notwendig, aber bewusst auf
genau diesen einen Container beschränkt:

- Niemals einen Port dieses Containers veröffentlichen.
- Niemals den App-Container (`ws-verlag-app`) selbst mit Docker-Socket-Zugriff versehen.
- Zugriff auf die Synology (SSH, DSM-Login) entsprechend absichern (starke Passwörter,
  2FA, keine Portweiterleitung von außen ohne VPN).

## Ersteinrichtung

```bash
cp .env.example .env
# .env bearbeiten: SECRET_KEY, MARIADB_PASSWORD, MARIADB_ROOT_PASSWORD setzen

docker build -t ws-verlag-app:local .
docker compose up -d

# Einmalig: Admin-Benutzer + Grunddaten anlegen
docker compose exec app python scripts/seed.py
```

Anwendung danach im lokalen Netzwerk erreichbar (Port und Freigabe je nach gewünschter
Synology-Netzwerkkonfiguration — Reverse Proxy im DSM empfohlen, nicht direkt ins Internet).

## Updates

Laufen automatisch nach Bestätigung in der App ab (siehe oben). Manuell auslösen:

```bash
docker compose exec app curl -X POST http://localhost:8000/updates/check
```

Backups landen unter `./backups` (Host-Verzeichnis, im Compose gemountet) — regelmäßig
extern sichern (z. B. Synology Hyper Backup auf dieses Verzeichnis ansetzen).

## Verifiziert (2026-08-30, lokaler Docker-Test)

Kompletter Stack (App + MariaDB + Updater) gebaut und gestartet, Seed gegen MariaDB
ausgeführt, sowie Update- und Rollback-Pfad des Updater-Containers gegen echte
Docker-Container getestet: Container-Austausch mit Health-Check bei Erfolg, automatischer
Rollback bei fehlgeschlagenem Health-Check — beide Fälle funktionierten wie vorgesehen.

**Wichtige Randnotiz aus diesem Test:** Der Updater tauscht Container direkt über die
Docker-Engine aus (nicht über `docker compose`). Nach einem durchgeführten Update/Rollback
kennt `docker compose down` diesen neu erzeugten Container nicht mehr über die
Compose-Projekt-Labels — `docker compose up -d` funktioniert danach weiterhin normal,
aber ein `docker compose down` sollte in der Praxis mit `docker ps -a` gegengeprüft werden,
falls der App-Container danach nicht mit entfernt wurde.

## Bugfix nach Live-Test gegen die echte Website (2026-08-30)

Beim ersten Check gegen `https://www.weidlinger-soft.at/apps/ws-verlag/version.json`
stellte sich heraus, dass dort noch das Platzhalter-Beispiel aus
`docs/update-manifest-format.md` liegt (Version 1.1.0, ungültiger Digest `sha256:3a1b...c9`).
**Das muss durch ein echtes Release oder eine version.json mit `version: "0.1.0"` (=
aktuell installierte Version, zeigt dann kein Update an) ersetzt werden, bevor Kunden-
Instanzen produktiv gegen diese URL prüfen.**

Dabei wurde ein echter Fehler im Updater gefunden und behoben: Schlug `create_backup()`
oder `pull_new_image()` fehl (z. B. wegen eines ungültigen Digests wie im Platzhalter),
löste der `except`-Block trotzdem `rollback()` aus — das hätte den noch unveränderten,
gesunden laufenden App-Container fälschlich gestoppt und entfernt, obwohl der eigentliche
Container-Austausch nie stattgefunden hatte. `updater.py` verfolgt jetzt explizit, ob der
Container-Austausch bereits begonnen hat (`container_swapped`), und ruft `rollback()` nur
noch auf, wenn das der Fall ist. Schlägt Backup/Pull vorher fehl, läuft die App unverändert
weiter und es wird lediglich `fehlgeschlagen` gemeldet.

## Bekannte Grenzen

- Datenbankschema-Änderungen zwischen Versionen werden aktuell nur additiv über
  `Base.metadata.create_all` beim App-Start abgedeckt. Für Migrationen mit Spalten-
  Umbenennungen/-Löschungen muss vor dem Release eine Alembic-Migration ergänzt und im
  Update-Prozess ausgeführt werden (aktuell nicht automatisiert — siehe `alembic/`).
- Der Updater rekonstruiert die Container-Konfiguration aus dem laufenden Container
  (Env/Mounts/Netzwerk). Änderungen an `docker-compose.yml` (z. B. neue Volumes) zwischen
  Versionen erfordern einen manuellen `docker compose up -d` zusätzlich zum Auto-Update.
