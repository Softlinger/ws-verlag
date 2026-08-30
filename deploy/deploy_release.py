"""Laedt den Inhalt von deploy/release_upload/ per FTPS (FTP over TLS) auf den
Webserver hoch, in das Verzeichnis https://www.weidlinger-soft.at/apps/ws-verlag/.

Verwendung (nach Freigabe eines Releases):
  1. deploy/release_upload/version.json aktuell halten (siehe
     docs/update-manifest-format.md fuer das Format).
  2. poetry run python deploy/deploy_release.py

Zugangsdaten kommen ausschliesslich aus deploy/.env.deploy (gitignored, niemals
committen). Vorlage: deploy/.env.deploy.example.

Sicherheit:
- Es wird ausschliesslich FTPS (verschluesselt) verwendet, kein Klartext-FTP -
  Zugangsdaten und Dateien laufen sonst unverschluesselt ueber das Netz.
- Es werden nur Dateien innerhalb von deploy/release_upload/ hochgeladen, niemals
  das gesamte Repository.
"""
import ftplib
import os
import sys
from pathlib import Path

DEPLOY_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = DEPLOY_DIR / "release_upload"
ENV_FILE = DEPLOY_DIR / ".env.deploy"


def load_env(path: Path) -> dict[str, str]:
    if not path.exists():
        print(f"FEHLER: {path} nicht gefunden. Vorlage: {path.with_suffix('.example' + path.suffix)}")
        sys.exit(1)
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def upload_directory(ftps: ftplib.FTP_TLS, local_dir: Path, remote_dir: str) -> None:
    for entry in sorted(local_dir.iterdir()):
        remote_path = f"{remote_dir}/{entry.name}"
        if entry.is_dir():
            try:
                ftps.mkd(remote_path)
            except ftplib.error_perm:
                pass  # Verzeichnis existiert bereits
            upload_directory(ftps, entry, remote_path)
        else:
            print(f"Lade hoch: {entry.relative_to(UPLOAD_DIR)} -> {remote_path}")
            with entry.open("rb") as f:
                ftps.storbinary(f"STOR {remote_path}", f)


def main() -> None:
    if not UPLOAD_DIR.exists() or not any(UPLOAD_DIR.iterdir()):
        print(f"FEHLER: {UPLOAD_DIR} existiert nicht oder ist leer. Erst version.json dort ablegen.")
        sys.exit(1)

    env = load_env(ENV_FILE)
    host = env["FTP_HOST"]
    user = env["FTP_USER"]
    password = env["FTP_PASSWORD"]
    remote_dir = env.get("FTP_REMOTE_DIR", "/apps/ws-verlag")

    print(f"Verbinde per FTPS zu {host} ...")
    ftps = ftplib.FTP_TLS(host, timeout=30)
    try:
        ftps.login(user=user, passwd=password)
        ftps.prot_p()  # Datenkanal ebenfalls verschluesseln, nicht nur den Login.

        try:
            ftps.mkd(remote_dir)
        except ftplib.error_perm:
            pass  # Verzeichnis existiert bereits

        upload_directory(ftps, UPLOAD_DIR, remote_dir)
        print("Upload abgeschlossen.")
    finally:
        ftps.quit()


if __name__ == "__main__":
    main()
