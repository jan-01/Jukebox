# Local Development Setup

## Voraussetzungen

- Docker + Docker Compose
- Python 3.12
- Node.js >= 20 (für Tailwind CSS Build)

---

## Einmalig: Setup

```bash
cp .env.example .env   # Konfigurationsdatei anlegen (Werte passen für lokale Entwicklung)
make install           # Virtualenv erstellen + Python- und npm-Abhängigkeiten installieren
make css-build         # Tailwind CSS kompilieren → frontend/static/output.css
```

---

## Täglich: Starten

```bash
make dev   # startet Datenbank (Docker) + CSS-Watcher + Backend in einem Befehl
```

`CTRL+C` beendet Flask **und** den CSS-Watcher automatisch.

Flask läuft auf **http://localhost:5000**.

---

## App testen

| URL | Beschreibung |
|---|---|
| http://localhost:5000/login | Login-Seite |
| http://localhost:5000/signup | Registrierung |
| http://localhost:5000/ | Hauptseite (erfordert Login) |


---

## Stoppen

```bash
make stop          # Datenbank stoppen (Daten bleiben erhalten)
make stop && docker-compose down -v  # inkl. Datenlöschung
```

Backend: `CTRL+C` in der Konsole.

---

## Wie das Schema entsteht

`init_db()` in `app.py` läuft automatisch beim App-Start und erstellt die Tabellen (`users`, `reviews`) falls sie noch nicht existieren. Kein manueller Migrationsschritt nötig.

```bash
# Schema direkt prüfen:
docker exec jukebox_db psql -U jukebox -d jukebox -c "\dt"
```

---

## Umgebungen im Überblick

| Variable | Dev (lokal) | Prod (Docker/K8s) |
|---|---|---|
| `FLASK_ENV` | `development` (aus `.env`) | `production` |
| `SESSION_COOKIE_SECURE` | `False` (automatisch) | `True` (automatisch) |
| `DB_HOST` | `localhost` (aus `.env`) | `db` (Docker) / k8s-Secret |
