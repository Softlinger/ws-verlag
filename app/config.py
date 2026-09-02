from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Zentrale Konfiguration. Werte via .env oder Umgebungsvariablen ueberschreibbar."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Datenbank: Standard SQLite fuer lokale Entwicklung/Test ohne Server-Abhaengigkeit.
    # Produktiv: MariaDB via z. B. "mysql+pymysql://user:pass@host:3306/ws_verlag"
    database_url: str = "sqlite:///./ws_verlag.db"

    secret_key: str = "change-me-in-production-please"
    session_cookie_name: str = "ws_verlag_session"
    session_max_age_seconds: int = 60 * 60 * 10  # 10 Stunden

    app_name: str = "WS-Verlag Verwaltung"
    port: int = 8000

    # Update-Check gegen das Auslieferungsverzeichnis auf der Website.
    update_manifest_url: str = "https://www.weidlinger-soft.at/apps/ws-verlag/version.json"
    update_check_interval_hours: int = 24
    update_check_enabled: bool = True

    # Nur relevant im Docker-/NAS-Betrieb: Verzeichnis, ueber das die App dem separaten,
    # privilegierten Updater-Container ein Update-Signal uebergibt (gemeinsames Volume).
    update_signal_dir: str = "/update-signal"

    # Nur relevant im Docker-Betrieb: read-only in den App-Container gemountetes
    # Backup-Verzeichnis (der Updater-Container schreibt dort, siehe updater/updater.py).
    backups_dir: str = "/backups"


settings = Settings()
