# Changelog — Exile Eye Navigator

**Regel (wichtig!):**
Jeder Upload mit Änderungen = **beide** Versionsnummern hochziehen + Eintrag hier.

1. `index.html` → `const APP_VERSION = "vX.Y";` (wird im Footer angezeigt)
2. `sw.js` → `const CACHE = "exile-eye-vN";` (jedes Mal +1 — räumt alte PWA-Caches auf den Geräten der Nutzer auf!)

Fehlt einer der beiden Bumps, sehen Nutzer evtl. weiter eine alte Version (Service-Worker-Cache).

---

## v1.15 (30.09.2026, Stufe 2a: Struktur & Ruhe)
- **Tab-Navigation statt Vertikal-Stapel:** Scanner / Charakter / Build / Einstellungen als horizontale Tabs, immer nur ein Bereich sichtbar.
- **Flache Buttons:** Primär-CTAs (Foto, Import) ohne Gradient, solide Tealfarbe.
- **DEMO-Badge im Header** statt grünem Vollbreiten-Banner (dezent neben dem Titel).
- **Kompaktes 2×2-Resist-Grid** statt vier Vollbreiten-Balken (Mini-Bars, kurze Labels „Feuer-Res" etc.)
- Trade-Link öffnet nicht mehr den Settings-Tab (stört nur, ohne Mehrwert)
- Mobile: Tab-Bar horizontal scrollbar, kein Layout-Overflow
- Bekannt (vor v1.15, nicht neu): HUD-3.-Spalte auf sehr schmalen Screens leicht beschnitten — wird in der ARPG-Layout-Stufe neu gebaut

## v1.14 (29.09.2026, Design-Skin)
- **Komplettes neues Design-System:** Charcoal-Grundton + Teal-Akzent statt PoE-Braun/Gold (66 Farb-Umstellungen)
- Rarity-Farben, Mod-Farben und blaue Build-Leiste bewusst beibehalten (Game-Konvention)
- Basis für die UI-Überarbeitung nach Community-Feedback

## v1.13 (28.09.2026)
- **Neu: "Why"-Hints im Item-Tooltip** (Antwort auf die Black-Box-Kritik):
  - **Cap-Awareness:** Resist-Stats zeigen, wie viel davon bei deinem aktuellen Gear-Stand wirklich zählt ("Fire Res: only ~50% of +60% counts (you're at 25% / 75% cap)")
  - **Bedingungs-Mods:** Mods wie "with Attacks" / "on Hit" / "on this item" werden als Hinweise markiert ("1 mod(s): only apply to attacks")
  - Bilingual (DE/EN), nutzt den gewählten Cap-Wert aus dem ResCap-Panel
- ResCap-Panel und Hints teilen jetzt dieselbe Total-Logik (getResistTotals)

## v1.12 (25.09.2026)
- **Neu: Runen als eigene Sektion im Item-Tooltip** („◈ Runen"/„◈ Runes", Tealfarbig) — waren bisher unsichtbar unter den anderen Mods versteckt.
- Hinweis: Runen-Stats zählen **bereits** in den Score mit (sofern der Stat gewichtet ist), z.B. +35% Fire Res auf einer Rune.

## v1.11 (25.09.2026)
- **Neu: Gesteckte Gems sichtbar!** Die GGG-API liefert pro Item `socketedItems` — wird jetzt angezeigt: im Item-Tooltip als Liste („✦ Gesteckte Gems"/„✦ Socketed Gems") und im HUD als ✦-Anzeige (Hover = Namen). Tabula-Rasa-Charaktere zeigen jetzt ihre Skills.
- **Fix:** „Besseres Item auf dem Trade suchen" + „Wichtig für deinen Build" waren hartkodiert deutsch → jetzt übersetzt

## v1.10 (25.09.2026, Hotfix)
- **Fix:** Nach Sprachwechsel zeigten geladene Item-Namen "leer"/"empty" statt des echten Namens — die Name-Spans behielten das `data-i18n="empty_slot"`-Attribut, und der Sprachwechsel setzte es zurück. Attribut wird jetzt beim Befüllen entfernt.
- **Fix:** `(unbenannt)`-Fallback im HUD war hartkodiert → jetzt `t("tt_unnamed")`

## v1.9 (25.09.2026, Hotfix)
- **Fix (EN-UI):** Resistenzen-Panel zeigte deutsche Labels ("Feuer-Resistenz", "noch X% bis Cap") — jetzt in beiden Sprachen
- **Fix (EN-UI):** Charakter-Dropdown-Platzhalter + "Charakter(e) geladen"-Banner waren hartkodiert deutsch — jetzt übersetzt, Demo-Modus bekommt auch den Platzhalter (konsistente Reihenfolge)

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
