Okay, ich habe die JSON-Antwort von der GGG API analysiert, die du mir geschickt hast, und das ist super hilfreich!

**Hier ist das Problem:**

*   **Mod-Struktur:** Die GGG API liefert die Modifikatoren (z.B. `implicitMods`, `explicitMods`) tatsächlich als **Listen von Dictionaries**, nicht als reine Strings. Jedes Dictionary hat einen Schlüssel `description`, der den lesbaren Mod-Text enthält. Beispiel: `{"description":"Has 3 [Charm] Slots"}`.
*   **Dein Backend:** Mein letzter Fix (der `_extract_mod_texts` hinzugefügt hat) hat die `processed_mods` für die `parse_item_stats` korrekt vorbereitet, aber ich habe vergessen, dass die `implicit`, `explicit`, etc. Listen **selbst** in deinem `items.append` auch bereinigt werden müssen, bevor sie ins `mods`-Dictionary für das Frontend kommen. Aktuell sind dort noch die originalen Listen mit den Dictionaries drin.
*   **Frontend:** Dein Frontend (JavaScript in `index.html`) iteriert über diese `mods`-Listen und versucht, die einzelnen Mod-Einträge direkt zu rendern. Wenn es ein Dictionary ist, zeigt es "`[object Object]`" an.

**Der Code-Fix:**

Ich werde die `app.py` noch einmal anpassen. Diesmal werde ich sicherstellen, dass die Mod-Listen (`implicit`, `enchant`, `explicit`, etc.) direkt nach dem Abrufen von der GGG-Antwort durch die `_extract_mod_texts`-Funktion laufen. Dann enthalten sie nur noch Strings und das Frontend sollte sie korrekt anzeigen können.

Ich werde auch die `_extract_mod_texts` Funktion außerhalb der `api_character_gear` Funktion definieren, um den Code sauberer und effizienter zu machen. Ich habe die Hilfsfunktion `_coerce_display_value` bereits korrekt für `properties` und `requirements` hinzugefügt, das sollte passen.

Hier ist der neue, vollständige Patch. Bitte ersetze deine `app.py` mit diesem Inhalt und pushe es erneut zu GitHub.

```python
# ============================================================
#  Exile Eye - Backend (Flask)
#  PoE2 Companion: OCR-Item-Scan + GGG-OAuth + Gear-Vergleich
# ============================================================
#
#  START:  python app.py
#  LOGIN:  http://localhost:8000/login
#
#  Vor dem ersten Start:
#    1. pip install flask requests python-dotenv pillow pytesseract pillow-heif opencv-python numpy
#       (pillow-heif = iPhone-HEIC-Support, opencv = bessere Foto-Erkennung)
#    2. .env.example kopieren -> ".env" und ausfuellen
#    3. SECRET_KEY erzeugen:
#       python -c "import secrets; print(secrets.token_hex(32))"
# ============================================================

import os
import time
import base64
import hashlib
import secrets
import urllib.parse

import requests
from flask import (
    Flask, request, redirect, session,
    jsonify, send_from_directory, url_for
)
from dotenv import load_dotenv
import zlib
import re
import json

# Stat-Woerterbuch (DE + EN) aus separater Datei
from stats_dict import (
    parse_stats as dict_parse_stats,
    guess_slot as dict_guess_slot,
    clean_item_text as dict_clean_text,
    PERCENT_STATS,
)

# --- .env laden (Secret Key, Client ID etc. liegen NICHT im Code) ---
load_dotenv()

app = Flask(__name__)

# --- Session-Cookie-Sicherheit (wichtig fuer gehostete HTTPS-Version) ---
# In Produktion (HTTPS) sollten Cookies nur ueber HTTPS gehen.
# Lokal (http://localhost) muss SECURE aus sein, sonst geht der Login nicht.
_is_prod = os.getenv("FLASK_DEBUG", "1") == "0"
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=_is_prod,   # nur in Produktion (HTTPS) erzwingen
)

# Secret Key kommt aus der .env - NICHT mehr os.urandom (sonst fliegen
# bei jedem Neustart alle Sessions raus). Fallback nur als Notnagel.
app.secret_key = os.getenv("SECRET_KEY")
if not app.secret_key:
    raise RuntimeError(
        "SECRET_KEY fehlt! Lege eine .env Datei an (siehe .env.example) "
        "und trage einen mit 'python -c \"import secrets; "
        "print(secrets.token_hex(32))\"' erzeugten Hex-String ein."
    )

# ------------------------------------------------------------
#  Konfiguration (alles aus der .env)
# ------------------------------------------------------------
CLIENT_ID    = os.getenv("POE_CLIENT_ID", "exileeyenavigator")
REDIRECT_URI = os.getenv("POE_REDIRECT_URI", "http://localhost:8000/callback")
REALM        = os.getenv("POE_REALM", "poe2")   # poe2 fuer Path of Exile 2!
SCOPES       = "account:profile account:characters"
APP_VERSION  = "1.0.0"
CONTACT      = os.getenv("POE_CONTACT", "deine-mail@example.com")

# WICHTIG: GGG schreibt diesen User-Agent vor:
#   OAuth {clientId}/{version} (contact: {mail})\n"
# Wird hier automatisch aus Client ID + Contact zusammengebaut.
USER_AGENT   = f"OAuth {CLIENT_ID}/{APP_VERSION} (contact: {CONTACT})"

# Tesseract-Pfad aus der .env (Windows) - bis zur .exe!
TESSERACT_PATH = os.getenv(
    "TESSERACT_PATH",
    r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
)

# OAuth-Endpunkte
AUTH_URL  = "https://www.pathofexile.com/oauth/authorize"
TOKEN_URL = "https://www.pathofexile.com/oauth/token"
# !!! WICHTIG: Daten-API laeuft auf api.pathofexile.com, NICHT auf www !!!
API_BASE  = "https://api.pathofexile.com"


# ------------------------------------------------------------
#  PKCE-Helfer (Public Client braucht code_verifier/challenge)
# ------------------------------------------------------------
def make_pkce_pair():
    """Erzeugt code_verifier + code_challenge (S256) fuer PKCE."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).decode().rstrip("=")
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


# ------------------------------------------------------------
#  Routen: Frontend
# ------------------------------------------------------------
@app.route("/")
def index():
    # index.html liegt im selben Ordner
    return send_from_directory(".", "index.html")


# ------------------------------------------------------------
#  PWA-Dateien (Manifest, Service Worker, Icons)
# ------------------------------------------------------------
@app.route("/manifest.json")
def manifest():
    return send_from_directory(".", "manifest.json", mimetype="application/manifest+json")

@app.route("/sw.js")
def service_worker():
    # Service Worker muss aus dem Root kommen (sonst greift der scope nicht)\n"
    resp = send_from_directory(".", "sw.js", mimetype="application/javascript")
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp

@app.route("/icons/<path:filename>")
def icons(filename):
    return send_from_directory("icons", filename)


# ------------------------------------------------------------
#  Rechtstexte (Impressum, Datenschutz, Nutzungsbedingungen)
# ------------------------------------------------------------
@app.route("/impressum")
def impressum():
    return send_from_directory(".", "impressum.html")

@app.route("/datenschutz")
def datenschutz():
    return send_from_directory(".", "datenschutz.html")

@app.route("/nutzungsbedingungen")
def nutzungsbedingungen():
    return send_from_directory(".", "nutzungsbedingungen.html")


# ------------------------------------------------------------
#  Routen: OAuth Login-Flow
# ------------------------------------------------------------
@app.route("/login")
def login():
    verifier, challenge = make_pkce_pair()
    state = secrets.token_urlsafe(24)

    # EINHEITLICHE Keys! (das war einer der alten Bugs:
    # mal 'oauth_code_verifier', mal 'oauth_verifier')\n"
    session["oauth_code_verifier"] = verifier
    session["oauth_state"] = state

    params = {
        "client_id":             CLIENT_ID,
        "response_type":         "code",
        "scope":                 SCOPES,
        "state":                 state,
        "redirect_uri":          REDIRECT_URI,
        "code_challenge":        challenge,
        "code_challenge_method": "S256",
        "prompt":                "consent",
    }
    return redirect(f"{AUTH_URL}?{urllib.parse.urlencode(params)}")


@app.route("/callback")
def callback():
    # Fehler von GGG direkt anzeigen
    if "error" in request.args:
        return redirect(url_for("index") + f"?error={request.args.get('error')}")

    code = request.args.get("code")
    state = request.args.get("state")

    # State pruefen (CSRF-Schutz)
    if not state or state != session.get("oauth_state"):
        return redirect(url_for("index") + "?error=state_mismatch")

    # GLEICHER Key wie in /login!\n"
    verifier = session.get("oauth_code_verifier")
    if not code or not verifier:
        return redirect(url_for("index") + "?error=missing_code_or_verifier")

    # Token-Austausch (PKCE: client_secret NICHT noetig bei Public Client)\n"
    data = {
        "client_id":     CLIENT_ID,
        "grant_type":    "authorization_code",
        "code":          code,
        "redirect_uri":  REDIRECT_URI,
        "scope":         SCOPES,
        "code_verifier": verifier,
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent":   USER_AGENT,
    }

    try:
        resp = requests.post(TOKEN_URL, data=data, headers=headers, timeout=20)
    except requests.RequestException as e:
        return redirect(url_for("index") + f"?error=token_request_failed&detail={e}")

    if resp.status_code != 200:
        print(f"[CALLBACK FEHLER] {resp.status_code}: {resp.text[:300]}")
        return redirect(url_for("index") + f"?error=token_{resp.status_code}")

    tok = resp.json()
    session["access_token"] = tok.get("access_token")
    session["token_expires"] = time.time() + tok.get("expires_in", 0)
    print(f"[CALLBACK OK] Token erhalten. Scopes: {tok.get('scope')}")

    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ------------------------------------------------------------
#  Hilfsfunktion: authentifizierter API-Call
# ------------------------------------------------------------
# ------------------------------------------------------------
#  Caching + Rate-Limit-Handling fuer GGG-API
# ------------------------------------------------------------
# Einfacher In-Memory-Cache: {cache_key: (zeitpunkt, daten)}\n"
# Spart GGG-Anfragen (jeder Klick fragt nicht neu) -> schont das Rate-Limit.\n"
_API_CACHE = {}\n"
CACHE_TTL = 60          # Sekunden, wie lange Daten \"frisch\" sind\n"
_CACHE_MAX = 500        # max. Eintraege (gegen Speicher-Voll-Laufen)\n"


def _cache_get(key):\n"
    entry = _API_CACHE.get(key)\n"
    if entry and (time.time() - entry[0]) < CACHE_TTL:\n"
        return entry[1]\n"
    return None\n"


def _cache_set(key, data):\n"
    if len(_API_CACHE) > _CACHE_MAX:\n"
        # aelteste Haelfte rauswerfen (simpel, reicht hier)\n"
        for k in list(_API_CACHE.keys())[: _CACHE_MAX // 2]:\n"
            _API_CACHE.pop(k, None)\n"
    _API_CACHE[key] = (time.time(), data)\n"


def api_get(path, use_cache=True):\n"
    """\n"
    GET gegen api.pathofexile.com mit Bearer-Token + User-Agent.\n"
    - nutzt Caching (schont das GGG-Rate-Limit)\n"
    - respektiert das Rate-Limit (wartet bei 429 die Retry-After-Zeit ab)\n"
    """\n"
    token = session.get("access_token")\n"
    if not token:\n"
        return None, 401, "not_logged_in"\n"

    # pro Account + Pfad cachen (jeder Nutzer hat eigene Daten)\n"
    cache_key = f"{token[:12]}:{path}"\n"
    if use_cache:\n"
        cached = _cache_get(cache_key)\n"
        if cached is not None:\n"
            return cached, 200, None\n"

    headers = {\n"
        "Authorization": f"Bearer {token}",\n"
        "User-Agent":    USER_AGENT,\n"
    }\n"
    url = f"{API_BASE}{path}"\n"

    # bis zu 2 Versuche (1x normal + 1x nach Rate-Limit-Wartezeit)\n"
    for attempt in range(2):\n"
        try:\n"
            r = requests.get(url, headers=headers, timeout=20)\n"
        except requests.RequestException as e:\n"
            return None, 0, str(e)\n"

        # Rate-Limit-Header auswerten (zum Mitloggen, wie nah wir am Limit sind)\n"
        _log_rate_limit(r, path)\n"

        # 429 = zu viele Anfragen -> warten und EINMAL erneut versuchen\n"
        if r.status_code == 429:\n"
            retry = int(r.headers.get("Retry-After", "5"))\n"
            retry = min(retry, 15)   # nie ewig blockieren\n"
            print(f"[RATE-LIMIT] 429 bei {path} -> warte {retry}s")\n"
            if attempt == 0:\n"
                time.sleep(retry)\n"
                continue\n"
            return None, 429, f"rate_limited_retry_after_{retry}"\n"

        if r.status_code != 200:\n"
            return None, r.status_code, r.text[:300]\n"

        try:\n"
            data = r.json()\n"
        except ValueError:\n"
            return None, r.status_code, "invalid_json"\n"

        if use_cache:\n"
            _cache_set(cache_key, data)\n"
        return data, 200, None\n"

    return None, 429, "rate_limited"\n"


def _log_rate_limit(resp, path):\n"
    """Loggt, wie nah wir am GGG-Rate-Limit sind (zur Kontrolle)."""\n"
    state = resp.headers.get("X-Rate-Limit-Account-State") or \\\n            resp.headers.get("X-Rate-Limit-Client-State") or \\\n            resp.headers.get("X-Rate-Limit-Ip-State")\n"
    rules = resp.headers.get("X-Rate-Limit-Account") or \\\n            resp.headers.get("X-Rate-Limit-Client") or \\\n            resp.headers.get("X-Rate-Limit-Ip")\n"
    if state and rules:\n"
        try:\n"
            hits = int(state.split(":")[0])\n"
            maxhits = int(rules.split(":")[0])\n"
            # Warnung, wenn wir ueber 70% des Limits sind\n"
            if maxhits and hits / maxhits > 0.7:\n"
                print(f"[RATE-LIMIT] {path}: {hits}/{maxhits} (achtung, nah am Limit)")\n"
        except (ValueError, IndexError):\n"
            pass\n"

# NEUE HILFSFUNKTION (auf Modulebene verschoben)
def _extract_mod_texts(mod_list):\n"
    extracted_texts = []\n"
    for mod_entry in mod_list:\n"
        if isinstance(mod_entry, dict) and "description" in mod_entry:\n"
            extracted_texts.append(mod_entry["description"])\n"
        elif isinstance(mod_entry, str):\n"
            extracted_texts.append(mod_entry)\n"
    return extracted_texts\n"

def _coerce_display_value(v):\n"
    """Poe2 API kann manchmal Werte als Objekte liefern.\n"
    Ziel: immer einen renderbaren Wert (string/number) ans Frontend geben.\"\"\"\n"
    if v is None:\n"
        return \"\"\n"
    if isinstance(v, (str, int, float, bool)):\n"
        return v\n"
    if isinstance(v, dict):\n"
        # Häufige Keys\n"
        for k in (\"text\", \"value\", \"number\", \"description\"):\n"  # Added "description" here
            if k in v and isinstance(v[k], (str, int, float, bool)):\n"
                return v[k]\n"
        # Fallback: versuche irgendeinen primitiven Wert\n"
        for vv in v.values():\n"
            if isinstance(vv, (str, int, float, bool)):\n"
                return vv\n"
        return str(v)\n"
    if isinstance(v, (list, tuple)):\n"
        return _coerce_display_value(v[0]) if v else \"\"\n"
    return str(v)\n"

# ------------------------------------------------------------
#  Routen: Auth-Status + Charakter-Daten
# ------------------------------------------------------------
@app.route("/api/status")
def api_status():
    """Sagt dem Frontend, ob eingeloggt + welcher Account."""\n"
    if not session.get("access_token"):\n"
        return jsonify({"logged_in": False})\n"

    profile, code, err = api_get("/profile")\n"
    if code != 200:\n"
        return jsonify({"logged_in": False, "error": err, "code": code})\n"

    return jsonify({\n"
        "logged_in": True,\n"
        "account": profile.get("name"),\n"
    })\n"


@app.route("/api/characters")
def api_characters():
    """\n"
    Liste aller PoE2-Charaktere des eingeloggten Accounts.\n"

    DER KERN-FIX: Der korrekte Endpunkt ist\n"
        GET https://api.pathofexile.com/character/poe2\n"
    (Realm steckt IM Pfad, nicht als ?realm= Query!)\n"
    Ohne /poe2 bekommst du nur PoE1-Chars -> leere Liste bei reinen\n"
    PoE2-Spielern. Genau das war euer "keine Charaktere"-Problem.\n"
    """\n"
    path = f"/character/{REALM}" if REALM and REALM != "pc" else "/character"\n"
    data, code, err = api_get(path)\n"

    print(f"[CHARS] GET {path} -> {code}")\n"
    if code != 200:\n"
        print(f"[CHARS] Fehler-Body: {err}")\n"
        return jsonify({"error": err, "code": code, "characters": []}), code\n"

    chars = data.get("characters", [])\n"
    print(f"[CHARS] Gefunden: {len(chars)} Charaktere")\n"

    # Nur die fuers HUD relevanten Felder ans Frontend\n"
    slim = [{\n"
        "name":   c.get("name"),\n"
        "class":  c.get("class"),\n"
        "level":  c.get("level"),\n"
        "league": c.get("league"),\n"
    } for c in chars]\n"

    return jsonify({"characters": slim})\n"


@app.route("/api/character-gear")
def api_character_gear():
    """\n"
    Ausruestung EINES Charakters.\n"

    DER KERN-FIX (Teil 2): Items kommen ueber\n"
        GET https://api.pathofexile.com/character/poe2/<name>\n"
    Die Antwort enthaelt character.equipment (Liste von Items).\n"
    Jedes Item hat 'inventoryId' (= Slot, z.B. 'Helm', 'BodyArmour').\n"
    """\n"
    name = request.args.get("name", "").strip()\n"
    if not name:\n"
        return jsonify({"error": "kein_charaktername", "items": []}), 400\n"

    enc_name = urllib.parse.quote(name)\n"
    if REALM and REALM != "pc":\n"
        path = f"/character/{REALM}/{enc_name}"\n"
    else:\n"
        path = f"/character/{enc_name}"\n"

    data, code, err = api_get(path)\n"
    print(f"[GEAR] GET {path} -> {code}")\n"
    if code != 200:\n"
        print(f"[GEAR] Fehler-Body: {err}")\n"
        return jsonify({"error": err, "code": code, "items": []}), code\n"

    character = data.get("character", {})\n"
    equipment = character.get("equipment", [])\n"
    print(f"[GEAR] {name}: {len(equipment)} ausgeruestete Items")\n"

    items = []\n"
    for it in equipment:\n"
        # --- Mods nach Typ getrennt sammeln (fuer schoene Anzeige) ---\n"
        # Mod-Listen direkt durch _extract_mod_texts schicken, damit sie nur Strings enthalten\n"
        implicit = _extract_mod_texts(it.get("implicitMods", []) or [])\n"
        enchant  = _extract_mod_texts(it.get("enchantMods", []) or [])\n"
        rune     = _extract_mod_texts(it.get("runeMods", []) or [])        # PoE2: Runen\n"
        explicit = _extract_mod_texts(it.get("explicitMods", []) or [])\n"
        crafted  = _extract_mod_texts(it.get("craftedMods", []) or [])\n"
        fractured = _extract_mod_texts(it.get("fracturedMods", []) or [])\n"

        # alle Mods zusammen (fuer Score-Berechnung)\n"
        all_mods = implicit + enchant + rune + explicit + crafted + fractured\n"

        # Einzelstats parsen (fuer Alt/Neu-Vergleich Stat-fuer-Stat)\n"
        parsed = parse_item_stats("\\n".join(all_mods))\n"

        # --- Eigenschaften (Schaden, Ruestung, Krit etc.) ---\n"
        props = []\n"
        for p in (it.get("properties", []) or []):\n"
            vals = p.get("values", [])\n"
            val_raw = \"\"\n"
            if vals:\n"
                first = vals[0]\n"
                # expected: [[value, ...]]\n"
                if isinstance(first, (list, tuple)) and first:\n"
                    val_raw = first[0]\n"
                else:\n"
                    val_raw = first\n"
            val_str = _coerce_display_value(val_raw)\n"
            props.append({"name": p.get("name", ""), "value": val_str})\n"

        # --- Anforderungen (Level, Attribute) ---\n"
        reqs = []\n"
        for r in (it.get("requirements", []) or []):\n"
            vals = r.get("values", [])\n"
            val_raw = \"\"\n"
            if vals:\n"
                first = vals[0]\n"
                if isinstance(first, (list, tuple)) and first:\n"
                    val_raw = first[0]\n"
                else:\n"
                    val_raw = first\n"
            val_str = _coerce_display_value(val_raw)\n"
            reqs.append({"name": r.get("name", ""), "value": val_str})\n"

        # --- Raritaet bestimmen (frameTypeId neu, frameType alt) ---\n"
        rarity_map = {"Normal": 0, "Magic": 1, "Rare": 2, "Unique": 3}\n"
        rarity = rarity_map.get(it.get("rarity"),\n"
                                it.get("frameType", 0))\n"

        items.append({\n"
            "slot":     it.get("inventoryId"),   # z.B. Helm, BodyArmour, Weapon\n"
            "name":     it.get("name", ""),\n"
            "typeLine": it.get("typeLine", ""),\n"
            "baseType": it.get("baseType", ""),\n"
            "icon":     it.get("icon", ""),      # <-- echtes Item-Bild!\n"
            "ilvl":     it.get("ilvl"),\n"
            "rarity":   rarity,\n"
            "corrupted": bool(it.get("corrupted")),\n"
            "properties":   props,\n"
            "requirements": reqs,\n"
            "mods": {\n"
                "implicit":  implicit,\n"
                "enchant":   enchant,\n"
                "rune":      rune,\n"
                "explicit":  explicit,\n"
                "crafted":   crafted,\n"
                "fractured": fractured,\n"
            },\n"
            "all_mods": all_mods,                # fuer Score (enthält jetzt Strings)\n"
            "parsed_stats": parsed,              # einzelne Werte fuer Vergleich\n"
        })\n"

    return jsonify({\n"
        "character": {\n"
            "name":  character.get("name"),\n"
            "class": character.get("class"),\n"
            "level": character.get("level"),\n"
        },\n"
        "items": items,\n"
    })\n"


# ------------------------------------------------------------
#  Auto-Tooltip-Erkennung (OpenCV) – findet den dunklen Item-Bereich\n"
# ------------------------------------------------------------\n"
def auto_crop_tooltip(pil_img):\n"
    """\n"
    Findet den dunklen Item-Tooltip im Foto und schneidet ihn zu.\n"
    Gibt (zugeschnittenes_PIL_Bild, gefunden?) zurueck.\n"
    PoE-Tooltips sind sehr dunkel -> als grosse dunkle Flaeche erkennbar.\n"
    """\n"
    try:\n"
        import cv2\n"
        import numpy as np\n"
    except ImportError:\n"
        return pil_img, False\n"

    try:\n"
        rgb = pil_img.convert("RGB")\n"
        arr = np.array(rgb)[:, :, ::-1].copy()   # RGB -> BGR fuer cv2\n"
        H, W = arr.shape[:2]\n"
        gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)\n"

        # dunkle Bereiche maskieren (Tooltip-Hintergrund ist fast schwarz)\n"
        _, dark = cv2.threshold(gray, 45, 255, cv2.THRESH_BINARY_INV)\n"
        # benachbarte dunkle Flaechen verbinden\n"
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25))\n"
        dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, kernel)\n"

        cnts, _ = cv2.findContours(dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)\n"
        best, best_area = None, 0\n"
        for c in cnts:\n"
            x, y, w, h = cv2.boundingRect(c)\n"
            area = w * h\n"
            # plausible Tooltip-Groesse: nicht winzig, nicht fast ganzes Bild\n"
            if (area > best_area and area > 12000 and w > 100 and h > 70\n"
                    and area < 0.9 * W * H):\n"
                best_area, best = area, (x, y, w, h)\n"

        if best:\n"
            x, y, w, h = best\n"
            # kleinen Rand zugeben (Schrift am Rand nicht abschneiden)\n"
            pad = 8\n"
            x = max(0, x - pad); y = max(0, y - pad)\n"
            w = min(W - x, w + 2 * pad); h = min(H - y, h + 2 * pad)\n"
            cropped = pil_img.crop((x, y, x + w, y + h))\n"
            return cropped, True\n"
    except Exception:\n"
        pass\n"
    return pil_img, False\n"


# ------------------------------------------------------------
#  OCR-Bildaufbereitung (OpenCV) + Mehrfach-Strategie\n"
# ------------------------------------------------------------\n"
def ocr_best_effort(pil_img, pytesseract, ocr_lang="deu+eng"):\n"
    """\n"
    Versucht mehrere Bildaufbereitungen und gibt den besten OCR-Text zurueck.\n"
    ocr_lang: Tesseract-Sprache je nach Spiel-Sprache des Users.\n"
    Nutzt OpenCV falls verfuegbar (viel besser bei Fotos), sonst Pillow-Fallback.\n"

    GESCHWINDIGKEIT: Tesseract ist der Flaschenhals (~1,5s pro Aufruf).\n"
    Darum: Varianten nach Erfolgswahrscheinlichkeit sortiert + Smart-Stop -\n"
    sobald eine Variante "gut genug" ist, hoeren wir sofort auf (oft 1 statt 6\n"
    Aufrufe = bis zu 6x schneller bei klaren Screenshots).\n"
    """\n"
    from PIL import Image, ImageOps, ImageFilter\n"

    candidates = []   # Liste von (PIL-Bild, tesseract-config)\n"

    # --- Versuch mit OpenCV (beste Qualitaet bei Fotos) ---\n"
    try:\n"
        import cv2\n"
        import numpy as np\n"

        rgb = pil_img.convert("RGB")\n"
        arr = np.array(rgb)[:, :, ::-1].copy()   # RGB -> BGR fuer cv2\n"
        gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)\n"

        # hochskalieren (OCR mag grosse Schrift) - 1500 reicht & ist schneller als 1800\n"
        h, w = gray.shape\n"
        if max(h, w) < 1500:\n"
            scale = 1500 / max(h, w)\n"
            gray = cv2.resize(gray, (int(w * scale), int(h * scale)),\n"
                              interpolation=cv2.INTER_CUBIC)\n"

        # Rauschen reduzieren (guenstig: ~0,02s)\n"
        denoised = cv2.bilateralFilter(gray, 9, 75, 75)\n"

        # PoE = heller Text auf dunkel. Mittlere Helligkeit pruefen, um zu\n"
        # entscheiden, ob wir invertieren muessen (Text soll schwarz auf weiss).\n"
        mean_val = float(denoised.mean())\n"

        # Variante 1 (BESTE zuerst): Otsu-Threshold\n"
        _, otsu = cv2.threshold(denoised, 0, 255,\n"
                                cv2.THRESH_BINARY + cv2.THRESH_OTSU)\n"
        # Bei dunklem Hintergrund (heller Text) zuerst die invertierte nehmen,\n"
        # damit der Smart-Stop sofort die richtige erwischt.\n"
        if mean_val < 110:\n"
            candidates.append((Image.fromarray(255 - otsu), "--psm 6"))\n"
            candidates.append((Image.fromarray(otsu), "--psm 6"))\n"
        else:\n"
            candidates.append((Image.fromarray(otsu), "--psm 6"))\n"
            candidates.append((Image.fromarray(255 - otsu), "--psm 6"))\n"

        # Variante 2 (Fallback): adaptiver Threshold (ungleichmaessige Beleuchtung)\n"
        adaptive = cv2.adaptiveThreshold(\n"
            denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,\n"
            cv2.THRESH_BINARY, 31, 11)\n"
        if mean_val < 110:\n"
            candidates.append((Image.fromarray(255 - adaptive), "--psm 6"))\n"
            candidates.append((Image.fromarray(adaptive), "--psm 6"))\n"
        else:\n"
            candidates.append((Image.fromarray(adaptive), "--psm 6"))\n"
            candidates.append((Image.fromarray(255 - adaptive), "--psm 6"))\n"

    except ImportError:\n"
        pass  # kein OpenCV -> Pillow-Fallback unten\n"

    # --- Pillow-Fallback / Zusatz-Varianten (nur wenn OpenCV fehlt) ---\n"
    if not candidates:\n"
        try:\n"
            g = pil_img.convert("L")\n"
            w, h = g.size\n"
            if max(w, h) < 1500:\n"
                s = 1500 / max(w, h)\n"
                g = g.resize((int(w * s), int(h * s)))\n"
            inv = ImageOps.autocontrast(ImageOps.invert(g)).filter(ImageFilter.SHARPEN)\n"
            candidates.append((inv, "--psm 6"))\n"
            candidates.append((ImageOps.autocontrast(g), "--psm 6"))\n"
        except Exception:\n"
            candidates.append((pil_img, "--psm 6"))\n"

    # --- Kandidaten durch Tesseract jagen, mit SMART-STOP ---\n"
    # "gut genug" = genug Stat-Schluesselwoerter erkannt -> sofort aufhoeren.\n"
    GOOD_ENOUGH = 18   # empirischer Schwellwert (mehrere Stats + Zahlen erkannt)\n"
    best_text = ""\n"
    best_score = -1\n"
    for cand_img, cfg in candidates:\n"
        try:\n"
            try:\n"
                t = pytesseract.image_to_string(cand_img, lang=ocr_lang, config=cfg)\n"
            except Exception:\n"
                t = pytesseract.image_to_string(cand_img, lang="eng", config=cfg)\n"
        except Exception:\n"
            continue\n"
        score = _ocr_quality(t)\n"
        if score > best_score:\n"
            best_score, best_text = score, t\n"
        # Smart-Stop: wenn schon klar gut, weitere Tesseract-Aufrufe sparen\n"
        if best_score >= GOOD_ENOUGH:\n"
            break\n"

    return best_text\n"


def _ocr_quality(text):\n"
    """Bewertet OCR-Text: mehr erkannte Zahlen + Stat-Woerter = besser."""\n"
    if not text:\n"
        return 0\n"
    low = text.lower()\n"
    score = 0\n"
    score += len(re.findall(r"\\d+", text)) * 2          # Zahlen sind Gold\n"
    # Schluesselwoerter Deutsch + Englisch\n"
    for kw in ["life", "mana", "resist", "armour", "energy", "damage",\n"
               "critical", "movement", "spirit", "level",\n"
               "leben", "widerstand", "energieschild", "rüstung", "ruestung",\n"
               "schaden", "kritische", "bewegungs", "geschwindigkeit", "stufe"]:\n"
        score += low.count(kw) * 3\n"
    score += len([c for c in text if c.isalnum()]) // 20  # Textmenge leicht gewichten\n"
    return score\n"


# ------------------------------------------------------------
#  Routen: OCR-Analyse eines hochgeladenen Item-Fotos\n"
# ------------------------------------------------------------\n"
@app.route("/api/analyze", methods=["POST"])\n"
def api_analyze():
    """\n"
    Nimmt ein (zugeschnittenes) Item-Foto entgegen, jagt es durch\n"
    Tesseract, parst die Stats und gibt einen Score zurueck.\n"
    """\n"
    if "image" not in request.files:\n"
        return jsonify({"error": "kein_bild"}), 400\n"

    try:\n"
        import pytesseract\n"
        from PIL import Image, ImageOps, ImageFilter\n"
    except ImportError:\n"
        return jsonify({\n"
            "error": "ocr_libs_fehlen",\n"
            "detail": "pip install pillow pytesseract"\n"
        }), 500\n"

    # iPhone-Fotos sind oft HEIC/HEIF -> Pillow kann das nur mit pillow-heif.\n"
    # Wenn installiert, registrieren wir den Decoder (sonst stiller Fallback).\n"
    try:\n"
        from pillow_heif import register_heif_opener\n"
        register_heif_opener()\n"
    except ImportError:\n"
        pass  # HEIC geht dann nicht, JPG/PNG aber schon\n"

    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH\n"

    file = request.files["image"]\n"
    try:\n"
        img = Image.open(file.stream)\n"
        # EXIF-Rotation vom Handy korrigieren (sonst steht das Bild quer)\n"
        img = ImageOps.exif_transpose(img)\n"
    except Exception as e:\n"
        return jsonify({\n"
            "error": "bild_unlesbar",\n"
            "detail": str(e),\n"
            "hint": "iPhone-Foto? Dann 'pip install pillow-heif' ausführen, "\n"
                    "oder am iPhone unter Einstellungen > Kamera > Formate "\n"
                    "auf 'Maximale Kompatibilität' (JPG) stellen."\n"
        }), 400\n"

    # Auto-Crop: dunklen Item-Tooltip automatisch finden & zuschneiden\n"
    # (kann das Frontend per autocrop=0 abschalten, dann manueller Rahmen)\n"
    autocrop = request.form.get("autocrop", "1") != "0"\n"
    cropped_flag = False\n"
    if autocrop:\n"
        img, cropped_flag = auto_crop_tooltip(img)\n"

    # OCR-Sprache je nach Spiel-Sprache: "de", "en" oder "auto" (=beide)\n"
    game_lang = request.form.get("game_lang", "auto")\n"
    lang_map = {"de": "deu+eng", "en": "eng", "auto": "deu+eng"}\n"
    ocr_lang = lang_map.get(game_lang, "deu+eng")\n"

    # OCR mit mehreren Strategien versuchen, beste Ausbeute gewinnt\n"
    text = ocr_best_effort(img, pytesseract, ocr_lang)\n"
    if not text or len(text.strip()) < 3:\n"
        return jsonify({\n"
            "error": "nichts_erkannt",\n"
            "detail": "Es konnte kein Text gelesen werden.",\n"
            "hint": "Tipp: Tooltip näher/schärfer fotografieren, gut beleuchten, "\n"
                    "und mit dem Zuschnitt-Rahmen genau auf den Item-Text ziehen."\n"
        }), 200  # 200, damit Frontend den Hinweis sauber anzeigt\n"

    stats = parse_item_stats(text)\n"

    # optionale Custom-Gewichtung vom Frontend (Regler/Build-Import)\n"
    custom_weights = None\n"
    try:\n"
        import json as _json\n"
        cw = request.form.get("weights")\n"
        if cw:\n"
            custom_weights = _json.loads(cw)\n"
    except Exception:\n"
        custom_weights = None\n"

    score = compute_score(stats, custom_weights)\n"
    guessed_slot = guess_slot(text)\n"

    return jsonify({\n"
        "raw_text": text,\n"
        "stats": stats,\n"
        "score": score,\n"
        "guessed_slot": guessed_slot,\n"
        "auto_cropped": cropped_flag,   # wurde der Tooltip automatisch gefunden?\n"
    })\n"


# ------------------------------------------------------------
#  Slot-Erkennung aus OCR-Text (Auto-Vorschlag)\n"
# ------------------------------------------------------------\n"
# Stichwoerter pro Slot - wird im OCR-Text gesucht.\n"
# Slot-Stichwoerter Deutsch + Englisch (deutsches Spiel = deutsche Item-Namen)\n"
SLOT_KEYWORDS = {\n"
    "Helm":       ["helm", "helmet", "crown", "mask", "hood", "circlet", "burgonet", "greathelm",\n"
                   "haube", "krone", "maske", "kapuze", "diadem", "sturmhaube"],\n"
    "BodyArmour": ["plate", "armour", "vest", "garb", "robe", "tunic", "jacket", "wraps", "brigandine", "carapace",\n"
                   "rüstung", "ruestung", "plattenrüstung", "plattenruestung", "robe", "weste", "panzer", "wams", "kürass", "kuerass"],\n"
    "Gloves":     ["gloves", "mitts", "gauntlets", "grips",\n"
                   "handschuhe", "fäustlinge", "faeustlinge", "panzerhandschuhe", "griffe"],\n"
    "Boots":      ["boots", "greaves", "sandals", "shoes", "slippers",\n"
                   "stiefel", "sandalen", "beinschienen", "schuhe", "schläppchen", "schlaeppchen", "treter"],\n"
    "Belt":       ["belt", "sash", "braid", "girdle",\n"
                   "gürtel", "guertel", "schärpe", "schaerpe", "band"],\n"
    "Amulet":     ["amulet", "necklace", "talisman", "pendant",\n"
                   "amulett", "halskette", "talisman", "anhänger", "anhaenger"],\n"
    "Ring":       ["ring", "band", "coil", "loop",\n"
                   "ring", "reif", "schleife"],\n"
    "Weapon":     ["staff", "wand", "sword", "axe", "mace", "bow", "dagger", "sceptre", "claw", "spear", "quarterstaff", "crossbow",\n"
                   "stab", "zauberstab", "schwert", "axt", "streitkolben", "bogen", "dolch", "zepter", "klaue", "speer", "armbrust"],\n"
    "Offhand":    ["shield", "buckler", "quiver", "focus",\n"
                   "schild", "tartsche", "köcher", "koecher", "fokus", "buckler", "turmschild"],\n"
}\n"


def guess_slot(text):\n"
    """Raet aus dem (DE/EN) Item-Text den Slot - nutzt stats_dict."""\n"
    return dict_guess_slot(text)\n"


# ------------------------------------------------------------
#  Stat-Parsing + Score-Berechnung
# ------------------------------------------------------------\n"
import re\n"

# Gewichte fuer den Score - hier kannst du spaeter tunen\n"
STAT_WEIGHTS = {\n"
    "life":            1.0,\n"
    "mana":            0.3,\n"
    "fire_res":        0.8,\n"
    "cold_res":        0.8,\n"
    "lightning_res":   0.8,\n"
    "chaos_res":       1.0,\n"
    "all_res":         1.0,\n"
    "energy_shield":   0.6,\n"
    "crit_chance":     0.5,\n"
    "spell_damage":    0.5,\n"
    "movement_speed":  0.4,\n"
    "armour":          0.4,\n"
}\n"

# Stat-Patterns: erkennen BEIDE Sprachen (Deutsch + Englisch).\n"
# Deutsch ist Standard bei deutschem Spiel-Client.\n"
STAT_PATTERNS = {\n"
    # Leben: "zu maximalem Leben" / "to maximum Life"\n"
    "life":           r"\\+?(\\d+)\\s+(?:zu\\s+maximalem\\s+Leben|to\\s+(?:maximum\\s+)?Life)",\n"
    # Mana\n"
    "mana":           r"\\+?(\\d+)\\s+(?:zu\\s+maximalem\\s+Mana|to\\s+(?:maximum\\s+)?Mana)",\n"
    # Resistenzen (deutsch: "...widerstand", englisch: "... Resistance")\n"
    "fire_res":       r"\\+?(\\d+)%?\\s+(?:zu\\s+Feuerwiderstand|to\\s+Fire\\s+Resistance)",\n"
    "cold_res":       r"\\+?(\\d+)%?\\s+(?:zu\\s+Kältewiderstand|zu\\s+Kaeltewiderstand|to\\s+Cold\\s+Resistance)",\n"
    "lightning_res":  r"\\+?(\\d+)%?\\s+(?:zu\\s+Blitzwiderstand|to\\s+Lightning\\s+Resistance)",\n"
    "chaos_res":      r"\\+?(\\d+)%?\\s+(?:zu\\s+Chaoswiderstand|to\\s+Chaos\\s+Resistance)",\n"
    # alle Elementarwiderstände: "zu allen Elementarwiderständen" / "to all Elemental Resistances"\n"
    "all_res":        r"\\+?(\\d+)%?\\s+(?:zu\\s+allen\\s+Elementarwiderständen|zu\\s+allen\\s+Elementarwiderstaenden|to\\s+all\\s+Elemental\\s+Resistances)",\n"
    # Energieschild: "maximalem Energieschild" / "increased Energieschild" / EN\n"
    "energy_shield":  r"(\\d+)%?\\s+(?:zu\\s+maximalem\\s+Energieschild|erhöhter\\s+Energieschild|erhoehter\\s+Energieschild|to\\s+(?:maximum\\s+)?Energy\\s+Shield|increased\\s+Energy\\s+Shield)(?!.*Wiederaufladung)(?!\\s+Recharge)",\n"
    # Krit: "kritischer Trefferchance" / "Critical"\n"
    "crit_chance":    r"(\\d+(?:[.,]\\d+)?)%\\s+(?:erhöhte\\s+kritische|erhoehte\\s+kritische|.*?kritischer\\s+Treffer|(?:to\\s+|increased\\s+)?Critical)",\n"
    # Zauberschaden: "erhöhter Zauberschaden" / "increased Spell Damage"\n"
    "spell_damage":   r"(\\d+)%\\s+(?:erhöhter\\s+Zauberschaden|erhoehter\\s+Zauberschaden|increased\\s+Spell\\s+Damage)",\n"
    # Bewegungsgeschwindigkeit: "Bewegungsgeschwindigkeit" / "Movement Speed"\n"
    "movement_speed": r"(\\d+)%\\s+(?:erhöhte\\s+Bewegungsgeschwindigkeit|erhoehte\\s+Bewegungsgeschwindigkeit|increased\\s+Movement\\s+Speed)",\n"
    # Rüstung: "erhöhte Rüstung" / "increased Armour"\n"
    "armour":         r"(\\d+)%\\s+(?:erhöhte\\s+Rüstung|erhoehte\\s+Ruestung|increased\\s+Armour)",\n"
}\n"


def clean_item_text(text):\n"
    """Entfernt GGG-Tags [Tag|Anzeige] -> Anzeige (nutzt stats_dict)."""\n"
    return dict_clean_text(text)\n"


def parse_item_stats(text):\n"
    """Zieht numerische Stats aus Item-/OCR-Text (DE + EN).\n"
    Nutzt das umfassende Woerterbuch aus stats_dict.py."""\n"
    return dict_parse_stats(text)\n"


def _unused_old_parse(text):\n"
    """(alt, nicht mehr genutzt - durch stats_dict ersetzt)"""\n"
    text = clean_item_text(text)\n"
    stats = {}\n"
    for key, pattern in STAT_PATTERNS.items():\n"
        total = 0.0\n"
        found = False\n"
        for m in re.finditer(pattern, text, re.IGNORECASE):\n"
            try:\n"
                total += float(m.group(1))\n"
                found = True\n"
            except (ValueError, IndexError):\n"
                pass\n"
        if found:\n"
            stats[key] = round(total, 1)\n"
    return stats\n"


def compute_score(stats, weights=None):\n"
    """Gewichteter Score. weights kann eine Custom-Gewichtung sein\n"
    (vom Regler oder Build-Import), sonst Standard STAT_WEIGHTS."""\n"
    w = weights if weights else STAT_WEIGHTS\n"
    score = 0.0\n"
    for key, value in stats.items():\n"
        try:\n"
            score += float(value) * float(w.get(key, 0.0))\n"
        except (TypeError, ValueError):\n"
            pass\n"
    return round(score, 1)\n"


# ============================================================\n"
#  BUILD-IMPORT (Path of Building)\n"
#  Liest einen PoB-Code oder pobb.in-Link und leitet daraus\n"
#  ab, welche Stats fuer den Build wichtig sind (= Gewichtung).\n"
# ============================================================\n"

# Wie oft taucht ein Stat im Build auf -> diese Regex zaehlen wir.\n"
BUILD_STAT_PATTERNS = {\n"
    "life":           r"(?:maximalem\\s+Leben|to\\s+(?:maximum\\s+)?Life)",\n"
    "fire_res":       r"(?:Feuerwiderstand|Fire\\s+Resistance)",\n"
    "cold_res":       r"(?:K[äa]ltewiderstand|Cold\\s+Resistance)",\n"
    "lightning_res":  r"(?:Blitzwiderstand|Lightning\\s+Resistance)",\n"
    "chaos_res":      r"(?:Chaoswiderstand|Chaos\\s+Resistance)",\n"
    "all_res":        r"(?:allen\\s+Elementarwiderst|all\\s+Elemental\\s+Resistances)",\n"
    "energy_shield":  r"(?:Energieschild|Energy\\s+Shield)",\n"
    "crit_chance":    r"(?:kritische[rn]?\\s+Treffer|Critical)",\n"
    "spell_damage":   r"(?:Zauberschaden|Spell\\s+Damage)",\n"
    "movement_speed": r"(?:Bewegungsgeschwindigkeit|Movement\\s+Speed)",\n"
    "armour":         r"(?:erh[öo]hte\\s+R[üu]stung|increased\\s+Armour)",\n"
}\n"


def decode_pob_code(code):\n"
    """PoB-Code -> XML. Format: URL-safe base64 -> zlib inflate -> XML."""\n"
    code = code.strip()\n"
    # Padding fuer base64 ggf. auffuellen\n"
    missing = len(code) % 4\n"
    if missing:\n"
        code += "=" * (4 - missing)\n"
    raw = base64.urlsafe_b64decode(code)\n"
    xml = zlib.decompress(raw).decode("utf-8", errors="ignore")\n"
    return xml\n"


def fetch_pobbin(url):\n"
    """Holt den rohen PoB-Code von einem pobb.in-Link."""\n"
    # pobb.in/<id>  ->  pobb.in/<id>/raw\n"
    m = re.search(r"pobb\\.in/([A-Za-z0-9_-]+)", url)\n"
    if not m:\n"
        return None\n"
    raw_url = f"https://pobb.in/{m.group(1)}/raw"\n"
    # pobb.in verlangt einen Browser-User-Agent\n"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "\n"
                             "AppleWebKit/537.36 (KHTML, like Gecko) "\n"
                             "Chrome/131.0.0.0 Safari/537.36"}\n"
    r = requests.get(raw_url, headers=headers, timeout=20)\n"
    if r.status_code == 200:\n"
        return r.text.strip()\n"
    return None\n"


def weights_from_build(xml):\n"
    """Leitet aus dem Build-XML Stat-Gewichte ab (0.2 - 1.0)."""\n"
    xml = clean_item_text(xml)   # GGG-Tags entfernen\n"
    counts = {}\n"
    for key, pat in BUILD_STAT_PATTERNS.items():\n"
        counts[key] = len(re.findall(pat, xml, re.IGNORECASE))\n"

    max_count = max(counts.values()) if counts.values() else 0\n"
    weights = {}\n"
    for key, c in counts.items():\n"
        if max_count > 0 and c > 0:\n"
            # normieren auf 0.2 - 1.0 (haeufigster Stat = 1.0)\n"
            weights[key] = round(0.2 + 0.8 * (c / max_count), 2)\n"
        else:\n"
            weights[key] = 0.0\n"
    return weights, counts\n"


def extract_build_info(xml):\n"
    """Zieht Klasse/Level/Ascendancy aus dem Build-XML (fuer Anzeige)."""\n"
    info = {}\n"
    m = re.search(r'className="([^"]+)"', xml)\n"
    if m: info["class"] = m.group(1)\n"
    m = re.search(r'ascendClassName="([^"]+)"', xml)\n"
    if m and m.group(1): info["ascendancy"] = m.group(1)\n"
    m = re.search(r'level="(\\d+)"', xml)\n"
    if m: info["level"] = int(m.group(1))\n"
    return info\n"


def fetch_maxroll(url):\n"
    """Holt den HTML/JSON-Inhalt einer Maxroll-Build-Seite.\n"
    Maxroll ist (anders als Mobalytics) nicht hart Cloudflare-geblockt."""\n"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "\n"
                             "AppleWebKit/537.36 (KHTML, like Gecko) "\n"
                             "Chrome/131.0.0.0 Safari/537.36"}\n"
    try:\n"
        r = requests.get(url, headers=headers, timeout=20)\n"
    except requests.RequestException:\n"
        return None\n"
    if r.status_code == 200 and "just a moment" not in r.text.lower()[:2000]:\n"
        return r.text\n"
    return None\n"


def weights_from_text(text):\n"
    """Wie weights_from_build, aber fuer beliebigen Item-/Stat-Text\n"
    (Maxroll-HTML oder vom User eingefuegter Gear-Text)."""\n"
    return weights_from_build(text)  # gleiche Zaehl-Logik\n"


@app.route("/api/import-build", methods=["POST"])\n"
def api_import_build():
    """\n"
    Universeller Build-Import. Erkennt automatisch die Quelle:\n"
      1. pobb.in-Link        -> Code holen -> dekodieren\n"
      2. PoB-Export-Code     -> direkt dekodieren\n"
      3. maxroll.gg-Link     -> Seite laden -> Stats aus Text zaehlen\n"
      4. roher Gear-Text      -> Stats direkt aus Text zaehlen (Fallback, geht immer)\n"
    """\n"
    data = request.get_json(silent=True) or {}\n"
    raw = (data.get("code") or "").strip()\n"
    if not raw:\n"
        return jsonify({"error": "kein_code"}), 400\n"

    source = "unbekannt"\n"
    text_for_stats = None\n"
    info = {}\n"
    passive_hints = {}\n"
    slot_stats = {}\n"
    slot_uniques = {}\n"
    extras = {}\n"

    try:\n"
        # --- 0: .build-Datei (JSON von Mobalytics/Build Planner) ---\n"
        if _looks_like_build_json(raw):\n"
            source = "build-datei"\n"
            text_for_stats, info, passive_hints, slot_stats, slot_uniques, extras = parse_build_json(raw)\n"

        # --- 1 & 2: PoB (Link oder Code) ---\n"
        elif "pobb.in" in raw:\n"
            source = "pobb.in"\n"
            code = fetch_pobbin(raw)\n"
            if not code:\n"
                return jsonify({"error": "pobbin_fehlgeschlagen",\n"
                                "detail": "Link konnte nicht geladen werden"}), 400\n"
            text_for_stats = decode_pob_code(code)\n"
            info = extract_build_info(text_for_stats)\n"

        # --- 3: Maxroll-Link ---\n"
        elif "maxroll.gg" in raw:\n"
            source = "maxroll"\n"
            html = fetch_maxroll(raw)\n"
            if not html:\n"
                return jsonify({"error": "maxroll_fehlgeschlagen",\n"
                                "detail": "Seite blockiert oder leer. Tipp: "\n"
                                          "Gear-Text direkt einfügen."}), 400\n"
            text_for_stats = html\n"

        # --- 4: pruefen ob es ein PoB-Code ist (base64) ---\n"
        elif _looks_like_pob_code(raw):\n"
            source = "pob-code"\n"
            try:\n"
                text_for_stats = decode_pob_code(raw)\n"
                info = extract_build_info(text_for_stats)\n"
            except Exception:\n"
                # kein gueltiger Code -> als Text behandeln\n"
                source = "text"\n"
                text_for_stats = raw\n"

        # --- sonst: roher Gear-Text (Fallback, geht immer) ---\n"
        else:\n"
            source = "text"\n"
            text_for_stats = raw\n"

    except Exception as e:\n"
        return jsonify({"error": "import_fehler", "detail": str(e)}), 400\n"

    if not text_for_stats or len(text_for_stats) < 5:\n"
        return jsonify({"error": "kein_inhalt",\n"
                        "detail": "Nichts auswertbares gefunden"}), 400\n"

    text_for_stats = clean_item_text(text_for_stats)   # GGG-Tags entfernen\n"
    counts = {k: len(re.findall(p, text_for_stats, re.IGNORECASE))\n"
              for k, p in BUILD_STAT_PATTERNS.items()}\n"

    # Passiv-Baum-Hinweise mit einrechnen (zaehlen halb so stark wie Items)\n"
    for stat, hint_count in passive_hints.items():\n"
        if stat in counts:\n"
            counts[stat] += hint_count * 0.5\n"

    # Wenn gar kein Stat UND keine Uniques gefunden wurden -> Hinweis\n"
    if sum(counts.values()) == 0 and not slot_uniques and not slot_stats:\n"
        return jsonify({"error": "keine_stats",\n"
                        "detail": "Keine bekannten Stats gefunden. "\n"
                                  "Bei Maxroll/Mobalytics: Gear-Text direkt einfügen.",\n"
                        "source": source}), 400\n"

    # Gewichte normieren (haeufigster Stat = 1.0)\n"
    max_count = max(counts.values()) if counts.values() else 0\n"
    weights = {}\n"
    for key, c in counts.items():\n"
        weights[key] = round(0.2 + 0.8 * (c / max_count), 2) if (max_count and c) else 0.0\n"

    print(f"[BUILD] Import OK (Quelle: {source}): {info}")\n"
    print(f"[BUILD] Gefundene Stats: {dict((k,round(v,1)) for k,v in counts.items() if v)}")\n"
    if passive_hints:\n"
        print(f"[BUILD] Passiv-Hinweise: {passive_hints}")\n"

    return jsonify({\n"
        "source": source,\n"
        "build_info": info,\n"
        "weights": weights,\n"
        "stat_counts": {k: round(v, 1) for k, v in counts.items()},\n"
        "passive_hints": passive_hints,\n"
        "slot_stats": slot_stats,       # pro Slot die Stats fuer slot-genaue Trade-Suche!\n"
        "slot_uniques": slot_uniques,   # pro Slot der Unique-Name (Namens-Suche)\n"
        "skills": extras.get("skills", []),    # Skill-Gems + Support-Gems\n"
        "flasks": extras.get("flasks", []),    # Flask-Slots\n"
        "charms": extras.get("charms", []),    # Charm-Slots\n"
    })\n"


def _looks_like_pob_code(s):\n"
    """Heuristik: sieht der String nach einem PoB-Base64-Code aus?"""\n"
    if len(s) < 40 or " " in s.strip():\n"
        return False\n"
    # PoB-Codes bestehen aus URL-safe base64 Zeichen\n"
    return bool(re.fullmatch(r"[A-Za-z0-9_\\-=]+", s.strip()))\n"


# ------------------------------------------------------------
#  .build-Datei (Mobalytics / PoE2 Build Planner Format)\n"
# ------------------------------------------------------------\n"
# Passiv-Baum-Themen -> welcher Stat dadurch wichtig wird.\n"
# (z.B. viele "elemental"-Knoten -> Resistenzen/Ele-Schaden wichtig)\n"
PASSIVE_THEME_HINTS = {\n"
    "elemental":     ["fire_res", "cold_res", "lightning_res"],\n"
    "cold":          ["cold_res"],\n"
    "fire":          ["fire_res"],\n"
    "lightning":     ["lightning_res"],\n"
    "chaos":         ["chaos_res"],\n"
    "life":          ["life"],\n"
    "energy":        ["energy_shield"],\n"
    "spell":         ["spell_damage"],\n"
    "criticals":     ["crit_chance"],\n"
}\n"


# Mapping: GGG-interne Ascendancy-ID -> Klasse + lesbarer Name\n"
# (Reihenfolge laut offizieller Klassen-Tabelle)\n"
ASCENDANCY_MAP = {\n"
    # Sorceress (Intelligence)\n"
    "Sorceress1": ("Sorceress", "Stormweaver"),\n"
    "Sorceress2": ("Sorceress", "Chronomancer"),\n"
    "Sorceress3": ("Sorceress", "Disciple of Varashta"),\n"
    # Witch (Intelligence)\n"
    "Witch1": ("Witch", "Infernalist"),\n"
    "Witch2": ("Witch", "Blood Mage"),\n"
    "Witch3": ("Witch", "Lich"),\n"
    # Warrior (Strength)\n"
    "Warrior1": ("Warrior", "Warbringer"),\n"
    "Warrior2": ("Warrior", "Titan"),\n"
    "Warrior3": ("Warrior", "Smith of Kitava"),\n"
    # Ranger (Dexterity)\n"
    "Ranger1": ("Ranger", "Deadeye"),\n"
    "Ranger2": ("Ranger", "Pathfinder"),\n"
    # Huntress (Dexterity)\n"
    "Huntress1": ("Huntress", "Amazon"),\n"
    "Huntress2": ("Huntress", "Ritualist"),\n"
    "Huntress3": ("Huntress", "Spirit Walker"),\n"
    # Monk (Int/Dex)\n"
    "Monk1": ("Monk", "Invoker"),\n"
    "Monk2": ("Monk", "Acolyte of Chayula"),\n"
    "Monk3": ("Monk", "Martial Artist"),\n"
    # Mercenary (Str/Dex)\n"
    "Mercenary1": ("Mercenary", "Witchhunter"),\n"
    "Mercenary2": ("Mercenary", "Gemling Legionnaire"),\n"
    "Mercenary3": ("Mercenary", "Tactician"),\n"
    # Druid (Str/Int)\n"
    "Druid1": ("Druid", "Shaman"),\n"
    "Druid2": ("Druid", "Oracle"),\n"
}\n"


def resolve_ascendancy(asc_id):\n"
    """Wandelt 'Sorceress1' -> {'class':'Sorceress','ascendancy':'Stormweaver','id':'Sorceress1'}."""\n"
    if not asc_id:\n"
        return {}\n"
    if asc_id in ASCENDANCY_MAP:\n"
        cls, name = ASCENDANCY_MAP[asc_id]\n"
        return {"class": cls, "ascendancy": name, "ascendancy_id": asc_id}\n"
    # Fallback: Klasse aus ID ableiten (Zahl abschneiden)\n"
    cls = re.sub(r"\\d+$", "", asc_id)\n"
    return {"class": cls, "ascendancy": asc_id, "ascendancy_id": asc_id}\n"


# Normalisiert Build-Slot-IDs (z.B. "Weapon1") auf unsere HUD-Slots ("Weapon")\n"
def normalize_slot(inv_id):\n"
    """Weapon1->Weapon, Helm1->Helm, Ring1->Ring, Ring2->Ring2 etc."""\n"
    if not inv_id:\n"
        return None\n"
    mapping = {\n"
        "Weapon1": "Weapon", "Weapon2": "Weapon2",\n"
        "Helm1": "Helm", "BodyArmour1": "BodyArmour",\n"
        "Gloves1": "Gloves", "Boots1": "Boots",\n"
        "Belt1": "Belt", "Amulet1": "Amulet",\n"
        "Ring1": "Ring", "Ring2": "Ring2",\n"
        "Offhand1": "Offhand", "Offhand2": "Offhand2",\n"
    }\n"
    return mapping.get(inv_id, inv_id)\n"


# Gem-Datenbank laden (Name -> Farbe + Typ), aus poe2db extrahiert.\n"
# Liefert die echte Gem-Farbe (blau/grün/rot) statt nur Raten.\n"
GEM_DB = {}\n"
try:\n"
    with open(os.path.join(os.path.dirname(__file__), "gems_db.json"),\n"
              encoding="utf-8") as _f:\n"
        GEM_DB = json.load(_f)\n"
    # auch in Kleinschreibung für robustes Nachschlagen\n"
    GEM_DB_LOWER = {k.lower(): v for k, v in GEM_DB.items()}\n"
except Exception:\n"
    GEM_DB_LOWER = {}\n"


# Stichwort in der Gem-ID -> lesbarer Tag (Element/Typ erkennen)\n"
GEM_TAG_HINTS = {\n"
    "Fire": "🔥 Feuer", "Flame": "🔥 Feuer", "Burn": "🔥 Feuer", "Ember": "🔥 Feuer",\n"
    "Frost": "❄️ Kälte", "Ice": "❄️ Kälte", "Cold": "❄️ Kälte", "Glacial": "❄️ Kälte",\n"
    "Spark": "⚡ Blitz", "Lightning": "⚡ Blitz", "Storm": "⚡ Blitz", "Shock": "⚡ Blitz",\n"
    "Chaos": "☠️ Chaos", "Poison": "☠️ Chaos", "Decay": "☠️ Chaos",\n"
    "Critical": "🎯 Krit", "Dart": "🎲 Projektil", "Projectile": "🎲 Projektil",\n"
    "Arrow": "🏹 Bogen", "Bolt": "🏹 Bogen",\n"
    "Minion": "💀 Diener", "Skeleton": "💀 Diener", "Summon": "💀 Diener",\n"
    "Aura": "✨ Aura", "Herald": "✨ Aura", "Curse": "🌀 Fluch",\n"
    "Melee": "⚔️ Nahkampf", "Strike": "⚔️ Nahkampf", "Slam": "⚔️ Nahkampf",\n"
}\n"


def gem_info_from_id(gem_id):\n"
    """\n"
    Leitet aus der Gem-Metadata-ID alle Infos ab:\n"
    Name, ob Support, und thematische Tags (Element/Typ).\n"
    """\n"
    if not gem_id:\n"
        return None\n"
    raw = gem_id.split("/")[-1]\n"
    is_support = "Support" in raw\n"
    name = raw.replace("SkillGem", "").replace("SupportGem", "").replace("Gem", "")\n"
    name = re.sub(r'(?<!^)(?=[A-Z])', ' ', name).strip()\n"
    name = re.sub(r'\\s+(Two|Three|Four|Five)$',\n"
                  lambda m: " " + {"Two": "II", "Three": "III",\n"
                                   "Four": "IV", "Five": "V"}[m.group(1)], name)\n"
    # Tags aus Stichwoertern in der ID\n"
    tags = []\n"
    for kw, tag in GEM_TAG_HINTS.items():\n"
        if kw in raw and tag not in tags:\n"
            tags.append(tag)\n"

    # Echte Gem-Farbe aus der DB (blau=Int, gruen=Dex, rot=Str)\n"
    color = None\n"
    db_entry = GEM_DB.get(name) or GEM_DB_LOWER.get(name.lower())\n"
    if db_entry:\n"
        color = db_entry.get("color")\n"

    return {\n"
        "name": name,\n"
        "is_support": is_support,\n"
        "tags": tags,\n"
        "color": color,   # "blue" / "green" / "red" / None\n"
    }\n"


def gem_name_from_id(gem_id):\n"
    """Nur der lesbare Name (Kompatibilitaet)."""\n"
    info = gem_info_from_id(gem_id)\n"
    return info["name"] if info else ""\n"


def parse_build_skills(data):\n"
    """Parst die Skill-Gems + Support-Gems aus dem .build.\n"
    Liefert eine Liste: [{skill, level, tags, supports:[{name,tags}]}].\n"
    """\n"
    result = []\n"
    for skill in data.get("skills", []):\n"
        # skills koennen laut GGG-Format Strings ODER Objekte sein\n"
        if isinstance(skill, str):\n"
            skill = {"id": skill}\n"
        elif not isinstance(skill, dict):\n"
            continue\n"
        main = gem_info_from_id(skill.get("id", ""))\n"
        if not main:\n"
            continue\n"
        li = skill.get("level_interval")\n"
        lvl = li[0] if isinstance(li, list) and li else (li if isinstance(li, int) else None)\n"
        supports = []\n"
        for s in skill.get("support_skills", []):\n"
            sid = s.get("id", "") if isinstance(s, dict) else str(s)\n"
            si = gem_info_from_id(sid)\n"
            if si:\n"
                supports.append({"name": si["name"], "tags": si["tags"],\n"
                                 "color": si.get("color")})\n"
        result.append({\n"
            "skill": main["name"],\n"
            "tags": main["tags"],\n"
            "color": main.get("color"),\n"
            "level": lvl,\n"
            "supports": supports,\n"
        })\n"
    return result\n"


def parse_build_consumables(data):\n"
    """Parst Charms + Flasks (Slots mit inventory_id Flask*/Charm*)."""\n"
    flasks, charms = [], []\n"
    for slot in data.get("inventory_slots", []):\n"
        inv = slot.get("inventory_id", "")\n"
        txt = (slot.get("additional_text", "") or slot.get("unique_name", "")).split("\\n")[0]\n"
        if not txt:\n"
            continue\n"
        if inv.startswith("Flask"):\n"
            flasks.append(txt)\n"
        elif inv.startswith("Charm"):\n"
            charms.append(txt)\n"
    return flasks, charms\n"


def parse_build_json(raw):\n"
    """\n"
    Parst eine .build-Datei (JSON aus Mobalytics/PoE2 Build Planner).\n"
    Liefert (gesammelter_item_text, build_info, passive_hints, slot_stats).\n"
    slot_stats = {slot: {stat_key: min_wert}} fuer slot-genaue Trade-Suche.\n"
    """\n"
    data = json.loads(raw)\n"

    # Item-Stats aus allen inventory_slots sammeln\n"
    texts = []\n"
    slot_stats = {}     # pro Slot die gesuchten Stats (wie Mobalytics!)\n"
    slot_uniques = {}   # pro Slot der Unique-Name (falls Unique-Item)\n"
    for slot in data.get("inventory_slots", []):\n"
        sname = normalize_slot(slot.get("inventory_id"))\n"
        # Unique-Item? -> nach Namen suchen statt nach Stats\n"
        uniq = slot.get("unique_name")\n"
        if uniq and sname:\n"
            slot_uniques[sname] = uniq\n"
            continue\n"
        t = slot.get("additional_text", "")\n"
        if t:\n"
            texts.append(t)\n"
            if sname:\n"
                # erste Zeile ist der Item-Name -> die Mods stehen danach\n"
                st = stats_from_mod_text(t)\n"
                if st:\n"
                    slot_stats[sname] = st\n"
    item_text = "\\n".join(texts)\n"

    # Build-Info\n"
    info = {}\n"
    if data.get("name"):   info["name"] = data["name"]\n"
    if data.get("author"): info["author"] = data["author"]\n"
    # Ascendancy-ID in lesbaren Namen + Klasse aufloesen\n"
    asc = resolve_ascendancy(data.get("ascendancy", ""))\n"
    info.update(asc)   # fuegt class, ascendancy (Name), ascendancy_id hinzu\n"

    # Passiv-Baum-Themen zaehlen -> Hinweise auf wichtige Stats\n"
    # WICHTIG: passives koennen laut GGG-Format Strings ODER Objekte sein!\n"
    passive_hints = {}\n"
    for p in data.get("passives", []):\n"
        pid = p.get("id", "") if isinstance(p, dict) else str(p)\n"
        base = re.sub(r"[0-9_]+$", "", pid).lower()\n"
        for theme, stats in PASSIVE_THEME_HINTS.items():\n"
            if theme in base:\n"
                for s in stats:\n"
                    passive_hints[s] = passive_hints.get(s, 0) + 1\n"

    # Skills/Gems + Charms/Flasks parsen\n"
    skills = parse_build_skills(data)\n"
    flasks, charms = parse_build_consumables(data)\n"
    extras = {"skills": skills, "flasks": flasks, "charms": charms}\n"

    return item_text, info, passive_hints, slot_stats, slot_uniques, extras\n"


def _looks_like_build_json(s):\n"
    """Erkennt eine .build JSON-Datei (offizielles GGG-Format, einzeilig moeglich)."""\n"
    s = s.strip()\n"
    if not s.startswith("{"):\n"
        return False\n"
    # Schnell-Check ueber Schluesselwoerter (die .build ist oft auf einer Zeile)\n"
    if any(k in s for k in ("inventory_slots", "passives", "support_skills", "ascendancy")):\n"
        return True\n"
    # Sicherer Fallback: echtes JSON-Parse und nach .build-typischen Keys schauen\n"
    try:\n"
        obj = json.loads(s)\n"
        if isinstance(obj, dict) and any(\n"
            k in obj for k in ("inventory_slots", "passives", "skills", "ascendancy", "name")\n"
        ):\n"
            return True\n"
    except Exception:\n"
        pass\n"
    return False\n"


# ------------------------------------------------------------
#  TRADE-Integration (Weg A: vorausgefuellte Trade-Links)\n"
# ------------------------------------------------------------\n"
# Slot (inventoryId) -> PoE2-Trade Item-Kategorie\n"
SLOT_TRADE_CATEGORY = {\n"
    "Weapon":     "weapon",\n"
    "Weapon2":    "weapon",\n"
    "Offhand":    "armour.shield",\n"
    "Offhand2":   "armour.shield",\n"
    "Helm":       "armour.helmet",\n"
    "BodyArmour": "armour.chest",\n"
    "Gloves":     "armour.gloves",\n"
    "Boots":      "armour.boots",\n"
    "Belt":       "accessory.belt",\n"
    "Amulet":     "accessory.amulet",\n"
    "Ring":       "accessory.ring",\n"
    "Ring2":      "accessory.ring",\n"
}\n"


# Bekannte PoE2-Trade Stat-IDs (explicit) fuer die Auto-Filter.\n"
# Quelle: ECHTE Trade-Links (vom User verifiziert!).\n"
TRADE_STAT_IDS = {\n"
    "life":             "explicit.stat_3299347043",   # +# to maximum Life  [verifiziert]\n"
    "mana":             "explicit.stat_1050105434",   # +# to maximum Mana  [verifiziert]\n"
    "energy_shield":    "explicit.stat_4052037485",   # +# to maximum Energy Shield  [verifiziert]\n"
    "spirit":           "explicit.stat_2704225257",   # +# to Spirit  [verifiziert]\n"
    "spell_damage":     "explicit.stat_2974417149",   # #% increased Spell Damage  [verifiziert]\n"
    "spell_skills":     "explicit.stat_124131830",    # +# to Level of all Spell Skills  [verifiziert]\n"
    "movement_speed":   "explicit.stat_2250533757",   # #% increased Movement Speed  [verifiziert]\n"
    "chaos_res":        "explicit.stat_2923486259",   # +#% to Chaos Resistance  [verifiziert]\n"
    "eva_es":           "explicit.stat_1999113824",   # #% increased Evasion and Energy Shield  [verifiziert]\n"
    "crit_dmg_bonus":   "explicit.stat_3556824919",   # #% increased Critical Damage Bonus  [verifiziert]\n"
    # Armour ist ein LOKALER Defense-Stat -> braucht die (Local)-ID!\n"
    # Ohne (Local) findet die Suche KEINE Items (haeufiger Fehler, auch bei Mobalytics).\n"
    "armour":           "explicit.stat_3484657501",   # #% increased Armour (Local)\n"
    # Resistenzen am besten ueber pseudo-total (egal welche Resi)\n"
    "ele_res":          "pseudo.pseudo_total_elemental_resistance",  # [verifiziert]\n"
}\n"

# Mapping: Regex (Zahl direkt am Stat) -> Stat-Key.\n"
# So erkennen wir aus dem Build-Item den Stat UND den Mindestwert.\n"
# Reihenfolge wichtig: spezifischere Muster (eva_es) VOR allgemeineren (energy_shield)!\n"
MOD_TO_STAT = [\n"
    (r"(\\d+)%?\\s+(?:erh[öo]hter\\s+Zauberschaden|increased\\s+Spell\\s+Damage)",       "spell_damage"),\n"
    (r"\\+?(\\d+)\\s+(?:zu\\s+Stufen?\\s+aller\\s+Zauberfertigkeiten|to\\s+Level\\s+of\\s+all\\s+Spell\\s+Skills)", "spell_skills"),\n"
    (r"(\\d+)%?\\s+(?:erh[öo]hte\\s+Bewegungsgeschwindigkeit|erhoehte\\s+Bewegungsgeschwindigkeit|increased\\s+Movement\\s+Speed)", "movement_speed"),\n"
    # "... und Energieschild" ZUERST (sonst greift Energieschild allein davor)\n"
    (r"(\\d+)%?\\s+(?:erh[öo]hte\\s+Ausweich\\w*\\s+und\\s+Energieschild|increased\\s+Evasion\\s+and\\s+Energy\\s+Shield)", "eva_es"),\n"
    (r"(\\d+)%?\\s+(?:erh[öo]hter\\s+kritischer\\s+Schadensbonus|increased\\s+Critical\\s+Damage\\s+Bonus)", "crit_dmg_bonus"),\n"
    (r"(\\d+)%?\\s+(?:erh[öo]hte\\s+kritische\\s+Trefferchance|increased\\s+Critical\\s+Hit\\s+Chance)", "crit_dmg_bonus"),\n"
    (r"(\\d+)%?\\s+(?:erh[öo]hte\\s+R[üu]stung|erhoehte\\s+Ruestung|increased\\s+Armour)",                   "armour"),\n"
    (r"\\+?(\\d+)\\s+(?:zu\\s+maximalem\\s+Leben|to\\s+(?:maximum\\s+)?Life)",             "life"),\n"
    (r"\\+?(\\d+)\\s+(?:zu\\s+maximalem\\s+Mana|to\\s+(?:maximum\\s+)?Mana)",              "mana"),\n"
    (r"\\+?(\\d+)\\s+(?:zu\\s+maximalem\\s+Energieschild|to\\s+(?:maximum\\s+)?Energy\\s+Shield)", "energy_shield"),\n"
    (r"\\+?(\\d+)\\s+(?:zu\\s+Wille|to\\s+Spirit)",                                      "spirit"),\n"
    # Chaos-Res separat (eigene Trade-ID), andere Resis -> pseudo total\n"
    (r"\\+?(\\d+)%?\\s+(?:zu\\s+Chaoswiderstand|to\\s+Chaos\\s+Resistance)",              "chaos_res"),\n"
    (r"\\+?(\\d+)%?\\s+(?:zu\\s+Feuerwiderstand|zu\\s+K[äa]ltewiderstand|zu\\s+Blitzwiderstand|zu\\s+allen\\s+Elementarwiderst\\w*|to\\s+(?:Fire|Cold|Lightning|all\\s+Elemental)\\s+Resistance)", "ele_res"),\n"
]\n"


def stats_from_mod_text(text):\n"
    """\n"
    Aus einem Item-Mod-Text (z.B. '+10% to Lightning Resistance\\n14% increased Armour')\n"
    die gesuchten {stat_key: min_wert} ableiten - wie Mobalytics es pro Slot macht.\n"
    Zieht den EXAKTEN Mindestwert aus dem Mod.\n"
    """\n"
    text = clean_item_text(text)\n"
    found = {}\n"
    for pattern, key in MOD_TO_STAT:\n"
        for m in re.finditer(pattern, text, re.IGNORECASE):\n"
            try:\n"
                val = int(m.group(1))\n"
            except (ValueError, IndexError):\n"
                continue\n"
            if key == "ele_res":\n"
                found[key] = found.get(key, 0) + val   # Resis summieren\n"
            else:\n"
                found[key] = val                       # exakter Wert\n"
    return found\n"


@app.route("/api/trade-link", methods=["GET", "POST"])\n"
def api_trade_link():
    """\n"
    Baut einen vorausgefuellten PoE2-Trade-Such-Link fuer einen Slot.\n"
    KORREKTES Format (aus echtem Link verifiziert):\n"
      https://www.pathofexile.com/trade2/search/<Liga>?q=<JSON>\n"

    Sucht SLOT-GENAU: pro Slot genau die Stats, die im Build auf\n"
    diesem Item-Slot stehen (wie Mobalytics) - nicht die globale Gewichtung.\n"

    POST-Body (JSON): {slot, league, stats: {stat_key: min_wert}}\n"
    """\n"
    if request.method == "POST":\n"
        body = request.get_json(silent=True) or {}\n"
        slot = (body.get("slot") or "").strip()\n"
        league = (body.get("league") or "Standard").strip() or "Standard"\n"
        want = body.get("stats") or {}            # {stat_key: min_wert}\n"
        unique_name = (body.get("unique_name") or "").strip()\n"
        trade_status = (body.get("trade_status") or "any").strip()\n"
        tolerance = body.get("tolerance", 0)      # +-% Toleranz auf Min-Werte\n"
    else:\n"
        slot = request.args.get("slot", "").strip()\n"
        league = request.args.get("league", "Standard").strip() or "Standard"\n"
        sp = request.args.get("stats", "").strip()\n"
        want = {k: None for k in sp.split(",") if k} if sp else {}\n"
        unique_name = request.args.get("unique_name", "").strip()\n"
        trade_status = request.args.get("trade_status", "any").strip()\n"
        tolerance = 0\n"

    # Handelsstatus: "online" (sofort kaufbar), "onlineleague", "any"\n"
    status_map = {\n"
        "buyout": "online",       # nur sofort kaufbar (Buyout)\n"
        "online": "online",\n"
        "any": "any",\n"
    }\n"
    status_option = status_map.get(trade_status, "any")\n"

    # Toleranz: senkt die Min-Werte um X% (mehr Treffer, z.B. -15%)\n"
    try:\n"
        tol = max(0, min(50, float(tolerance))) / 100.0\n"
    except (ValueError, TypeError):\n"
        tol = 0.0\n"

    category = SLOT_TRADE_CATEGORY.get(slot)\n"

    query = {\n"
        "query": {\n"
            "status": {"option": status_option},\n"
            "stats": [{"type": "and", "filters": []}],\n"
        },\n"
        "sort": {"price": "asc"},\n"
    }\n"

    applied = []\n"

    if unique_name:\n"
        # --- Unique-Item: nach Namen + Rarity suchen ---\n"
        query["query"]["name"] = unique_name\n"
        query["query"]["filters"] = {\n"
            "type_filters": {"filters": {"rarity": {"option": "unique"}}}\n"
        }\n"
        applied = ["unique:" + unique_name]\n"
    else:\n"
        # --- Rare/Magic: nach Kategorie + Stats suchen ---\n"
        stat_filters = []\n"
        for key, minval in want.items():\n"
            sid = TRADE_STAT_IDS.get(key)\n"
            if not sid:\n"
                continue\n"
            f = {"id": sid, "disabled": False}\n"
            if minval is not None:\n"
                try:\n"
                    # Toleranz abziehen (z.B. -15% -> mehr Treffer)\n"
                    mv = float(minval) * (1.0 - tol)\n"
                    f["value"] = {"min": int(mv)}\n"
                except (ValueError, TypeError):\n"
                    pass\n"
            stat_filters.append(f)\n"
            applied.append(key)\n"
        query["query"]["stats"] = [{"type": "and", "filters": stat_filters}]\n"
        if category:\n"
            query["query"]["filters"] = {\n"
                "type_filters": {"filters": {"category": {"option": category}}}\n"
            }\n"

    q = urllib.parse.quote(json.dumps(query))\n"
    # WICHTIG: Pfad ist /trade2/search/<Liga>  (NICHT /poe2/<Liga> !)\n"
    url = f"https://www.pathofexile.com/trade2/search/{urllib.parse.quote(league)}?q={q}"\n"

    return jsonify({\n"
        "url": url,\n"
        "category": category,\n"
        "slot": slot,\n"
        "applied_stats": applied,\n"
        "is_unique": bool(unique_name),\n"
    })\n"


# ------------------------------------------------------------
#  Start
# ------------------------------------------------------------\n"
if __name__ == "__main__":\n"
    # Port + Debug aus Umgebung (Hosting-Anbieter geben PORT vor)\n"
    port = int(os.getenv("PORT", "8000"))\n"
    debug = os.getenv("FLASK_DEBUG", "1") == "1"   # in Produktion FLASK_DEBUG=0 setzen!\n"
    print("=" * 50)\n"
    print(f"  Exile Eye Navigator startet auf Port {port}")\n"
    print(f"  Login: /login   Realm: {REALM}   Debug: {debug}")\n"
    print("=" * 50)\n"
    app.run(host="0.0.0.0", port=port, debug=debug)\n"
```
