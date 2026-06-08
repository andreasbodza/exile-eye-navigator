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
#   OAuth {clientId}/{version} (contact: {mail})
# Wird hier automatisch aus Client ID + Contact zusammengebaut.
USER_AGENT   = f"OAuth {CLIENT_ID}/{APP_VERSION} (contact: {CONTACT})"

# Tesseract-Pfad aus der .env (Windows) - bis zur .exe!
TESSERACT_PATH = os.getenv(
    "TESSERACT_PATH",
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
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
    # Service Worker muss aus dem Root kommen (sonst greift der scope nicht)
    resp = send_from_directory(".", "sw.js", mimetype="application/javascript")
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp

@app.route("/icons/<path:filename>")
def icons(filename):
    return send_from_directory("icons", filename)


# ------------------------------------------------------------
#  Routen: OAuth Login-Flow
# ------------------------------------------------------------
@app.route("/login")
def login():
    verifier, challenge = make_pkce_pair()
    state = secrets.token_urlsafe(24)

    # EINHEITLICHE Keys! (das war einer der alten Bugs:
    # mal 'oauth_code_verifier', mal 'oauth_verifier')
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

    # GLEICHER Key wie in /login!
    verifier = session.get("oauth_code_verifier")
    if not code or not verifier:
        return redirect(url_for("index") + "?error=missing_code_or_verifier")

    # Token-Austausch (PKCE: client_secret NICHT noetig bei Public Client)
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
# Einfacher In-Memory-Cache: {cache_key: (zeitpunkt, daten)}
# Spart GGG-Anfragen (jeder Klick fragt nicht neu) -> schont das Rate-Limit.
_API_CACHE = {}
CACHE_TTL = 60          # Sekunden, wie lange Daten "frisch" sind
_CACHE_MAX = 500        # max. Eintraege (gegen Speicher-Voll-Laufen)


def _cache_get(key):
    entry = _API_CACHE.get(key)
    if entry and (time.time() - entry[0]) < CACHE_TTL:
        return entry[1]
    return None


def _cache_set(key, data):
    if len(_API_CACHE) > _CACHE_MAX:
        # aelteste Haelfte rauswerfen (simpel, reicht hier)
        for k in list(_API_CACHE.keys())[: _CACHE_MAX // 2]:
            _API_CACHE.pop(k, None)
    _API_CACHE[key] = (time.time(), data)


def api_get(path, use_cache=True):
    """
    GET gegen api.pathofexile.com mit Bearer-Token + User-Agent.
    - nutzt Caching (schont das GGG-Rate-Limit)
    - respektiert das Rate-Limit (wartet bei 429 die Retry-After-Zeit ab)
    """
    token = session.get("access_token")
    if not token:
        return None, 401, "not_logged_in"

    # pro Account + Pfad cachen (jeder Nutzer hat eigene Daten)
    cache_key = f"{token[:12]}:{path}"
    if use_cache:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached, 200, None

    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent":    USER_AGENT,
    }
    url = f"{API_BASE}{path}"

    # bis zu 2 Versuche (1x normal + 1x nach Rate-Limit-Wartezeit)
    for attempt in range(2):
        try:
            r = requests.get(url, headers=headers, timeout=20)
        except requests.RequestException as e:
            return None, 0, str(e)

        # Rate-Limit-Header auswerten (zum Mitloggen, wie nah wir am Limit sind)
        _log_rate_limit(r, path)

        # 429 = zu viele Anfragen -> warten und EINMAL erneut versuchen
        if r.status_code == 429:
            retry = int(r.headers.get("Retry-After", "5"))
            retry = min(retry, 15)   # nie ewig blockieren
            print(f"[RATE-LIMIT] 429 bei {path} -> warte {retry}s")
            if attempt == 0:
                time.sleep(retry)
                continue
            return None, 429, f"rate_limited_retry_after_{retry}"

        if r.status_code != 200:
            return None, r.status_code, r.text[:300]

        try:
            data = r.json()
        except ValueError:
            return None, r.status_code, "invalid_json"

        if use_cache:
            _cache_set(cache_key, data)
        return data, 200, None

    return None, 429, "rate_limited"


def _log_rate_limit(resp, path):
    """Loggt, wie nah wir am GGG-Rate-Limit sind (zur Kontrolle)."""
    state = resp.headers.get("X-Rate-Limit-Account-State") or \
            resp.headers.get("X-Rate-Limit-Client-State") or \
            resp.headers.get("X-Rate-Limit-Ip-State")
    rules = resp.headers.get("X-Rate-Limit-Account") or \
            resp.headers.get("X-Rate-Limit-Client") or \
            resp.headers.get("X-Rate-Limit-Ip")
    if state and rules:
        try:
            hits = int(state.split(":")[0])
            maxhits = int(rules.split(":")[0])
            # Warnung, wenn wir ueber 70% des Limits sind
            if maxhits and hits / maxhits > 0.7:
                print(f"[RATE-LIMIT] {path}: {hits}/{maxhits} (achtung, nah am Limit)")
        except (ValueError, IndexError):
            pass


# ------------------------------------------------------------
#  Routen: Auth-Status + Charakter-Daten
# ------------------------------------------------------------
@app.route("/api/status")
def api_status():
    """Sagt dem Frontend, ob eingeloggt + welcher Account."""
    if not session.get("access_token"):
        return jsonify({"logged_in": False})

    profile, code, err = api_get("/profile")
    if code != 200:
        return jsonify({"logged_in": False, "error": err, "code": code})

    return jsonify({
        "logged_in": True,
        "account": profile.get("name"),
    })


@app.route("/api/characters")
def api_characters():
    """
    Liste aller PoE2-Charaktere des eingeloggten Accounts.

    DER KERN-FIX: Der korrekte Endpunkt ist
        GET https://api.pathofexile.com/character/poe2
    (Realm steckt IM Pfad, nicht als ?realm= Query!)
    Ohne /poe2 bekommst du nur PoE1-Chars -> leere Liste bei reinen
    PoE2-Spielern. Genau das war euer "keine Charaktere"-Problem.
    """
    path = f"/character/{REALM}" if REALM and REALM != "pc" else "/character"
    data, code, err = api_get(path)

    print(f"[CHARS] GET {path} -> {code}")
    if code != 200:
        print(f"[CHARS] Fehler-Body: {err}")
        return jsonify({"error": err, "code": code, "characters": []}), code

    chars = data.get("characters", [])
    print(f"[CHARS] Gefunden: {len(chars)} Charaktere")

    # Nur die fuers HUD relevanten Felder ans Frontend
    slim = [{
        "name":   c.get("name"),
        "class":  c.get("class"),
        "level":  c.get("level"),
        "league": c.get("league"),
    } for c in chars]

    return jsonify({"characters": slim})


@app.route("/api/character-gear")
def api_character_gear():
    """
    Ausruestung EINES Charakters.

    DER KERN-FIX (Teil 2): Items kommen ueber
        GET https://api.pathofexile.com/character/poe2/<name>
    Die Antwort enthaelt character.equipment (Liste von Items).
    Jedes Item hat 'inventoryId' (= Slot, z.B. 'Helm', 'BodyArmour').
    """
    name = request.args.get("name", "").strip()
    if not name:
        return jsonify({"error": "kein_charaktername", "items": []}), 400

    enc_name = urllib.parse.quote(name)
    if REALM and REALM != "pc":
        path = f"/character/{REALM}/{enc_name}"
    else:
        path = f"/character/{enc_name}"

    data, code, err = api_get(path)
    print(f"[GEAR] GET {path} -> {code}")
    if code != 200:
        print(f"[GEAR] Fehler-Body: {err}")
        return jsonify({"error": err, "code": code, "items": []}), code

    character = data.get("character", {})
    equipment = character.get("equipment", [])
    print(f"[GEAR] {name}: {len(equipment)} ausgeruestete Items")

    items = []
    for it in equipment:
        # --- Mods nach Typ getrennt sammeln (fuer schoene Anzeige) ---
        implicit = it.get("implicitMods", []) or []
        enchant  = it.get("enchantMods", []) or []
        rune     = it.get("runeMods", []) or []        # PoE2: Runen
        explicit = it.get("explicitMods", []) or []
        crafted  = it.get("craftedMods", []) or []
        fractured = it.get("fracturedMods", []) or []

        # alle Mods zusammen (fuer Score-Berechnung)
        all_mods = implicit + enchant + rune + explicit + crafted + fractured

        # Einzelstats parsen (fuer Alt/Neu-Vergleich Stat-fuer-Stat)
        parsed = parse_item_stats("\n".join(all_mods))

        # --- Eigenschaften (Schaden, Ruestung, Krit etc.) ---
        props = []
        for p in (it.get("properties", []) or []):
            vals = p.get("values", [])
            val_str = vals[0][0] if vals and vals[0] else ""
            props.append({"name": p.get("name", ""), "value": val_str})

        # --- Anforderungen (Level, Attribute) ---
        reqs = []
        for r in (it.get("requirements", []) or []):
            vals = r.get("values", [])
            val_str = vals[0][0] if vals and vals[0] else ""
            reqs.append({"name": r.get("name", ""), "value": val_str})

        # --- Raritaet bestimmen (frameTypeId neu, frameType alt) ---
        rarity_map = {"Normal": 0, "Magic": 1, "Rare": 2, "Unique": 3}
        rarity = rarity_map.get(it.get("rarity"),
                                it.get("frameType", 0))

        items.append({
            "slot":     it.get("inventoryId"),   # z.B. Helm, BodyArmour, Weapon
            "name":     it.get("name", ""),
            "typeLine": it.get("typeLine", ""),
            "baseType": it.get("baseType", ""),
            "icon":     it.get("icon", ""),      # <-- echtes Item-Bild!
            "ilvl":     it.get("ilvl"),
            "rarity":   rarity,
            "corrupted": bool(it.get("corrupted")),
            "properties":   props,
            "requirements": reqs,
            "mods": {
                "implicit":  implicit,
                "enchant":   enchant,
                "rune":      rune,
                "explicit":  explicit,
                "crafted":   crafted,
                "fractured": fractured,
            },
            "all_mods": all_mods,                # fuer Score
            "parsed_stats": parsed,              # einzelne Werte fuer Vergleich
        })


    return jsonify({
        "character": {
            "name":  character.get("name"),
            "class": character.get("class"),
            "level": character.get("level"),
        },
        "items": items,
    })


# ------------------------------------------------------------
#  Auto-Tooltip-Erkennung (OpenCV) – findet den dunklen Item-Bereich
# ------------------------------------------------------------
def auto_crop_tooltip(pil_img):
    """
    Findet den dunklen Item-Tooltip im Foto und schneidet ihn zu.
    Gibt (zugeschnittenes_PIL_Bild, gefunden?) zurueck.
    PoE-Tooltips sind sehr dunkel -> als grosse dunkle Flaeche erkennbar.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        return pil_img, False

    try:
        rgb = pil_img.convert("RGB")
        arr = np.array(rgb)[:, :, ::-1].copy()
        H, W = arr.shape[:2]
        gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)

        # dunkle Bereiche maskieren (Tooltip-Hintergrund ist fast schwarz)
        _, dark = cv2.threshold(gray, 45, 255, cv2.THRESH_BINARY_INV)
        # benachbarte dunkle Flaechen verbinden
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25))
        dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, kernel)

        cnts, _ = cv2.findContours(dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best, best_area = None, 0
        for c in cnts:
            x, y, w, h = cv2.boundingRect(c)
            area = w * h
            # plausible Tooltip-Groesse: nicht winzig, nicht fast ganzes Bild
            if (area > best_area and area > 12000 and w > 100 and h > 70
                    and area < 0.9 * W * H):
                best_area, best = area, (x, y, w, h)

        if best:
            x, y, w, h = best
            # kleinen Rand zugeben (Schrift am Rand nicht abschneiden)
            pad = 8
            x = max(0, x - pad); y = max(0, y - pad)
            w = min(W - x, w + 2 * pad); h = min(H - y, h + 2 * pad)
            cropped = pil_img.crop((x, y, x + w, y + h))
            return cropped, True
    except Exception:
        pass
    return pil_img, False


# ------------------------------------------------------------
#  OCR-Bildaufbereitung (OpenCV) + Mehrfach-Strategie
# ------------------------------------------------------------
def ocr_best_effort(pil_img, pytesseract, ocr_lang="deu+eng"):
    """
    Versucht mehrere Bildaufbereitungen und gibt den besten OCR-Text zurueck.
    ocr_lang: Tesseract-Sprache je nach Spiel-Sprache des Users.
    Nutzt OpenCV falls verfuegbar (viel besser bei Fotos), sonst Pillow-Fallback.
    """
    from PIL import Image, ImageOps, ImageFilter

    candidates = []   # Liste von (PIL-Bild, tesseract-config)

    # --- Versuch mit OpenCV (beste Qualitaet bei Fotos) ---
    try:
        import cv2
        import numpy as np

        rgb = pil_img.convert("RGB")
        arr = np.array(rgb)[:, :, ::-1].copy()   # RGB -> BGR fuer cv2
        gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)

        # hochskalieren (OCR mag grosse Schrift)
        h, w = gray.shape
        if max(h, w) < 1800:
            scale = 1800 / max(h, w)
            gray = cv2.resize(gray, (int(w * scale), int(h * scale)),
                              interpolation=cv2.INTER_CUBIC)

        # Rauschen reduzieren
        denoised = cv2.bilateralFilter(gray, 9, 75, 75)

        # Variante 1: Otsu-Threshold (gut bei gleichmaessigem Hintergrund)
        _, otsu = cv2.threshold(denoised, 0, 255,
                                cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        # PoE = heller Text auf dunkel -> Otsu macht Text schwarz auf weiss = passt
        candidates.append((Image.fromarray(otsu), "--psm 6"))
        candidates.append((Image.fromarray(255 - otsu), "--psm 6"))  # invertiert

        # Variante 2: adaptiver Threshold (gut bei ungleichmaessiger Beleuchtung/Fotos)
        adaptive = cv2.adaptiveThreshold(
            denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 31, 11)
        candidates.append((Image.fromarray(adaptive), "--psm 6"))
        candidates.append((Image.fromarray(255 - adaptive), "--psm 6"))

    except ImportError:
        pass  # kein OpenCV -> Pillow-Fallback unten

    # --- Pillow-Fallback / Zusatz-Varianten ---
    try:
        g = pil_img.convert("L")
        w, h = g.size
        if max(w, h) < 1800:
            s = 1800 / max(w, h)
            g = g.resize((int(w * s), int(h * s)))
        inv = ImageOps.autocontrast(ImageOps.invert(g)).filter(ImageFilter.SHARPEN)
        candidates.append((inv, "--psm 6"))
        candidates.append((ImageOps.autocontrast(g), "--psm 6"))
    except Exception:
        candidates.append((pil_img, "--psm 6"))

    # --- alle Kandidaten durch Tesseract jagen, besten nehmen ---
    best_text = ""
    best_score = -1
    for cand_img, cfg in candidates:
        try:
            # gewaehlte Sprache (z.B. "deu+eng" oder "eng")
            # Fallback auf eng, falls das Sprachpaket nicht installiert ist
            try:
                t = pytesseract.image_to_string(cand_img, lang=ocr_lang, config=cfg)
            except Exception:
                t = pytesseract.image_to_string(cand_img, lang="eng", config=cfg)
        except Exception:
            continue
        # "Güte" = wie viele relevante Stat-Schluesselwoerter gefunden wurden
        score = _ocr_quality(t)
        if score > best_score:
            best_score, best_text = score, t

    return best_text


def _ocr_quality(text):
    """Bewertet OCR-Text: mehr erkannte Zahlen + Stat-Woerter = besser."""
    if not text:
        return 0
    low = text.lower()
    score = 0
    score += len(re.findall(r"\d+", text)) * 2          # Zahlen sind Gold
    # Schluesselwoerter Deutsch + Englisch
    for kw in ["life", "mana", "resist", "armour", "energy", "damage",
               "critical", "movement", "spirit", "level",
               "leben", "widerstand", "energieschild", "rüstung", "ruestung",
               "schaden", "kritische", "bewegungs", "geschwindigkeit", "stufe"]:
        score += low.count(kw) * 3
    score += len([c for c in text if c.isalnum()]) // 20  # Textmenge leicht gewichten
    return score


# ------------------------------------------------------------
#  Routen: OCR-Analyse eines hochgeladenen Item-Fotos
# ------------------------------------------------------------
@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """
    Nimmt ein (zugeschnittenes) Item-Foto entgegen, jagt es durch
    Tesseract, parst die Stats und gibt einen Score zurueck.
    """
    if "image" not in request.files:
        return jsonify({"error": "kein_bild"}), 400

    try:
        import pytesseract
        from PIL import Image, ImageOps, ImageFilter
    except ImportError:
        return jsonify({
            "error": "ocr_libs_fehlen",
            "detail": "pip install pillow pytesseract"
        }), 500

    # iPhone-Fotos sind oft HEIC/HEIF -> Pillow kann das nur mit pillow-heif.
    # Wenn installiert, registrieren wir den Decoder (sonst stiller Fallback).
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except ImportError:
        pass  # HEIC geht dann nicht, JPG/PNG aber schon

    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

    file = request.files["image"]
    try:
        img = Image.open(file.stream)
        # EXIF-Rotation vom Handy korrigieren (sonst steht das Bild quer)
        img = ImageOps.exif_transpose(img)
    except Exception as e:
        return jsonify({
            "error": "bild_unlesbar",
            "detail": str(e),
            "hint": "iPhone-Foto? Dann 'pip install pillow-heif' ausführen, "
                    "oder am iPhone unter Einstellungen > Kamera > Formate "
                    "auf 'Maximale Kompatibilität' (JPG) stellen."
        }), 400

    # Auto-Crop: dunklen Item-Tooltip automatisch finden & zuschneiden
    # (kann das Frontend per autocrop=0 abschalten, dann manueller Rahmen)
    autocrop = request.form.get("autocrop", "1") != "0"
    cropped_flag = False
    if autocrop:
        img, cropped_flag = auto_crop_tooltip(img)

    # OCR-Sprache je nach Spiel-Sprache: "de", "en" oder "auto" (=beide)
    game_lang = request.form.get("game_lang", "auto")
    lang_map = {"de": "deu+eng", "en": "eng", "auto": "deu+eng"}
    ocr_lang = lang_map.get(game_lang, "deu+eng")

    # OCR mit mehreren Strategien versuchen, beste Ausbeute gewinnt
    text = ocr_best_effort(img, pytesseract, ocr_lang)
    if not text or len(text.strip()) < 3:
        return jsonify({
            "error": "nichts_erkannt",
            "detail": "Es konnte kein Text gelesen werden.",
            "hint": "Tipp: Tooltip näher/schärfer fotografieren, gut beleuchten, "
                    "und mit dem Zuschnitt-Rahmen genau auf den Item-Text ziehen."
        }), 200  # 200, damit Frontend den Hinweis sauber anzeigt

    stats = parse_item_stats(text)

    # optionale Custom-Gewichtung vom Frontend (Regler/Build-Import)
    custom_weights = None
    try:
        import json as _json
        cw = request.form.get("weights")
        if cw:
            custom_weights = _json.loads(cw)
    except Exception:
        custom_weights = None

    score = compute_score(stats, custom_weights)
    guessed_slot = guess_slot(text)

    return jsonify({
        "raw_text": text,
        "stats": stats,
        "score": score,
        "guessed_slot": guessed_slot,
        "auto_cropped": cropped_flag,   # wurde der Tooltip automatisch gefunden?
    })


# ------------------------------------------------------------
#  Slot-Erkennung aus OCR-Text (Auto-Vorschlag)
# ------------------------------------------------------------
# Stichwoerter pro Slot - wird im OCR-Text gesucht.
# Slot-Stichwoerter Deutsch + Englisch (deutsches Spiel = deutsche Item-Namen)
SLOT_KEYWORDS = {
    "Helm":       ["helm", "helmet", "crown", "mask", "hood", "circlet", "burgonet", "greathelm",
                   "haube", "krone", "maske", "kapuze", "diadem", "sturmhaube"],
    "BodyArmour": ["plate", "armour", "vest", "garb", "robe", "tunic", "jacket", "wraps", "brigandine", "carapace",
                   "rüstung", "ruestung", "plattenrüstung", "plattenruestung", "robe", "weste", "panzer", "wams", "kürass", "kuerass"],
    "Gloves":     ["gloves", "mitts", "gauntlets", "grips",
                   "handschuhe", "fäustlinge", "faeustlinge", "panzerhandschuhe", "griffe"],
    "Boots":      ["boots", "greaves", "sandals", "shoes", "slippers",
                   "stiefel", "sandalen", "beinschienen", "schuhe", "schläppchen", "schlaeppchen", "treter"],
    "Belt":       ["belt", "sash", "braid", "girdle",
                   "gürtel", "guertel", "schärpe", "schaerpe", "band"],
    "Amulet":     ["amulet", "necklace", "talisman", "pendant",
                   "amulett", "halskette", "talisman", "anhänger", "anhaenger"],
    "Ring":       ["ring", "band", "coil", "loop",
                   "ring", "reif", "schleife"],
    "Weapon":     ["staff", "wand", "sword", "axe", "mace", "bow", "dagger", "sceptre", "claw", "spear", "quarterstaff", "crossbow",
                   "stab", "zauberstab", "schwert", "axt", "streitkolben", "bogen", "dolch", "zepter", "klaue", "speer", "armbrust"],
    "Offhand":    ["shield", "buckler", "quiver", "focus",
                   "schild", "tartsche", "köcher", "koecher", "fokus", "buckler", "turmschild"],
}


def guess_slot(text):
    """Raet aus dem (DE/EN) Item-Text den Slot - nutzt stats_dict."""
    return dict_guess_slot(text)



# ------------------------------------------------------------
#  Stat-Parsing + Score-Berechnung
# ------------------------------------------------------------
import re

# Gewichte fuer den Score - hier kannst du spaeter tunen
STAT_WEIGHTS = {
    "life":            1.0,
    "mana":            0.3,
    "fire_res":        0.8,
    "cold_res":        0.8,
    "lightning_res":   0.8,
    "chaos_res":       1.0,
    "all_res":         1.0,
    "energy_shield":   0.6,
    "crit_chance":     0.5,
    "spell_damage":    0.5,
    "movement_speed":  0.4,
    "armour":          0.4,
}

# Stat-Patterns: erkennen BEIDE Sprachen (Deutsch + Englisch).
# Deutsch ist Standard bei deutschem Spiel-Client.
STAT_PATTERNS = {
    # Leben: "zu maximalem Leben" / "to maximum Life"
    "life":           r"\+?(\d+)\s+(?:zu\s+maximalem\s+Leben|to\s+(?:maximum\s+)?Life)",
    # Mana
    "mana":           r"\+?(\d+)\s+(?:zu\s+maximalem\s+Mana|to\s+(?:maximum\s+)?Mana)",
    # Resistenzen (deutsch: "...widerstand", englisch: "... Resistance")
    "fire_res":       r"\+?(\d+)%?\s+(?:zu\s+Feuerwiderstand|to\s+Fire\s+Resistance)",
    "cold_res":       r"\+?(\d+)%?\s+(?:zu\s+Kältewiderstand|zu\s+Kaeltewiderstand|to\s+Cold\s+Resistance)",
    "lightning_res":  r"\+?(\d+)%?\s+(?:zu\s+Blitzwiderstand|to\s+Lightning\s+Resistance)",
    "chaos_res":      r"\+?(\d+)%?\s+(?:zu\s+Chaoswiderstand|to\s+Chaos\s+Resistance)",
    # alle Elementarwiderstände: "zu allen Elementarwiderständen" / "to all Elemental Resistances"
    "all_res":        r"\+?(\d+)%?\s+(?:zu\s+allen\s+Elementarwiderständen|zu\s+allen\s+Elementarwiderstaenden|to\s+all\s+Elemental\s+Resistances)",
    # Energieschild: "maximalem Energieschild" / "increased Energieschild" / EN
    "energy_shield":  r"(\d+)%?\s+(?:zu\s+maximalem\s+Energieschild|erhöhter\s+Energieschild|erhoehter\s+Energieschild|to\s+(?:maximum\s+)?Energy\s+Shield|increased\s+Energy\s+Shield)(?!.*Wiederaufladung)(?!\s+Recharge)",
    # Krit: "kritischer Trefferchance" / "Critical"
    "crit_chance":    r"(\d+(?:[.,]\d+)?)%\s+(?:erhöhte\s+kritische|erhoehte\s+kritische|.*?kritischer\s+Treffer|(?:to\s+|increased\s+)?Critical)",
    # Zauberschaden: "erhöhter Zauberschaden" / "increased Spell Damage"
    "spell_damage":   r"(\d+)%\s+(?:erhöhter\s+Zauberschaden|erhoehter\s+Zauberschaden|increased\s+Spell\s+Damage)",
    # Bewegungsgeschwindigkeit: "Bewegungsgeschwindigkeit" / "Movement Speed"
    "movement_speed": r"(\d+)%\s+(?:erhöhte\s+Bewegungsgeschwindigkeit|erhoehte\s+Bewegungsgeschwindigkeit|increased\s+Movement\s+Speed)",
    # Rüstung: "erhöhte Rüstung" / "increased Armour"
    "armour":         r"(\d+)%\s+(?:erhöhte\s+Rüstung|erhoehte\s+Ruestung|increased\s+Armour)",
}


def clean_item_text(text):
    """Entfernt GGG-Tags [Tag|Anzeige] -> Anzeige (nutzt stats_dict)."""
    return dict_clean_text(text)


def parse_item_stats(text):
    """Zieht numerische Stats aus Item-/OCR-Text (DE + EN).
    Nutzt das umfassende Woerterbuch aus stats_dict.py."""
    return dict_parse_stats(text)


def _unused_old_parse(text):
    """(alt, nicht mehr genutzt - durch stats_dict ersetzt)"""
    text = clean_item_text(text)
    stats = {}
    for key, pattern in STAT_PATTERNS.items():
        total = 0.0
        found = False
        for m in re.finditer(pattern, text, re.IGNORECASE):
            try:
                total += float(m.group(1))
                found = True
            except (ValueError, IndexError):
                pass
        if found:
            stats[key] = round(total, 1)
    return stats


def compute_score(stats, weights=None):
    """Gewichteter Score. weights kann eine Custom-Gewichtung sein
    (vom Regler oder Build-Import), sonst Standard STAT_WEIGHTS."""
    w = weights if weights else STAT_WEIGHTS
    score = 0.0
    for key, value in stats.items():
        try:
            score += float(value) * float(w.get(key, 0.0))
        except (TypeError, ValueError):
            pass
    return round(score, 1)


# ============================================================
#  BUILD-IMPORT (Path of Building)
#  Liest einen PoB-Code oder pobb.in-Link und leitet daraus
#  ab, welche Stats fuer den Build wichtig sind (= Gewichtung).
# ============================================================

# Wie oft taucht ein Stat im Build auf -> diese Regex zaehlen wir.
BUILD_STAT_PATTERNS = {
    "life":           r"(?:maximalem\s+Leben|to\s+(?:maximum\s+)?Life)",
    "fire_res":       r"(?:Feuerwiderstand|Fire\s+Resistance)",
    "cold_res":       r"(?:K[äa]ltewiderstand|Cold\s+Resistance)",
    "lightning_res":  r"(?:Blitzwiderstand|Lightning\s+Resistance)",
    "chaos_res":      r"(?:Chaoswiderstand|Chaos\s+Resistance)",
    "all_res":        r"(?:allen\s+Elementarwiderst|all\s+Elemental\s+Resistances)",
    "energy_shield":  r"(?:Energieschild|Energy\s+Shield)",
    "crit_chance":    r"(?:kritische[rn]?\s+Treffer|Critical)",
    "spell_damage":   r"(?:Zauberschaden|Spell\s+Damage)",
    "movement_speed": r"(?:Bewegungsgeschwindigkeit|Movement\s+Speed)",
    "armour":         r"(?:erh[öo]hte\s+R[üu]stung|increased\s+Armour)",
}


def decode_pob_code(code):
    """PoB-Code -> XML. Format: URL-safe base64 -> zlib inflate -> XML."""
    code = code.strip()
    # Padding fuer base64 ggf. auffuellen
    missing = len(code) % 4
    if missing:
        code += "=" * (4 - missing)
    raw = base64.urlsafe_b64decode(code)
    xml = zlib.decompress(raw).decode("utf-8", errors="ignore")
    return xml


def fetch_pobbin(url):
    """Holt den rohen PoB-Code von einem pobb.in-Link."""
    # pobb.in/<id>  ->  pobb.in/<id>/raw
    m = re.search(r"pobb\.in/([A-Za-z0-9_-]+)", url)
    if not m:
        return None
    raw_url = f"https://pobb.in/{m.group(1)}/raw"
    # pobb.in verlangt einen Browser-User-Agent
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                             "AppleWebKit/537.36 (KHTML, like Gecko) "
                             "Chrome/131.0.0.0 Safari/537.36"}
    r = requests.get(raw_url, headers=headers, timeout=20)
    if r.status_code == 200:
        return r.text.strip()
    return None


def weights_from_build(xml):
    """Leitet aus dem Build-XML Stat-Gewichte ab (0.2 - 1.0)."""
    xml = clean_item_text(xml)   # GGG-Tags entfernen
    counts = {}
    for key, pat in BUILD_STAT_PATTERNS.items():
        counts[key] = len(re.findall(pat, xml, re.IGNORECASE))

    max_count = max(counts.values()) if counts.values() else 0
    weights = {}
    for key, c in counts.items():
        if max_count > 0 and c > 0:
            # normieren auf 0.2 - 1.0 (haeufigster Stat = 1.0)
            weights[key] = round(0.2 + 0.8 * (c / max_count), 2)
        else:
            weights[key] = 0.0
    return weights, counts


def extract_build_info(xml):
    """Zieht Klasse/Level/Ascendancy aus dem Build-XML (fuer Anzeige)."""
    info = {}
    m = re.search(r'className="([^"]+)"', xml)
    if m: info["class"] = m.group(1)
    m = re.search(r'ascendClassName="([^"]+)"', xml)
    if m and m.group(1): info["ascendancy"] = m.group(1)
    m = re.search(r'level="(\d+)"', xml)
    if m: info["level"] = int(m.group(1))
    return info


def fetch_maxroll(url):
    """Holt den HTML/JSON-Inhalt einer Maxroll-Build-Seite.
    Maxroll ist (anders als Mobalytics) nicht hart Cloudflare-geblockt."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                             "AppleWebKit/537.36 (KHTML, like Gecko) "
                             "Chrome/131.0.0.0 Safari/537.36"}
    try:
        r = requests.get(url, headers=headers, timeout=20)
    except requests.RequestException:
        return None
    if r.status_code == 200 and "just a moment" not in r.text.lower()[:2000]:
        return r.text
    return None


def weights_from_text(text):
    """Wie weights_from_build, aber fuer beliebigen Item-/Stat-Text
    (Maxroll-HTML oder vom User eingefuegter Gear-Text)."""
    return weights_from_build(text)  # gleiche Zaehl-Logik


@app.route("/api/import-build", methods=["POST"])
def api_import_build():
    """
    Universeller Build-Import. Erkennt automatisch die Quelle:
      1. pobb.in-Link        -> Code holen -> dekodieren
      2. PoB-Export-Code     -> direkt dekodieren
      3. maxroll.gg-Link     -> Seite laden -> Stats aus Text zaehlen
      4. roher Gear-Text      -> Stats direkt aus Text zaehlen (Fallback, geht immer)
    """
    data = request.get_json(silent=True) or {}
    raw = (data.get("code") or "").strip()
    if not raw:
        return jsonify({"error": "kein_code"}), 400

    source = "unbekannt"
    text_for_stats = None
    info = {}
    passive_hints = {}
    slot_stats = {}
    slot_uniques = {}
    extras = {}

    try:
        # --- 0: .build-Datei (JSON von Mobalytics/Build Planner) ---
        if _looks_like_build_json(raw):
            source = "build-datei"
            text_for_stats, info, passive_hints, slot_stats, slot_uniques, extras = parse_build_json(raw)

        # --- 1 & 2: PoB (Link oder Code) ---
        elif "pobb.in" in raw:
            source = "pobb.in"
            code = fetch_pobbin(raw)
            if not code:
                return jsonify({"error": "pobbin_fehlgeschlagen",
                                "detail": "Link konnte nicht geladen werden"}), 400
            text_for_stats = decode_pob_code(code)
            info = extract_build_info(text_for_stats)

        # --- 3: Maxroll-Link ---
        elif "maxroll.gg" in raw:
            source = "maxroll"
            html = fetch_maxroll(raw)
            if not html:
                return jsonify({"error": "maxroll_fehlgeschlagen",
                                "detail": "Seite blockiert oder leer. Tipp: "
                                          "Gear-Text manuell einfügen."}), 400
            text_for_stats = html

        # --- 4: pruefen ob es ein PoB-Code ist (base64) ---
        elif _looks_like_pob_code(raw):
            source = "pob-code"
            try:
                text_for_stats = decode_pob_code(raw)
                info = extract_build_info(text_for_stats)
            except Exception:
                # kein gueltiger Code -> als Text behandeln
                source = "text"
                text_for_stats = raw

        # --- sonst: roher Gear-Text (Fallback, geht immer) ---
        else:
            source = "text"
            text_for_stats = raw

    except Exception as e:
        return jsonify({"error": "import_fehler", "detail": str(e)}), 400

    if not text_for_stats or len(text_for_stats) < 5:
        return jsonify({"error": "kein_inhalt",
                        "detail": "Nichts auswertbares gefunden"}), 400

    text_for_stats = clean_item_text(text_for_stats)   # GGG-Tags entfernen
    counts = {k: len(re.findall(p, text_for_stats, re.IGNORECASE))
              for k, p in BUILD_STAT_PATTERNS.items()}

    # Passiv-Baum-Hinweise mit einrechnen (zaehlen halb so stark wie Items)
    for stat, hint_count in passive_hints.items():
        if stat in counts:
            counts[stat] += hint_count * 0.5

    # Wenn gar kein Stat UND keine Uniques gefunden wurden -> Hinweis
    if sum(counts.values()) == 0 and not slot_uniques and not slot_stats:
        return jsonify({"error": "keine_stats",
                        "detail": "Keine bekannten Stats gefunden. "
                                  "Bei Maxroll/Mobalytics: Gear-Text direkt einfügen.",
                        "source": source}), 400

    # Gewichte normieren (haeufigster Stat = 1.0)
    max_count = max(counts.values()) if counts.values() else 0
    weights = {}
    for key, c in counts.items():
        weights[key] = round(0.2 + 0.8 * (c / max_count), 2) if (max_count and c) else 0.0

    print(f"[BUILD] Import OK (Quelle: {source}): {info}")
    print(f"[BUILD] Gefundene Stats: {dict((k,round(v,1)) for k,v in counts.items() if v)}")
    if passive_hints:
        print(f"[BUILD] Passiv-Hinweise: {passive_hints}")

    return jsonify({
        "source": source,
        "build_info": info,
        "weights": weights,
        "stat_counts": {k: round(v, 1) for k, v in counts.items()},
        "passive_hints": passive_hints,
        "slot_stats": slot_stats,       # pro Slot die Stats fuer slot-genaue Trade-Suche!
        "slot_uniques": slot_uniques,   # pro Slot der Unique-Name (Namens-Suche)
        "skills": extras.get("skills", []),    # Skill-Gems + Support-Gems
        "flasks": extras.get("flasks", []),    # Flask-Slots
        "charms": extras.get("charms", []),    # Charm-Slots
    })


def _looks_like_pob_code(s):
    """Heuristik: sieht der String nach einem PoB-Base64-Code aus?"""
    if len(s) < 40 or " " in s.strip():
        return False
    # PoB-Codes bestehen aus URL-safe base64 Zeichen
    return bool(re.fullmatch(r"[A-Za-z0-9_\-=]+", s.strip()))


# ------------------------------------------------------------
#  .build-Datei (Mobalytics / PoE2 Build Planner Format)
# ------------------------------------------------------------
# Passiv-Baum-Themen -> welcher Stat dadurch wichtig wird.
# (z.B. viele "elemental"-Knoten -> Resistenzen/Ele-Schaden wichtig)
PASSIVE_THEME_HINTS = {
    "elemental":     ["fire_res", "cold_res", "lightning_res"],
    "cold":          ["cold_res"],
    "fire":          ["fire_res"],
    "lightning":     ["lightning_res"],
    "chaos":         ["chaos_res"],
    "life":          ["life"],
    "energy":        ["energy_shield"],
    "spell":         ["spell_damage"],
    "criticals":     ["crit_chance"],
}


# Mapping: GGG-interne Ascendancy-ID -> Klasse + lesbarer Name
# (Reihenfolge laut offizieller Klassen-Tabelle)
ASCENDANCY_MAP = {
    # Sorceress (Intelligence)
    "Sorceress1": ("Sorceress", "Stormweaver"),
    "Sorceress2": ("Sorceress", "Chronomancer"),
    "Sorceress3": ("Sorceress", "Disciple of Varashta"),
    # Witch (Intelligence)
    "Witch1": ("Witch", "Infernalist"),
    "Witch2": ("Witch", "Blood Mage"),
    "Witch3": ("Witch", "Lich"),
    # Warrior (Strength)
    "Warrior1": ("Warrior", "Warbringer"),
    "Warrior2": ("Warrior", "Titan"),
    "Warrior3": ("Warrior", "Smith of Kitava"),
    # Ranger (Dexterity)
    "Ranger1": ("Ranger", "Deadeye"),
    "Ranger2": ("Ranger", "Pathfinder"),
    # Huntress (Dexterity)
    "Huntress1": ("Huntress", "Amazon"),
    "Huntress2": ("Huntress", "Ritualist"),
    "Huntress3": ("Huntress", "Spirit Walker"),
    # Monk (Int/Dex)
    "Monk1": ("Monk", "Invoker"),
    "Monk2": ("Monk", "Acolyte of Chayula"),
    "Monk3": ("Monk", "Martial Artist"),
    # Mercenary (Str/Dex)
    "Mercenary1": ("Mercenary", "Witchhunter"),
    "Mercenary2": ("Mercenary", "Gemling Legionnaire"),
    "Mercenary3": ("Mercenary", "Tactician"),
    # Druid (Str/Int)
    "Druid1": ("Druid", "Shaman"),
    "Druid2": ("Druid", "Oracle"),
}


def resolve_ascendancy(asc_id):
    """Wandelt 'Sorceress1' -> {'class':'Sorceress','ascendancy':'Stormweaver','id':'Sorceress1'}."""
    if not asc_id:
        return {}
    if asc_id in ASCENDANCY_MAP:
        cls, name = ASCENDANCY_MAP[asc_id]
        return {"class": cls, "ascendancy": name, "ascendancy_id": asc_id}
    # Fallback: Klasse aus ID ableiten (Zahl abschneiden)
    cls = re.sub(r"\d+$", "", asc_id)
    return {"class": cls, "ascendancy": asc_id, "ascendancy_id": asc_id}


# Normalisiert Build-Slot-IDs (z.B. "Weapon1") auf unsere HUD-Slots ("Weapon")
def normalize_slot(inv_id):
    """Weapon1->Weapon, Helm1->Helm, Ring1->Ring, Ring2->Ring2 etc."""
    if not inv_id:
        return None
    mapping = {
        "Weapon1": "Weapon", "Weapon2": "Weapon2",
        "Helm1": "Helm", "BodyArmour1": "BodyArmour",
        "Gloves1": "Gloves", "Boots1": "Boots",
        "Belt1": "Belt", "Amulet1": "Amulet",
        "Ring1": "Ring", "Ring2": "Ring2",
        "Offhand1": "Offhand", "Offhand2": "Offhand2",
    }
    return mapping.get(inv_id, inv_id)


# Stichwort in der Gem-ID -> lesbarer Tag (Element/Typ erkennen)
GEM_TAG_HINTS = {
    "Fire": "🔥 Feuer", "Flame": "🔥 Feuer", "Burn": "🔥 Feuer", "Ember": "🔥 Feuer",
    "Frost": "❄️ Kälte", "Ice": "❄️ Kälte", "Cold": "❄️ Kälte", "Glacial": "❄️ Kälte",
    "Spark": "⚡ Blitz", "Lightning": "⚡ Blitz", "Storm": "⚡ Blitz", "Shock": "⚡ Blitz",
    "Chaos": "☠️ Chaos", "Poison": "☠️ Chaos", "Decay": "☠️ Chaos",
    "Critical": "🎯 Krit", "Dart": "🎲 Projektil", "Projectile": "🎲 Projektil",
    "Arrow": "🏹 Bogen", "Bolt": "🏹 Bogen",
    "Minion": "💀 Diener", "Skeleton": "💀 Diener", "Summon": "💀 Diener",
    "Aura": "✨ Aura", "Herald": "✨ Aura", "Curse": "🌀 Fluch",
    "Melee": "⚔️ Nahkampf", "Strike": "⚔️ Nahkampf", "Slam": "⚔️ Nahkampf",
}


def gem_info_from_id(gem_id):
    """
    Leitet aus der Gem-Metadata-ID alle Infos ab:
    Name, ob Support, und thematische Tags (Element/Typ).
    """
    if not gem_id:
        return None
    raw = gem_id.split("/")[-1]
    is_support = "Support" in raw
    name = raw.replace("SkillGem", "").replace("SupportGem", "").replace("Gem", "")
    name = re.sub(r'(?<!^)(?=[A-Z])', ' ', name).strip()
    name = re.sub(r'\s+(Two|Three|Four|Five)$',
                  lambda m: " " + {"Two": "II", "Three": "III",
                                   "Four": "IV", "Five": "V"}[m.group(1)], name)
    # Tags aus Stichwoertern in der ID
    tags = []
    for kw, tag in GEM_TAG_HINTS.items():
        if kw in raw and tag not in tags:
            tags.append(tag)
    return {
        "name": name,
        "is_support": is_support,
        "tags": tags,
    }


def gem_name_from_id(gem_id):
    """Nur der lesbare Name (Kompatibilitaet)."""
    info = gem_info_from_id(gem_id)
    return info["name"] if info else ""


def parse_build_skills(data):
    """Parst die Skill-Gems + Support-Gems aus dem .build.
    Liefert eine Liste: [{skill, level, tags, supports:[{name,tags}]}].
    """
    result = []
    for skill in data.get("skills", []):
        main = gem_info_from_id(skill.get("id", ""))
        if not main:
            continue
        lvl = (skill.get("level_interval") or [None])[0]
        supports = []
        for s in skill.get("support_skills", []):
            si = gem_info_from_id(s.get("id", ""))
            if si:
                supports.append({"name": si["name"], "tags": si["tags"]})
        result.append({
            "skill": main["name"],
            "tags": main["tags"],
            "level": lvl,
            "supports": supports,
        })
    return result


def parse_build_consumables(data):
    """Parst Charms + Flasks (Slots mit inventory_id Flask*/Charm*)."""
    flasks, charms = [], []
    for slot in data.get("inventory_slots", []):
        inv = slot.get("inventory_id", "")
        txt = (slot.get("additional_text", "") or slot.get("unique_name", "")).split("\n")[0]
        if not txt:
            continue
        if inv.startswith("Flask"):
            flasks.append(txt)
        elif inv.startswith("Charm"):
            charms.append(txt)
    return flasks, charms


def parse_build_json(raw):
    """
    Parst eine .build-Datei (JSON aus Mobalytics/PoE2 Build Planner).
    Liefert (gesammelter_item_text, build_info, passive_hints, slot_stats).
    slot_stats = {slot: {stat_key: min_wert}} fuer slot-genaue Trade-Suche.
    """
    data = json.loads(raw)

    # Item-Stats aus allen inventory_slots sammeln
    texts = []
    slot_stats = {}     # pro Slot die gesuchten Stats (wie Mobalytics!)
    slot_uniques = {}   # pro Slot der Unique-Name (falls Unique-Item)
    for slot in data.get("inventory_slots", []):
        sname = normalize_slot(slot.get("inventory_id"))
        # Unique-Item? -> nach Namen suchen statt nach Stats
        uniq = slot.get("unique_name")
        if uniq and sname:
            slot_uniques[sname] = uniq
            continue
        t = slot.get("additional_text", "")
        if t:
            texts.append(t)
            if sname:
                # erste Zeile ist der Item-Name -> die Mods stehen danach
                st = stats_from_mod_text(t)
                if st:
                    slot_stats[sname] = st
    item_text = "\n".join(texts)

    # Build-Info
    info = {}
    if data.get("name"):   info["name"] = data["name"]
    if data.get("author"): info["author"] = data["author"]
    # Ascendancy-ID in lesbaren Namen + Klasse aufloesen
    asc = resolve_ascendancy(data.get("ascendancy", ""))
    info.update(asc)   # fuegt class, ascendancy (Name), ascendancy_id hinzu

    # Passiv-Baum-Themen zaehlen -> Hinweise auf wichtige Stats
    passive_hints = {}
    for p in data.get("passives", []):
        pid = p.get("id", "")
        base = re.sub(r"[0-9_]+$", "", pid).lower()
        for theme, stats in PASSIVE_THEME_HINTS.items():
            if theme in base:
                for s in stats:
                    passive_hints[s] = passive_hints.get(s, 0) + 1

    # Skills/Gems + Charms/Flasks parsen
    skills = parse_build_skills(data)
    flasks, charms = parse_build_consumables(data)
    extras = {"skills": skills, "flasks": flasks, "charms": charms}

    return item_text, info, passive_hints, slot_stats, slot_uniques, extras


def _looks_like_build_json(s):
    """Erkennt eine .build JSON-Datei."""
    s = s.strip()
    return s.startswith("{") and ("inventory_slots" in s or "passives" in s)


# ------------------------------------------------------------
#  TRADE-Integration (Weg A: vorausgefuellte Trade-Links)
# ------------------------------------------------------------
# Slot (inventoryId) -> PoE2-Trade Item-Kategorie
SLOT_TRADE_CATEGORY = {
    "Weapon":     "weapon",
    "Weapon2":    "weapon",
    "Offhand":    "armour.shield",
    "Offhand2":   "armour.shield",
    "Helm":       "armour.helmet",
    "BodyArmour": "armour.chest",
    "Gloves":     "armour.gloves",
    "Boots":      "armour.boots",
    "Belt":       "accessory.belt",
    "Amulet":     "accessory.amulet",
    "Ring":       "accessory.ring",
    "Ring2":      "accessory.ring",
}


# Bekannte PoE2-Trade Stat-IDs (explicit) fuer die Auto-Filter.
# Quelle: ECHTE Trade-Links (vom User verifiziert!).
TRADE_STAT_IDS = {
    "life":             "explicit.stat_3299347043",   # +# to maximum Life  [verifiziert]
    "mana":             "explicit.stat_1050105434",   # +# to maximum Mana  [verifiziert]
    "energy_shield":    "explicit.stat_4052037485",   # +# to maximum Energy Shield  [verifiziert]
    "spirit":           "explicit.stat_2704225257",   # +# to Spirit  [verifiziert]
    "spell_damage":     "explicit.stat_2974417149",   # #% increased Spell Damage  [verifiziert]
    "spell_skills":     "explicit.stat_124131830",    # +# to Level of all Spell Skills  [verifiziert]
    "movement_speed":   "explicit.stat_2250533757",   # #% increased Movement Speed  [verifiziert]
    "chaos_res":        "explicit.stat_2923486259",   # +#% to Chaos Resistance  [verifiziert]
    "eva_es":           "explicit.stat_1999113824",   # #% increased Evasion and Energy Shield  [verifiziert]
    "crit_dmg_bonus":   "explicit.stat_3556824919",   # #% increased Critical Damage Bonus  [verifiziert]
    # Armour ist ein LOKALER Defense-Stat -> braucht die (Local)-ID!
    # Ohne (Local) findet die Suche KEINE Items (haeufiger Fehler, auch bei Mobalytics).
    "armour":           "explicit.stat_3484657501",   # #% increased Armour (Local)
    # Resistenzen am besten ueber pseudo-total (egal welche Resi)
    "ele_res":          "pseudo.pseudo_total_elemental_resistance",  # [verifiziert]
}

# Mapping: Regex (Zahl direkt am Stat) -> Stat-Key.
# So erkennen wir aus dem Build-Item den Stat UND den Mindestwert.
# Reihenfolge wichtig: spezifischere Muster (eva_es) VOR allgemeineren (energy_shield)!
MOD_TO_STAT = [
    (r"(\d+)%?\s+(?:erh[öo]hter\s+Zauberschaden|increased\s+Spell\s+Damage)",       "spell_damage"),
    (r"\+?(\d+)\s+(?:zu\s+Stufen?\s+aller\s+Zauberfertigkeiten|to\s+Level\s+of\s+all\s+Spell\s+Skills)", "spell_skills"),
    (r"(\d+)%?\s+(?:erh[öo]hte\s+Bewegungsgeschwindigkeit|increased\s+Movement\s+Speed)", "movement_speed"),
    # "... und Energieschild" ZUERST (sonst greift Energieschild allein davor)
    (r"(\d+)%?\s+(?:erh[öo]hte\s+Ausweich\w*\s+und\s+Energieschild|increased\s+Evasion\s+and\s+Energy\s+Shield)", "eva_es"),
    (r"(\d+)%?\s+(?:erh[öo]hter\s+kritischer\s+Schadensbonus|increased\s+Critical\s+Damage\s+Bonus)", "crit_dmg_bonus"),
    (r"(\d+)%?\s+(?:erh[öo]hte\s+kritische\s+Trefferchance|increased\s+Critical\s+Hit\s+Chance)", "crit_dmg_bonus"),
    (r"(\d+)%?\s+(?:erh[öo]hte\s+R[üu]stung|increased\s+Armour)",                   "armour"),
    (r"\+?(\d+)\s+(?:zu\s+maximalem\s+Leben|to\s+(?:maximum\s+)?Life)",             "life"),
    (r"\+?(\d+)\s+(?:zu\s+maximalem\s+Mana|to\s+(?:maximum\s+)?Mana)",              "mana"),
    (r"\+?(\d+)\s+(?:zu\s+maximalem\s+Energieschild|to\s+(?:maximum\s+)?Energy\s+Shield)", "energy_shield"),
    (r"\+?(\d+)\s+(?:zu\s+Wille|to\s+Spirit)",                                      "spirit"),
    # Chaos-Res separat (eigene Trade-ID), andere Resis -> pseudo total
    (r"\+?(\d+)%?\s+(?:zu\s+Chaoswiderstand|to\s+Chaos\s+Resistance)",              "chaos_res"),
    (r"\+?(\d+)%?\s+(?:zu\s+Feuerwiderstand|zu\s+K[äa]ltewiderstand|zu\s+Blitzwiderstand|zu\s+allen\s+Elementarwiderst\w*|to\s+(?:Fire|Cold|Lightning|all\s+Elemental)\s+Resistance)", "ele_res"),
]


def stats_from_mod_text(text):
    """
    Aus einem Item-Mod-Text (z.B. '+10% to Lightning Resistance\\n14% increased Armour')
    die gesuchten {stat_key: min_wert} ableiten - wie Mobalytics es pro Slot macht.
    Zieht den EXAKTEN Mindestwert aus dem Mod.
    """
    text = clean_item_text(text)
    found = {}
    for pattern, key in MOD_TO_STAT:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            try:
                val = int(m.group(1))
            except (ValueError, IndexError):
                continue
            if key == "ele_res":
                found[key] = found.get(key, 0) + val   # Resis summieren
            else:
                found[key] = val                       # exakter Wert
    return found


@app.route("/api/trade-link", methods=["GET", "POST"])
def api_trade_link():
    """
    Baut einen vorausgefuellten PoE2-Trade-Such-Link fuer einen Slot.
    KORREKTES Format (aus echtem Link verifiziert):
      https://www.pathofexile.com/trade2/search/<Liga>?q=<JSON>

    Sucht SLOT-GENAU: pro Slot genau die Stats, die im Build auf
    diesem Item-Slot stehen (wie Mobalytics) - nicht die globale Gewichtung.

    POST-Body (JSON): {slot, league, stats: {stat_key: min_wert}}
    """
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        slot = (body.get("slot") or "").strip()
        league = (body.get("league") or "Standard").strip() or "Standard"
        want = body.get("stats") or {}            # {stat_key: min_wert}
        unique_name = (body.get("unique_name") or "").strip()
        trade_status = (body.get("trade_status") or "any").strip()
        tolerance = body.get("tolerance", 0)      # +-% Toleranz auf Min-Werte
    else:
        slot = request.args.get("slot", "").strip()
        league = request.args.get("league", "Standard").strip() or "Standard"
        sp = request.args.get("stats", "").strip()
        want = {k: None for k in sp.split(",") if k} if sp else {}
        unique_name = request.args.get("unique_name", "").strip()
        trade_status = request.args.get("trade_status", "any").strip()
        tolerance = 0

    # Handelsstatus: "online" (sofort kaufbar), "onlineleague", "any"
    status_map = {
        "buyout": "online",       # nur sofort kaufbar (Buyout)
        "online": "online",
        "any": "any",
    }
    status_option = status_map.get(trade_status, "any")

    # Toleranz: senkt die Min-Werte um X% (mehr Treffer, z.B. -15%)
    try:
        tol = max(0, min(50, float(tolerance))) / 100.0
    except (ValueError, TypeError):
        tol = 0.0

    category = SLOT_TRADE_CATEGORY.get(slot)

    query = {
        "query": {
            "status": {"option": status_option},
            "stats": [{"type": "and", "filters": []}],
        },
        "sort": {"price": "asc"},
    }

    applied = []

    if unique_name:
        # --- Unique-Item: nach Namen + Rarity suchen ---
        query["query"]["name"] = unique_name
        query["query"]["filters"] = {
            "type_filters": {"filters": {"rarity": {"option": "unique"}}}
        }
        applied = ["unique:" + unique_name]
    else:
        # --- Rare/Magic: nach Kategorie + Stats suchen ---
        stat_filters = []
        for key, minval in want.items():
            sid = TRADE_STAT_IDS.get(key)
            if not sid:
                continue
            f = {"id": sid, "disabled": False}
            if minval is not None:
                try:
                    # Toleranz abziehen (z.B. -15% -> mehr Treffer)
                    mv = float(minval) * (1.0 - tol)
                    f["value"] = {"min": int(mv)}
                except (ValueError, TypeError):
                    pass
            stat_filters.append(f)
            applied.append(key)
        query["query"]["stats"] = [{"type": "and", "filters": stat_filters}]
        if category:
            query["query"]["filters"] = {
                "type_filters": {"filters": {"category": {"option": category}}}
            }

    q = urllib.parse.quote(json.dumps(query))
    # WICHTIG: Pfad ist /trade2/search/<Liga>  (NICHT /poe2/<Liga> !)
    url = f"https://www.pathofexile.com/trade2/search/{urllib.parse.quote(league)}?q={q}"

    return jsonify({
        "url": url,
        "category": category,
        "slot": slot,
        "applied_stats": applied,
        "is_unique": bool(unique_name),
    })


# ------------------------------------------------------------
#  Start
# ------------------------------------------------------------
if __name__ == "__main__":
    # Port + Debug aus Umgebung (Hosting-Anbieter geben PORT vor)
    port = int(os.getenv("PORT", "8000"))
    debug = os.getenv("FLASK_DEBUG", "1") == "1"   # in Produktion FLASK_DEBUG=0 setzen!
    print("=" * 50)
    print(f"  Exile Eye Navigator startet auf Port {port}")
    print(f"  Login: /login   Realm: {REALM}   Debug: {debug}")
    print("=" * 50)
    app.run(host="0.0.0.0", port=port, debug=debug)
