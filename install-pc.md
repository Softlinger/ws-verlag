# WS-Verlag Verwaltung auf dem Server-PC installieren (Windows, Docker Desktop)

Diese Anleitung richtet sich an Personen **ohne Docker- oder Kommandozeilen-Erfahrung**.
Jeder Schritt wird einzeln erklärt. Wenn ein Punkt unklar ist, lieber vorher nachfragen als
raten — insbesondere bei Passwörtern und Netzwerk-Einstellungen.

Zielserver ist hier **kein NAS**, sondern ein leistungsfähiger Windows-PC beim Kunden, der
durchgehend (24/7) läuft. Die Docker-Architektur (App + MariaDB + Updater, automatischer
Update-Mechanismus) ist identisch zur NAS-Variante — siehe `README-DEPLOYMENT.md` für die
technischen Hintergründe. Es ändert sich nur der Docker-Host.

Geschätzte Dauer: 45–60 Minuten (etwas länger als bei einer NAS, wegen WSL2/Docker-Desktop-
Installation und Autostart-Einrichtung).

---

## Inhaltsverzeichnis

1. [Voraussetzungen](#1-voraussetzungen)
2. [Docker Desktop installieren](#2-docker-desktop-installieren)
3. [Autostart & Dauerbetrieb einrichten](#3-autostart--dauerbetrieb-einrichten)
4. [Ordner auf dem PC anlegen](#4-ordner-auf-dem-pc-anlegen)
5. [Projektdateien auf den PC kopieren](#5-projektdateien-auf-den-pc-kopieren)
6. [Konfigurationsdatei (.env) erstellen](#6-konfigurationsdatei-env-erstellen)
7. [Projekt starten](#7-projekt-starten)
8. [Admin-Benutzer anlegen (einmalig)](#8-admin-benutzer-anlegen-einmalig)
9. [Zugriff im Netzwerk testen](#9-zugriff-im-netzwerk-testen)
10. [Sicherer Zugriff per HTTPS (optional)](#10-sicherer-zugriff-per-https-optional)
11. [Automatische Datensicherung einrichten](#11-automatische-datensicherung-einrichten)
12. [Updates](#12-updates)
13. [Fehlerbehebung](#13-fehlerbehebung)
14. [Sicherheitshinweise](#14-sicherheitshinweise)

---

## 1. Voraussetzungen

- **Windows 10 (64-Bit, Version 21H2 oder neuer) oder Windows 11 (64-Bit)** — Home,
  Pro oder Server. Prüfen: *Einstellungen → System → Info*.
- **Virtualisierung im BIOS/UEFI aktiviert** (Intel VT-x bzw. AMD-V). Bei den meisten
  aktuellen PCs ab Werk aktiv. Prüfen: *Task-Manager → Leistung → CPU* — unten rechts muss
  „Virtualisierung: Aktiviert" stehen. Falls „Deaktiviert": im BIOS/UEFI-Setup aktivieren
  (Taste beim Start meist Entf/F2/F10, je nach Hersteller).
- Mindestens **8 GB RAM**, empfohlen 16 GB (MariaDB + App + Updater + normale
  Windows-Nutzung laufen gleichzeitig; mehr RAM verbessert MariaDB-Performance spürbar).
- Mindestens **20 GB freier Festplattenspeicher** (Docker-Images, MariaDB-Daten, Backups).
- Ein **Administrator-Benutzerkonto** auf dem PC.
- Internetzugang des PCs (zum Herunterladen von Docker Desktop und dem Anwendungs-Image).
- Der PC muss **dauerhaft eingeschaltet und mit dem Netzwerk verbunden** bleiben
  (Energiesparmodus/Ruhezustand deaktivieren — siehe [Abschnitt 3](#3-autostart--dauerbetrieb-einrichten)).
- **Empfohlen:** dem PC im Router eine **feste IP-Adresse (DHCP-Reservierung)** zuweisen,
  damit die Anschrift (`http://<PC-IP>:8000`) sich nicht ändert. In der Regel in der
  Router-Oberfläche unter *DHCP-Reservierung* anhand der MAC-Adresse des PCs einzurichten —
  die MAC-Adresse zeigt `ipconfig /all` in der PowerShell.

---

## 2. Docker Desktop installieren

1. **WSL 2 vorbereiten** (Windows-Subsystem für Linux, Voraussetzung für Docker Desktop):
   - PowerShell **als Administrator** öffnen (Rechtsklick auf Start-Symbol →
     *Windows PowerShell (Administrator)* bzw. *Terminal (Administrator)*).
   - Eingeben und mit Enter bestätigen:

     ```powershell
     wsl --install
     ```

   - Den PC danach **neu starten**, wenn dazu aufgefordert wird.
   - Falls WSL bereits vorhanden ist, meldet der Befehl das entsprechend — dann einfach
     fortfahren.

2. **Docker Desktop herunterladen:** im Browser `https://www.docker.com/products/docker-desktop/`
   öffnen und den Installer für Windows herunterladen.

3. Installer ausführen, Option **„Use WSL 2 instead of Hyper-V"** (Standardauswahl)
   bestätigen, Installation abschließen, PC bei Aufforderung neu starten.

4. Docker Desktop starten. Beim ersten Start:
   - Lizenzbedingungen akzeptieren.
   - Eine Anmeldung mit einem Docker-Konto wird angeboten, ist aber für die normale
     Nutzung **nicht zwingend erforderlich** — kann übersprungen werden
     („Continue without signing in" o. ä.). Docker Desktop ist für kleine Unternehmen
     kostenlos nutzbar; die kostenpflichtige Lizenzpflicht betrifft nur Unternehmen ab
     250 Mitarbeitern bzw. 10 Mio. USD Jahresumsatz.
   - Kurz warten, bis unten links **„Engine running"** (grüner Punkt) angezeigt wird.

---

## 3. Autostart & Dauerbetrieb einrichten

**Das ist der wichtigste Unterschied zur NAS-Installation.** Eine Synology NAS startet
Docker-Container automatisch im Hintergrund, auch ohne dass sich jemand an der
Oberfläche anmeldet. Docker Desktop unter Windows ist dagegen ein Programm, das an eine
**angemeldete Windows-Benutzersitzung** gebunden ist — nach einem Neustart des PCs
(z. B. durch ein Windows-Update) läuft die Anwendung erst wieder, wenn sich der
konfigurierte Benutzer angemeldet hat.

Damit der Server auch nach einem unbeaufsichtigten Neustart automatisch wieder
hochfährt, folgende drei Einstellungen vornehmen:

### 3a. Docker Desktop beim Anmelden automatisch starten

Docker Desktop → Zahnrad-Symbol (Settings) → **General** → Häkchen bei
**„Start Docker Desktop when you sign in"** setzen → **Apply & restart**.

### 3b. Automatische Windows-Anmeldung einrichten

Damit „sign in" auch ohne physisch anwesende Person passiert, braucht der PC eine
automatische Anmeldung. Dafür **nicht** manuell das Passwort im Klartext in der
Registry hinterlegen, sondern das offizielle Microsoft-Werkzeug **Sysinternals
Autologon** verwenden (verschlüsselt das Passwort sicher, statt es lesbar zu speichern):

1. `https://learn.microsoft.com/sysinternals/downloads/autologon` öffnen, `Autologon.exe`
   herunterladen.
2. **Empfehlung:** dafür ein eigenes, lokal eingeschränktes Windows-Benutzerkonto anlegen
   (kein Administrator-Konto), das ausschließlich zum automatischen Starten von Docker
   Desktop dient — nicht das persönliche Admin-Konto für den Autologin verwenden.
3. `Autologon.exe` als Administrator ausführen, Lizenzbedingungen bestätigen,
   Benutzername/Domäne (bei einem lokalen Konto: PC-Name) und Passwort des in Schritt 2
   angelegten Kontos eintragen, **Enable** klicken.
4. Mit diesem Konto einmal manuell anmelden und prüfen, dass Docker Desktop wie in 3a
   automatisch startet.

### 3c. Energiesparmodus/Ruhezustand deaktivieren

*Einstellungen → System → Energie* (bzw. *Netzbetrieb & Standbymodus*):

- „Bildschirm ausschalten nach" und „Gerät in den Energiesparmodus versetzen nach"
  jeweils auf **„Nie"** setzen.
- Zusätzlich in der **Systemsteuerung → Energieoptionen → Energiesparplan ändern →
  Erweiterte Energieeinstellungen**: *Ruhezustand nach* ebenfalls auf **Nie**.

### 3d. Windows-Update-Neustarts eindämmen

*Einstellungen → Windows Update → Erweiterte Optionen → Aktive Stunden* auf die üblichen
Geschäftszeiten einstellen, damit automatische Neustarts nicht während des Betriebs
erfolgen. Ein Neustart lässt sich damit nicht vollständig verhindern (wichtig für
Sicherheitsupdates) — dank 3a/3b fährt der Server danach aber automatisch wieder hoch.

> **Hinweis für IT-Administratoren:** Wer eine echte headless-taugliche Lösung ohne
> automatische Windows-Anmeldung bevorzugt, kann statt Docker Desktop die Docker Engine
> direkt in einer WSL2-Distribution mit aktiviertem `systemd` betreiben und per
> geplantem Task (*„Unabhängig von der Benutzeranmeldung ausführen"*) beim Systemstart
> wecken. Das ist robuster, erfordert aber Kommandozeilen-Erfahrung mit Linux/WSL —
> bei Bedarf beim Software-Anbieter erfragen.

---

## 4. Ordner auf dem PC anlegen

Im Windows-Explorer folgende Ordnerstruktur anlegen, z. B. unter `C:\ws-verlag`:

```
C:\ws-verlag\
  backups\
  updater\
```

Konkret: Ordner `C:\ws-verlag` anlegen, darin die zwei leeren Unterordner `backups` und
`updater`.

---

## 5. Projektdateien auf den PC kopieren

Aus dem Projekt-Repository werden **nur wenige Dateien** benötigt (der Anwendungscode
selbst kommt fertig gebaut als Docker-Image aus dem Internet — nicht als Quellcode auf
den PC).

Vom bereitgestellten Projektordner (z. B. `D:\dev\WS-Verlag-nxt`) folgende Dateien nach
`C:\ws-verlag` kopieren (Drag & Drop im Explorer):

| Datei/Ordner in der Quelle | Ziel auf dem Server-PC |
|---|---|
| `docker-compose.yml` | `C:\ws-verlag\docker-compose.yml` |
| `.env.example` | `C:\ws-verlag\.env.example` |
| gesamter Ordner `updater\` (mit `Dockerfile`, `requirements.txt`, `updater.py`) | `C:\ws-verlag\updater\` |

Der Ordner `backups` bleibt vorerst leer — er wird beim ersten Update automatisch befüllt.

---

## 6. Konfigurationsdatei (.env) erstellen

Diese Datei enthält Passwörter und darf **niemals öffentlich geteilt oder committet**
werden.

1. Im Explorer: `C:\ws-verlag\.env.example` kopieren, im selben Ordner einfügen, die
   Kopie umbenennen in **`.env`** (Punkt am Anfang, keine Dateiendung — Windows fragt
   ggf. nach, ob die Dateiendung wirklich geändert werden soll: mit Ja bestätigen).
2. `.env` mit Rechtsklick → **Öffnen mit** → **Editor** (Notepad) bearbeiten.
3. Werte wie folgt setzen (Beispiel):

   ```
   DATABASE_URL=sqlite:///./ws_verlag.db
   SECRET_KEY=<siehe Schritt 6a>
   PORT=8000

   MARIADB_PASSWORD=<siehe Schritt 6b>
   MARIADB_ROOT_PASSWORD=<siehe Schritt 6b>
   WS_VERLAG_IMAGE=ghcr.io/softlinger/ws-verlag:latest
   ```

   Die Zeile `DATABASE_URL` wird von `docker-compose.yml` beim Start automatisch auf die
   MariaDB-Verbindung überschrieben — sie kann wie oben stehen bleiben.

   **6a. `SECRET_KEY` erzeugen:** ein zufälliger, langer Text. In der PowerShell:

   ```powershell
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

   Falls Python nicht installiert ist: ersatzweise einen Passwort-Generator für 40
   zufällige Zeichen (Buchstaben, Zahlen) verwenden. Niemals den Beispielwert
   `change-me-in-production-please` übernehmen — damit werden Session-Cookies signiert;
   ein schwacher Wert gefährdet die Anmeldesicherheit.

   **6b. `MARIADB_PASSWORD` / `MARIADB_ROOT_PASSWORD` setzen:** zwei unterschiedliche,
   starke Passwörter (mindestens 16 Zeichen, Groß-/Kleinbuchstaben, Zahlen,
   Sonderzeichen) vergeben und **sicher notieren** (z. B. im Passwort-Manager der
   Firma). Ohne diese Passwörter ist im Fehlerfall kein Zugriff auf die Datenbank
   möglich.

4. Datei speichern.

> **Hinweis `WS_VERLAG_IMAGE`:** Dieser Wert bestimmt, welches fertige Docker-Image
> heruntergeladen wird. `:latest` lädt die jeweils neueste veröffentlichte Version. Für
> eine bestimmte, geprüfte Version stattdessen z. B. `ghcr.io/softlinger/ws-verlag:0.2.0`
> eintragen.

---

## 7. Projekt starten

1. PowerShell öffnen (muss **nicht** als Administrator laufen) und in den Projektordner
   wechseln:

   ```powershell
   cd C:\ws-verlag
   ```

2. Stack starten:

   ```powershell
   docker compose up -d
   ```

3. Der Download des App-Images (aus dem Internet) sowie der Build des Updater-Images
   starten automatisch. Das kann je nach Internetverbindung einige Minuten dauern.

4. Ergebnis prüfen: entweder in der PowerShell mit `docker compose ps`, oder in der
   **Docker Desktop Dashboard**-Oberfläche unter **Containers** — dort erscheint eine
   Gruppe **`ws-verlag`** mit den drei Diensten `app`, `mariadb`, `updater`. Alle drei
   sollten den Status **„Running"** (grün) zeigen.

**Falls der Download mit „unauthorized" oder „denied" fehlschlägt:** Das Image ist
(noch) nicht öffentlich freigegeben. In diesem Fall den Software-Anbieter kontaktieren
oder — falls Zugangsdaten vorliegen — vorher `docker login ghcr.io` in der PowerShell
mit einem bereitgestellten Zugangstoken ausführen (siehe [Fehlerbehebung](#13-fehlerbehebung)).

---

## 8. Admin-Benutzer anlegen (einmalig)

Nach dem ersten Start sind zwar die Datenbanktabellen angelegt, aber es existiert noch
**kein Benutzerkonto**. Dieses wird einmalig erzeugt:

In der PowerShell (im Ordner `C:\ws-verlag`):

```powershell
docker compose exec app python scripts/seed.py
```

Alternativ über die **Docker Desktop Dashboard**-Oberfläche: auf den Container
`ws-verlag-app` klicken → Reiter **Exec** → dort denselben Befehl ohne das vorangestellte
`docker compose exec app` eingeben (also nur `python scripts/seed.py`).

Die Ausgabe zeigt einen Benutzernamen und ein **generiertes Passwort**, z. B.:

```
============================================================
Admin-Benutzer angelegt: admin / Xy7-kP2mNq8sT
WICHTIG: Passwort nach dem ersten Login aendern!
============================================================
```

**Dieses Passwort jetzt notieren** — es wird nirgendwo sonst angezeigt oder gespeichert.
Nach dem ersten Login in der Anwendung sofort ändern.

Das Skript legt außerdem Beispiel-Stammdaten an (Musterfirma, Beispielkunden, Artikel,
ein Beispiel-Auftrag). Diese unter **Firmenstammdaten** bzw. **Kunden/Artikel** nach dem
ersten Login durch die echten Daten des Verlags ersetzen bzw. löschen.

---

## 9. Zugriff im Netzwerk testen

1. Die IP-Adresse des Server-PCs ermitteln: PowerShell → `ipconfig` → Wert bei
   „IPv4-Adresse" der aktiven Netzwerkverbindung (bzw. die feste IP aus der
   DHCP-Reservierung, siehe [Abschnitt 1](#1-voraussetzungen)).
2. Im Browser eines Rechners im selben Netzwerk aufrufen:

   ```
   http://<PC-IP>:8000
   ```

   Beispiel: `http://192.168.1.50:8000`

3. Es sollte die Login-Seite der WS-Verlag Verwaltung erscheinen. Mit `admin` und dem in
   Schritt 8 notierten Passwort anmelden, danach sofort das Passwort ändern
   (Benutzermenü → Passwort ändern).

Falls die Seite nicht erreichbar ist: siehe [Fehlerbehebung](#13-fehlerbehebung) — meist
ist die Ursache die **Windows-Firewall**, die eingehende Verbindungen auf Port 8000
standardmäßig blockiert:

```powershell
New-NetFirewallRule -DisplayName "WS-Verlag (Port 8000)" -Direction Inbound -Protocol TCP -LocalPort 8000 -Profile Domain,Private -Action Allow
```

(In PowerShell **als Administrator** ausführen. `-Profile Domain,Private` beschränkt die
Freigabe bewusst auf das interne/Firmennetzwerk, nicht auf „Öffentlich".)

---

## 10. Sicherer Zugriff per HTTPS (optional)

Port 8000 direkt im internen Netzwerk zu verwenden ist für den Betrieb in einem
vertrauenswürdigen Büro-/Firmennetzwerk ausreichend. Anders als eine Synology NAS bringt
Windows **keinen eingebauten Reverse Proxy mit grafischer Oberfläche** mit. Für
verschlüsselten HTTPS-Zugriff (z. B. bei externem Zugriff über VPN) gibt es zwei Wege:

- **Einfachste Option:** beim internen Netzwerkzugriff auf HTTPS verzichten (Port 8000,
  wie oben) und externen Zugriff ausschließlich über ein VPN zum Firmennetzwerk
  absichern — kein direktes Port-Forwarding von Port 8000 ins Internet, siehe
  [Sicherheitshinweise](#14-sicherheitshinweise).
- **Für internes HTTPS:** ein zusätzlicher Reverse-Proxy-Container (z. B. Caddy oder
  nginx) vor die Anwendung schalten. Das erfordert eine Anpassung von
  `docker-compose.yml` und ist nicht Teil dieser Standard-Installation — bei Bedarf
  bitte beim Software-Anbieter anfragen, das wird gezielt für die konkrete
  Netzwerkumgebung eingerichtet.

---

## 11. Automatische Datensicherung einrichten

Der Ordner `C:\ws-verlag\backups` enthält ab dem ersten automatischen Update
Datenbank-Sicherungen (siehe [Updates](#12-updates)). Dieser Ordner sollte zusätzlich
regelmäßig **extern** gesichert werden (externe Festplatte, Netzlaufwerk, o. ä.), z. B.
per Windows-Aufgabenplanung + Robocopy:

1. **Aufgabenplanung** öffnen (Start-Menü → „Aufgabenplanung" eingeben).
2. Rechts **Einfache Aufgabe erstellen…** wählen, Name z. B. `WS-Verlag Backup-Sicherung`.
3. Trigger: **Täglich**, Uhrzeit außerhalb der Geschäftszeiten (z. B. 3:00 Uhr).
4. Aktion: **Programm starten** → Programm/Skript: `robocopy`, Argumente z. B.:

   ```
   C:\ws-verlag\backups E:\Backups\ws-verlag /MIR /R:2 /W:5
   ```

   (`E:\Backups\ws-verlag` durch das tatsächliche externe Ziel ersetzen — externe
   Festplatte, Netzlaufwerk oder NAS-Freigabe.)
5. Fertigstellen. Optional: die Aufgabe danach in den Eigenschaften auf **„Unabhängig von
   der Benutzeranmeldung ausführen"** stellen, damit sie auch läuft, wenn kein Benutzer
   angemeldet ist.

Damit besteht eine zweite, unabhängige Kopie der Datenbank-Sicherungen — falls der
Server-PC selbst ausfällt oder beschädigt wird.

---

## 12. Updates

Die Anwendung prüft selbstständig (bei jeder Admin-Anmeldung sowie mindestens alle 24
Stunden) auf neue Versionen und zeigt bei Verfügbarkeit im Dashboard bzw. unter
**„Updates"** die Frage *„Soll ich das Update installieren?"* an.

Nach Bestätigung läuft der komplette Vorgang automatisch ab:

1. Sicherung der aktuellen Datenbank nach `C:\ws-verlag\backups`.
2. Herunterladen der neuen Version.
3. Austausch des laufenden Containers gegen die neue Version.
4. Prüfung, ob die neue Version fehlerfrei startet.
5. **Bei Erfolg:** neue Version bleibt aktiv, alte Version wird (umbenannt, nicht
   gelöscht) aufbewahrt.
   **Bei Fehlschlag:** automatischer Rollback auf die vorherige Version — die
   Anwendung bleibt nutzbar.

Es ist **keine manuelle Aktion** in Docker Desktop notwendig — außer, wenn sich
`docker-compose.yml` selbst zwischen Versionen ändert (z. B. neue Konfigurationswerte).
Ein solcher Fall wird gesondert vom Software-Anbieter angekündigt; in diesem Fall in der
PowerShell im Ordner `C:\ws-verlag` erneut `docker compose up -d` ausführen.

---

## 13. Fehlerbehebung

**Seite unter `http://<PC-IP>:8000` nicht erreichbar**
- Docker Desktop Dashboard → Containers → Status von `ws-verlag-app` und `ws-verlag-db`
  prüfen (müssen „Running"/grün sein).
- Auf den Container `ws-verlag-app` klicken → Reiter **Logs** → nach Fehlermeldungen
  suchen (häufigste Ursache: falsches `MARIADB_PASSWORD` in `.env`, oder `mariadb` noch
  nicht bereit — App startet automatisch neu, kurz abwarten).
- Windows-Firewall prüfen (siehe [Abschnitt 9](#9-zugriff-im-netzwerk-testen)) — Port
  8000 muss für „Domain"/„Privat" freigegeben sein.
- Prüfen, ob der PC tatsächlich läuft und Docker Desktop aktiv ist (siehe
  [Abschnitt 3](#3-autostart--dauerbetrieb-einrichten) — vor allem nach einem Neustart
  durch Windows-Update).

**Container `ws-verlag-updater` lässt sich nicht starten**
- Prüfen, ob der Ordner `C:\ws-verlag\updater` alle drei Dateien enthält (`Dockerfile`,
  `requirements.txt`, `updater.py`).

**Image-Download schlägt mit „unauthorized" fehl**
- Das Docker-Image ist privat. Zugangsdaten (GitHub-Benutzername + Token) beim
  Software-Anbieter anfordern, dann in der PowerShell ausführen:

  ```powershell
  docker login ghcr.io -u <benutzername>
  ```

  (Token als Passwort eingeben.) Danach `docker compose up -d` erneut ausführen.

**Docker Desktop startet nach einem Neustart nicht automatisch**
- Autostart-Einrichtung aus [Abschnitt 3](#3-autostart--dauerbetrieb-einrichten)
  überprüfen: Windows-Autologin (Sysinternals Autologon) und Docker-Desktop-Autostart-
  Einstellung.

**Admin-Passwort vergessen / verloren**
- Neuen Admin-Benutzer nicht selbst in der Datenbank anlegen — stattdessen den
  Software-Anbieter kontaktieren, oder falls ein zweiter Admin-Account existiert, über
  diesen ein neues Passwort setzen (Benutzerverwaltung).

**Bei jedem anderen, hier nicht aufgeführten Problem:** Logs (*Docker Desktop →
Containers → ws-verlag-app → Logs*) sichern/kopieren und dem Software-Anbieter mit
genauer Fehlerbeschreibung übermitteln, statt selbstständig an der Konfiguration zu
experimentieren.

---

## 14. Sicherheitshinweise

- **`.env` niemals weitergeben** — sie enthält `SECRET_KEY` und Datenbank-Passwörter.
- **`ws-verlag-updater` niemals über Port-Freigabe/Reverse Proxy von außen erreichbar
  machen** — dieser Container hat Zugriff auf den Docker-Socket des PCs und damit
  faktisch Root-Rechte auf dem gesamten Gerät. Er ist bewusst so konzipiert, dass er
  ausschließlich intern mit `ws-verlag-app` kommuniziert.
- **Autologin-Konto absichern** (siehe [Abschnitt 3b](#3-autostart--dauerbetrieb-einrichten)):
  eigenes, lokal eingeschränktes Konto ohne Administratorrechte verwenden, physischen
  Zugriff auf den Server-PC beschränken (verschlossener Raum/Serverschrank), da eine
  automatische Anmeldung grundsätzlich bedeutet, dass jeder mit physischem
  Zugriff auf den eingeschalteten PC ohne Passworteingabe an den Desktop gelangt.
- **Kein direktes Port-Forwarding** von Port 8000 vom Router ins Internet ohne VPN —
  siehe [Abschnitt 10](#10-sicherer-zugriff-per-https-optional).
- Windows-Updates zeitnah einspielen, Windows-Anmeldung mit starkem Passwort schützen.
- Nach dem ersten Login **Admin-Passwort ändern** und die in Schritt 8 automatisch
  angelegten Beispiel-Stammdaten (Musterfirma, Beispielkunden) durch die echten Daten
  ersetzen bzw. entfernen.
