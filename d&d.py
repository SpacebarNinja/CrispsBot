"""
D&D Roll System - The Golden Krispyre Tale
/roll command with character-specific dropdown, character webhook impersonation,
and auto-sudo for quoted roleplay in the designated channel.

All output formatting lives in the OUTPUT FORMATTING section - edit there to
change how roll results look.
"""

import io
import discord
import random
import re
import os
import math
from pathlib import Path
from typing import Optional

# ======================== CONFIGURATION ========================

# Category where messages starting with " auto-sudo as the player's character
QUOTE_CATEGORY_ID = 1499581665171734658

# Discord user ID of the Dungeon Master
DM_USER_ID = "779245588596129812"

# DM borrows this character's stats when using /roll (debug purposes)
DM_ROLL_AS = "aeran"

# Proficiency bonus - level 1
PROF_BONUS = 2

# Path to character profile pictures
PFP_DIR = Path(__file__).parent / "D&D PFPs"

# Discord user ID → character key
# DM is mapped to aeran for rolling; quotes still show as "Dungeon Master"
PLAYER_CHARS: dict[str, str] = {
    "779245588596129812":  "aeran",   # DM (Space) → Aeran for debug rolls
    "1226954275587100834": "viola",   # VOICE
    "1368849513980104745": "isaiah",  # ALFRED
    "837999559547420702":  "bablino", # RYLEY
    "1389163922451333160": "aeran",   # BIRB
    "921246592269430885":  "faye",    # ELLA
    "1372181809298931815": "steria",  # AYA
}

# ======================== CHARACTER DATA ========================
# Ability scores are final values (racial bonuses already applied).

CHARACTERS: dict[str, dict] = {
    "viola": {
        "name":        'Viola "Vi" Morvael',
        "race":        "Tiefling (Glasya)",
        "cls":         "Wizard",
        "pfp":         "PFP_Viola.png",
        "hp":          8,
        "hit_die":     6,
        "str": 5,  "dex": 15, "con": 15,
        "int": 18, "wis": 11, "cha": 14,
        "save_profs":  {"int", "wis"},
        "skill_profs": {"arcana", "history"},
        "features":    [],
        "attack_stat": "int",
        "speed":       30,
        "weapons": [
            {"name": "Fire Bolt",    "emoji": "🔥", "stat": "int", "extra": -1, "desc": "Ranged spell, 1d10",   "dmg": (1, 10, 0), "kind": "cantrip"},
            {"name": "Sleep",        "emoji": "💤", "stat": "int", "extra":  0, "desc": "1st Level, 5d8 HP effect", "dmg": (5, 8, 0), "kind": "spell", "type": "hp_affected", "has_atk": False},
            {"name": "Cloud of Daggers", "emoji": "🌀", "stat": "int", "extra": 0, "desc": "2nd Level, 4d4 slashing per turn in area", "dmg": (4, 4, 0), "kind": "spell", "type": "damage", "has_atk": False},
            {"name": "Dagger",       "emoji": "🗡️",  "stat": "dex", "extra":  0, "desc": "Melee/Ranged, 1d4+2",  "dmg": (1,  4, 2)},
            {"name": "Quarterstaff", "emoji": "🦯", "stat": "str", "extra":  1, "desc": "Melee, 1d6-3",          "dmg": (1,  6,-3)},
        ],
    },
    "isaiah": {
        "name":        "Isaiah Sylvester",
        "race":        "Dhampir",
        "cls":         "Eldritch Knight",
        "pfp":         "PFP_Isaiah.png",
        "hp":          12,
        "hit_die":     10,
        "str": 14, "dex": 11, "con": 15,
        "int": 13, "wis": 12, "cha": 12,
        "save_profs":  {"str", "con"},
        "skill_profs": {"athletics", "perception"},
        "features":    [],
        "attack_stat": "str",
        "speed":       30,
        "weapons": [
            {"name": "Longsword",      "emoji": "⚔️",  "stat": "str", "extra": 0, "desc": "Melee, 1d8+2",   "dmg": (1, 8, 2)},
            {"name": "Light Crossbow", "emoji": "🎯", "stat": "dex", "extra": 0, "desc": "Ranged, 1d8",     "dmg": (1, 8, 0)},
            {"name": "Vampiric Bite",  "emoji": "🧛", "stat": "str", "extra": 0, "desc": "1d4+2 damage + heal 2", "dmg": (1, 4, 2)},
        ],
    },
    "aeran": {
        "name":        "Aeran Wrenkhyre",
        "race":        "Aarakocra",
        "cls":         "Ranger",
        "pfp":         "PFP_Aeran.png",
        "hp":          10,
        "hit_die":     10,
        "str": 12, "dex": 18, "con": 10,
        "int": 14, "wis": 15, "cha": 13,
        "save_profs":  {"str", "dex"},
        "skill_profs": {"nature", "perception", "stealth", "survival"},
        "features":    ["archery_style"],
        "attack_stat": "dex",
        "speed":       30,
        "weapons": [
            {"name": "Longbow",       "emoji": "🏹", "stat": "dex", "extra": 0, "desc": "Ranged, 1d8+4",                      "dmg": (1, 8, 4)},
            {"name": "Shortsword",    "emoji": "🗡️",  "stat": "dex", "extra": 0, "desc": "Melee, 1d6+4",                       "dmg": (1, 6, 4)},
            {"name": "Talons",        "emoji": "🦅", "stat": "dex", "extra": 0, "desc": "Natural, 1d6+4",                     "dmg": (1, 6, 4)},
            {"name": "Hunter's Mark", "emoji": "🎯", "stat": "wis", "extra": 0, "desc": "1st Level Conc., +1d6 per hit",          "dmg": (1, 6, 0), "kind": "spell", "type": "damage", "has_atk": False},
            {"name": "Cure Wounds",   "emoji": "💚", "stat": "wis", "extra": 0, "desc": "1st Level, 1d8+2 HP healing",            "dmg": (1, 8, 2), "kind": "spell", "type": "heal",   "has_atk": False},
        ],
    },
    "bablino": {
        "name":        'Bablino "Babi" Darvpinpin',
        "race":        "Goblin",
        "cls":         "Barbarian",
        "pfp":         "PFP_Bablino.png",
        "hp":          14,
        "hit_die":     12,
        "str": 15, "dex": 13, "con": 14,
        "int": 4,  "wis": 12, "cha": 11,
        "save_profs":  {"str", "con"},
        "skill_profs": {"athletics", "intimidation", "stealth"},
        "features":    ["rage", "reckless_attack", "danger_sense"],
        "attack_stat": "str",
        "speed":       30,
        "weapons": [
            {"name": "Greataxe",     "emoji": "🪓", "stat": "str", "extra": 0, "desc": "Melee, 1d12+2",          "dmg": (1, 12, 2)},
            {"name": "Handaxe",     "emoji": "🔪", "stat": "str", "extra": 0, "desc": "Melee, 1d6+2",            "dmg": (1,  6, 2)},
            {"name": "Javelin",     "emoji": "🔱", "stat": "str", "extra": 0, "desc": "Thrown, 1d6+2",           "dmg": (1,  6, 2)},
            {"name": "Light Crossbow", "emoji": "🎯", "stat": "dex", "extra": 0, "desc": "Ranged, 1d8+1 — 10 bolts", "dmg": (1,  8, 1)},
        ],
    },
    "faye": {
        "name":        'Faye Nelia "Fey" Peregrine',
        "race":        "Wood Elf",
        "cls":         "Druid",
        "pfp":         "PFP_Faye.png",
        "hp":          10,
        "hit_die":     8,
        "str": 12, "dex": 16, "con": 15,
        "int": 13, "wis": 18, "cha": 8,
        "save_profs":  {"int", "wis"},
        "skill_profs": {"animal_handling", "nature", "perception", "survival"},
        "features":    [],
        "attack_stat": "wis",
        "speed":       35,
        "weapons": [
            {"name": "Thorn Whip",   "emoji": "🧶", "stat": "wis", "extra": 0, "desc": "Melee spell, 1d6",    "dmg": (1, 6, 0), "kind": "cantrip"},
            {"name": "Shillelagh",   "emoji": "🌿", "stat": "wis", "extra": 0, "desc": "Melee spell, 1d8+4",  "dmg": (1, 8, 4), "kind": "cantrip"},
            {"name": "Healing Word", "emoji": "✨", "stat": "wis", "extra": 0, "desc": "1st Level, 1d4+4 healing", "dmg": (1, 4, 4), "kind": "spell", "type": "heal", "has_atk": False},
            {"name": "Scimitar",     "emoji": "⚔️",  "stat": "dex", "extra": 0, "desc": "Melee, 1d6+3",       "dmg": (1, 6, 3)},
            {"name": "Quarterstaff", "emoji": "🦯", "stat": "str", "extra": 0, "desc": "Melee, 1d6+1",        "dmg": (1, 6, 1)},
        ],
    },
    "steria": {
        "name":        "Steria Starspire",
        "race":        "Kalashtar",
        "cls":         "Paladin",
        "pfp":         "PFP_Steria.png",
        "hp":          11,
        "hit_die":     10,
        "str": 15, "dex": 12, "con": 13,
        "int": 13, "wis": 16, "cha": 16,
        "save_profs":  {"wis", "cha"},
        "skill_profs": {"insight", "persuasion"},
        "features":    ["kalashtar_dual_mind"],
        "attack_stat": "str",
        "speed":       30,
        "weapons": [
            {"name": "Longsword",     "emoji": "⚔️",  "stat": "str", "extra": 0, "desc": "Melee, 1d8+2",                       "dmg": (1, 8, 2)},
            {"name": "Javelin",     "emoji": "🔱", "stat": "str", "extra": 0, "desc": "Thrown, 1d6+2",                      "dmg": (1, 6, 2)},
            {"name": "Divine Smite",   "emoji": "✨", "stat": "cha", "extra": 0, "desc": "1st Level Slot, 2d8 radiant on hit",  "dmg": (2, 8, 0), "kind": "spell", "type": "damage", "has_atk": False},
            {"name": "Divine Favor",   "emoji": "🌟", "stat": "cha", "extra": 0, "desc": "Concentration, +1d4 radiant per hit", "dmg": (1, 4, 0), "kind": "spell", "type": "damage", "has_atk": False},
            {"name": "Wrathful Smite", "emoji": "😤", "stat": "cha", "extra": 0, "desc": "Concentration, +1d6 psychic on hit",  "dmg": (1, 6, 0), "kind": "spell", "type": "damage", "has_atk": False},
            {"name": "Searing Smite",  "emoji": "🔥", "stat": "cha", "extra": 0, "desc": "Concentration, +1d6 fire on hit",     "dmg": (1, 6, 0), "kind": "spell", "type": "damage", "has_atk": False},
        ],
    },
}

STAT_LABELS = {
    "str": "Strength",    "dex": "Dexterity",     "con": "Constitution",
    "int": "Intelligence","wis": "Wisdom",         "cha": "Charisma",
}
STAT_ABBR = {
    "str": "STR", "dex": "DEX", "con": "CON",
    "int": "INT", "wis": "WIS", "cha": "CHA",
}

# Skills: key → (base_stat, display_label)
# ★ marks show in the roll dropdowns for proficient skills per character.
SKILLS: dict[str, tuple[str, str]] = {
    "athletics":       ("str", "Athletics"),
    "acrobatics":      ("dex", "Acrobatics"),
    "sleight_of_hand": ("dex", "Sleight of Hand"),
    "stealth":         ("dex", "Stealth"),
    "arcana":          ("int", "Arcana"),
    "history":         ("int", "History"),
    "investigation":   ("int", "Investigation"),
    "nature":          ("int", "Nature"),
    "religion":        ("int", "Religion"),
    "animal_handling": ("wis", "Animal Handling"),
    "insight":         ("wis", "Insight"),
    "medicine":        ("wis", "Medicine"),
    "perception":      ("wis", "Perception"),
    "survival":        ("wis", "Survival"),
    "deception":       ("cha", "Deception"),
    "intimidation":    ("cha", "Intimidation"),
    "performance":     ("cha", "Performance"),
    "persuasion":      ("cha", "Persuasion"),
}

SKILL_DESCS: dict[str, str] = {
    "athletics":       "Climb, swim, jump, grapple",
    "acrobatics":      "Balance, tumble, dodge",
    "sleight_of_hand": "Pickpocket, conceal, trick",
    "stealth":         "Move unseen and unheard",
    "arcana":          "Recall magic, spells, planes",
    "history":         "Recall lore, events, lineages",
    "investigation":   "Search, deduce, examine clues",
    "nature":          "Know flora, fauna, weather",
    "religion":        "Know gods, rites, undead",
    "animal_handling": "Calm, train, read animals",
    "insight":         "Read intentions, detect lies",
    "medicine":        "Stabilize, diagnose, treat wounds",
    "perception":      "Spot, hear, sense threats",
    "survival":        "Track, forage, navigate wilderness",
    "deception":       "Convincingly lie, bluff, misdirect",
    "intimidation":    "Threaten, coerce, unsettle",
    "performance":     "Entertain, sing, act, play",
    "persuasion":      "Convince through reason or charm",
}

# ======================== CLASS / RACIAL FEATURES ========================
# Each entry: adv_on = roll choice values that get advantage while active.
# auto_on = toggled ON by default when the RollView opens.
# attack_bonus = flat bonus added to the attack roll total.

FEATURE_DEFS: dict[str, dict] = {
    "rage": {
        "label":  "⚡ Rage",
        "desc":   "ADV: STR checks, STR saves, Athletics",
        "adv_on": {"check_str", "save_str", "skill_athletics"},
    },
    "reckless_attack": {
        "label":  "🗡️ Reckless Atk",
        "desc":   "ADV: Attack rolls (melee STR)",
        "adv_on": {"attack"},
    },
    "danger_sense": {
        "label":  "👁️ Danger Sense",
        "desc":   "ADV: DEX saves (vs visible threats)",
        "adv_on": {"save_dex"},
    },
    "kalashtar_dual_mind": {
        "label":   "🧧 Dual Mind",
        "desc":    "ADV: all WIS saves (Kalashtar)",
        "adv_on":  {"save_wis"},
    },
    "archery_style": {
        "label":        "🏹 Archery Style",
        "desc":         "+2 to ranged attack rolls",
        "attack_bonus": 2,
    },
}

# ======================== OUTPUT FORMATTING ========================
# ─── All roll output is assembled here. Edit this section to restyle results. ───

def _mod(score: int) -> int:
    return math.floor((score - 10) / 2)

def _fmt_mod(m: int) -> str:
    return f"+{m}" if m >= 0 else str(m)

def _d20() -> int:
    return random.randint(1, 20)

def _d20_with_mode(adv_mode=None):
    """Roll d20 respecting advantage/disadvantage. Returns (result, annotation)."""
    if adv_mode == "advantage":
        r1, r2 = random.randint(1, 20), random.randint(1, 20)
        kept, dropped = max(r1, r2), min(r1, r2)
        return kept, f" *(kept ~~`{dropped}`~~)*"
    elif adv_mode == "disadvantage":
        r1, r2 = random.randint(1, 20), random.randint(1, 20)
        kept, dropped = min(r1, r2), max(r1, r2)
        return kept, f" *(kept ~~`{dropped}`~~)*"
    return random.randint(1, 20), ""

def _crit_tag(roll: int) -> str:
    if roll == 20: return " ✨ **NAT 20!**"
    if roll == 1:  return " 💀 **NAT 1**"
    return ""

def _adv_suffix(adv_mode) -> str:
    if adv_mode == "advantage":    return " *(w/Advantage)*"
    if adv_mode == "disadvantage": return " *(w/Disadvantage)*"
    return ""


def _effective_adv(manual_adv: str | None, active_features: set, choice: str) -> str | None:
    """Compute 5e-correct adv/dis for a specific roll, merging manual toggle and active features."""
    feat_key = "attack" if choice.startswith("weapon_") else choice
    feature_adv = any(
        feat_key in FEATURE_DEFS[fk].get("adv_on", set())
        for fk in active_features if fk in FEATURE_DEFS
    )
    has_adv = (manual_adv == "advantage") or feature_adv
    has_dis = manual_adv == "disadvantage"   # no current feature grants dis
    if has_adv and has_dis: return None       # cancel per 5e rules
    if has_adv:             return "advantage"
    if has_dis:             return "disadvantage"
    return None


def fmt_ability_check(char: dict, stat: str, adv_mode=None) -> str:
    mod  = _mod(char[stat])
    roll, adv_note = _d20_with_mode(adv_mode)
    eq   = f"`{roll}`{adv_note}" + (f" {_fmt_mod(mod)}" if mod != 0 else "")
    return (
        f"🎲 **{STAT_LABELS[stat]} Check**{_adv_suffix(adv_mode)}{_crit_tag(roll)}\n"
        f"╰ {eq} = **{roll + mod}**"
    )


def fmt_skill_check(char: dict, skill_key: str, adv_mode=None) -> str:
    stat, label = SKILLS[skill_key]
    mod      = _mod(char[stat])
    has_prof = skill_key in char.get("skill_profs", set())
    bonus    = mod + (PROF_BONUS if has_prof else 0)
    roll, adv_note = _d20_with_mode(adv_mode)
    total    = roll + bonus
    breakdown = f"`{roll}`{adv_note}" + (f" {_fmt_mod(bonus)}" if bonus != 0 else "")
    prof_tag  = " *(proficient)*" if has_prof else ""
    if has_prof and mod != 0:
        breakdown += f" *(mod {_fmt_mod(mod)}, prof +{PROF_BONUS})*"
    elif has_prof:
        breakdown += f" *(prof +{PROF_BONUS})*"
    return (
        f"🎲 **{label} Check**{_adv_suffix(adv_mode)}{prof_tag}{_crit_tag(roll)}\n"
        f"╰ {breakdown} = **{total}**"
    )


def fmt_saving_throw(char: dict, stat: str, adv_mode=None) -> str:
    mod      = _mod(char[stat])
    has_prof = stat in char["save_profs"]
    bonus    = mod + (PROF_BONUS if has_prof else 0)
    roll, adv_note = _d20_with_mode(adv_mode)
    total    = roll + bonus

    breakdown = f"`{roll}`{adv_note}" + (f" {_fmt_mod(bonus)}" if bonus != 0 else "")
    prof_tag  = " *(proficient)*" if has_prof else ""

    # Show the split when proficiency is involved
    if has_prof and mod != 0:
        breakdown += f" *(mod {_fmt_mod(mod)}, prof +{PROF_BONUS})*"
    elif has_prof:
        breakdown += f" *(prof +{PROF_BONUS})*"

    return (
        f"🎲 **{STAT_LABELS[stat]} Save**{_adv_suffix(adv_mode)}{prof_tag}{_crit_tag(roll)}\n"
        f"╰ {breakdown} = **{total}**"
    )


def fmt_attack_roll(char: dict, weapon: dict, adv_mode=None) -> tuple[str, int, bool]:
    """Roll attack only. Returns (text, raw_d20_roll, is_crit_hit)."""
    stat     = weapon["stat"]
    bonus    = _mod(char[stat]) + PROF_BONUS + weapon.get("extra", 0)
    roll, adv_note = _d20_with_mode(adv_mode)
    emoji    = weapon["emoji"]
    kind_tag = {"cantrip": " (Cantrip)", "spell": " (Spell)"}.get(weapon.get("kind", ""), "")
    name     = f"{weapon['name']}{kind_tag}"

    if roll == 1:
        text = (
            f"{emoji} **{name}**{_adv_suffix(adv_mode)} 💀 **CRITICAL MISS**\n"
            f"╰ `1`{adv_note}"
        )
        return text, 1, False

    is_crit = roll == 20
    crit    = " ✨ **CRITICAL HIT!**" if is_crit else ""
    total   = roll + bonus
    text = (
        f"{emoji} **{name}**{_adv_suffix(adv_mode)}{crit}\n"
        f"╰ `{roll}`{adv_note} {_fmt_mod(bonus)} = **{total}**"
    )
    return text, roll, is_crit


def fmt_initiative(char: dict, adv_mode=None) -> str:
    mod   = _mod(char["dex"])
    roll, adv_note = _d20_with_mode(adv_mode)
    total = roll + mod
    return (
        f"🎲 **Initiative**{_adv_suffix(adv_mode)}{_crit_tag(roll)}\n"
        f"╰ `{roll}`{adv_note} {_fmt_mod(mod)} *(DEX)* = **{total}**"
    )


def roll_initiative(char: dict, adv_mode=None) -> tuple[int, str]:
    """Roll initiative and return (total, formatted_text)."""
    mod = _mod(char["dex"])
    roll, adv_note = _d20_with_mode(adv_mode)
    total = roll + mod
    text = (
        f"🎲 **Initiative**{_adv_suffix(adv_mode)}{_crit_tag(roll)}\n"
        f"╰ `{roll}`{adv_note} {_fmt_mod(mod)} *(DEX)* = **{total}**"
    )
    return total, text


def fmt_death_save(adv_mode=None) -> str:
    roll, adv_note = _d20_with_mode(adv_mode)
    if roll == 20:
        verdict = "✨ **NAT 20 - Back on your feet!**"
        note    = "Instant stabilize + 1 HP"
    elif roll >= 10:
        verdict = "✅ **Success**"
        note    = "Holding on..."
    elif roll == 1:
        verdict = "💀 **NAT 1 - Two failures at once**"
        note    = "Fading fast..."
    else:
        verdict = "❌ **Failure**"
        note    = "Fading fast..."
    return (
        f"🎲 **Death Saving Throw**{_adv_suffix(adv_mode)}\n"
        f"╰ `{roll}`{adv_note} → {verdict}\n"
        f"  *{note}*"
    )


def fmt_hit_die(char: dict) -> str:
    con_mod = _mod(char["con"])
    die     = char["hit_die"]
    roll    = random.randint(1, die)
    healed  = max(1, roll + con_mod)
    return (
        f"🎲 **Hit Die** *(Short Rest)*\n"
        f"╰ `d{die}: {roll}` {_fmt_mod(con_mod)} *(CON)* = **+{healed} HP**"
    )


def fmt_raw_die(sides: int) -> str:
    roll = random.randint(1, sides)
    return (
        f"🎲 **d{sides}**\n"
        f"╰ → **{roll}**"
    )


def fmt_damage_roll(formula: str, rolls: list[int], modifier: int, total: int, stat_mod: int = 0, stat_label: str = "") -> str:
    roll_str  = " + ".join(f"`{r}`" for r in rolls)
    mod_str   = f" {_fmt_mod(modifier)}" if modifier != 0 else ""
    stat_str  = f" {_fmt_mod(stat_mod)} *({stat_label})*" if stat_mod != 0 else ""
    return (
        f"🎲 **Damage** `{formula}`\n"
        f"╰ {roll_str}{mod_str}{stat_str} = **{total} dmg**"
    )


def fmt_custom_roll(formula: str, rolls: list[int], modifier: int, total: int) -> str:
    roll_str = " + ".join(f"`{r}`" for r in rolls)
    mod_str  = f" {_fmt_mod(modifier)}" if modifier != 0 else ""
    return (
        f"🎲 **Custom** `{formula}`\n"
        f"╰ {roll_str}{mod_str} = **{total}**"
    )


def fmt_weapon_damage(char: dict, weapon: dict, is_crit: bool = False) -> str:
    kind_tag     = {"cantrip": " (Cantrip)", "spell": " (Spell)"}.get(weapon.get("kind", ""), "")
    display_name = f"{weapon['name']}{kind_tag}"
    if "dmg" not in weapon:
        return f"{weapon['emoji']} **{display_name}** — *(no dice to roll)*"
    
    count, sides, mod = weapon["dmg"]
    dice_count = count * 2 if is_crit else count
    rolls   = roll_dice(dice_count, sides)
    total   = sum(rolls) + mod
    if weapon.get("type", "damage") == "damage":
        total = max(1, total)

    roll_str = " + ".join(f"`{r}`" for r in rolls)
    mod_str  = f" {_fmt_mod(mod)}" if mod != 0 else ""
    formula  = f"{dice_count}d{sides}" + (f"+{mod}" if mod > 0 else str(mod) if mod < 0 else "")
    crit_note = " ✨ *(crit — double dice)*" if is_crit else ""

    atype = weapon.get("type", "damage")
    if atype == "heal": label, unit = "healing", "HP"
    elif atype == "hp_affected": label, unit = "HP affected", "HP"
    else: label, unit = "damage", "dmg"

    return (
        f"{weapon['emoji']} **{display_name}** {label} `{formula}`{crit_note}\n"
        f"╰ {roll_str}{mod_str} = **{total} {unit}**"
    )

# ======================== DICE PARSER ========================

_DICE_RE = re.compile(r"^(\d+)?d(\d+)\s*([+\-]\s*\d+)?$", re.IGNORECASE)

def parse_dice(formula: str) -> Optional[tuple[int, int, int]]:
    """Parse '2d6+3', 'd8', '1d4-1'. Returns (count, sides, modifier) or None."""
    formula = formula.strip().replace(" ", "")
    m = _DICE_RE.match(formula)
    if not m:
        return None
    count    = int(m.group(1)) if m.group(1) else 1
    sides    = int(m.group(2))
    modifier = int((m.group(3) or "0").replace(" ", ""))
    if not (1 <= count <= 99 and 2 <= sides <= 1000):
        return None
    return count, sides, modifier

def roll_dice(count: int, sides: int) -> list[int]:
    return [random.randint(1, sides) for _ in range(count)]

# ======================== ROLL RESOLVER ========================

def resolve_roll(choice: str, char: dict, adv_mode=None, atk_extra: int = 0) -> str:
    """Map a select menu value to a formatted roll string. (weapon_ is handled separately.)"""
    if choice.startswith("weapon_"):
        idx = int(choice[len("weapon_"):])
        text, _, _ = fmt_attack_roll(char, char["weapons"][idx], adv_mode)
        return text
    if choice.startswith("dmg_"):
        idx = int(choice[len("dmg_"):])
        return fmt_weapon_damage(char, char["weapons"][idx])
    if choice.startswith("check_"):
        return fmt_ability_check(char, choice[len("check_"):], adv_mode)
    if choice.startswith("skill_"):
        return fmt_skill_check(char, choice[len("skill_"):], adv_mode)
    if choice.startswith("save_"):
        return fmt_saving_throw(char, choice[len("save_"):], adv_mode)
    if choice.startswith("die_"):
        return fmt_raw_die(int(choice[len("die_"):]))
    dispatch = {
        "initiative":  lambda: fmt_initiative(char, adv_mode),
        "death_save":  lambda: fmt_death_save(adv_mode),
        "hit_die":     lambda: fmt_hit_die(char),
    }
    fn = dispatch.get(choice)
    return fn() if fn else "❌ Unknown roll type."

# ======================== WEBHOOK MANAGEMENT ========================

_webhook_cache: dict[str, discord.Webhook] = {}  # "channel_id:key"


async def _get_char_webhook(channel: discord.TextChannel, char_key: str) -> discord.Webhook:
    """Return (or create) a per-character webhook with their PFP baked in as avatar."""
    cache_key = f"{channel.id}:{char_key}"
    if cache_key in _webhook_cache:
        return _webhook_cache[cache_key]

    char     = CHARACTERS[char_key]
    wh_name  = f"DnD_{char_key.capitalize()}"

    for wh in await channel.webhooks():
        if wh.name == wh_name:
            # Repair missing avatar (happens if webhook was created before PFP was deployed)
            if wh.avatar is None:
                pfp_path = PFP_DIR / char["pfp"]
                if pfp_path.exists():
                    try:
                        await wh.edit(avatar=pfp_path.read_bytes())
                    except Exception as e:
                        print(f"[DnD] Could not update avatar for {wh_name}: {e}")
            _webhook_cache[cache_key] = wh
            return wh

    pfp_path     = PFP_DIR / char["pfp"]
    avatar_bytes = pfp_path.read_bytes() if pfp_path.exists() else None

    wh = await channel.create_webhook(name=wh_name, avatar=avatar_bytes)
    _webhook_cache[cache_key] = wh
    return wh


async def _get_dm_webhook(channel: discord.TextChannel) -> discord.Webhook:
    """Return (or create) a Dungeon Master webhook with PFP_DM.png baked in as avatar."""
    cache_key = f"{channel.id}:dm"
    if cache_key in _webhook_cache:
        return _webhook_cache[cache_key]
    pfp_path = PFP_DIR / "PFP_DM.png"
    for wh in await channel.webhooks():
        if wh.name == "DnD_DungeonMaster":
            if wh.avatar is None and pfp_path.exists():
                try:
                    await wh.edit(avatar=pfp_path.read_bytes())
                except Exception as e:
                    print(f"[DnD] Could not update DM avatar: {e}")
            _webhook_cache[cache_key] = wh
            return wh
    avatar_bytes = pfp_path.read_bytes() if pfp_path.exists() else None
    wh = await channel.create_webhook(name="DnD_DungeonMaster", avatar=avatar_bytes)
    _webhook_cache[cache_key] = wh
    return wh


async def _send_as_char(
    channel: discord.abc.Messageable,
    char_key: str,
    content: str,
    files: list = None,
    view: discord.ui.View = None,
):
    """Send as a character. Works in both TextChannels and Threads.
    Returns the sent WebhookMessage if a view was attached (or None otherwise)."""
    char = CHARACTERS[char_key]
    wh_channel = channel.parent if isinstance(channel, discord.Thread) else channel
    if not isinstance(wh_channel, discord.TextChannel):
        return None
    wh = await _get_char_webhook(wh_channel, char_key)
    send_kw = dict(username=char["name"], allowed_mentions=discord.AllowedMentions.none())
    if isinstance(channel, discord.Thread):
        send_kw["thread"] = channel
    if files:
        send_kw["files"] = files
    if view is not None:
        send_kw["view"] = view
        send_kw["wait"] = True
    try:
        if content:
            return await wh.send(content, **send_kw)
        else:
            return await wh.send(**send_kw)
    except discord.NotFound:
        # Webhook was deleted — bust cache and recreate
        _webhook_cache.pop(f"{wh_channel.id}:{char_key}", None)
        wh = await _get_char_webhook(wh_channel, char_key)
        if content:
            return await wh.send(content, **send_kw)
        else:
            return await wh.send(**send_kw)


async def _send_as_dm(
    channel: discord.abc.Messageable,
    content: str,
    files: list = None,
) -> None:
    """Send as Dungeon Master using PFP_DM.png baked into the webhook."""
    wh_channel = channel.parent if isinstance(channel, discord.Thread) else channel
    if not isinstance(wh_channel, discord.TextChannel):
        return
    wh = await _get_dm_webhook(wh_channel)
    send_kw = dict(
        username="Dungeon Master",
        allowed_mentions=discord.AllowedMentions.none(),
    )
    if isinstance(channel, discord.Thread):
        send_kw["thread"] = channel
    if files:
        send_kw["files"] = files
    try:
        if content:
            await wh.send(content, **send_kw)
        else:
            await wh.send(**send_kw)
    except discord.NotFound:
        # Webhook was deleted — bust cache and recreate
        _webhook_cache.pop(f"{wh_channel.id}:dm", None)
        wh = await _get_dm_webhook(wh_channel)
        if content:
            await wh.send(content, **send_kw)
        else:
            await wh.send(**send_kw)

# ======================== MODALS ========================

# ── DM-specific modals (no character stat auto-apply) ──

class DMAttackModal(discord.ui.Modal, title="DM Attack Roll"):
    formula = discord.ui.TextInput(
        label="Dice Formula",
        placeholder="e.g.  d20+5  |  d20  |  d20-1",
        max_length=30,
    )

    def __init__(self, roll_interaction: discord.Interaction, adv_mode=None):
        super().__init__()
        self.roll_interaction = roll_interaction
        self.adv_mode         = adv_mode

    async def on_submit(self, interaction: discord.Interaction):
        parsed = parse_dice(self.formula.value.strip() or "d20")
        if not parsed:
            await interaction.response.send_message("❌ Invalid formula — try `d20+5` or `d20`.", ephemeral=True)
            return
        _, _, mod = parsed
        roll, adv_note = _d20_with_mode(self.adv_mode)
        total = roll + mod
        adv_str = _adv_suffix(self.adv_mode)
        if roll == 1:
            text = (
                f"🎲 **Attack Roll**{adv_str} 💀 **CRITICAL MISS**\n"
                f"╰ `1`{adv_note}"
            )
        else:
            crit    = " ✨ **CRITICAL HIT!**" if roll == 20 else ""
            mod_str = f" {_fmt_mod(mod)}" if mod != 0 else ""
            text = (
                f"🎲 **Attack Roll**{adv_str}{crit}\n"
                f"╰ `{roll}`{adv_note}{mod_str} = **{total}**"
            )
        await interaction.response.defer(ephemeral=True)
        await _send_as_dm(interaction.channel, text)
        try:
            await self.roll_interaction.delete_original_response()
        except Exception:
            pass


class DMDiceModal(discord.ui.Modal, title="DM Dice Roll"):
    formula = discord.ui.TextInput(
        label="Dice Formula",
        placeholder="e.g.  2d8+3  |  d6  |  3d4-1",
        max_length=30,
    )

    def __init__(self, roll_interaction: discord.Interaction, label: str = "Damage"):
        super().__init__(title=f"DM {label} Roll")
        self.roll_interaction = roll_interaction
        self.label            = label

    async def on_submit(self, interaction: discord.Interaction):
        parsed = parse_dice(self.formula.value)
        if not parsed:
            await interaction.response.send_message("❌ Invalid formula — try `2d6+3` or `d8`.", ephemeral=True)
            return
        count, sides, modifier = parsed
        rolls = roll_dice(count, sides)
        total = sum(rolls) + modifier
        if self.label == "Damage":
            text = fmt_damage_roll(self.formula.value.strip(), rolls, modifier, total)
        else:
            text = fmt_custom_roll(self.formula.value.strip(), rolls, modifier, total)
        await interaction.response.defer(ephemeral=True)
        await _send_as_dm(interaction.channel, text)
        try:
            await self.roll_interaction.edit_original_response(content="✅ Done! Check the channel.", view=None)
        except Exception:
            pass


# ── DM Roll View ──

class DMRollAdvButton(discord.ui.Button):
    def __init__(self, mode: str):
        label = "🔼 w/ Advantage?" if mode == "advantage" else "🔽 w/ Disadvantage?"
        super().__init__(label=label, style=discord.ButtonStyle.secondary, row=1)
        self.mode = mode

    async def callback(self, interaction: discord.Interaction):
        view: DMRollView = self.view
        view.adv_mode = None if view.adv_mode == self.mode else self.mode
        for item in view.children:
            if isinstance(item, DMRollAdvButton):
                if view.adv_mode == item.mode:
                    item.style = discord.ButtonStyle.success if item.mode == "advantage" else discord.ButtonStyle.danger
                else:
                    item.style = discord.ButtonStyle.secondary
        await interaction.response.edit_message(view=view)


class DMRollView(discord.ui.View):
    def __init__(self, roll_interaction: discord.Interaction):
        super().__init__(timeout=90)
        self.adv_mode         = None
        self.roll_interaction = roll_interaction

    @discord.ui.button(label="⚔️ Attack Roll", style=discord.ButtonStyle.primary, row=0)
    async def attack_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DMAttackModal(self.roll_interaction, self.adv_mode))

    @discord.ui.button(label="🗡️ Damage Roll", style=discord.ButtonStyle.secondary, row=0)
    async def damage_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DMDiceModal(self.roll_interaction, "Damage"))

    @discord.ui.button(label="✏️ Custom Roll", style=discord.ButtonStyle.secondary, row=0)
    async def custom_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DMDiceModal(self.roll_interaction, "Custom"))

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


# ── Player character modals ──

class DamageModal(discord.ui.Modal, title="Damage Roll"):
    formula = discord.ui.TextInput(
        label="Dice Formula",
        placeholder="e.g.  2d6  |  1d8  |  d4  (atk modifier auto-added)",
        max_length=30,
    )

    def __init__(self, char_key: str, roll_interaction: discord.Interaction):
        super().__init__()
        self.char_key         = char_key
        self.roll_interaction = roll_interaction

    async def on_submit(self, interaction: discord.Interaction):
        parsed = parse_dice(self.formula.value)
        if not parsed:
            await interaction.response.send_message(
                "❌ Invalid formula - try something like `2d6` or `d8`.",
                ephemeral=True,
            )
            return
        count, sides, modifier = parsed
        char     = CHARACTERS[self.char_key]
        stat     = char["attack_stat"]
        stat_mod = _mod(char[stat])
        rolls    = roll_dice(count, sides)
        total    = sum(rolls) + modifier + stat_mod
        text     = fmt_damage_roll(self.formula.value.strip(), rolls, modifier, total, stat_mod, STAT_ABBR[stat])

        await interaction.response.defer(ephemeral=True)
        await _send_as_char(interaction.channel, self.char_key, text)
        try:
            await self.roll_interaction.delete_original_response()
        except Exception:
            pass


class CustomRollModal(discord.ui.Modal, title="Custom Roll"):
    formula = discord.ui.TextInput(
        label="Dice Formula",
        placeholder="e.g.  4d6+2  |  1d20-1  |  d100",
        max_length=30,
    )

    def __init__(self, char_key: str, roll_interaction: discord.Interaction):
        super().__init__()
        self.char_key         = char_key
        self.roll_interaction = roll_interaction

    async def on_submit(self, interaction: discord.Interaction):
        parsed = parse_dice(self.formula.value)
        if not parsed:
            await interaction.response.send_message(
                "❌ Invalid formula - try something like `4d6+2` or `d20`.",
                ephemeral=True,
            )
            return
        count, sides, modifier = parsed
        rolls = roll_dice(count, sides)
        total = sum(rolls) + modifier
        text  = fmt_custom_roll(self.formula.value.strip(), rolls, modifier, total)

        await interaction.response.defer(ephemeral=True)
        await _send_as_char(interaction.channel, self.char_key, text)
        try:
            await self.roll_interaction.delete_original_response()
        except Exception:
            pass

# ======================== SELECT MENUS ========================

def _weapon_options(char: dict) -> list[discord.SelectOption]:
    options = []
    for i, w in enumerate(char.get("weapons", [])):
        if w.get("has_atk", True):
            bonus = _mod(char[w['stat']]) + PROF_BONUS + w.get("extra", 0)
            options.append(discord.SelectOption(
                label=f"{w['emoji']}  {w['name']}",
                value=f"weapon_{i}",
                description=f"d20 {_fmt_mod(bonus)} — {w['desc']}",
            ))
        elif "dmg" in w:
            # spell/effect with no attack roll — roll-only entry
            count, sides, mod = w["dmg"]
            formula = f"{count}d{sides}" + (f"+{mod}" if mod > 0 else str(mod) if mod < 0 else "")
            atype = w.get("type", "damage")
            lbl = "▸ Healing" if atype == "heal" else "▸ Roll"
            options.append(discord.SelectOption(
                label=f"{w['emoji']}  {w['name']}  {lbl}",
                value=f"dmg_{i}",
                description=formula,
            ))
    return options


def _check_roll_options(char: dict) -> list[discord.SelectOption]:
    _stat_emoji = {"str": "💪", "dex": "🤸", "int": "📚", "wis": "👁️", "cha": "💬"}
    options = []
    for skill_key, (stat, label) in SKILLS.items():
        has_prof = skill_key in char.get("skill_profs", set())
        star     = " ★" if has_prof else ""
        options.append(discord.SelectOption(
            label=f"{_stat_emoji.get(stat, '🎲')}  {label}{star}",
            value=f"skill_{skill_key}",
            description=SKILL_DESCS.get(skill_key, ""),
        ))
    for stat in ("str", "dex", "con", "int", "wis", "cha"):
        mod = _mod(char[stat])
        options.append(discord.SelectOption(
            label=f"🎲  {STAT_LABELS[stat]} Check",
            value=f"check_{stat}",
            description=f"d20 {_fmt_mod(mod)}",
        ))
    options.append(discord.SelectOption(
        label="✏️  Custom Roll",
        value="custom_roll",
        description="Enter any dice formula, e.g. 4d6+2",
    ))
    return options  # 25 options


def _saves_options(char: dict) -> list[discord.SelectOption]:
    con_m = _mod(char["con"])
    die   = char["hit_die"]
    options = []
    for stat in ("str", "dex", "con", "int", "wis", "cha"):
        mod      = _mod(char[stat])
        has_prof = stat in char["save_profs"]
        total    = mod + (PROF_BONUS if has_prof else 0)
        options.append(discord.SelectOption(
            label=f"🛡️  {STAT_ABBR[stat]} Save",
            value=f"save_{stat}",
            description=f"d20 {_fmt_mod(total)}",
        ))
    options += [
        discord.SelectOption(label="💀  Death Save",       value="death_save", description="Stabilize or fade"),
        discord.SelectOption(label=f"💊  Hit Die  (d{die})", value="hit_die",    description=f"d{die} {_fmt_mod(con_m)} — Short Rest"),
    ]
    return options  # 8 options


def _sel_update(view, select_item, choice):
    """Shared state update for all roll select callbacks."""
    view.selected_roll = choice
    _sync_select_defaults(view, select_item, choice)
    for item in view.children:
        if isinstance(item, RollConfirmButton):
            item.disabled = False


class WeaponsSelect(discord.ui.Select):
    def __init__(self, char_key: str, char: dict, roll_interaction: discord.Interaction):
        self.char_key = char_key; self.char = char; self.roll_interaction = roll_interaction
        super().__init__(placeholder="Weapons", options=_weapon_options(char), row=0)

    async def callback(self, interaction: discord.Interaction):
        _sel_update(self.view, self, self.values[0])
        await interaction.response.edit_message(
            content=_roll_view_content(self.view.char, self.view.selected_roll, self.view.adv_mode, self.view.active_features),
            view=self.view,
        )


class CheckRollsSelect(discord.ui.Select):
    def __init__(self, char_key: str, char: dict, roll_interaction: discord.Interaction):
        self.char_key = char_key; self.char = char; self.roll_interaction = roll_interaction
        super().__init__(placeholder="Check Rolls", options=_check_roll_options(char), row=1)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "custom_roll":
            await interaction.response.send_modal(CustomRollModal(self.char_key, self.roll_interaction))
            return
        _sel_update(self.view, self, self.values[0])
        await interaction.response.edit_message(
            content=_roll_view_content(self.view.char, self.view.selected_roll, self.view.adv_mode, self.view.active_features),
            view=self.view,
        )


class SavesSelect(discord.ui.Select):
    def __init__(self, char_key: str, char: dict, roll_interaction: discord.Interaction):
        self.char_key = char_key; self.char = char; self.roll_interaction = roll_interaction
        super().__init__(placeholder="Saves", options=_saves_options(char), row=2)

    async def callback(self, interaction: discord.Interaction):
        _sel_update(self.view, self, self.values[0])
        await interaction.response.edit_message(
            content=_roll_view_content(self.view.char, self.view.selected_roll, self.view.adv_mode, self.view.active_features),
            view=self.view,
        )


def _choice_label(choice: str, char: dict = None) -> str:
    if choice.startswith("check_"): return f"{STAT_LABELS[choice[6:]]} Check"
    if choice.startswith("save_"):  return f"{STAT_LABELS[choice[5:]]} Save"
    if choice.startswith("skill_"): return f"{SKILLS[choice[6:]][1]} Check"
    if choice == "custom_roll":    return "Custom Roll"
    if choice.startswith("die_"):   return f"d{choice[4:]}"
    if choice.startswith("weapon_") and char is not None:
        idx = int(choice[len("weapon_"):])
        w = char["weapons"][idx]
        return f"{w['emoji']} {w['name']}"
    if choice.startswith("dmg_") and char is not None:
        idx = int(choice[len("dmg_"):])
        w = char["weapons"][idx]
        return f"{w['emoji']} {w['name']}"
    return {"initiative": "Initiative",
            "death_save": "Death Save", "hit_die": "Hit Die"}.get(choice, choice)


def _sync_select_defaults(view: discord.ui.View, active_select, chosen_value: str) -> None:
    """Mark chosen_value as default in active_select; clear defaults on the others."""
    for item in view.children:
        if not isinstance(item, (WeaponsSelect, CheckRollsSelect, SavesSelect)):
            continue
        for opt in item.options:
            opt.default = (item is active_select and opt.value == chosen_value)


def _roll_view_content(char: dict, selected_roll, adv_mode, active_features=None) -> str:
    lines = [f"*Rolling as **{char['name']}** — {char['cls']}...*"]
    # Passive features line — always shown if character has features
    if active_features:
        feat_labels = [FEATURE_DEFS[fk]["label"] for fk in active_features if fk in FEATURE_DEFS]
        if feat_labels:
            lines.append("-# ✶ " + " • ".join(feat_labels))
    # Selection + manual adv/dis overrides
    sel_parts = []
    if selected_roll:
        sel_parts.append(f"🎯 **{_choice_label(selected_roll, char)}**")
    if adv_mode == "advantage":
        sel_parts.append("🔼 Override: w/Advantage")
    elif adv_mode == "disadvantage":
        sel_parts.append("🔽 Override: w/Disadvantage")
    if sel_parts:
        lines.append("-# " + " • ".join(sel_parts))
    return "\n".join(lines)


class RollDamageView(discord.ui.View):
    """View attached to a public attack message — clicking the button rolls damage as
    the same character, then strips the button from the original message."""
    def __init__(self, char_key: str, weapon_idx: int, is_crit: bool):
        super().__init__(timeout=900)  # 15 min
        self.char_key   = char_key
        self.weapon_idx = weapon_idx
        self.is_crit    = is_crit
        self.message: discord.WebhookMessage | None = None

    @discord.ui.button(label="🎲 Roll Damage", style=discord.ButtonStyle.primary)
    async def roll_damage(self, interaction: discord.Interaction, button: discord.ui.Button):
        char   = CHARACTERS[self.char_key]
        weapon = char["weapons"][self.weapon_idx]
        text   = fmt_weapon_damage(char, weapon, is_crit=self.is_crit)
        try:
            await interaction.response.edit_message(view=None)
        except Exception:
            pass
        self.stop()
        await _send_as_char(interaction.channel, self.char_key, text)

    async def on_timeout(self):
        if self.message is not None:
            try:
                await self.message.edit(view=None)
            except Exception:
                pass


class RollConfirmButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="🎲 ROLL!", style=discord.ButtonStyle.primary, row=3, disabled=True)

    async def callback(self, interaction: discord.Interaction):
        view: RollView = self.view
        choice   = view.selected_roll
        if not choice:
            await interaction.response.defer(ephemeral=True)
            return
        effective_adv = _effective_adv(view.adv_mode, view.active_features, choice)
        atk_extra = sum(
            FEATURE_DEFS[fk].get("attack_bonus", 0)
            for fk in view.active_features if fk in FEATURE_DEFS
        )
        channel = interaction.channel
        view.selected_roll = None
        self.disabled = True
        for item in view.children:
            if isinstance(item, (WeaponsSelect, CheckRollsSelect, SavesSelect)):
                for opt in item.options:
                    opt.default = False
        await interaction.response.defer(ephemeral=True)

        # Special path: weapon attacks attach a "Roll Damage" button (unless nat 1
        # or the weapon has no damage dice).
        if choice.startswith("weapon_"):
            idx     = int(choice[len("weapon_"):])
            weapon  = view.char["weapons"][idx]
            text, raw_roll, is_crit = fmt_attack_roll(view.char, weapon, effective_adv)
            dmg_view = None
            if raw_roll != 1 and "dmg" in weapon:
                dmg_view = RollDamageView(view.char_key, idx, is_crit)
            sent = await _send_as_char(channel, view.char_key, text, view=dmg_view)
            if dmg_view is not None and sent is not None:
                dmg_view.message = sent
        else:
            result = resolve_roll(choice, view.char, effective_adv, atk_extra)
            await _send_as_char(channel, view.char_key, result)

        try:
            await interaction.delete_original_response()
        except Exception:
            pass


class InitiativeButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="⚡ Roll Initiative", style=discord.ButtonStyle.secondary, row=3)

    async def callback(self, interaction: discord.Interaction):
        view: RollView = self.view
        effective_adv  = _effective_adv(view.adv_mode, view.active_features, "initiative")
        result         = fmt_initiative(view.char, effective_adv)
        await interaction.response.defer(ephemeral=True)
        await _send_as_char(interaction.channel, view.char_key, result)
        try:
            await interaction.delete_original_response()
        except Exception:
            pass


class AdvToggleButton(discord.ui.Button):
    def __init__(self, mode: str):
        label = "🔼 w/ Advantage?" if mode == "advantage" else "🔽 w/ Disadvantage?"
        super().__init__(label=label, style=discord.ButtonStyle.secondary, row=4)
        self.mode = mode

    async def callback(self, interaction: discord.Interaction):
        view: RollView = self.view
        view.adv_mode = None if view.adv_mode == self.mode else self.mode
        for item in view.children:
            if isinstance(item, AdvToggleButton):
                if view.adv_mode == item.mode:
                    item.style = discord.ButtonStyle.success if item.mode == "advantage" else discord.ButtonStyle.danger
                else:
                    item.style = discord.ButtonStyle.secondary
        await interaction.response.edit_message(
            content=_roll_view_content(view.char, view.selected_roll, view.adv_mode, view.active_features),
            view=view,
        )


class RollView(discord.ui.View):
    def __init__(self, char_key: str, char: dict, roll_interaction: discord.Interaction):
        super().__init__(timeout=90)
        self.adv_mode: str | None = None
        self.selected_roll: str | None = None
        self.active_features: set[str] = set(char.get("features", []))  # always on — passive
        self.char = char
        self.char_key = char_key
        self.roll_interaction = roll_interaction
        self.add_item(WeaponsSelect(char_key, char, roll_interaction))
        self.add_item(CheckRollsSelect(char_key, char, roll_interaction))
        self.add_item(SavesSelect(char_key, char, roll_interaction))
        self.add_item(RollConfirmButton())
        self.add_item(InitiativeButton())
        self.add_item(AdvToggleButton("advantage"))
        self.add_item(AdvToggleButton("disadvantage"))

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


# ======================== DM CHARACTER PICKER ========================

class CharPickerButton(discord.ui.Button):
    def __init__(self, char_key: str, char: dict, roll_interaction: discord.Interaction):
        super().__init__(label=char["name"], style=discord.ButtonStyle.secondary)
        self.char_key         = char_key
        self.char             = char
        self.roll_interaction = roll_interaction

    async def callback(self, interaction: discord.Interaction):
        view = RollView(self.char_key, self.char, self.roll_interaction)
        await interaction.response.edit_message(
            content=f"*Rolling as **{self.char['name']}** — {self.char['cls']}...*",
            view=view,
        )


class CharPickerView(discord.ui.View):
    def __init__(self, roll_interaction: discord.Interaction):
        super().__init__(timeout=60)
        for char_key, char in CHARACTERS.items():
            self.add_item(CharPickerButton(char_key, char, roll_interaction))
        # DM-own roll button (row 1 so it doesn't crowd the character buttons)
        dm_btn = discord.ui.Button(
            label="🎲 Roll as DM",
            style=discord.ButtonStyle.danger,
            row=1,
        )
        async def _dm_roll(interaction: discord.Interaction, _btn=dm_btn):
            view = DMRollView(roll_interaction)
            view.add_item(DMRollAdvButton("advantage"))
            view.add_item(DMRollAdvButton("disadvantage"))
            await interaction.response.edit_message(
                content="*Dungeon Master — choose a roll type:*",
                view=view,
            )
        dm_btn.callback = _dm_roll
        self.add_item(dm_btn)


# ======================== QUOTE AUTO-SUDO ========================

_QUOTE_STARTERS = ('"', '\u201c', '\u201d', '\u00ab', '\u00bb')


async def warm_webhooks(bot) -> None:
    """Pre-fetch / create all character + DM webhooks for every text channel in the
    quote category.  Called from on_ready so the first quoted message hits a warm cache."""
    unique_chars = set(PLAYER_CHARS.values())
    for guild in bot.guilds:
        for channel in guild.text_channels:
            if channel.category_id != QUOTE_CATEGORY_ID:
                continue
        for char_key in unique_chars:
            if char_key in CHARACTERS:
                try:
                    await _get_char_webhook(channel, char_key)
                except Exception as e:
                    print(f"[DnD] Pre-warm {char_key} #{channel.name}: {e}")
        try:
            await _get_dm_webhook(channel)
        except Exception as e:
            print(f"[DnD] Pre-warm DM #{channel.name}: {e}")


async def process_quote(message: discord.Message) -> bool:
    """
    If the message is in the quote channel and starts with a quote character,
    delete it and re-send via the character's webhook.
    Any attachments on the same message are forwarded too.
    A quote starter is always required — attachments alone do NOT trigger roleplay.
    Returns True if handled (caller should skip further processing).
    """
    if not message.guild or getattr(message.channel, 'category_id', None) != QUOTE_CATEGORY_ID:
        return False
    # Strip any Discord block prefix (# / ## / ### / -#) and inline formatting (* / ** / _)
    # before checking for a quote starter, so things like `# *"text"*` trigger correctly.
    _stripped = re.sub(r"^(?:(?:-#|#{1,3})\s+)?(?:\*{1,3}|_{1,3})?", "", message.content) if message.content else ""
    if not (_stripped and _stripped.startswith(_QUOTE_STARTERS)):
        return False
    if not isinstance(message.channel, (discord.TextChannel, discord.Thread)):
        return False

    uid   = str(message.author.id)
    is_dm = uid == DM_USER_ID

    if not is_dm and uid not in PLAYER_CHARS:
        return False

    # Build content, prepending a blockquote preview if this is a Discord reply
    content = message.content or ""
    if message.reference and isinstance(getattr(message.reference, "resolved", None), discord.Message):
        ref = message.reference.resolved
        # Only use the first word of the display name
        ref_name = ref.author.display_name.split()[0] if ref.author.display_name else ref.author.display_name
        if ref.content:
            # Strip existing blockquote lines (> ...) so reply chains don't stack
            ref_lines = [l for l in ref.content.splitlines() if not l.startswith(">")]
            ref_text = " ".join(ref_lines).strip()
            if ref_text:
                # Truncate at ~40 chars but don't cut mid-word
                if len(ref_text) > 40:
                    truncated = ref_text[:40].rsplit(" ", 1)[0]
                    ref_preview = truncated + "..."
                else:
                    ref_preview = ref_text
                content = f"> **{ref_name}** \u2014 {ref_preview}\n{content}"
        elif ref.attachments:
            content = f"> *[image from {ref_name}]*\n{content}"

    # Download attachments for re-upload
    files = []
    for att in message.attachments:
        try:
            data = await att.read()
            files.append(discord.File(io.BytesIO(data), filename=att.filename))
        except Exception as e:
            print(f"[DnD] Failed to read attachment {att.filename}: {e}")

    try:
        # Send FIRST (feels instant), then delete — mirrors April Fools behaviour
        if is_dm:
            await _send_as_dm(message.channel, content, files=files or None)
        else:
            await _send_as_char(message.channel, PLAYER_CHARS[uid], content, files=files or None)
        await message.delete()
        return True
    except Exception as e:
        print(f"[DnD] Quote error (uid={uid}, is_dm={is_dm}): {type(e).__name__}: {e}")
        return False

# /roll is registered directly in bot.py via @bot.tree.command, same as all other commands.

# ======================== INVENTORY & INITIATIVE SYSTEM ========================

# Player letter shortcodes → char_key  (for !give DM chat command)
PLAYER_LETTERS: dict[str, str] = {
    "V": "viola",
    "A": "aeran",
    "B": "bablino",
    "I": "isaiah",
    "F": "faye",
    "S": "steria",
}

# Item shorthands → full display name
ITEM_SHORTHANDS: dict[str, str] = {
    # Healing potions
    "pot1": "Potion of Healing",
    "pot2": "Potion of Greater Healing",
    "pot3": "Potion of Superior Healing",
    "pot4": "Potion of Supreme Healing",
    # Ammo
    "arrow":     "Arrow",
    "arrows":    "Arrow",
    "bolt":      "Crossbow Bolt",
    "bolts":     "Crossbow Bolt",
    "dart":      "Dart",
    "darts":     "Dart",
    # Common gear
    "torch":     "Torch",
    "rope":      "Hempen Rope (50ft)",
    "ration":    "Ration",
    "antitoxin": "Antitoxin",
    "tinderbox": "Tinderbox",
    "oil":       "Flask of Oil",
    "bandage":   "Bandage",
    "hkit":      "Healer's Kit",
    # Spell scrolls
    "scroll1":   "Spell Scroll (1st)",
    "scroll2":   "Spell Scroll (2nd)",
    "scroll3":   "Spell Scroll (3rd)",
    # Currency
    "gp":        "Gold Piece",
    "gold":      "Gold Piece",
    "sp":        "Silver Piece",
    "cp":        "Copper Piece",
    "csc":       "Concord Silver Crown",
    "crown":     "Concord Silver Crown",
}

# Healing potions → (dice_count, dice_sides, bonus)  used by /heal
POTION_HEALS: dict[str, tuple[int, int, int]] = {
    "Potion of Healing":         (2, 4,  2),
    "Potion of Greater Healing": (4, 4,  4),
    "Potion of Superior Healing":(8, 4,  8),
    "Potion of Supreme Healing": (10, 4, 20),
}

# All items usable via /heal
# type "heal"   → dice: (count, sides, bonus), desc shown in dropdown
# type "effect" → no dice, effect_text posted publicly
USABLE_ITEM_DEFS: dict[str, dict] = {
    "Potion of Healing":         {"type": "heal",   "dice": (2, 4,  2),  "desc": "2d4+2 HP"},
    "Potion of Greater Healing": {"type": "heal",   "dice": (4, 4,  4),  "desc": "4d4+4 HP"},
    "Potion of Superior Healing":{"type": "heal",   "dice": (8, 4,  8),  "desc": "8d4+8 HP"},
    "Potion of Supreme Healing": {"type": "heal",   "dice": (10, 4, 20), "desc": "10d4+20 HP"},
    "Healer's Kit":              {"type": "heal",   "dice": (1, 6,  4),  "desc": "1d6+4 HP"},
    "Bandage":                   {"type": "heal",   "dice": (1, 4,  0),  "desc": "1d4 HP"},
    "Antitoxin":                 {"type": "effect", "desc": "ADV on CON saves vs. poison  ·  1 hour",
                                  "text": "Used **Antitoxin**.\n╰ Advantage on CON saves vs. **poison** for 1 hour."},
}

# Class emojis for /bag embed
CHAR_EMOJIS: dict[str, str] = {
    "viola":   "🪄",
    "aeran":   "🏹",
    "bablino": "🪓",
    "isaiah":  "⚔️",
    "faye":    "🌿",
    "steria":  "🛡️",
}

# Currency items with display emojis (ordered: highest → lowest denomination)
CURRENCY_EMOJIS: dict[str, str] = {
    "Gold Piece":           "🪙",
    "Concord Silver Crown": "👑",
    "Silver Piece":         "🔘",
    "Copper Piece":         "🟤",
}

# In-memory initiative state per guild
# guild_id → {"entries": [...], "channel_id": int|None, "message_id": int|None}
_initiative_state: dict[str, dict] = {}


def resolve_item_name(raw: str) -> str:
    """Convert a shorthand (e.g. 'pot1') to its full item name, or return the raw string."""
    return ITEM_SHORTHANDS.get(raw.lower(), raw)


def _char_first_name(char: dict) -> str:
    """Return a character's casual first name, stripping nicknames in quotes."""
    return char["name"].split('"')[0].strip().split()[0]


def _get_initiative(guild_id: str) -> dict:
    if guild_id not in _initiative_state:
        _initiative_state[guild_id] = {"entries": [], "channel_id": None, "message_id": None}
    return _initiative_state[guild_id]


def _sort_initiative(entries: list[dict]) -> list[dict]:
    """Sort by roll descending; ties: players beat enemies (5e RAW)."""
    return sorted(entries, key=lambda e: (e["roll"], 1 if e["type"] == "player" else 0), reverse=True)


def _awaiting_players(guild_id: str) -> list[str]:
    """First names of players who haven't rolled initiative yet."""
    state = _get_initiative(guild_id)
    rolled = {e["char_key"] for e in state["entries"] if e.get("char_key")}
    return [_char_first_name(char) for key, char in CHARACTERS.items() if key not in rolled]


# ─── Embed builders ───────────────────────────────────────────────────────────

def _item_display(item: str, amt: int) -> str:
    """Format a single inventory line, adding emoji for known item types."""
    if item in USABLE_ITEM_DEFS or item.startswith("Potion"):
        return f"`{amt}×` 💊 {item}"
    return f"`{amt}×` {item}"


def build_bag_embed(inventories: dict[str, dict[str, int]]) -> discord.Embed:
    """Compact embed showing every character's inventory side-by-side."""
    embed = discord.Embed(title="🎒  Party Inventory", color=0xD4A53A)
    for char_key, char in CHARACTERS.items():
        items = inventories.get(char_key, {})
        # Exclude pure currency items from the bag view
        non_currency = {k: v for k, v in items.items() if k not in CURRENCY_EMOJIS}
        emoji = CHAR_EMOJIS.get(char_key, "🎲")
        value = (
            "\n".join(_item_display(item, amt) for item, amt in sorted(non_currency.items()))
            if non_currency else "*(empty)*"
        )
        embed.add_field(name=f"{emoji}  {_char_first_name(char)}", value=value, inline=True)
    return embed


def build_wallet_embed(inventories: dict[str, dict[str, int]]) -> discord.Embed:
    """Embed showing each character's currencies only."""
    embed = discord.Embed(title="💰  Party Wallet", color=0xF1C40F)
    for char_key, char in CHARACTERS.items():
        items = inventories.get(char_key, {})
        emoji = CHAR_EMOJIS.get(char_key, "🎲")
        lines = [
            f"{cur_emoji} `{items[cur]}` {cur}"
            for cur, cur_emoji in CURRENCY_EMOJIS.items()
            if cur in items and items[cur] > 0
        ]
        value = "\n".join(lines) if lines else "*(empty)*"
        embed.add_field(name=f"{emoji}  {_char_first_name(char)}", value=value, inline=True)
    return embed


def build_initiative_embed(entries: list[dict], awaiting: list[str]) -> discord.Embed:
    """Build the live initiative-order embed."""
    embed = discord.Embed(title="⚔️  Initiative Order", color=0xC0392B)
    if not entries:
        embed.description = "*No one has rolled yet. Waiting for players…*"
    else:
        ranks = ["1st","2nd","3rd","4th","5th","6th","7th","8th","9th","10th",
                 "11th","12th","13th","14th","15th","16th","17th","18th","19th","20th"]
        lines = []
        for i, e in enumerate(entries):
            pos = ranks[i] if i < len(ranks) else f"{i+1}th"
            tag = "  〔player〕" if e["type"] == "player" else ""
            lines.append(f"`{pos}`  **{e['name']}**  —  **{e['roll']}**{tag}")
        embed.description = "\n".join(lines)
    if awaiting:
        embed.set_footer(text="⏳ Still rolling: " + ", ".join(awaiting))
    else:
        embed.set_footer(text="✅ All players have rolled!")
    return embed


def _dm_initiative_content(guild_id: str) -> str:
    """Status text for the DM's ephemeral initiative manager."""
    state = _get_initiative(guild_id)
    enemies = [e for e in state["entries"] if e["type"] == "enemy"]
    players = [e for e in state["entries"] if e["type"] == "player"]
    lines = ["*⚔️  Dungeon Master — Initiative Manager*"]
    if enemies:
        lines.append("-# 🗡️ " + "  ·  ".join(f"**{e['name']}** `{e['roll']}`" for e in enemies))
    else:
        lines.append("-# 🗡️ No enemies added yet")
    if players:
        lines.append("-# 🧝 Rolled: " + "  ·  ".join(
            f"**{e['name'].split()[0]}** `{e['roll']}`" for e in players))
    awaiting = _awaiting_players(guild_id)
    if awaiting:
        lines.append("-# ⏳ Awaiting: " + ", ".join(awaiting))
    if state["message_id"]:
        lines.append("-# ✅ Initiative embed is live")
    return "\n".join(lines)


async def _refresh_initiative_embed(guild: discord.Guild, guild_id: str) -> None:
    """Re-render the live initiative embed after any state change."""
    state = _get_initiative(guild_id)
    if not state["channel_id"] or not state["message_id"]:
        return
    try:
        channel = guild.get_channel(state["channel_id"])
        if channel:
            msg = await channel.fetch_message(state["message_id"])
            await msg.edit(embed=build_initiative_embed(state["entries"], _awaiting_players(guild_id)))
    except Exception as e:
        print(f"[DnD] Initiative embed refresh failed: {e}")


# ─── Initiative Views ─────────────────────────────────────────────────────────

class AddEnemyModal(discord.ui.Modal, title="Add Enemy to Initiative"):
    enemy_name = discord.ui.TextInput(
        label="Enemy Name",
        placeholder="e.g.  Goblin Rogue,  Skeleton,  Cultist",
        max_length=60,
    )
    enemy_roll = discord.ui.TextInput(
        label="Initiative Roll  (blank = auto-roll d20)",
        required=False,
        placeholder="Leave blank to auto-roll",
        max_length=4,
    )

    def __init__(self, guild_id: str, mgmt_interaction: discord.Interaction):
        super().__init__()
        self.guild_id = guild_id
        self.mgmt_interaction = mgmt_interaction

    async def on_submit(self, interaction: discord.Interaction):
        name = self.enemy_name.value.strip()
        raw  = self.enemy_roll.value.strip()
        if raw:
            try:
                roll = max(1, min(30, int(raw)))
            except ValueError:
                await interaction.response.send_message("❌ Roll must be a number.", ephemeral=True)
                return
        else:
            roll = random.randint(1, 20)

        state = _get_initiative(self.guild_id)
        state["entries"].append({"name": name, "roll": roll, "type": "enemy", "char_key": None})
        state["entries"] = _sort_initiative(state["entries"])

        await interaction.response.defer(ephemeral=True)
        await _refresh_initiative_embed(interaction.guild, self.guild_id)
        try:
            await self.mgmt_interaction.edit_original_response(
                content=_dm_initiative_content(self.guild_id)
            )
        except Exception:
            pass


class DMInitiativeView(discord.ui.View):
    def __init__(self, guild_id: str, mgmt_interaction: discord.Interaction):
        super().__init__(timeout=1800)  # 30 min
        self.guild_id = guild_id
        self.mgmt_interaction = mgmt_interaction

    @discord.ui.button(label="➕ Add Enemy", style=discord.ButtonStyle.primary, row=0)
    async def add_enemy_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddEnemyModal(self.guild_id, self.mgmt_interaction))

    @discord.ui.button(label="⚡ Start Initiative", style=discord.ButtonStyle.success, row=0)
    async def start_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = _get_initiative(self.guild_id)
        embed = build_initiative_embed(state["entries"], _awaiting_players(self.guild_id))
        await interaction.response.defer(ephemeral=True)
        msg = await interaction.channel.send(embed=embed)
        state["channel_id"] = interaction.channel.id
        state["message_id"]  = msg.id
        button.label = "🔄 Restart"
        button.style = discord.ButtonStyle.secondary
        try:
            await self.mgmt_interaction.edit_original_response(
                content=_dm_initiative_content(self.guild_id),
                view=self,
            )
        except Exception:
            pass

    @discord.ui.button(label="🗑️ Clear All", style=discord.ButtonStyle.danger, row=0)
    async def clear_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        _initiative_state.pop(self.guild_id, None)
        new_view = DMInitiativeView(self.guild_id, self.mgmt_interaction)
        await interaction.response.edit_message(
            content="*⚔️  Initiative cleared. Ready for the next encounter.*",
            view=new_view,
        )

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


# ─── /heal View ───────────────────────────────────────────────────────────────

class HealSelect(discord.ui.Select):
    def __init__(self, char_key: str, items: dict[str, int]):
        options = []
        for item_name, amt in sorted(items.items()):
            defn = USABLE_ITEM_DEFS[item_name]
            options.append(discord.SelectOption(
                label=f"💊  {item_name}",
                value=item_name,
                description=f"{defn['desc']}  ·  {amt} remaining",
            ))
        super().__init__(placeholder="Choose an item to use…", options=options, row=0)
        self.char_key = char_key

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_potion = self.values[0]
        defn = USABLE_ITEM_DEFS[self.values[0]]
        action = "Using" if defn["type"] == "effect" else "Drinking"
        for item in self.view.children:
            if isinstance(item, HealConfirmButton):
                item.disabled = False
        await interaction.response.edit_message(
            content=f"*{action} **{self.values[0]}**… confirm?*",
            view=self.view,
        )


class HealConfirmButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="💊 Use!", style=discord.ButtonStyle.success, row=1, disabled=True)

    async def callback(self, interaction: discord.Interaction):
        view: HealView = self.view
        item_name = view.selected_potion
        if not item_name:
            await interaction.response.defer(ephemeral=True)
            return
        success = await view._remove_fn(view.char_key, item_name, 1)
        if not success:
            await interaction.response.send_message("❌ You don't have that item anymore!", ephemeral=True)
            return
        defn = USABLE_ITEM_DEFS[item_name]
        if defn["type"] == "effect":
            text = f"💊 {defn['text']}"
        else:
            count, sides, bonus = defn["dice"]
            rolls = roll_dice(count, sides)
            total = sum(rolls) + bonus
            roll_str = " + ".join(f"`{r}`" for r in rolls)
            mod_str = f" +{bonus}" if bonus else ""
            text = (
                f"💊 **{item_name}**\n"
                f"╰ {roll_str}{mod_str} = **+{total} HP** restored"
            )
        await interaction.response.defer(ephemeral=True)
        await _send_as_char(interaction.channel, view.char_key, text)
        try:
            await interaction.delete_original_response()
        except Exception:
            pass


class HealView(discord.ui.View):
    def __init__(self, char_key: str, items: dict[str, int], remove_fn):
        super().__init__(timeout=60)
        self.char_key = char_key
        self.selected_potion: str | None = None
        self._remove_fn = remove_fn
        self.add_item(HealSelect(char_key, items))
        self.add_item(HealConfirmButton())

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


# ─── /give Player View ────────────────────────────────────────────────────────

class GiveItemSelect(discord.ui.Select):
    def __init__(self, char_key: str, items: dict[str, int]):
        options = [
            discord.SelectOption(label=name, value=name, description=f"{amt} in bag")
            for name, amt in sorted(items.items())
        ]
        super().__init__(placeholder="What to give?", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_item = self.values[0]
        _sync_give_defaults(self.view, self, self.values[0])
        _check_give_confirm(self.view)
        await interaction.response.edit_message(view=self.view)


class GiveRecipientSelect(discord.ui.Select):
    def __init__(self, giver_key: str):
        options = [
            discord.SelectOption(
                label=_char_first_name(char),
                value=char_key,
                description=char["cls"],
            )
            for char_key, char in CHARACTERS.items()
            if char_key != giver_key
        ]
        super().__init__(placeholder="Give to…", options=options, row=1)

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_recipient = self.values[0]
        _sync_give_defaults(self.view, self, self.values[0])
        _check_give_confirm(self.view)
        await interaction.response.edit_message(view=self.view)


def _sync_give_defaults(view, active_select, val: str) -> None:
    for item in view.children:
        if not isinstance(item, (GiveItemSelect, GiveRecipientSelect)):
            continue
        for opt in item.options:
            opt.default = (item is active_select and opt.value == val)


def _check_give_confirm(view) -> None:
    for item in view.children:
        if isinstance(item, GiveConfirmButton):
            item.disabled = not (view.selected_item and view.selected_recipient)


class GiveConfirmButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="🤝 Give 1×", style=discord.ButtonStyle.success, row=2, disabled=True)

    async def callback(self, interaction: discord.Interaction):
        view: GiveView = self.view
        if not view.selected_item or not view.selected_recipient:
            await interaction.response.defer(ephemeral=True)
            return
        success = await view._remove_fn(view.char_key, view.selected_item, 1)
        if not success:
            await interaction.response.send_message("❌ You don't have that item anymore!", ephemeral=True)
            return
        await view._add_fn(view.selected_recipient, view.selected_item, 1)
        giver = CHARACTERS[view.char_key]
        recip = CHARACTERS[view.selected_recipient]
        text = (
            f"🤝 **{_char_first_name(giver)}** gave "
            f"**1× {view.selected_item}** to **{_char_first_name(recip)}**."
        )
        await interaction.response.defer(ephemeral=True)
        await _send_as_char(interaction.channel, view.char_key, text)
        try:
            await interaction.delete_original_response()
        except Exception:
            pass


class GiveView(discord.ui.View):
    def __init__(self, char_key: str, items: dict[str, int], remove_fn, add_fn):
        super().__init__(timeout=60)
        self.char_key = char_key
        self.selected_item: str | None = None
        self.selected_recipient: str | None = None
        self._remove_fn = remove_fn
        self._add_fn    = add_fn
        self.add_item(GiveItemSelect(char_key, items))
        self.add_item(GiveRecipientSelect(char_key))
        self.add_item(GiveConfirmButton())

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
