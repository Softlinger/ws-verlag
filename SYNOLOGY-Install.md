# WS-Verlag Verwaltung auf der Synology NAS installieren

> **Hinweis (2026-09-01):** Beim aktuellen Kunden wird **nicht mehr die Synology NAS**
> als Zielserver verwendet — die NAS hat keine ausreichenden Kapazitäten mehr für die
> Docker-Installation. Stattdessen kommt ein leistungsfähiger, 24/7 laufender Windows-PC
> zum Einsatz, siehe **`install-pc.md`**. Diese Anleitung bleibt als Referenz erhalten,
> falls künftig doch wieder eine Synology NAS als Zielserver zum Einsatz kommt.

Diese Anleitung richtet sich an Personen **ohne Docker- oder Kommandozeilen-Erfahrung**.
Jeder Schritt wird einzeln erklärt. Wenn ein Punkt unklar ist, lieber vorher nachfragen als
raten — insbesondere bei Passwörtern und Netzwerk-Einstellungen.

Geschätzte Dauer: 30–45 Minuten.

---

## Inhaltsverzeichnis

1. [Voraussetzungen](#1-voraussetzungen)
2. [Container Manager installieren](#2-container-manager-installieren)
3. [Ordner auf der NAS anlegen](#3-ordner-auf-der-nas-anlegen)
4. [Projektdateien auf die NAS kopieren](#4-projektdateien-auf-die-nas-kopieren)
5. [Konfigurationsdatei (.env) erstellen](#5-konfigurationsdatei-env-erstellen)
6. [Projekt in Container Manager starten](#6-projekt-in-container-manager-starten)
7. [Admin-Benutzer anlegen (einmalig)](#7-admin-benutzer-anlegen-einmalig)
8. [Zugriff im Netzwerk testen](#8-zugriff-im-netzwerk-testen)
9. [Sicherer Zugriff per HTTPS (Reverse Proxy)](#9-sicherer-zugriff-per-https-reverse-proxy)
10. [Automatische Datensicherung einrichten](#10-automatische-datensicherung-einrichten)
11. [Updates](#11-updates)
12. [Fehlerbehebung](#12-fehlerbehebung)
13. [Sicherheitshinweise](#13-sicherheitshinweise)

---

## 1. Voraussetzungen

- Eine Synology NAS mit **DSM 7.2 oder neuer** (Container Manager erfordert DSM 7.2+).
  Prüfen: DSM oben rechts → Zahnrad-Symbol → *Systemsteuerung* → *Info-Center* → Reiter
  *Allgemein* → Feld „DSM-Version".
- Mindestens **4 GB RAM** auf der NAS (MariaDB + App + Updater laufen gleichzeitig).
- Ein Benutzerkonto auf der NAS mit **Administrator-Rechten**.
- Internetzugang der NAS (zum Herunterladen des Docker-Images).
- Ein Windows-/Mac-Rechner im selben Netzwerk, um DSM im Browser zu bedienen und Dateien
  hochzuladen.

Alle folgenden Schritte finden über die **DSM-Weboberfläche** statt
(`http://<NAS-IP>:5000` bzw. `https://<NAS-IP>:5001`). Eine SSH-Konsole wird **nicht**
benötigt.

---

## 2. Container Manager installieren

1. In DSM öffnen: **Paket-Zentrum** (App-Symbol auf dem Desktop).
2. Suchfeld oben rechts: `Container Manager` eingeben.
3. Bei *Container Manager* auf **Installieren** klicken und den Vorgang abwarten.
4. Nach der Installation öffnet sich das Programm automatisch (oder über das
   Hauptmenü-Symbol oben links → *Container Manager*).

---

## 3. Ordner auf der NAS anlegen

Die Anwendung braucht drei feste Ordner. Diese über **File Station** anlegen:

1. **File Station** öffnen (Hauptmenü → File Station).
2. Im freigegebenen Ordner `docker` (falls nicht vorhanden: mit Rechtsklick →
   *Neuer Ordner* anlegen, Name `docker`) folgende Unterstruktur anlegen:

   ```
   docker/
     ws-verlag/
       backups/
       updater/
   ```

   Konkret: In `docker` einen Ordner `ws-verlag` anlegen, darin die zwei leeren Ordner
   `backups` und `updater`.

Ergebnis danach: `docker/ws-verlag/backups` und `docker/ws-verlag/updater` existieren.

---

## 4. Projektdateien auf die NAS kopieren

Aus dem Projekt-Repository werden **nur wenige Dateien** benötigt (der Anwendungscode
selbst kommt fertig gebaut als Docker-Image aus dem Internet — nicht als Quellcode auf
die NAS).

Vom bereitgestellten Projektordner (auf dem PC, z. B. `D:\dev\WS-Verlag-nxt`) folgende
Dateien in **File Station → docker → ws-verlag** hochladen (Drag & Drop funktioniert):

| Datei/Ordner auf dem PC | Ziel auf der NAS |
|---|---|
| `docker-compose.yml` | `docker/ws-verlag/docker-compose.yml` |
| `.env.example` | `docker/ws-verlag/.env.example` |
| gesamter Ordner `updater/` (mit `Dockerfile`, `requirements.txt`, `updater.py`) | `docker/ws-verlag/updater/` |

Hochladen in File Station: Zielordner öffnen → Symbol **Hochladen** (Wolke mit Pfeil) →
Dateien auswählen. Für den `updater`-Ordner: den ganzen Ordner per Drag & Drop in
`docker/ws-verlag` ziehen, File Station übernimmt die Unterstruktur automatisch.

Der Ordner `backups` bleibt vorerst leer — er wird beim ersten Update automatisch befüllt.

---

## 5. Konfigurationsdatei (.env) erstellen

Diese Datei enthält Passwörter und darf **niemals öffentlich geteilt oder committet**
werden.

1. In File Station: `docker/ws-verlag/.env.example` anklicken → **Kopieren** →
   im selben Ordner einfügen → die Kopie umbenennen in **`.env`** (Punkt am Anfang,
   keine Dateiendung).
2. `.env` mit Rechtsklick → **Öffnen mit** → **Text-Editor** (falls kein Text-Editor
   installiert ist: Paket-Zentrum → `Text Editor` installieren).
3. Werte wie folgt setzen (Beispiel):

   ```
   DATABASE_URL=sqlite:///./ws_verlag.db
   SECRET_KEY=<siehe Schritt 5a>
   PORT=8000

   MARIADB_PASSWORD=<siehe Schritt 5b>
   MARIADB_ROOT_PASSWORD=<siehe Schritt 5b>
   WS_VERLAG_IMAGE=ghcr.io/softlinger/ws-verlag:latest
   ```

   Die Zeile `DATABASE_URL` wird von `docker-compose.yml` beim Start automatisch auf die
   MariaDB-Verbindung überschrieben — sie kann wie oben stehen bleiben.

   **5a. `SECRET_KEY` erzeugen:** Ein zufälliger, langer Text, z. B. mit einem
   Passwort-Generator 40 zufällige Zeichen (Buchstaben, Zahlen) erzeugen und einfügen.
   Niemals den Beispielwert `change-me-in-production-please` verwenden — damit werden
   Session-Cookies signiert; ein schwacher Wert gefährdet die Anmeldesicherheit.

   **5b. `MARIADB_PASSWORD` / `MARIADB_ROOT_PASSWORD` setzen:** Zwei unterschiedliche,
   starke Passwörter (mindestens 16 Zeichen, Groß-/Kleinbuchstaben, Zahlen, Sonderzeichen)
   vergeben und **sicher notieren** (z. B. im Passwort-Manager der Firma). Ohne diese
   Passwörter ist im Fehlerfall kein Zugriff auf die Datenbank möglich.

4. Datei speichern.

> **Hinweis `WS_VERLAG_IMAGE`:** Dieser Wert bestimmt, welches fertige Docker-Image
> heruntergeladen wird. `:latest` lädt die jeweils neueste veröffentlichte Version. Für
> eine bestimmte, geprüfte Version stattdessen z. B. `ghcr.io/softlinger/ws-verlag:0.2.0`
> eintragen.

---

## 6. Projekt in Container Manager starten

1. **Container Manager** öffnen → linkes Menü → **Projekt**.
2. Auf **Erstellen** klicken.
3. **Projektname:** `ws-verlag`
4. **Pfad:** den Ordner `docker/ws-verlag` auswählen (den Ordner mit `docker-compose.yml`).
5. Bei *Quelle* die Option **„Vorhandene docker-compose.yml verwenden"** wählen — Container
   Manager erkennt die Datei im gewählten Pfad automatisch.
6. **Weiter** klicken. Container Manager zeigt eine Zusammenfassung der drei Dienste
   (`app`, `mariadb`, `updater`) — kontrollieren, dann **Fertig/Erstellen** klicken.
7. Der Download des App-Images (aus dem Internet) sowie der Build des Updater-Images
   starten automatisch. Das kann je nach Internetverbindung einige Minuten dauern —
   Fortschritt ist im Projekt-Fenster sichtbar.
8. Nach Abschluss sollten alle drei Container den Status **„Wird ausgeführt"** (grün)
   zeigen. Zu sehen unter **Container Manager → Container**.

**Falls der Download mit „unauthorized" oder „denied" fehlschlägt:** Das Image ist
(noch) nicht öffentlich freigegeben. In diesem Fall den Software-Anbieter kontaktieren
oder — falls Zugangsdaten vorliegen — vorher per SSH `docker login ghcr.io` mit einem
bereitgestellten Zugangstoken ausführen (siehe [Fehlerbehebung](#12-fehlerbehebung)).

---

## 7. Admin-Benutzer anlegen (einmalig)

Nach dem ersten Start sind zwar die Datenbanktabellen angelegt, aber es existiert noch
**kein Benutzerkonto**. Dieses wird einmalig über die eingebaute Kommandozeile des
App-Containers erzeugt:

1. **Container Manager → Container** → auf den Container **`ws-verlag-app`** klicken.
2. Oben im Detailfenster den Reiter **Terminal** wählen (Symbol `>_`).
3. Falls kein aktives Terminal-Fenster angezeigt wird: **Erstellen** → *bash* (oder *sh*,
   falls *bash* nicht verfügbar ist) auswählen.
4. Im Terminalfenster eintippen und mit Enter bestätigen:

   ```
   python scripts/seed.py
   ```

5. Die Ausgabe zeigt einen Benutzernamen und ein **generiertes Passwort**, z. B.:

   ```
   ============================================================
   Admin-Benutzer angelegt: admin / Xy7-kP2mNq8sT
   WICHTIG: Passwort nach dem ersten Login aendern!
   ============================================================
   ```

   **Dieses Passwort jetzt notieren** — es wird nirgendwo sonst angezeigt oder
   gespeichert. Nach dem ersten Login in der Anwendung sofort ändern.

6. Das Skript legt außerdem Beispiel-Stammdaten an (Musterfirma, Beispielkunden,
   Artikel, ein Beispiel-Auftrag). Diese unter **Firmenstammdaten** bzw. **Kunden/Artikel**
   nach dem ersten Login durch die echten Daten des Verlags ersetzen bzw. löschen.

---

## 8. Zugriff im Netzwerk testen

1. Die interne IP-Adresse der NAS ermitteln: DSM → *Systemsteuerung* → *Netzwerk* →
   Reiter *Netzwerkschnittstelle*, oder auf dem Router-Login nachsehen.
2. Im Browser eines Rechners im selben Netzwerk aufrufen:

   ```
   http://<NAS-IP>:8000
   ```

   Beispiel: `http://192.168.1.50:8000`

3. Es sollte die Login-Seite der WS-Verlag Verwaltung erscheinen. Mit `admin` und dem in
   Schritt 7 notierten Passwort anmelden, danach sofort das Passwort ändern
   (Benutzermenü → Passwort ändern).

Falls die Seite nicht erreichbar ist: siehe [Fehlerbehebung](#12-fehlerbehebung).

---

## 9. Sicherer Zugriff per HTTPS (Reverse Proxy)

Port 8000 direkt im lokalen Netzwerk zu verwenden ist für einen ersten Test in Ordnung.
Für den dauerhaften Betrieb — insbesondere wenn mehrere Arbeitsplätze zugreifen — sollte
stattdessen ein **verschlüsselter Zugriff über HTTPS** eingerichtet werden, über den in
DSM eingebauten Reverse Proxy:

1. DSM → *Systemsteuerung* → *Anmeldeportal* → Reiter **Erweitert** → Button
   **Reverse-Proxy** → **Erstellen**.
2. **Beschreibung:** `WS-Verlag`
3. **Quelle:**
   - Protokoll: `HTTPS`
   - Hostname: z. B. `ws-verlag.<interner-name>` oder die NAS-Adresse
   - Port: `443` (oder frei wählbarer interner Port)
4. **Ziel:**
   - Protokoll: `HTTP`
   - Hostname: `localhost`
   - Port: `8000`
5. Speichern.
6. Für ein gültiges HTTPS-Zertifikat: DSM → *Systemsteuerung* → *Sicherheit* →
   *Zertifikat* — entweder das Standard-DSM-Zertifikat verwenden (Browser-Warnung bei
   selbstsigniertem Zertifikat ist normal im internen Netz) oder ein eigenes Zertifikat /
   Let's-Encrypt-Zertifikat hinterlegen, falls die NAS aus dem Internet über eine eigene
   Domain erreichbar sein soll.

**Wichtig:** Die Anwendung **nicht direkt ohne Reverse Proxy und ohne VPN aus dem
Internet erreichbar machen** (kein Port-Forwarding von Port 8000 auf dem Router). Wenn
externer Zugriff (z. B. Homeoffice) benötigt wird: entweder VPN zur NAS (Synology
bietet dafür das Paket *VPN Server*) oder Reverse Proxy mit gültigem Zertifikat und
zusätzlicher Absicherung (2FA am DSM-Login, aktuelle DSM-Version) — im Zweifel vorher
mit dem Software-Anbieter abstimmen.

---

## 10. Automatische Datensicherung einrichten

Der Ordner `docker/ws-verlag/backups` enthält ab dem ersten automatischen Update
Datenbank-Sicherungen (siehe [Updates](#11-updates)). Dieser Ordner sollte zusätzlich
regelmäßig **extern** gesichert werden:

1. Paket-Zentrum → **Hyper Backup** installieren (falls noch nicht vorhanden).
2. Hyper Backup öffnen → **+** → Sicherungsziel wählen (externe Festplatte, ein weiteres
   NAS, oder ein Cloud-Anbieter).
3. Als zu sichernden Ordner **`docker/ws-verlag/backups`** auswählen.
4. Zeitplan festlegen (z. B. täglich nachts).

Damit besteht eine zweite, unabhängige Kopie der Datenbank-Sicherungen — falls die NAS
selbst ausfällt oder beschädigt wird.

---

## 11. Updates

Die Anwendung prüft selbstständig (bei jeder Admin-Anmeldung sowie mindestens alle 24
Stunden) auf neue Versionen und zeigt bei Verfügbarkeit im Dashboard bzw. unter
**„Updates"** die Frage *„Soll ich das Update installieren?"* an.

Nach Bestätigung läuft der komplette Vorgang automatisch ab:

1. Sicherung der aktuellen Datenbank nach `docker/ws-verlag/backups`.
2. Herunterladen der neuen Version.
3. Austausch des laufenden Containers gegen die neue Version.
4. Prüfung, ob die neue Version fehlerfrei startet.
5. **Bei Erfolg:** neue Version bleibt aktiv, alte Version wird (umbenannt, nicht
   gelöscht) aufbewahrt.
   **Bei Fehlschlag:** automatischer Rollback auf die vorherige Version — die
   Anwendung bleibt nutzbar.

Es ist **keine manuelle Aktion** in Container Manager notwendig — außer, wenn sich
`docker-compose.yml` selbst zwischen Versionen ändert (z. B. neue Konfigurationswerte).
Ein solcher Fall wird gesondert vom Software-Anbieter angekündigt; in diesem Fall in
Container Manager beim Projekt **„Neu erstellen/Aktualisieren"** ausführen.

---

## 12. Fehlerbehebung

**Seite unter `http://<NAS-IP>:8000` nicht erreichbar**
- Container Manager → Container → Status von `ws-verlag-app` und `ws-verlag-db` prüfen
  (müssen grün/„Wird ausgeführt" sein).
- Auf den Container `ws-verlag-app` klicken → Reiter **Protokoll** → nach Fehlermeldungen
  suchen (häufigste Ursache: falsches `MARIADB_PASSWORD` in `.env`, oder `mariadb` noch
  nicht bereit — App startet automatisch neu, kurz abwarten).
- Firewall der NAS prüfen: *Systemsteuerung* → *Sicherheit* → *Firewall* — Port 8000 für
  das lokale Netzwerk freigegeben?

**Container `ws-verlag-updater` lässt sich nicht starten**
- Prüfen, ob der Ordner `docker/ws-verlag/updater` alle drei Dateien enthält
  (`Dockerfile`, `requirements.txt`, `updater.py`).

**Image-Download schlägt mit „unauthorized" fehl**
- Das Docker-Image ist privat. Zugangsdaten (GitHub-Benutzername + Token) beim
  Software-Anbieter anfordern, dann per SSH auf der NAS einmalig anmelden:
  *Systemsteuerung → Terminal & SNMP → SSH-Dienst aktivieren*, dann von einem PC aus
  per SSH verbinden und ausführen: `docker login ghcr.io -u <benutzername>` (Token als
  Passwort eingeben). Danach in Container Manager das Projekt neu starten. SSH danach
  wieder deaktivieren, falls nicht dauerhaft benötigt.

**Admin-Passwort vergessen / verloren**
- Neuen Admin-Benutzer nicht selbst in der Datenbank anlegen — stattdessen den
  Software-Anbieter kontaktieren, oder falls ein zweiter Admin-Account existiert, über
  diesen ein neues Passwort setzen (Benutzerverwaltung).

**Bei jedem anderen, hier nicht aufgeführten Problem:** Protokoll (*Container Manager →
Container → ws-verlag-app → Protokoll*) sichern/kopieren und dem Software-Anbieter mit
genauer Fehlerbeschreibung übermitteln, statt selbstständig an der Konfiguration zu
experimentieren.

---

## 13. Sicherheitshinweise

- **`.env` niemals weitergeben** — sie enthält `SECRET_KEY` und Datenbank-Passwörter.
- **`ws-verlag-updater` niemals über Port-Freigabe/Reverse Proxy von außen erreichbar
  machen** — dieser Container hat Zugriff auf den Docker-Socket der NAS und damit
  faktisch Root-Rechte auf dem gesamten Gerät. Er ist bewusst so konzipiert, dass er
  ausschließlich intern mit `ws-verlag-app` kommuniziert.
- **DSM-Zugang absichern:** starkes Administrator-Passwort, Zwei-Faktor-Authentifizierung
  aktivieren (*Systemsteuerung → Benutzer & Gruppe → Erweitert → 2-Faktor-
  Authentifizierung*), DSM-Updates zeitnah einspielen.
- **Kein direktes Port-Forwarding** von Port 8000 (oder 5000/5001 für DSM selbst) vom
  Router ins Internet ohne VPN — siehe Schritt 9.
- Nach dem ersten Login **Admin-Passwort ändern** und die in Schritt 7 automatisch
  angelegten Beispiel-Stammdaten (Musterfirma, Beispielkunden) durch die echten Daten
  ersetzen bzw. entfernen.
