"""
TT Dashboard All – Flask Web-App
================================
Scrapt XTTV und zeigt ALLE verfügbaren Ligen/Klassen.
Jede Liga kann einzeln aufgerufen werden.
"""

import requests
from bs4 import BeautifulSoup
import json
import os
import re
import threading
import time
from datetime import datetime
from flask import Flask, render_template, jsonify, request

app = Flask(__name__)

# ─── Konfiguration ──────────────────────────────────────────────────────────────

BASE_URL  = "https://oettv.xttv.at/ed/index.php"
ENCODING  = "iso-8859-1"
UPDATE_INTERVALL_STUNDEN = 4

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/122.0.0.0 Safari/537.36"
}

# OÖTTV Verband-ID (für die Haupt-Navigationsseite)
OETTV_OID = 191   # OÖTTV – Oberösterreichischer Tischtennis Verband

# ─── Globaler Cache ──────────────────────────────────────────────────────────────

_ligen_liste = []          # [{"id": 8297, "name": "...", "gruppe": "..."}]
_liga_cache  = {}          # {liga_id: {"tabelle": [], ...}}
_cache_lock  = threading.Lock()
_ligen_geladen = False

# ─── Scraping-Hilfsfunktionen ────────────────────────────────────────────────────

def fetch(url: str, params: dict = None) -> BeautifulSoup:
    r = requests.get(url, params=params, headers=HEADERS, timeout=8)
    r.encoding = ENCODING
    return BeautifulSoup(r.text, "html.parser")

def safe_text(el) -> str:
    if el is None:
        return ""
    return el.get_text(separator=" ", strip=True)

# ─── Liga-Entdeckung ─────────────────────────────────────────────────────────────

def pruefe_liga(lid: int) -> dict | None:
    """
    Prüft ob eine Liga-ID gültig ist und gibt Infos zurück.
    Gibt None zurück wenn keine Teams gefunden wurden.
    """
    try:
        soup = fetch(BASE_URL, {"lid": lid})
        teams = []
        for row in soup.find_all("tr"):
            zellen = row.find_all("td")
            if len(zellen) < 15:
                continue
            if not zellen[1].get("data-msrangsort"):
                continue
            rang_text = safe_text(zellen[1]).strip().rstrip(".")
            if not rang_text.isdigit():
                continue
            name = safe_text(zellen[2]).strip()
            if name:
                teams.append(name)
        if not teams:
            return None
        # Liga-Namen aus Titel
        titel = soup.find("title")
        liga_name = safe_text(titel).strip() if titel else f"Liga {lid}"
        # Reinigen: "OÖTTV" und Trennzeichen entfernen
        liga_name = re.sub(r"^\s*OÖTTV\s*[-–|]\s*", "", liga_name).strip()
        liga_name = re.sub(r"\s*[-–|]\s*XTTV.*$", "", liga_name).strip()
        if not liga_name or liga_name.lower().startswith("xttv"):
            liga_name = f"Liga {lid}"
        # Gruppe aus Namen ableiten
        gruppe = extrahiere_gruppe(liga_name)
        return {"id": lid, "name": liga_name, "gruppe": gruppe, "teams": len(teams)}
    except Exception:
        return None


def extrahiere_gruppe(name: str) -> str:
    """Leitet die Gruppe/Klasse aus dem Liga-Namen ab."""
    n = name.lower()
    if "oö-liga" in n or "oo-liga" in n:
        return "OÖ-Liga"
    if "landesliga" in n:
        return "Landesliga"
    if "landesklasse" in n:
        return "Landesklasse"
    if "regionalliga" in n:
        return "Regionalliga"
    if "regionsklasse" in n:
        return "Regionsklasse"
    if "bezirksliga" in n:
        return "Bezirksliga"
    if "bezirksklasse" in n:
        return "Bezirksklasse"
    if "1. klasse" in n:
        return "1. Klasse"
    if "2. klasse" in n:
        return "2. Klasse"
    if "cup" in n or "uniqa" in n:
        return "Cup / Sonstiges"
    return "Sonstiges"


def entdecke_ligen() -> list:
    """
    Lädt alle verfügbaren Ligen direkt von der OÖTTV-Navigationsseite.
    Alle Ligen werden in einem einzigen Request gefunden.
    """
    print("Lade OÖTTV-Ligen von Hauptseite...")
    ligen = []
    try:
        soup = fetch(BASE_URL, {"oid": OETTV_OID})
        for a in soup.find_all("a", href=True):
            m = re.search(r"lid=(\d+)", a["href"])
            if not m:
                continue
            lid = int(m.group(1))
            name_roh = safe_text(a).strip()
            if not name_roh:
                continue
            # Führende Klassennummer extrahieren und separat speichern: "631 Bezirksklasse Steyr..." → nr=631
            nr_match = re.match(r"^(\d{3})\s+", name_roh)
            nummer = nr_match.group(1) if nr_match else ""
            name = re.sub(r"^\d{3}\s+", "", name_roh).strip()
            # "RK " → "Regionsklasse " (muss VOR dem Sponsor-Strip passieren)
            name = re.sub(r"^RK\s+", "Regionsklasse ", name)
            # Sponsoren-Präfixe entfernen: "DONIC/GO SPORTS OÖ-Liga" → "OÖ-Liga"
            name = re.sub(r"^(?:[A-Z]{2,}[/\s&-]*)+(?=[A-ZÖÜÄa-züöä])", "", name).strip()
            # Sponsoren-Suffixe kürzen: "powered by Go Sports"
            name = re.sub(r"\s+(powered by|presented by|sponsored by).*$", "", name, flags=re.IGNORECASE).strip()
            if not name:
                name = name_roh

            gruppe = extrahiere_gruppe(name)
            if not any(l["id"] == lid for l in ligen):
                ligen.append({"id": lid, "name": name, "nummer": nummer, "gruppe": gruppe, "teams": 0})

        print(f"  {len(ligen)} Ligen gefunden.")
    except Exception as e:
        print(f"  Hauptseiten-Fehler: {e}")

    # Fallback: aktuelle Saison auch mit sjid=25 versuchen
    if not ligen:
        print("  Fallback: Lade mit sjid=25...")
        try:
            soup = fetch(BASE_URL, {"oid": OETTV_OID, "sjid": 25})
            for a in soup.find_all("a", href=True):
                m = re.search(r"lid=(\d+)", a["href"])
                if not m:
                    continue
                lid = int(m.group(1))
                name_roh2 = safe_text(a).strip()
                nr_match2 = re.match(r"^(\d{3})\s+", name_roh2)
                nummer2 = nr_match2.group(1) if nr_match2 else ""
                name = re.sub(r"^\d{3}\s+", "", name_roh2).strip()
                name = re.sub(r"^RK\s+", "Regionsklasse ", name)
                name = re.sub(r"\s+(powered by|presented by|sponsored by).*$", "", name, flags=re.IGNORECASE).strip()
                gruppe = extrahiere_gruppe(name)
                if not any(l["id"] == lid for l in ligen):
                    ligen.append({"id": lid, "name": name, "nummer": nummer2, "gruppe": gruppe, "teams": 0})
            print(f"  Fallback: {len(ligen)} Ligen gefunden.")
        except Exception as e2:
            print(f"  Fallback-Fehler: {e2}")

    ligen.sort(key=lambda x: (x["gruppe"], x["name"]))
    return ligen


# ─── Tabelle + Rangliste in einem einzigen Fetch ────────────────────────────────

def lade_tabelle_und_rangliste(liga_id: int) -> tuple:
    """
    Parsed Ligatabelle UND Einzelrangliste aus einem einzigen HTTP-Request.
    Das spart einen kompletten Roundtrip pro Liga-Aufruf.
    """
    soup = fetch(BASE_URL, {"lid": liga_id})
    tabelle   = []
    rangliste = []
    rang_fake = 9000

    def to_int(zelle):
        t = safe_text(zelle).strip()
        return int(t) if t.isdigit() else 0

    for row in soup.find_all("tr"):
        zellen = row.find_all("td")

        # ── Tabellenzeile erkennen (≥15 Zellen, td[1] hat data-msrangsort) ──
        if len(zellen) >= 15 and zellen[1].get("data-msrangsort"):
            rang_text = safe_text(zellen[1]).strip().rstrip(".")
            if rang_text.isdigit():
                kürzel = safe_text(zellen[3]).strip()
                if kürzel:
                    tabelle.append({
                        "rang":   int(rang_text),
                        "name":   safe_text(zellen[2]).strip(),
                        "kürzel": kürzel,
                        "sp":     to_int(zellen[4]),
                        "s":      to_int(zellen[5]),
                        "u":      to_int(zellen[6]),
                        "n":      to_int(zellen[7]),
                        "p":      to_int(zellen[14]),
                    })
            continue

        # ── Ranglisten-Zeile erkennen (hat Spieler-Link) ──
        spieler_link = row.find("a", href=lambda h: h and "spid=" in h and "uebersicht=" in h)
        if not spieler_link:
            continue
        name = safe_text(spieler_link)
        if not name or len(name) < 3:
            continue

        texts = [safe_text(z) for z in zellen]
        if not texts:
            continue

        rang_text = texts[0].strip().rstrip(".")
        nicht_gewertet = False
        if rang_text.isdigit():
            rang = int(rang_text)
        else:
            nicht_gewertet = True
            rang = rang_fake
            rang_fake += 1

        verein_link = row.find("a", href=lambda h: h and "tid=" in (h or "") and "do=spiele" not in (h or ""))
        verein = safe_text(verein_link) if verein_link else ""

        einsätze = 0
        if len(texts) > 4 and texts[4].isdigit():
            einsätze = int(texts[4])

        s, n = 0, 0
        for i, t in enumerate(texts):
            if t.strip() == ":" and 0 < i < len(texts) - 1:
                try:
                    s = int(texts[i - 1])
                    n = int(texts[i + 1])
                    break
                except ValueError:
                    pass

        rc = ""
        rc_link = row.find("a", href=lambda h: h and "ratingscentral" in (h or ""))
        if rc_link:
            rc_text = rc_link.get_text(strip=True)
            if rc_text.isdigit() and len(rc_text) in (3, 4):
                rc = rc_text
        if not rc:
            for t in texts:
                t2 = t.strip()
                if t2.isdigit() and 3 <= len(t2) <= 4 and int(t2) > 500:
                    rc = t2
                    break

        rangliste.append({
            "rang":           rang,
            "name":           name,
            "verein":         verein,
            "einsaetze":      einsätze,
            "siege":          s,
            "niederl":        n,
            "rc":             rc,
            "nicht_gewertet": nicht_gewertet,
            "win_pct":        round(s / (s + n) * 100, 1) if (s + n) > 0 else 0.0,
        })

    return sorted(tabelle, key=lambda x: x["rang"]), rangliste


# ─── Spiele scrapen ──────────────────────────────────────────────────────────────

def _parse_spiele_seite(soup, alle: list):
    for item in soup.select("li, tr"):
        text = safe_text(item)
        m = re.search(r"(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})", text)
        if not m:
            continue
        try:
            dt = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%d.%m.%Y %H:%M")
        except ValueError:
            continue
        mm = re.search(r"([A-Z]{2,6}\d?)\s*-\s*([A-Z]{2,6}\d?)", text)
        if not mm:
            continue
        heim, gast = mm.group(1), mm.group(2)
        rest = text[mm.end():]
        erg = re.search(r"\b(\d{1,2}):(\d{1,2})\b", rest)
        ergebnis = f"{erg.group(1)}:{erg.group(2)}" if erg else ""
        alle.append({
            "datum":    dt.strftime("%a %d.%m.%Y"),
            "zeit":     m.group(2),
            "heim":     heim,
            "gast":     gast,
            "ergebnis": ergebnis,
            "ts":       dt.timestamp(),
            "_dt":      dt,
        })


def lade_spiele(liga_id: int) -> tuple:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    alle  = []
    jetzt = datetime.now()
    params_base = {"do": "spiele", "lid": liga_id, "zeit": "alle"}

    # Seite 1 laden und Gesamtanzahl ermitteln
    soup1 = fetch(BASE_URL, params_base)
    _parse_spiele_seite(soup1, alle)
    pm = re.search(r"Seite\s+\d+\s+von\s+(\d+)", soup1.get_text())
    gesamt = int(pm.group(1)) if pm else 1

    # Alle weiteren Seiten parallel laden (max 15 gleichzeitig)
    if gesamt > 1:
        def fetch_seite(nr):
            s = fetch(BASE_URL, {**params_base, "seite": nr})
            teil = []
            _parse_spiele_seite(s, teil)
            return teil

        with ThreadPoolExecutor(max_workers=8) as ex:
            futures = {ex.submit(fetch_seite, nr): nr for nr in range(2, gesamt + 1)}
            for fut in as_completed(futures):
                alle.extend(fut.result())

    seen, unique = set(), []
    for s in alle:
        key = (s["datum"], s["heim"], s["gast"])
        if key not in seen:
            seen.add(key)
            unique.append(s)
    unique.sort(key=lambda x: x["ts"])
    vergangene = [s for s in unique if s["_dt"] < jetzt]
    kuenftige  = [s for s in unique if s["_dt"] >= jetzt]
    for s in unique:
        del s["_dt"]
    return vergangene, kuenftige


# ─── Liga-Cache ──────────────────────────────────────────────────────────────────

def lade_liga_daten(liga_id: int, force: bool = False) -> dict:
    """Lädt Daten für eine Liga (mit Caching)."""
    with _cache_lock:
        cached = _liga_cache.get(liga_id)

    # Cache-Check (max 4 Stunden alt)
    if not force and cached:
        alter_sek = (datetime.now() - cached["geladen_am"]).total_seconds()
        if alter_sek < UPDATE_INTERVALL_STUNDEN * 3600:
            return cached

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Lade Liga {liga_id}...")
    try:
        from concurrent.futures import ThreadPoolExecutor

        # Tabelle+Rangliste und Spiele parallel laden (2 statt 3 sequenzielle Requests)
        with ThreadPoolExecutor(max_workers=2) as ex:
            fut_haupt  = ex.submit(lade_tabelle_und_rangliste, liga_id)
            fut_spiele = ex.submit(lade_spiele, liga_id)
            tabelle, rangliste    = fut_haupt.result()
            vergangene, kuenftige = fut_spiele.result()

        # Liga-Name aus bekannter Liste
        liga_name = ""
        with _cache_lock:
            for l in _ligen_liste:
                if l["id"] == liga_id:
                    liga_name = l["name"]
                    break
        if not liga_name:
            liga_name = f"Liga {liga_id}"

        daten = {
            "liga_id":   liga_id,
            "liga_name": liga_name,
            "tabelle":   tabelle,
            "rangliste": rangliste,
            "vergangene": vergangene,
            "kuenftige":  kuenftige,
            "geladen_am": datetime.now(),
            "zuletzt":    datetime.now().strftime("%d.%m.%Y %H:%M"),
            "fehler":     None,
        }
        with _cache_lock:
            _liga_cache[liga_id] = daten
        print(f"  OK – {len(tabelle)} Teams, {len(rangliste)} Spieler")
        return daten

    except Exception as e:
        print(f"  Fehler: {e}")
        fehler_daten = {
            "liga_id": liga_id, "liga_name": f"Liga {liga_id}",
            "tabelle": [], "rangliste": [], "vergangene": [], "kuenftige": [],
            "geladen_am": datetime.now(), "zuletzt": None, "fehler": str(e),
        }
        with _cache_lock:
            _liga_cache[liga_id] = fehler_daten
        return fehler_daten


# ─── Mannschaften schnell laden ─────────────────────────────────────────────────

def lade_mannschaften_schnell(liga_id: int) -> list:
    """Lädt nur die Mannschaftsnamen einer Liga (kein vollständiger Daten-Load)."""
    try:
        soup = fetch(BASE_URL, {"lid": liga_id})
        teams = []
        for row in soup.find_all("tr"):
            zellen = row.find_all("td")
            if len(zellen) < 15:
                continue
            if not zellen[1].get("data-msrangsort"):
                continue
            rang_text = safe_text(zellen[1]).strip().rstrip(".")
            if not rang_text.isdigit():
                continue
            name   = safe_text(zellen[2]).strip()
            kürzel = safe_text(zellen[3]).strip()
            if name and kürzel:
                teams.append({"name": name, "kürzel": kürzel})
        return teams
    except Exception:
        return []


# ─── Hintergrund-Thread ──────────────────────────────────────────────────────────

def hintergrund_init():
    """Lädt beim Start die Ligen-Liste und danach alle Mannschaftsnamen."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    global _ligen_liste, _ligen_geladen

    ligen = entdecke_ligen()
    with _cache_lock:
        _ligen_liste[:] = ligen
        _ligen_geladen = True
    print(f"Ligen-Liste geladen: {len(ligen)} Einträge")

    print("Bereit.")


# ─── Flask-Routen ────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    with _cache_lock:
        ligen = list(_ligen_liste)
        geladen = _ligen_geladen
    return render_template("index.html",
                           ligen=ligen,
                           geladen=geladen,
                           ligen_json=json.dumps(ligen))


@app.route("/api/ligen")
def api_ligen():
    with _cache_lock:
        return jsonify(_ligen_liste)


@app.route("/api/liga/<int:liga_id>/mannschaften")
def api_mannschaften(liga_id):
    """Gibt nur die Mannschaftsliste zurück – schnell, kein Spiele-Fetch."""
    # Aus Cache wenn schon geladen
    with _cache_lock:
        cached = _liga_cache.get(liga_id)
    if cached and cached.get("tabelle"):
        teams = [{"name": t["name"], "kürzel": t["kürzel"]} for t in cached["tabelle"]]
        return jsonify(teams)
    # Sonst schnell holen
    teams = lade_mannschaften_schnell(liga_id)
    return jsonify(teams)


@app.route("/api/liga/<int:liga_id>")
def api_liga(liga_id):
    force = request.args.get("refresh") == "1"
    daten = lade_liga_daten(liga_id, force=force)
    return jsonify({
        "liga_id":    daten["liga_id"],
        "liga_name":  daten["liga_name"],
        "tabelle":    daten["tabelle"],
        "rangliste":  daten["rangliste"],
        "vergangene": daten["vergangene"],
        "kuenftige":  daten["kuenftige"],
        "zuletzt":    daten["zuletzt"],
        "fehler":     daten["fehler"],
    })


@app.route("/api/status")
def api_status():
    with _cache_lock:
        return jsonify({
            "ligen_geladen": _ligen_geladen,
            "ligen_anzahl":  len(_ligen_liste),
            "cache_groesse": len(_liga_cache),
        })


# ─── Start ───────────────────────────────────────────────────────────────────────

_init_gestartet = False
_init_lock = threading.Lock()


def starte_init_thread():
    global _init_gestartet
    with _init_lock:
        if not _init_gestartet:
            _init_gestartet = True
            t = threading.Thread(target=hintergrund_init, daemon=True)
            t.start()


@app.before_request
def sicherstelle_init():
    starte_init_thread()


if __name__ == "__main__":
    starte_init_thread()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
