"""Privilegierter Sidecar-Container: fuehrt Docker-Update-Operationen fuer die
WS-Verlag Verwaltung aus (Pull, Backup, Container-Austausch, Health-Check, Rollback).

WICHTIG - Sicherheitsmodell:
- Nur DIESER Container hat Zugriff auf den Docker-Socket (/var/run/docker.sock).
  Der App-Container (ws-verlag-app) hat KEINEN Docker-Zugriff.
- Dieser Container sollte NICHT nach aussen exponiert werden (kein Port-Publish,
  nur internes Docker-Netzwerk). Socket-Zugriff ist aequivalent zu Root auf dem Host -
  entsprechend restriktiv behandeln (siehe README-DEPLOYMENT.md).
- Es wird ausschliesslich per Digest gepullt (docker pull <image>@sha256:...), Docker
  verifiziert den Inhalt dabei selbst inhaltsadressiert - kein zusaetzlicher Hash-Check noetig.
- Alte Version wird als gestoppter (nicht geloeschter) Container aufbewahrt, bis der
  naechste Update-Zyklus erfolgreich war -> jederzeit manuell wiederherstellbar.

Ablauf pro Zyklus:
  1. update_request.json im Signal-Verzeichnis lesen (vom Hauptcontainer geschrieben).
  2. Backup der Datenbank anlegen (SQLite-Datei kopieren oder MariaDB-Dump per docker exec).
  3. Neues Image per Digest pullen.
  4. Laufenden App-Container umbenennen (Rollback-Kandidat), neuen Container mit identischer
     Konfiguration (Env/Mounts/Netzwerk) aus dem neuen Image starten.
  5. Health-Check gegen /healthz im internen Netzwerk, mit Timeout.
  6. Erfolg: alten Container entfernen, Ergebnis an die App melden.
     Fehlschlag: neuen Container stoppen, alten Container reaktivieren, Ergebnis melden.

Zusaetzlich, unabhaengig vom Update-Ablauf: regelmaessige Datenbank-Sicherung.
  - Automatisch alle BACKUP_INTERVAL_HOURS Stunden (Default 24), erkannt anhand des
    Zeitstempels der juengsten vorhandenen Backup-Datei (kein zusaetzlicher State noetig -
    ein Update-Backup oder manuelles Backup verschiebt den naechsten faelligen Zeitpunkt,
    das ist bewusst so einfach gehalten).
  - Manuell ausloesbar per backup_request.json im Signal-Verzeichnis (siehe app/routers/help.py).
  - Nach jedem Backup werden alte Sicherungen ueber BACKUP_RETENTION_COUNT hinaus geloescht.
  - Sicherungen landen im gemeinsamen ./backups-Verzeichnis, das read-only auch in den
    App-Container gemountet ist (Hilfe-Seite listet sie direkt aus dem Dateisystem).

Zusaetzlich: Wiederherstellung (Restore) einer Sicherung, ausgeloest per restore_request.json
  im Signal-Verzeichnis (siehe app/routers/help.py, nur Admin, mit Bestaetigung in der UI).
  Vor dem Ueberschreiben wird sicherheitshalber selbst nochmal ein Backup angelegt. Das
  Ergebnis wird als restore_status.json ins Signal-Verzeichnis geschrieben (App liest das
  read-only, kein zusaetzlicher HTTP-Report-Endpunkt noetig - gleiches Volume wie fuers Signal).
"""
import io
import json
import os
import shutil
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path

import docker
import requests

SIGNAL_DIR = Path(os.environ.get("UPDATE_SIGNAL_DIR", "/update-signal"))
REQUEST_FILE = SIGNAL_DIR / "update_request.json"
BACKUP_REQUEST_FILE = SIGNAL_DIR / "backup_request.json"
RESTORE_REQUEST_FILE = SIGNAL_DIR / "restore_request.json"
RESTORE_STATUS_FILE = SIGNAL_DIR / "restore_status.json"
BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", "/backups"))
BACKUP_INTERVAL_HOURS = int(os.environ.get("BACKUP_INTERVAL_HOURS", "24"))
BACKUP_RETENTION_COUNT = int(os.environ.get("BACKUP_RETENTION_COUNT", "14"))
POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "15"))
HEALTHCHECK_TIMEOUT_SECONDS = int(os.environ.get("HEALTHCHECK_TIMEOUT_SECONDS", "90"))
HEALTHCHECK_URL = os.environ.get("HEALTHCHECK_URL", "http://ws-verlag-app:8000/healthz")
REPORT_URL = os.environ.get("REPORT_URL", "http://ws-verlag-app:8000/updates/report")
APP_CONTAINER_NAME = os.environ.get("APP_CONTAINER_NAME", "ws-verlag-app")
ROLLBACK_SUFFIX = "-rollback"

# Backup-Konfiguration: entweder SQLite-Datei-Pfad ODER MariaDB-Container-Name + Zugangsdaten.
SQLITE_DB_PATH = os.environ.get("SQLITE_DB_PATH", "")
MARIADB_CONTAINER_NAME = os.environ.get("MARIADB_CONTAINER_NAME", "")
MARIADB_DATABASE = os.environ.get("MARIADB_DATABASE", "ws_verlag")
MARIADB_USER = os.environ.get("MARIADB_USER", "root")
MARIADB_PASSWORD = os.environ.get("MARIADB_PASSWORD", "")

# GHCR-Zugangsdaten fuer den Image-Pull. Ein "docker login" auf dem Host wirkt sich NICHT
# auf Pulls aus, die dieser Container ueber die Docker-Engine-API (Socket) ausloest - die
# Engine-API braucht Credentials explizit im Request. Read-only PAT (Scope: read:packages)
# genuegt, siehe README-DEPLOYMENT.md.
GHCR_USERNAME = os.environ.get("GHCR_USERNAME", "")
GHCR_TOKEN = os.environ.get("GHCR_TOKEN", "")

client = docker.from_env()


def log(message: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat()}] {message}", flush=True)


def report(status: str, message: str = "") -> None:
    try:
        requests.post(REPORT_URL, json={"status": status, "message": message}, timeout=10)
    except requests.RequestException as exc:
        log(f"Konnte Ergebnis nicht an die App melden: {exc}")


def create_backup() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    if SQLITE_DB_PATH and Path(SQLITE_DB_PATH).exists():
        target = BACKUP_DIR / f"ws_verlag-{timestamp}.db"
        shutil.copy2(SQLITE_DB_PATH, target)
        log(f"SQLite-Backup angelegt: {target}")
        return target

    if MARIADB_CONTAINER_NAME:
        target = BACKUP_DIR / f"ws_verlag-{timestamp}.sql"
        dump_container = client.containers.get(MARIADB_CONTAINER_NAME)

        # "mariadb-dump" ist der aktuelle Binaername (mariadb:11-Image); "mysqldump" als
        # Fallback fuer aeltere Images, die noch den klassischen Namen mitbringen (gleiches
        # Muster wie beim Restore weiter unten mit "mariadb"/"mysql").
        last_exit_code = 127
        output = b""
        for dump_bin in ("mariadb-dump", "mysqldump"):
            exit_code, output = dump_container.exec_run(
                [dump_bin, f"-u{MARIADB_USER}", f"-p{MARIADB_PASSWORD}", MARIADB_DATABASE]
            )
            last_exit_code = exit_code
            if exit_code == 0:
                break

        if last_exit_code != 0:
            raise RuntimeError(f"mariadb-dump/mysqldump fehlgeschlagen (exit {last_exit_code})")
        target.write_bytes(output)
        log(f"MariaDB-Backup angelegt: {target}")
        return target

    raise RuntimeError("Weder SQLITE_DB_PATH noch MARIADB_CONTAINER_NAME konfiguriert - kein Backup moeglich.")


def _backup_files() -> list[Path]:
    if not BACKUP_DIR.is_dir():
        return []
    return [p for p in BACKUP_DIR.iterdir() if p.is_file() and p.name.startswith("ws_verlag-")]


def rotate_backups(retention: int = BACKUP_RETENTION_COUNT) -> None:
    """Behaelt nur die 'retention' juengsten Backup-Dateien, aeltere werden geloescht."""
    files = sorted(_backup_files(), key=lambda p: p.stat().st_mtime, reverse=True)
    for old_file in files[retention:]:
        old_file.unlink(missing_ok=True)
        log(f"Alte Sicherung geloescht (Rotation): {old_file}")


def latest_backup_age_seconds() -> float | None:
    files = _backup_files()
    if not files:
        return None
    newest_mtime = max(p.stat().st_mtime for p in files)
    return time.time() - newest_mtime


def run_backup_cycle() -> None:
    create_backup()
    rotate_backups()


def write_restore_status(status: str, message: str, filename: str) -> None:
    payload = {
        "status": status,
        "message": message[:500],
        "filename": filename,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    RESTORE_STATUS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _copy_file_into_container(container, file_path: Path, container_dir: str) -> None:
    tar_stream = io.BytesIO()
    with tarfile.open(fileobj=tar_stream, mode="w") as tar:
        tar.add(str(file_path), arcname=file_path.name)
    tar_stream.seek(0)
    container.put_archive(container_dir, tar_stream)


def restore_backup(filename: str) -> None:
    """Ueberschreibt die aktuelle Datenbank mit dem Inhalt der angegebenen Sicherungsdatei.
    filename muss bereits von app/routers/help.py gegen die tatsaechlich vorhandenen
    Backup-Dateien geprueft worden sein; hier trotzdem sicherheitshalber nur der reine
    Dateiname ohne Pfadanteil verwendet."""
    backup_file = BACKUP_DIR / Path(filename).name
    if not backup_file.is_file():
        raise RuntimeError(f"Sicherungsdatei nicht gefunden: {filename}")

    log(f"Stelle Sicherung wieder her: {filename}")
    run_backup_cycle()  # Sicherheitsnetz: Stand vor dem Restore bleibt selbst als Backup erhalten.

    if SQLITE_DB_PATH:
        shutil.copy2(backup_file, SQLITE_DB_PATH)
        log(f"SQLite-Datenbank aus {filename} wiederhergestellt.")
        return

    if MARIADB_CONTAINER_NAME:
        dump_container = client.containers.get(MARIADB_CONTAINER_NAME)
        _copy_file_into_container(dump_container, backup_file, "/tmp")
        # Konstanter Zielname im Container, damit der Shell-Befehl unten keinen
        # variablen Dateinamen enthalten muss.
        dump_container.exec_run(["mv", f"/tmp/{backup_file.name}", "/tmp/restore_source"])

        # Zugangsdaten bewusst als Umgebungsvariablen statt String-Interpolation in den
        # Shell-Befehl, damit Sonderzeichen im Passwort keine Shell-Injection ermoeglichen.
        env = {"DB_USER": MARIADB_USER, "DB_PASSWORD": MARIADB_PASSWORD, "DB_NAME": MARIADB_DATABASE}
        restore_commands = [
            'mariadb -u"$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" < /tmp/restore_source',
            'mysql -u"$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" < /tmp/restore_source',
        ]

        last_exit_code = 127
        last_output = b""
        for command in restore_commands:
            exit_code, output = dump_container.exec_run(["sh", "-c", command], environment=env)
            last_exit_code = exit_code
            last_output = output
            if exit_code == 0:
                break

        dump_container.exec_run(["rm", "-f", "/tmp/restore_source"])

        if last_exit_code != 0:
            raise RuntimeError(
                f"Wiederherstellung fehlgeschlagen (exit {last_exit_code}): "
                f"{last_output.decode(errors='replace')[:300]}"
            )
        log(f"MariaDB-Datenbank aus {filename} wiederhergestellt.")
        return

    raise RuntimeError("Weder SQLITE_DB_PATH noch MARIADB_CONTAINER_NAME konfiguriert - keine Wiederherstellung moeglich.")


def pull_new_image(image_ref: str, image_digest: str) -> str:
    full_ref = f"{image_ref}@{image_digest}"
    log(f"Ziehe neues Image: {full_ref}")
    auth_config = {"username": GHCR_USERNAME, "password": GHCR_TOKEN} if GHCR_USERNAME and GHCR_TOKEN else None
    image = client.images.pull(full_ref, auth_config=auth_config)
    return image.id


def _convert_port_bindings(raw_bindings: dict | None) -> dict | None:
    """Wandelt das rohe Docker-Engine-Format von HostConfig.PortBindings
    (z. B. {"8000/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8000"}]}) in das von
    docker-py's containers.run(ports=...) erwartete Format um. Ohne diese Umwandlung
    verliert der neue Container beim Update jede Portfreigabe des alten Containers."""
    if not raw_bindings:
        return None
    ports: dict = {}
    for container_port, host_entries in raw_bindings.items():
        if not host_entries:
            continue
        values = [
            (entry["HostIp"], entry["HostPort"]) if entry.get("HostIp") else entry["HostPort"]
            for entry in host_entries
        ]
        ports[container_port] = values if len(values) > 1 else values[0]
    return ports or None


def recreate_container(new_image_id: str) -> None:
    old_container = client.containers.get(APP_CONTAINER_NAME)
    config = old_container.attrs["Config"]
    host_config = old_container.attrs["HostConfig"]
    networks = list(old_container.attrs["NetworkSettings"]["Networks"].keys())

    # Alten Container umbenennen statt loeschen -> sofortiges Rollback moeglich.
    old_container.rename(APP_CONTAINER_NAME + ROLLBACK_SUFFIX)
    old_container.stop(timeout=30)

    new_container = client.containers.run(
        new_image_id,
        name=APP_CONTAINER_NAME,
        detach=True,
        environment=config.get("Env", []),
        volumes=host_config.get("Binds", []),
        ports=_convert_port_bindings(host_config.get("PortBindings")),
        network=networks[0] if networks else None,
        restart_policy=host_config.get("RestartPolicy"),
    )
    log(f"Neuer Container gestartet: {new_container.short_id}")


def wait_for_healthy() -> bool:
    deadline = time.monotonic() + HEALTHCHECK_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            response = requests.get(HEALTHCHECK_URL, timeout=5)
            if response.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(3)
    return False


def rollback() -> None:
    """Setzt den zuvor umbenannten, noch laufenden/gestoppten alten Container wieder als
    ws-verlag-app ein. Wird NUR aufgerufen, wenn recreate_container() tatsaechlich
    ausgefuehrt wurde (siehe process_request) - sonst wuerde ein noch unveraenderter,
    gesunder App-Container faelschlich als 'fehlgeschlagenes Update' entfernt."""
    try:
        failed = client.containers.get(APP_CONTAINER_NAME)
        failed.stop(timeout=10)
        failed.remove()
    except docker.errors.NotFound:
        pass

    old_container = client.containers.get(APP_CONTAINER_NAME + ROLLBACK_SUFFIX)
    old_container.rename(APP_CONTAINER_NAME)
    old_container.start()
    log("Rollback auf vorherige Version durchgefuehrt.")


def cleanup_rollback_container() -> None:
    try:
        old_container = client.containers.get(APP_CONTAINER_NAME + ROLLBACK_SUFFIX)
        old_container.remove(force=True)
    except docker.errors.NotFound:
        pass


def process_request(payload: dict) -> None:
    image_ref = payload["image"]
    image_digest = payload["image_digest"]
    target_version = payload.get("target_version", "?")

    log(f"Update auf Version {target_version} angefordert ({image_ref}@{image_digest}).")
    report("wird_installiert", f"Installation von Version {target_version} laeuft.")

    container_swapped = False
    try:
        run_backup_cycle()
        new_image_id = pull_new_image(image_ref, image_digest)

        # Ab hier wird der laufende Container tatsaechlich angefasst - erst jetzt darf im
        # Fehlerfall ein Rollback ausgeloest werden. Schlaegt Backup oder Pull VORHER fehl,
        # laeuft der bisherige, unveraenderte Container einfach unbeeinflusst weiter.
        container_swapped = True
        recreate_container(new_image_id)

        if wait_for_healthy():
            cleanup_rollback_container()
            report("erfolgreich", f"Version {target_version} erfolgreich installiert.")
            log("Update erfolgreich.")
        else:
            rollback()
            report("zurueckgerollt", "Health-Check nach Update fehlgeschlagen - automatisch zurueckgesetzt.")

    except Exception as exc:  # noqa: BLE001 - jeder Fehler muss zu einem gemeldeten Ergebnis fuehren
        log(f"Fehler beim Update: {exc}")
        if not container_swapped:
            # Der bisherige Container wurde nicht angefasst (Backup/Pull schlugen vorher fehl) -
            # kein Rollback noetig, die App laeuft unveraendert weiter.
            report("fehlgeschlagen", f"Installation abgebrochen, App laeuft unveraendert weiter: {exc}"[:500])
            return
        try:
            rollback()
            report("zurueckgerollt", f"Fehler waehrend Installation, zurueckgesetzt: {exc}"[:500])
        except Exception as rollback_exc:  # noqa: BLE001
            log(f"Rollback fehlgeschlagen: {rollback_exc}")
            report("fehlgeschlagen", f"Update UND Rollback fehlgeschlagen: {rollback_exc}"[:500])


def main() -> None:
    log("Updater gestartet, warte auf Update-/Sicherungs-Anforderungen...")
    while True:
        if REQUEST_FILE.exists():
            try:
                payload = json.loads(REQUEST_FILE.read_text(encoding="utf-8"))
                REQUEST_FILE.unlink()
                process_request(payload)
            except (json.JSONDecodeError, KeyError) as exc:
                log(f"Ungueltige Update-Anforderung ignoriert: {exc}")
                REQUEST_FILE.unlink(missing_ok=True)

        if BACKUP_REQUEST_FILE.exists():
            BACKUP_REQUEST_FILE.unlink(missing_ok=True)
            log("Manuelle Sicherung angefordert.")
            try:
                run_backup_cycle()
            except Exception as exc:  # noqa: BLE001 - Fehler darf die Schleife nicht beenden
                log(f"Manuelle Sicherung fehlgeschlagen: {exc}")

        if RESTORE_REQUEST_FILE.exists():
            filename = ""
            try:
                payload = json.loads(RESTORE_REQUEST_FILE.read_text(encoding="utf-8"))
                filename = payload["filename"]
                RESTORE_REQUEST_FILE.unlink()
                restore_backup(filename)
                write_restore_status("erfolgreich", f"Sicherung {filename} erfolgreich wiederhergestellt.", filename)
            except Exception as exc:  # noqa: BLE001 - Fehler darf die Schleife nicht beenden
                log(f"Wiederherstellung fehlgeschlagen: {exc}")
                RESTORE_REQUEST_FILE.unlink(missing_ok=True)
                write_restore_status("fehlgeschlagen", str(exc), filename)

        age_seconds = latest_backup_age_seconds()
        if age_seconds is None or age_seconds >= BACKUP_INTERVAL_HOURS * 3600:
            log("Regelmaessige Sicherung faellig.")
            try:
                run_backup_cycle()
            except Exception as exc:  # noqa: BLE001 - Fehler darf die Schleife nicht beenden
                log(f"Regelmaessige Sicherung fehlgeschlagen: {exc}")

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
