# Update-Manifest-Format (`version.json`)

Muss unter `https://www.weidlinger-soft.at/apps/ws-verlag/version.json` per HTTPS
abrufbar sein (dieses Verzeichnis auf der Website existiert noch nicht und muss beim
Website-Update separat aufgebaut werden — siehe Master-Prompt Website-Arbeit für
Sicherheits-/Datenschutzanforderungen an diesen Bereich der Website selbst).

## Schema

```json
{
  "version": "1.1.0",
  "release_date": "2026-09-15",
  "changelog": "- Neue Funktion X\n- Fehlerbehebung Y",
  "image": "ghcr.io/Softlinger/ws-verlag",
  "image_digest": "sha256:3a1b...c9",
  "min_upgrade_from": "1.0.0"
}
```

| Feld | Pflicht | Beschreibung |
|---|---|---|
| `version` | ja | SemVer-Versionsnummer der neuen Version (`MAJOR.MINOR.PATCH`). Wird per `packaging.version` mit der installierten Version verglichen — nur bei echtem Anstieg wird ein Update angezeigt. |
| `release_date` | nein | Anzeige-Datum, beliebiges Format (nur Text, keine Berechnung). |
| `changelog` | nein | Freitext, wird 1:1 in der App angezeigt (kein HTML — wird als reiner Text gerendert). |
| `image` | ja | Vollständige Docker-Image-Referenz ohne Tag/Digest, z. B. `ghcr.io/Softlinger/ws-verlag`. |
| `image_digest` | ja | Inhaltsadressierter SHA-256-Digest des Images (`docker inspect --format '{{.RepoDigests}}'` nach dem Build). Der Updater pullt ausschließlich per `<image>@<digest>` — Docker verifiziert die Integrität dabei selbst. |
| `min_upgrade_from` | nein | Informativ, aktuell nicht ausgewertet. Vorgesehen für künftige Sprünge, die eine Zwischenversion erfordern. |

## Sicherheitsanforderungen an die Auslieferung

- **Nur HTTPS**, kein automatisches Folgen von Redirects (die App bricht bei Nicht-HTTPS ab).
- Der Digest muss zum tatsächlich gepushten Image passen — bei jedem Release nach dem
  Build/Push erneut ermitteln, niemals von Hand raten oder wiederverwenden.
- Ein Downgrade (niedrigere `version` als installiert) wird von der App ignoriert.
- Das Manifest selbst wird aktuell nicht signiert (Entscheidung: SHA-256 über den
  Docker-Digest statt zusätzlicher Signatur, siehe Rückfrage vom 2026-08-30). Der
  Schutz beruht auf HTTPS (Transportintegrität) + Docker-Content-Digest (Inhaltsintegrität).
  Bei Bedarf später auf signierte Manifeste (z. B. Sigstore/cosign) umstellen.

## Release-Ablauf (Kurzfassung)

Ein Kommando deckt Versionsbump, Commit/Tag, Docker-Build/Push, Digest-Ermittlung und
FTP-Upload von `version.json` ab (Details siehe `README-DEPLOYMENT.md`):

```bash
poetry run python deploy/release.py 1.1.0 --changelog "..."
```

Kunden-Instanzen prüfen automatisch beim nächsten Admin-Login bzw. binnen 24h und zeigen
danach die Update-Bestätigung ("Soll ich das Update installieren?") an.
