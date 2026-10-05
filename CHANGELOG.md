# Changelog — Exile Eye Navigator

**Regel (wichtig!):**
Jeder Upload mit Änderungen = **beide** Versionsnummern hochziehen + Eintrag hier.

1. `index.html` → `const APP_VERSION = "vX.Y";` (wird im Footer angezeigt)
2. `sw.js` → `const CACHE = "exile-eye-vN";` (jedes Mal +1 — räumt alte PWA-Caches auf den Geräten der Nutzer auf!)

Fehlt einer der beiden Bumps, sehen Nutzer evtl. weiter eine alte Version (Service-Worker-Cache).

---

## v1.24 (05.10.2026, Polish-Trio)
- **Fix: Layout springt nicht mehr** — die Scrollbar reserviert jetzt permanent ihren Platz (`scrollbar-gutter: stable`), kein seitliches Einrücken/Springen mehr, wenn Seiten länger werden oder man Tabs wechselt
- **Fix: DEMO-Badge bleib nach Login hängen** — der Badge verschwindet jetzt zuverlässig, sobald man eingeloggt ist / echte Charaktere lädt / einen echten Char wählt (war vorher nach Demo→Login klebrig sichtbar)
- **Aufgeräumt: doppelte Build-Auswahl im Build-Tab entfernt** — der globale Switcher unter den Tabs übernimmt komplett. Der 🗑-Löschen-Knopf bleibt erhalten: direkt neben „Aktiven Build entfernen" (löscht den AKTIVEN Build endgültig aus der Liste; danach springt der nächste gespeicherte nach)

## v1.23 (05.10.2026, Globaler Build-Switcher)
- **Neu: Build-Dropdown direkt unter der Tab-Leiste** — den aktiven Build jetzt von überall wechseln, ohne erst in den Build-Tab zu müssen (sichtbar, sobald ≥1 Build gespeichert ist; „kein Build" zum Abwählen)
- **Fortschritts-Chip direkt daneben:** `7/13 ✓` zeigt sofort, wie viele Build-Slots dein Gear erfüllt — grün wenn komplett, amber wenn noch was fehlt (gleiche Logik wie die Fortschritts-Leiste im Charakter-Tab)
- Wechsel wirkt sofort auf alles: Gewichtung, Support-Gem-Badges, ✓/✗-Slot-Markierungen, Stat-Score, Trade-Links — egal in welchem Tab du gerade bist
- Bleibt mit dem Build-Dropdown im Build-Tab synchronisiert; Sprachwechsel übersetzt „kein Build" mit

## v1.22 (05.10.2026, Waffenset 2 im HUD)
- **Neu: Weapon-Swap-Slots** — das HUD zeigt jetzt auch das zweite Waffenset (GGG liefert es als `Weapon2`/`Offhand2`, siehe offizielle API/PoB-Import). Die beiden Flanken sind geteilt: oben Haupt-Set (Waffe/Nebenhand), unten Set 2 — mit eigenen Silhouetten. Vorher wurden Swap-Items aus der API still verworfen!
- Swap-Set fließt mit in Stat-Score, Tooltips und Tap-Details ein; Trade-Kategorien dafür gab es schon (`Weapon2`→weapon, `Offhand2`→shield)
- Scanner-Slot-Auswahl: „Waffe 2"/„Nebenhand 2" ergänzt (Scan-Vergleich auch gegen Swap-Set möglich)
- Demo-Sorceress hat jetzt Beispiel-Swap-Items (Initiate's Sceptre + Rotted Buckler)

## v1.21 (05.10.2026, HUD-Stufe 2c: Paper-Doll-Feinschliff)
- **Handy-Modus (≤480px): Item-Art statt Text** — gefüllte Slots zeigen auf schmalen Screens jetzt das große Item-Icon wie ingame (Name, Details & Co. per Tap im Tooltip); ohne Icon (Demo) bleibt der Text-Modus als Fallback
- **Item-Namen umbrechen auf 2 Zeilen** statt hart abzuschneiden — „Oak Staff" statt „Oak S…", volle Namen auch in schmalen Slots lesbar
- **Leere Slots aufgeräumt:** große, besser sichtbare Silhouette zentriert (je Slot-Typ skaliert: Waffen 68px, Ringe 40px), doppeltes Mini-Icon entfernt, „leer/empty" klein am unteren Rand platziert
- **Seltenheits-Kante:** gefüllte Slots bekommen oben einen 2px-Farbstreifen in PoE-Seltenheitsfarben (Magic blau / Rare gelb / Unique orange) mit leichtem Glow — Rarität auf den ersten Blick erkennbar, nicht nur am Namen
- **Stat-Score als Pill-Badge** im Slot (teal, gerundet) statt nacktem Text
- **Grid-Balance:** Amulett/Ring-Spalten etwas breiter, weniger Quetschung

## v1.20 (05.10.2026, Namenskonflikte im Support-Check)
- **Fuzzy-Gem-Matching:** GGG und Build-Planer nennen dieselben Skills oft anders — jetzt werden sie trotzdem erkannt:
  - „**Maul**" = „**Bear** Maul", „Fire Spell on Hit" = „**Ascendancy** Fire Spell On Hit" (Flavor-Präfixe Bear/Wolf/Wyvern/Ascendancy werden ignoriert)
  - „Primal Armament **Two**" = „Primal Armament **II**" (Tier-Wörter & Ziffern werden wie römische Zahlen behandelt)
  - „Living Bomb **Player**" = „Living Bomb" (Maxroll-Varianten-Suffix)
- **Support-Overlap-Paarung:** Wenn Namen komplett abweichen (z.B. Maxroll „Bear Rampage" vs. GGG „Furious Slam"), werden Skills über ≥2 gemeinsame Support-Gems gepaart — die ✓/✗-Badges sitzen dann trotz Umbenennung richtig.
- **Neu: „≈"-Alias-Badge** zeigt an, wie der Skill im Build heißt, wenn der Name vom Gear-Namen abweicht (teal, nicht grau — klar von „nicht im Build" unterscheidbar).

## v1.19 (02.10.2026)
- **Fix: Skill-Namen im Charakter-Tab** — GGG liefert bei Main-Skills offenbar oft keinen Namen (statt „Bear Maul" stand da im schlimmsten Fall die rohe CDN-Icon-URL). Neuer Fallback: der Name wird aus der Icon-URL abgeleitet (`DruidBearMaul.png` → „Bear Maul", `SmithOfKitavaTriggerFireballsSkillIcon` → „Trigger Fireballs"). Unit-getestet mit allen 10 Skills aus dem echten Charakter.
- **Neu: Support-Gem-Check gegen den aktiven Build** — der Charakter-Tab markiert jetzt direkt: ✓ Support passt zum importierten Build, ✗ der Build will diesen Support, du hast ihn aber nicht gesockelt (rot gestrichelt), und „nicht im Build"-Badge bei Skills, die dein Build gar nicht nutzt. Tier-Suffixe („Overabundance I" vs „Overabundance II") zählen beim Abgleich nicht.
- **Build-Tab: Reihenfolge getauscht** — Gewichtung & Slider zuerst, Skills & Support-Gems darunter (gleiche Struktur wie Charakter-Tab: Inhalt oben, Gems unten).

## v1.18 (01.10.2026, Hotfix)
- **Fix: Skill-Gems-Extraktion laut offizieller GGG-Doku** — `character.skills` ist ein Item-Array; Main-Gems = Skill-Gruppen, Support-Gems kommen aus `socketedItems` oder als eigene Einträge mit `support: true`. Beide Shapes werden verarbeitet (unit-getestet).
- **Fix: Gem-Modal zweisprachig** — „Skill-Gemme/Support-Gemme", „ab Level X", „UNTERSTÜTZUNGS-GEMMEN", Hinweis-Text sind jetzt i18n (EN: „Skill Gem", „from Level", „SUPPORT GEMS", „in-game hint").
- **Fix: Modal schließt beim Sprachwechsel** — steht nicht mehr in der alten Sprache im Raum.

## v1.17 (01.10.2026, Stufe 2b: Pro-Niveau)
- **Stat-Score als kompaktes Chip im Header** statt eigener Zeile (immer sichtbar, Bounce-Animation bleibt, auf Mobile nur die Zahl)
- **Status-Meldungen als Toast** (oben rechts, ploppt auf, verschwindet von selbst: ok 3s / Fehler 5s) statt Vollbreiten-Banner, der die App nach unten schiebt
- **Leere Slots mit Icon-Silhouetten** (halbtransparente Waffen/Helm/Schild-Umrisse statt kahlen Textkästen)
- **Gewichts-Slider gruppiert**: Defensiv / Offensiv / Utility, je 2 Spalten (1 auf Mobile)
- **„.build-Datei auswählen" dezent** (gestrichelte Zone statt dominantem Button)
- „App installieren"-Button als dezenter Ghost-Button

## v1.16 (30.09.2026)
- **Neu: Skill-Gems aus der GGG-API** — der Charakter-Tab zeigt jetzt die Skill-Sets deines Charakters mit Main-Gem + Support-Gems (Icons + Namen). Zum Vergleichen, ob die richtigen Gems gesteckt sind, ohne ins Spiel zu müssen.
- **Neu: Login-Button im Header** — „Mit GGG anmelden" ist jetzt immer sichtbar (war vorher nur im Charakter-Panel).
- **Fix:** Sprachwechsel sprang in den Build-Tab (Re-Render der Build-Leiste zwang den Tab-Wechsel)
- **Fix:** Preis-Check/Trade-Link springt nicht mehr in den Settings-Tab
- **Fix:** Winzige Scrollbar an der Tab-Bar (overflow-y) entfernt
- **Neu: Tab-Position bleibt über Reloads erhalten** (localStorage)

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
