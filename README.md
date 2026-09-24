# Exile Eye Navigator

Free, open-source companion web tool for **Path of Exile 2** — scan items from screenshots, score your real in-game gear with *your own* weights, and import your build.

**Live app:** https://exile-eye-navigator.up.railway.app/

> **Just want to use it?** No setup needed — the hosted version works out of the box and can be installed as a PWA on your phone. The local setup at the bottom of this README is only for developers who want to tinker with or contribute to the code.

## Features

- 📸 **Item scanner (OCR)** — screenshot a tooltip, get the stats. German & English game, auto-crop, works on mobile. No login needed.
- 🧍 **Real character gear** — optional login via the official GGG OAuth API. Loads your equipped items (icons, mods, properties) and scores each one with a **Stat-Score** based on your personal weighting — including base values, so a `85% increased Armour` mod counts on the actual armour base.
- 🧠 **Build import** — Mobalytics `.build` files, pobb.in links, Maxroll links, PoB codes or plain gear text. Sets the weights for you and shows skills, flasks, charms and per-slot requirements (✓/✗).
- 💰 **Trade links** — slot-exact, pre-filled PoE2 trade search links (unique name search, min-values, attribute tolerance).
- 📱 **PWA** — installable on phone & desktop.

## How the Stat-Score works

```
effective = (base + flat mods) × (1 + Σ increased % / 100)
```

You tune 14 weights (life, all resistances, ES, crit, spell + elemental fire/cold/lightning/chaos damage, movement speed, armour) via sliders or presets — or just import a build and it's set automatically. The score is a *weighted stat proxy*: unique effects, gem synergies and build mechanics are intentionally not included.

## Tech stack

Python (Flask) · Tesseract OCR · OpenCV · vanilla JS frontend · hosted on [Railway](https://railway.app)

## Running it locally

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in SECRET_KEY, POE_* values
python app.py          # → http://localhost:8000/login
```

You need your own [GGG OAuth application](https://www.pathofexile.com/developer/applications) (public client, PKCE) with the `account:profile` + `account:characters` scopes and a redirect URI matching your local URL. Tesseract OCR must be installed (`TESSERACT_PATH` in `.env`).

## Disclaimer

This product isn't affiliated with or endorsed by Grinding Gear Games in any way. Path of Exile and Path of Exile 2 are trademarks of Grinding Gear Games. All data comes from the official GGG API; the tool stores no item data persistently (see [Datenschutzerklärung](https://exile-eye-navigator.up.railway.app/datenschutz)).
