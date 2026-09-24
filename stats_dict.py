# ============================================================
#  Exile Eye - Stat-Woerterbuch (Deutsch + Englisch)
# ============================================================
#  Erkennt PoE2-Item-Mods in BEIDEN Sprachen.
#  Jeder Eintrag: stat_key -> Liste von Regex-Mustern (DE + EN).
#  Die (\d+) Gruppe faengt den Zahlenwert.
#
#  Erweitern ist easy: einfach beim passenden Key ein Muster ergaenzen.
#  Tipp: Umlaute IMMER doppelt abdecken (ä UND ae), weil OCR mal so
#  mal so liest.
# ============================================================

import re

# Format: "stat_key": [ (regex, ist_prozent), ... ]
STAT_DICT = {
    # ---------- LEBEN / MANA / ES ----------
    "life": [
        r"\+?(\d+)\s+zu\s+maximalem\s+Leben",
        r"\+?(\d+)\s+to\s+(?:maximum\s+)?Life",
    ],
    "mana": [
        r"\+?(\d+)\s+zu\s+maximalem\s+Mana",
        r"\+?(\d+)\s+to\s+(?:maximum\s+)?Mana",
    ],
    "energy_shield": [
        r"\+?(\d+)\s+zu\s+maximalem\s+Energieschild",
        r"\+?(\d+)\s+to\s+(?:maximum\s+)?Energy\s+Shield",
        r"(\d+)%\s+erh[öo]hter\s+(?:maximaler\s+)?Energieschild",
        r"(\d+)%\s+increased\s+(?:maximum\s+)?Energy\s+Shield(?!\s+Recharge)",
    ],
    "spirit": [
        r"\+?(\d+)\s+zu\s+Wille",          # PoE2 DE: Spirit = "Wille"
        r"\+?(\d+)\s+to\s+Spirit",
    ],

    # ---------- WIDERSTÄNDE ----------
    "fire_res": [
        r"\+?(\d+)%?\s+zu\s+Feuerwiderstand",
        r"\+?(\d+)%?\s+to\s+Fire\s+Resistance",
    ],
    "cold_res": [
        r"\+?(\d+)%?\s+zu\s+K[äa]ltewiderstand",
        r"\+?(\d+)%?\s+to\s+Cold\s+Resistance",
    ],
    "lightning_res": [
        r"\+?(\d+)%?\s+zu\s+Blitzwiderstand",
        r"\+?(\d+)%?\s+to\s+Lightning\s+Resistance",
    ],
    "chaos_res": [
        r"\+?(\d+)%?\s+zu\s+Chaoswiderstand",
        r"\+?(\d+)%?\s+to\s+Chaos\s+Resistance",
    ],
    "all_res": [
        r"\+?(\d+)%?\s+zu\s+allen\s+Elementarwiderst[äa]nden",
        r"\+?(\d+)%?\s+to\s+all\s+Elemental\s+Resistances",
    ],

    # ---------- ATTRIBUTE ----------
    "strength": [
        r"\+?(\d+)\s+zu\s+St[äa]rke",
        r"\+?(\d+)\s+to\s+Strength",
    ],
    "dexterity": [
        r"\+?(\d+)\s+zu\s+Geschick(?:lichkeit)?",
        r"\+?(\d+)\s+to\s+Dexterity",
    ],
    "intelligence": [
        r"\+?(\d+)\s+zu\s+Intelligenz",
        r"\+?(\d+)\s+to\s+Intelligence",
    ],
    "all_attributes": [
        r"\+?(\d+)\s+zu\s+allen\s+Attributen",
        r"\+?(\d+)\s+to\s+all\s+Attributes",
    ],

    # ---------- VERTEIDIGUNG ----------
    "armour": [
        r"(\d+)%\s+erh[öo]hte\s+R[üu]stung\b(?!\s+und)",
        r"(\d+)%\s+increased\s+Armour\b(?!\s+and)",
    ],
    "evasion": [
        r"(\d+)%\s+erh[öo]hte\s+Ausweich(?:wertung)?\b(?!\s+und)",
        r"(\d+)%\s+increased\s+Evasion(?:\s+Rating)?\b(?!\s+and)",
    ],
    "armour_es": [
        r"(\d+)%\s+erh[öo]hte\s+R[üu]stung\s+und\s+Energieschild",
        r"(\d+)%\s+increased\s+Armour\s+and\s+Energy\s+Shield",
    ],
    "eva_es": [
        r"(\d+)%\s+erh[öo]hte\s+Ausweich(?:wertung)?\s+und\s+Energieschild",
        r"(\d+)%\s+increased\s+Evasion\s+and\s+Energy\s+Shield",
    ],
    "armour_eva": [
        r"(\d+)%\s+erh[öo]hte\s+R[üu]stung\s+und\s+Ausweich(?:wertung)?",
        r"(\d+)%\s+increased\s+Armour\s+and\s+Evasion",
    ],

    # ---------- SCHADEN ----------
    "spell_damage": [
        r"(\d+)%\s+erh[öo]hter\s+Zauberschaden",
        r"(\d+)%\s+increased\s+Spell\s+Damage",
    ],
    "phys_damage": [
        r"(\d+)%\s+erh[öo]hter\s+physischer\s+Schaden",
        r"(\d+)%\s+increased\s+Physical\s+Damage",
    ],
    "elemental_damage": [
        r"(\d+)%\s+erh[öo]hter\s+Elementarschaden",
        r"(\d+)%\s+increased\s+Elemental\s+Damage",
    ],
    "fire_damage": [
        r"(\d+)%\s+erh[öo]hter\s+Feuerschaden",
        r"(\d+)%\s+increased\s+Fire\s+Damage",
    ],
    "cold_damage": [
        r"(\d+)%\s+erh[öo]hter\s+K[äa]lteschaden",
        r"(\d+)%\s+increased\s+Cold\s+Damage",
    ],
    "lightning_damage": [
        r"(\d+)%\s+erh[öo]hter\s+Blitzschaden",
        r"(\d+)%\s+increased\s+Lightning\s+Damage",
    ],
    "chaos_damage": [
        r"(\d+)%\s+erh[öo]hter\s+Chaosschaden",
        r"(\d+)%\s+increased\s+Chaos\s+Damage",
    ],

    # ---------- KRIT / SPEED ----------
    "crit_chance": [
        r"(\d+(?:[.,]\d+)?)%\s+erh[öo]hte\s+kritische\s+Trefferchance",
        r"(\d+(?:[.,]\d+)?)%\s+(?:to\s+|increased\s+)?Critical\s+(?:Hit\s+|Strike\s+)?Chance",
        r"\+?(\d+(?:[.,]\d+)?)%\s+zu\s+kritischer\s+Trefferchance",
    ],
    "crit_damage": [
        r"(\d+)%\s+erh[öo]hter\s+kritischer\s+Schadensbonus",
        r"(\d+)%\s+increased\s+Critical\s+Damage\s+Bonus",
    ],
    "attack_speed": [
        r"(\d+)%\s+erh[öo]hte\s+Angriffsgeschwindigkeit",
        r"(\d+)%\s+increased\s+Attack\s+Speed",
    ],
    "cast_speed": [
        r"(\d+)%\s+erh[öo]hte\s+Zaubergeschwindigkeit",
        r"(\d+)%\s+increased\s+Cast\s+Speed",
    ],
    "movement_speed": [
        r"(\d+)%\s+erh[öo]hte\s+Bewegungsgeschwindigkeit",
        r"(\d+)%\s+increased\s+Movement\s+Speed",
    ],

    # ---------- SKILLS / SONSTIGES ----------
    "spell_skills": [
        r"\+?(\d+)\s+zu\s+Stufen?\s+aller\s+Zauberfertigkeiten",
        r"\+?(\d+)\s+to\s+Level\s+of\s+all\s+Spell\s+Skills",
    ],
    "all_skills": [
        r"\+?(\d+)\s+zu\s+Stufen?\s+aller\s+Fertigkeiten",
        r"\+?(\d+)\s+to\s+Level\s+of\s+all\s+Skills",
    ],
    "mana_regen": [
        r"(\d+)%\s+erh[öo]hte\s+Manaregenerations(?:rate|-Rate)",
        r"(\d+)%\s+increased\s+Mana\s+Regeneration\s+Rate",
    ],
    "stun_threshold": [
        r"\+?(\d+)\s+zur\s+Bet[äa]ubungsschwelle",
        r"\+?(\d+)\s+to\s+Stun\s+Threshold",
    ],

    # ---------- "GAIN X% AS EXTRA ... DAMAGE" ----------
    "gain_fire": [
        r"(\d+)%\s+des\s+Schadens\s+als\s+(?:zus[äa]tzlichen|extra)\s+Feuerschaden",
        r"Gain\s+(\d+)%\s+of\s+(?:.*?\s+)?Damage\s+as\s+(?:Extra\s+)?Fire",
    ],
    "gain_cold": [
        r"(\d+)%\s+des\s+Schadens\s+als\s+(?:zus[äa]tzlichen|extra)\s+K[äa]lteschaden",
        r"Gain\s+(\d+)%\s+of\s+(?:.*?\s+)?Damage\s+as\s+(?:Extra\s+)?Cold",
    ],
    "gain_lightning": [
        r"(\d+)%\s+des\s+Schadens\s+als\s+(?:zus[äa]tzlichen|extra)\s+Blitzschaden",
        r"Gain\s+(\d+)%\s+of\s+(?:.*?\s+)?Damage\s+as\s+(?:Extra\s+)?Lightning",
    ],
    "gain_chaos": [
        r"(\d+)%\s+des\s+Schadens\s+als\s+(?:zus[äa]tzlichen|extra)\s+Chaosschaden",
        r"Gain\s+(\d+)%\s+of\s+(?:.*?\s+)?Damage\s+as\s+(?:Extra\s+)?Chaos",
    ],

    # ---------- FLAT DAMAGE TO ATTACKS ----------
    "flat_fire_atk": [
        r"verursacht\s+(\d+)\s+bis\s+\d+\s+Feuerschaden\s+bei\s+Angriffen",
        r"Adds\s+(\d+)\s+to\s+\d+\s+Fire\s+[Dd]amage\s+to\s+Attacks",
    ],
    "flat_cold_atk": [
        r"verursacht\s+(\d+)\s+bis\s+\d+\s+K[äa]lteschaden\s+bei\s+Angriffen",
        r"Adds\s+(\d+)\s+to\s+\d+\s+Cold\s+[Dd]amage\s+to\s+Attacks",
    ],
    "flat_lightning_atk": [
        r"verursacht\s+(\d+)\s+bis\s+\d+\s+Blitzschaden\s+bei\s+Angriffen",
        r"Adds\s+(\d+)\s+to\s+\d+\s+Lightning\s+[Dd]amage\s+to\s+Attacks",
    ],
}


# Welche Stats sind Prozentwerte (fuer Anzeige "%")
PERCENT_STATS = {
    "fire_res", "cold_res", "lightning_res", "chaos_res", "all_res",
    "armour", "evasion", "armour_es", "eva_es", "armour_eva",
    "spell_damage", "phys_damage", "elemental_damage", "fire_damage",
    "cold_damage", "lightning_damage", "chaos_damage",
    "crit_chance", "crit_damage", "attack_speed", "cast_speed",
    "movement_speed", "mana_regen",
    "gain_fire", "gain_cold", "gain_lightning", "gain_chaos",
}


# Vorkompilierte Muster (Performance)
_COMPILED = {
    key: [re.compile(p, re.IGNORECASE) for p in patterns]
    for key, patterns in STAT_DICT.items()
}


def clean_item_text(text):
    """Entfernt GGG-Tags [Tag|Anzeige] -> Anzeige."""
    return re.sub(r"\[([^\|\]]+)\|([^\]]+)\]", r"\2", text or "")


def parse_stats(text):
    """
    Zieht alle erkannten Stats aus einem Item-/OCR-Text (DE oder EN).
    Summiert mehrfache Vorkommen (z.B. 2x Leben).
    Gibt {stat_key: summe} zurueck.
    """
    text = clean_item_text(text)
    stats = {}
    for key, regexes in _COMPILED.items():
        total = 0.0
        found = False
        for rx in regexes:
            for m in rx.finditer(text):
                try:
                    val = float(m.group(1).replace(",", "."))
                    total += val
                    found = True
                except (ValueError, IndexError):
                    pass
        if found:
            stats[key] = round(total, 1)

    # Kombi-Stats zaehlen auch auf ihre Komponenten (siehe COMPOUND_TARGETS)
    _apply_compound(stats)
    return stats


# ------------------------------------------------------------
#  Split-Auswertung: flat ("+45 zu maximalem Leben") vs.
#  increased ("40% increased Energy Shield") - Basis fuer die
#  Effektive-Werte-Berechnung im Backend:
#     effektiv = (Basis + flat) * (1 + increased/100)
# ------------------------------------------------------------

# Kombi-Stats -> ihre Komponenten (genau das macht der Mod im Game):
#   "85% increased Armour and Energy Shield" -> +85 Ruestung, +85 ES
#   "+15% to all Elemental Resistances"      -> +15 Feuer, +15 Kaelte, +15 Blitz
COMPOUND_TARGETS = (
    ("eva_es",     ("energy_shield",)),
    ("armour_es",  ("energy_shield", "armour")),
    ("armour_eva", ("armour",)),
    ("all_res",    ("fire_res", "cold_res", "lightning_res")),
)


def _apply_compound(d):
    """Faellt Kombi-Stats auf ihre Komponenten in Dict d zurueck (summiert)."""
    for src, targets in COMPOUND_TARGETS:
        if src in d:
            for t in targets:
                d[t] = round(d.get(t, 0) + d[src], 1)


def _is_increased_text(text):
    """Erkannter Mod-Text: Multiplikator ("increased"/"erhöht") oder flat?"""
    t = text.lower()
    return ("increased" in t) or ("erhöht" in t) or ("erhoeht" in t)


def parse_stats_split(text):
    """
    Wie parse_stats, aber zerlegt die erkannten Werte in
      flat: additive Stats   ("+45 zu maximalem Leben", "+15 zu Feuerwiderstand")
      inc:  Multiplikatoren  ("40% increased Energy Shield", "85% erhöhte Rüstung")
    Kombi-Stats werden auf ihre Komponenten aufgeteilt (wie in parse_stats).
    Gibt (flat, inc) zurueck.
    """
    text = clean_item_text(text)
    flat, inc = {}, {}
    for key, regexes in _COMPILED.items():
        f = 0.0
        p = 0.0
        for rx in regexes:
            for m in rx.finditer(text):
                try:
                    val = float(m.group(1).replace(",", "."))
                except (ValueError, IndexError):
                    continue
                if _is_increased_text(m.group(0)):
                    p += val
                else:
                    f += val
        if f:
            flat[key] = round(f, 1)
        if p:
            inc[key] = round(p, 1)
    _apply_compound(flat)
    _apply_compound(inc)
    return flat, inc


# ---------- Slot-Erkennung (DE + EN) ----------
SLOT_KEYWORDS = {
    "Helm": ["helm", "helmet", "crown", "mask", "hood", "circlet", "burgonet", "greathelm",
             "haube", "krone", "maske", "kapuze", "diadem", "sturmhaube", "kettenhaube"],
    "BodyArmour": ["plate", "armour", "vest", "garb", "robe", "tunic", "jacket", "wraps",
                   "brigandine", "carapace",
                   "rüstung", "ruestung", "plattenrüstung", "plattenruestung", "robe",
                   "weste", "panzer", "wams", "kürass", "kuerass", "gewand", "kleid"],
    "Gloves": ["gloves", "mitts", "gauntlets", "grips",
               "handschuhe", "fäustlinge", "faeustlinge", "panzerhandschuhe", "griffe", "stulpen"],
    "Boots": ["boots", "greaves", "sandals", "shoes", "slippers",
              "stiefel", "sandalen", "beinschienen", "schuhe", "schläppchen",
              "schlaeppchen", "treter"],
    "Belt": ["belt", "sash", "braid", "girdle",
             "gürtel", "guertel", "schärpe", "schaerpe", "leibbinde", "koppel"],
    "Amulet": ["amulet", "necklace", "talisman", "pendant",
               "amulett", "halskette", "talisman", "anhänger", "anhaenger", "kette"],
    "Ring": ["ring", "band", "coil", "loop",
             "ring", "reif", "schleife"],
    "Weapon": ["staff", "wand", "sword", "axe", "mace", "bow", "dagger", "sceptre",
               "claw", "spear", "quarterstaff", "crossbow", "flail",
               "stab", "zauberstab", "schwert", "axt", "streitkolben", "einhandstreitkolben",
               "zweihandstreitkolben", "bogen", "dolch", "zepter", "klaue", "speer",
               "armbrust", "kampfstab", "zauberstecken", "morgenstern", "hellebarde"],
    "Offhand": ["shield", "buckler", "quiver", "focus",
                "schild", "tartsche", "köcher", "koecher", "fokus", "buckler",
                "turmschild", "rundschild"],
}


def guess_slot(text):
    """Raet aus dem (DE/EN) Item-Text, zu welchem Slot das Item gehoert."""
    low = clean_item_text(text).lower()
    best, best_hits = None, 0
    for slot, words in SLOT_KEYWORDS.items():
        hits = sum(1 for w in words if w in low)
        if hits > best_hits:
            best, best_hits = slot, hits
    return best
