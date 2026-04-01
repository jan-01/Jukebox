# Jukebox

Jukebox ist eine webbasierte Musik-Review-Plattform — ähnlich wie Letterboxd, aber für Musik. Nutzer können sich registrieren, einloggen und Rezensionen zu Songs und Alben verfassen, bearbeiten und löschen. Jede Rezension enthält Titel, Freitext und eine Sternbewertung.

Das Projekt entstand im Rahmen eines DHBW-Universitätsprojekts und demonstriert eine vollständige Web-Applikation mit Flask-Backend, PostgreSQL-Datenbank und Kubernetes-Deployment.

---
## Setup Guide
**Vorbedingungen:**
- Docker installiert und Nutzer ist in Docker-group
- Kubectl installiert
- Minikube installiert
- Cosign installiert
- Openssl intalliert

**Cluster deployen**
1. Repository klonen
2. Um den Cluster hochzufahren innerhalb von repository folgenden Command ausführen:
   ```bash
   make up
   ```
3. Den Anweisungen in der Ausgabe folgen.
4. Um den Cluster wieder herunterzufahren:
   ```bash
   make down
   ```
---

## Security Requirements

Die Anwendung implementiert fünf Sicherheitsanforderungen, die gängige Web-Schwachstellen adressieren.

### SR-01 · Session Timeout

**Was:** Sessions laufen nach 30 Minuten Inaktivität ab. Zusätzlich gilt ein absolutes Limit von 8 Stunden pro Session.

**Umsetzung:** Ein `before_request`-Hook in `backend/app.py` prüft bei jedem Aufruf den Zeitstempel `last_active` in der Session. Liegt die letzte Aktivität länger als 1800 Sekunden zurück, wird die Session gecleart und ein `401`-Fehler zurückgegeben. Das absolute Limit wird über `PERMANENT_SESSION_LIFETIME=timedelta(hours=8)` in der Flask-Konfiguration gesetzt.

**Nutzen:** Verhindert Session-Hijacking durch unbeaufsichtigte Browser-Sessions und begrenzt das Zeitfenster für gestohlene Session-Cookies.

---

### SR-02 · Sichere Session-Cookie-Flags

**Was:** Der Session-Cookie wird mit den Flags `Secure`, `HttpOnly` und `SameSite=Lax` ausgeliefert.

**Umsetzung:** In der Flask-App-Konfiguration (`backend/app.py`, `app.config.update(...)`) sind alle drei Attribute fest gesetzt. `SESSION_COOKIE_SECURE=True` ist nicht mehr umgebungsabhängig, sondern immer aktiv.

**Nutzen:** `Secure` verhindert die Übertragung des Cookies über unverschlüsselte HTTP-Verbindungen. `HttpOnly` blockiert den Zugriff per JavaScript und schützt so vor XSS-basierten Cookie-Diebstählen. `SameSite=Lax` reduziert CSRF-Risiken bei Cross-Site-Requests.

---

### SR-03 · CORS Origin Restriction

**Was:** Die API akzeptiert Cross-Origin-Anfragen nur von explizit erlaubten Origins, nicht mehr von beliebigen Domains (`*`).

**Umsetzung:** Die erlaubten Origins werden über die Umgebungsvariable `ALLOWED_ORIGINS` (kommaseparierte Liste) konfiguriert. Fallback ist `http://localhost:5000`. Die CORS-Konfiguration in `backend/app.py` setzt zusätzlich `supports_credentials=True` und schränkt erlaubte Methoden und Header ein.

**Nutzen:** Verhindert, dass beliebige Webseiten im Browser Cross-Origin-Requests mit Credentials an die API stellen können. `ALLOWED_ORIGINS` kann pro Umgebung (Docker Compose, Kubernetes) separat gesetzt werden.

---

### SR-04 · Passwort-Mindestanforderungen

**Was:** Bei der Registrierung werden Passwörter gegen Mindestanforderungen geprüft: mindestens 8 Zeichen, Groß- und Kleinbuchstaben, eine Ziffer und ein Sonderzeichen.

**Umsetzung:** Die Hilfsfunktion `validate_password()` in `backend/app.py` führt die Prüfungen via `re.search` durch und gibt eine sprechende Fehlermeldung zurück. Sie wird im `/api/signup`-Endpoint direkt nach dem Leer-Check aufgerufen — bevor das Passwort gehasht wird.

**Nutzen:** Schützt Nutzeraccounts vor trivialen Passwörtern, die Brute-Force- und Credential-Stuffing-Angriffe begünstigen.

---

### SR-05 · Security HTTP Response Headers

**Was:** Alle Responses der Anwendung enthalten sicherheitsrelevante HTTP-Header.

**Umsetzung:** Ein `after_request`-Hook in `backend/app.py` setzt folgende Header auf jede Response:

| Header | Wert |
|---|---|
| `X-Frame-Options` | `DENY` |
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | Kamera, Mikrofon, Geolocation deaktiviert |
| `Strict-Transport-Security` | 1 Jahr, inkl. Subdomains |
| `Content-Security-Policy` | `default-src 'self'`; Tailwind CSS CDN explizit erlaubt |

**Nutzen:** Verhindert Clickjacking (`X-Frame-Options`), MIME-Sniffing-Angriffe (`X-Content-Type-Options`) und schränkt erlaubte Ressourcenquellen per CSP ein. HSTS erzwingt HTTPS für zukünftige Verbindungen.
