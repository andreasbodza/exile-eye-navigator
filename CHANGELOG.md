# Changelog — Exile Eye Navigator

**Regel (wichtig!):**
Jeder Upload mit Änderungen = **beide** Versionsnummern hochziehen + Eintrag hier.

1. `index.html` → `const APP_VERSION = "vX.Y";` (wird im Footer angezeigt)
2. `sw.js` → `const CACHE = "exile-eye-vN";` (jedes Mal +1 — räumt alte PWA-Caches auf den Geräten der Nutzer auf!)

Fehlt einer der beiden Bumps, sehen Nutzer evtl. weiter eine alte Version (Service-Worker-Cache).

---

## v1.8 (25.09.2026)
- **EN-UI:** Vollständige zweisprachige App (DE/EN, ~120 Strings), Auto-Erkennung der Browser-Sprache, Toggle oben rechts, Auswahl wird gespeichert
- **Elementar-Schaden:** 4 neue Gewichts-Regler (Feuer/Kälte/Blitz/Chaos-Schaden), Build-Import leitet daraus Gewichte ab
- **Effektivwert-Scoring:** Stat-Score rechnet `(Basis + flat-Mods) × (1 + increased%)` — Basiswerte aus den Item-Properties zählen jetzt mit
- **Fix:** Mobalytics `.build`-Dateien werden wieder importiert (nur echte mobalytics.gg-URLs werden blockiert)
- **Fix:** Aktiver Build wird jetzt immer in der blauen Leiste angezeigt (auch reine Gewichts-Builds), abwählbar
- **Fix:** Stat-Score updatet automatisch beim Build-Wechsel/Import (ohne Slider-Ziehen)
- **Fix:** Talisman wird im OCR-Slot als Waffe erkannt (PoE2-Regel), "Choker" als Amulett
- **Fix:** "40% increased maximum Energy Shield" wird erkannt (fehlte "maximum" im Pattern)
- **Fix:** Kombi-Stats (Eva+ES, Rüstung+ES, all-Res) zählen auf ihre Komponenten

## v1.7 (vorher)
- Stat-Score-Leiste (sticky, mit Bounce-Animation), Gewichts-Regler mit Live-Update
- Build-Import (Mobalytics .build, pobb.in, Maxroll, PoB-Code, Gear-Text)
- GGG-OAuth-Login, Charakter-Gear-HUD, OCR-Item-Scan, Trade-Links
- (Ältere Versionen nicht dokumentiert — bei Bedarf nachtragen)
