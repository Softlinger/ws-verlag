from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Zentrale Konfiguration. Werte via .env oder Umgebungsvariablen ueberschreibbar."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Datenbank: ausschliesslich MariaDB/MySQL. SQLite wird in diesem Projekt nicht
    # mehr unterstuetzt (Mehrfaehigkeit ist Pflicht; FOR UPDATE / Transaktions-
    # Isolierung / Fremdschluessel-Enforcement sind nur bei MariaDB verlaesslich).
    # Pflichtfeld ohne stillen Default: ohne gesetzte DATABASE_URL bricht die App
    # beim Start mit klarer Meldung ab (siehe Validator).
    database_url: str

    @field_validator("database_url")
    @classmethod
    def _require_mariadb(cls, value: str) -> str:
        if not value.startswith(("mysql+pymysql://", "mysql://", "mariadb://")):
            raise ValueError(
                "DATABASE_URL muss eine MariaDB/MySQL-Verbindung sein "
                "(z. B. mysql+pymysql://user:pass@host:3306/ws_verlag). "
                "SQLite wird nicht mehr unterstuetzt."
            )
        return value

    secret_key: str = "change-me-in-production-please"
    session_cookie_name: str = "ws_verlag_session"
    session_max_age_seconds: int = 60 * 60 * 10  # 10 Stunden

    app_name: str = "WS-Verlag Verwaltung"
    port: int = 8000

    # Update-Check gegen das Auslieferungsverzeichnis auf der Website.
    update_manifest_url: str = "https://www.weidlinger-soft.at/apps/ws-verlag/version.json"
    update_check_interval_hours: int = 24
    update_check_enabled: bool = True

    # Optionale Ed25519-Signaturpruefung des Update-Manifests (Base64-Public-Key,
    # raw 32 Bytes). Leer => keine Pruefung (Manifest bleibt vertrauenswuerdig allein
    # ueber HTTPS). Wenn gesetzt, muss das Manifest ein Feld "signature" tragen, das
    # die kanonischen Nutzdaten signiert - schuetzt vor einer kompromittierten
    # Website/Registry-Promotion, die ein fremdes Image-Digest ausliefert.
    update_manifest_public_key: str = ""

    # Nur relevant im Docker-/NAS-Betrieb: Verzeichnis, ueber das die App dem separaten,
    # privilegierten Updater-Container ein Update-Signal uebergibt (gemeinsames Volume).
    update_signal_dir: str = "/update-signal"

    # Nur relevant im Docker-Betrieb: read-only in den App-Container gemountetes
    # Backup-Verzeichnis (der Updater-Container schreibt dort, siehe updater/updater.py).
    backups_dir: str = "/backups"

    # Gemeinsames Geheimnis zwischen App und Updater-Container. Der Updater meldet
    # Update-/Sicherungs-Ergebnisse gegen dieses Token (Header X-Updater-Token), damit
    # nicht irgendein LAN-Teilnehmer /updates/report aufrufen und den Status
    # manipolieren kann. Leer => Prüfung deaktiviert (z. B. lokale Entwicklung).
    updater_token: str = ""

    # Wartungsfenster: solange ein Update laeuft (apply_status ANGEFORDERT /
    # WIRD_INSTALLIERT), blockiert die App normalen Benutzerzugriff (503), damit
    # niemand waehrend Backup/Container-Tausch auf App oder DB schreibt. Saengt ein
    # Update (Updater crasht vor dem Abschluss-Report), gilt das Fenster nur so lange
    # wie seit apply_requested_at vergangen ist - danach hebt der Guard automatisch auf.
    update_maintenance_timeout_seconds: int = 900


settings = Settings()
