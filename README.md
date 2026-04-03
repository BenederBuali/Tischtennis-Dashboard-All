# 🏓 OÖTTV Tischtennis Dashboard

Ein modernes Web-Dashboard für alle Ligen und Klassen des **Oberösterreichischen Tischtennis Verbands (OÖTTV)**. Daten werden direkt von [XTTV](https://oettv.xttv.at) gescrapt und übersichtlich dargestellt.

![Python](https://img.shields.io/badge/Python-3.10+-blue?style=flat-square&logo=python)
![Flask](https://img.shields.io/badge/Flask-3.0+-lightgrey?style=flat-square&logo=flask)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)

---

## Features

- **Alle 64 OÖTTV-Ligen** auf einen Blick – von der OÖ-Liga bis zur Bezirksklasse
- **Liga-Browser** in der Seitenleiste, nach Klasse gruppiert und durchsuchbar
- **Pro Liga:**
  - Ligatabelle mit Rang, Siege, Unentschieden, Niederlagen, Punkte
  - Einzelrangliste mit Winrate-Balken und RatingsCentral-Rating (RC)
  - Spielplan – vergangene und kommende Spiele
  - Charts: Punkte der Teams, Siege/Niederlagen der Spieler
- **On-Demand Laden**: Daten werden erst beim Anklicken einer Liga geladen
- **Caching**: Geladene Ligen werden 4 Stunden gecacht, kein unnötiger Traffic
- **Dark Mode UI** – modernes, responsives Design

---

## Lokale Installation

```bash
# 1. Repository klonen
git clone https://github.com/BenederBuali/Tischtennis-Dashboard-All.git
cd Tischtennis-Dashboard-All

# 2. Abhängigkeiten installieren
pip install -r requirements.txt

# 3. Starten
python app.py
```

Danach ist das Dashboard unter **http://localhost:10000** erreichbar.

---

## Deployment (Render / Railway)

Das Projekt ist direkt für [Render](https://render.com) vorkonfiguriert:

1. Repository auf GitHub pushen
2. Neuen **Web Service** auf Render erstellen
3. Repository verbinden – `render.yaml` wird automatisch erkannt
4. Deploy starten

Für Railway oder andere Plattformen: Das `Procfile` wird unterstützt.

```
web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
```

---

## Projektstruktur

```
Tischtennis-Dashboard-All/
├── app.py               # Flask Backend – Scraper, Cache, API
├── templates/
│   └── index.html       # Single-Page Frontend
├── requirements.txt     # Python-Abhängigkeiten
├── Procfile             # Gunicorn Start-Befehl
└── render.yaml          # Render Deployment-Konfiguration
```

---

## API-Endpunkte

| Endpunkt | Beschreibung |
|---|---|
| `GET /` | Hauptseite (Liga-Browser) |
| `GET /api/ligen` | Liste aller verfügbaren Ligen als JSON |
| `GET /api/liga/<id>` | Tabelle, Spieler & Spiele einer Liga |
| `GET /api/liga/<id>?refresh=1` | Daten einer Liga neu laden (Cache umgehen) |
| `GET /api/status` | Cache-Status und Anzahl geladener Ligen |

---

## Datenquelle

Alle Daten stammen von **[oettv.xttv.at](https://oettv.xttv.at)** – dem offiziellen Ergebnisdienst des OÖTTV. Die Daten werden beim ersten Aufruf einer Liga gescrapt und danach für 4 Stunden gecacht.

---

## Verwandtes Projekt

[Tischtennis-Dashboard](https://github.com/BenederBuali/Tischtennis-Dashboard) – Dashboard speziell für ASKö Schwertberg (SWER) mit RC-Verlaufsdiagramm und automatischer Saison-Erkennung.