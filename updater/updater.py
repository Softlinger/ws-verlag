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
"""
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import docker
import requests

SIGNAL_DIR = Path(os.environ.get("UPDATE_SIGNAL_DIR", "/update-signal"))
REQUEST_FILE = SIGNAL_DIR / "update_request.json"
BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", "/backups"))
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
        exit_code, output = dump_container.exec_run(
            ["mysqldump", f"-u{MARIADB_USER}", f"-p{MARIADB_PASSWORD}", MARIADB_DATABASE]
        )
        if exit_code != 0:
            raise RuntimeError(f"mysqldump fehlgeschlagen (exit {exit_code})")
        target.write_bytes(output)
        log(f"MariaDB-Backup angelegt: {target}")
        return target

    raise RuntimeError("Weder SQLITE_DB_PATH noch MARIADB_CONTAINER_NAME konfiguriert - kein Backup moeglich.")


def pull_new_image(image_ref: str, image_digest: str) -> str:
    full_ref = f"{image_ref}@{image_digest}"
    log(f"Ziehe neues Image: {full_ref}")
    image = client.images.pull(full_ref)
    return image.id


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

    try:
        create_backup()
        new_image_id = pull_new_image(image_ref, image_digest)
        recreate_container(new_image_id)

        if wait_for_healthy():
            cleanup_rollback_container()
            report("erfolgreich", f"Version {target_version} erfolgreich installiert.")
            log("Update erfolgreich.")
        else:
            rollback()
            report("zurueckgerollt", "Health-Check nach Update fehlgeschlagen - automatisch zurueckgesetzt.")

    except Exception as exc:  # noqa: BLE001 - jeder Fehler muss zu einem gemeldeten Rollback fuehren
        log(f"Fehler beim Update: {exc}")
        try:
            rollback()
            report("zurueckgerollt", f"Fehler waehrend Installation, zurueckgesetzt: {exc}"[:500])
        except Exception as rollback_exc:  # noqa: BLE001
            log(f"Rollback fehlgeschlagen: {rollback_exc}")
            report("fehlgeschlagen", f"Update UND Rollback fehlgeschlagen: {rollback_exc}"[:500])


def main() -> None:
    log("Updater gestartet, warte auf Update-Anforderungen...")
    while True:
        if REQUEST_FILE.exists():
            try:
                payload = json.loads(REQUEST_FILE.read_text(encoding="utf-8"))
                REQUEST_FILE.unlink()
                process_request(payload)
            except (json.JSONDecodeError, KeyError) as exc:
                log(f"Ungueltige Update-Anforderung ignoriert: {exc}")
                REQUEST_FILE.unlink(missing_ok=True)
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
