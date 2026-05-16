"""
D&D Roll System - The Golden Krispyre Tale
/roll command with character-specific dropdown, character webhook impersonation,
and auto-sudo for quoted roleplay in the designated channel.

All output formatting lives in the OUTPUT FORMATTING section - edit there to
change how roll results look.
"""

import discord
import random
import re
import os
import math
from pathlib import Path
from typing import Optional

# ======================== CONFIGURATION ========================

# Channel where messages starting with " auto-sudo as the player's character
QUOTE_CHANNEL_ID = 1505272854877306970

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
        "attack_stat": "int",
        "speed":       30,
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
        "attack_stat": "str",
        "speed":       30,
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
        "attack_stat": "dex",
        "speed":       30,
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
        "attack_stat": "str",
        "speed":       30,
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
        "attack_stat": "wis",
        "speed":       35,
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
        "attack_stat": "str",
        "speed":       30,
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

# ======================== OUTPUT FORMATTING ========================
# ─── All roll output is assembled here. Edit this section to restyle results. ───

def _mod(score: int) -> int:
    return math.floor((score - 10) / 2)

def _fmt_mod(m: int) -> str:
    return f"+{m}" if m >= 0 else str(m)

def _d20() -> int:
    return random.randint(1, 20)

def _crit_tag(roll: int) -> str:
    if roll == 20: return " ✨ **NAT 20!**"
    if roll == 1:  return " 💀 **NAT 1**"
    return ""


def fmt_ability_check(char: dict, stat: str) -> str:
    mod  = _mod(char[stat])
    roll = _d20()
    eq   = f"`{roll}`" + (f" {_fmt_mod(mod)}" if mod != 0 else "")
    return (
        f"**{STAT_LABELS[stat]} Check**{_crit_tag(roll)}\n"
        f"╰ {eq} = **{roll + mod}**"
    )


def fmt_saving_throw(char: dict, stat: str) -> str:
    mod      = _mod(char[stat])
    has_prof = stat in char["save_profs"]
    bonus    = mod + (PROF_BONUS if has_prof else 0)
    roll     = _d20()
    total    = roll + bonus

    breakdown = f"`{roll}`" + (f" {_fmt_mod(bonus)}" if bonus != 0 else "")
    prof_tag  = " *(proficient)*" if has_prof else ""

    # Show the split when proficiency is involved
    if has_prof and mod != 0:
        breakdown += f" *(mod {_fmt_mod(mod)}, prof +{PROF_BONUS})*"
    elif has_prof:
        breakdown += f" *(prof +{PROF_BONUS})*"

    return (
        f"**{STAT_LABELS[stat]} Save**{prof_tag}{_crit_tag(roll)}\n"
        f"╰ {breakdown} = **{total}**"
    )


def fmt_attack_roll(char: dict) -> str:
    stat  = char["attack_stat"]
    bonus = _mod(char[stat]) + PROF_BONUS
    roll  = _d20()
    total = roll + bonus

    crit = ""
    if roll == 20: crit = " ✨ **CRITICAL HIT!**"
    elif roll == 1: crit = " 💀 **CRITICAL MISS**"

    return (
        f"**Attack Roll**{crit}\n"
        f"╰ `{roll}` {_fmt_mod(bonus)} *({STAT_ABBR[stat]} + Prof)* = **{total}**"
    )


def fmt_initiative(char: dict) -> str:
    mod   = _mod(char["dex"])
    roll  = _d20()
    total = roll + mod
    return (
        f"**Initiative**{_crit_tag(roll)}\n"
        f"╰ `{roll}` {_fmt_mod(mod)} *(DEX)* = **{total}**"
    )


def fmt_advantage() -> str:
    r1, r2 = _d20(), _d20()
    kept, dropped = max(r1, r2), min(r1, r2)
    crit = ""
    if kept == 20: crit = " ✨ **NAT 20!**"
    elif kept == 1: crit = " 💀 **NAT 1**"
    return (
        f"**Roll with Advantage**{crit}\n"
        f"╰ kept `{kept}`, dropped ~~`{dropped}`~~ → **{kept}**"
    )


def fmt_disadvantage() -> str:
    r1, r2 = _d20(), _d20()
    kept, dropped = min(r1, r2), max(r1, r2)
    crit = ""
    if kept == 1: crit = " 💀 **NAT 1**"
    elif kept == 20: crit = " ✨ NAT 20 *(against the odds)*"
    return (
        f"**Roll with Disadvantage**{crit}\n"
        f"╰ kept `{kept}`, dropped ~~`{dropped}`~~ → **{kept}**"
    )


def fmt_death_save() -> str:
    roll = _d20()
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
        f"**Death Saving Throw**\n"
        f"╰ `{roll}` → {verdict}\n"
        f"  *{note}*"
    )


def fmt_hit_die(char: dict) -> str:
    con_mod = _mod(char["con"])
    die     = char["hit_die"]
    roll    = random.randint(1, die)
    healed  = max(1, roll + con_mod)
    return (
        f"**Hit Die** *(Short Rest)*\n"
        f"╰ `d{die}: {roll}` {_fmt_mod(con_mod)} *(CON)* = **+{healed} HP**"
    )


def fmt_raw_die(sides: int) -> str:
    roll = random.randint(1, sides)
    return (
        f"**d{sides}**\n"
        f"╰ → **{roll}**"
    )


def fmt_damage_roll(formula: str, rolls: list[int], modifier: int, total: int) -> str:
    roll_str = " + ".join(f"`{r}`" for r in rolls)
    mod_str  = f" {_fmt_mod(modifier)}" if modifier != 0 else ""
    return (
        f"**Damage** `{formula}`\n"
        f"╰ {roll_str}{mod_str} = **{total} dmg**"
    )


def fmt_custom_roll(formula: str, rolls: list[int], modifier: int, total: int) -> str:
    roll_str = " + ".join(f"`{r}`" for r in rolls)
    mod_str  = f" {_fmt_mod(modifier)}" if modifier != 0 else ""
    return (
        f"**Custom** `{formula}`\n"
        f"╰ {roll_str}{mod_str} = **{total}**"
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

def resolve_roll(choice: str, char: dict) -> str:
    """Map a select menu value to a formatted roll string."""
    if choice.startswith("check_"):
        return fmt_ability_check(char, choice[len("check_"):])
    if choice.startswith("save_"):
        return fmt_saving_throw(char, choice[len("save_"):])
    if choice.startswith("die_"):
        return fmt_raw_die(int(choice[len("die_"):]))
    dispatch = {
        "attack":      lambda: fmt_attack_roll(char),
        "initiative":  lambda: fmt_initiative(char),
        "advantage":   fmt_advantage,
        "disadvantage":fmt_disadvantage,
        "death_save":  fmt_death_save,
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
            _webhook_cache[cache_key] = wh
            return wh

    pfp_path     = PFP_DIR / char["pfp"]
    avatar_bytes = pfp_path.read_bytes() if pfp_path.exists() else None

    wh = await channel.create_webhook(name=wh_name, avatar=avatar_bytes)
    _webhook_cache[cache_key] = wh
    return wh


async def _get_dm_webhook(channel: discord.TextChannel) -> discord.Webhook:
    """Return (or create) a Dungeon Master webhook. No avatar stored — passed as URL at send time."""
    cache_key = f"{channel.id}:dm"
    if cache_key in _webhook_cache:
        return _webhook_cache[cache_key]
    for wh in await channel.webhooks():
        if wh.name == "DnD_DungeonMaster":
            _webhook_cache[cache_key] = wh
            return wh
    wh = await channel.create_webhook(name="DnD_DungeonMaster")
    _webhook_cache[cache_key] = wh
    return wh


async def _send_as_char(
    channel: discord.abc.Messageable,
    char_key: str,
    content: str,
) -> None:
    """Send as a character. Works in both TextChannels and Threads."""
    char = CHARACTERS[char_key]
    wh_channel = channel.parent if isinstance(channel, discord.Thread) else channel
    if not isinstance(wh_channel, discord.TextChannel):
        return
    wh = await _get_char_webhook(wh_channel, char_key)
    send_kw = dict(username=char["name"], allowed_mentions=discord.AllowedMentions.none())
    if isinstance(channel, discord.Thread):
        send_kw["thread"] = channel
    await wh.send(content, **send_kw)


async def _send_as_dm(
    channel: discord.abc.Messageable,
    member:  discord.Member,
    content: str,
) -> None:
    """Send as Dungeon Master. Works in both TextChannels and Threads."""
    wh_channel = channel.parent if isinstance(channel, discord.Thread) else channel
    if not isinstance(wh_channel, discord.TextChannel):
        return
    wh = await _get_dm_webhook(wh_channel)
    send_kw = dict(
        username="Dungeon Master",
        avatar_url=member.display_avatar.url,  # URL string — no download, always current
        allowed_mentions=discord.AllowedMentions.none(),
    )
    if isinstance(channel, discord.Thread):
        send_kw["thread"] = channel
    await wh.send(content, **send_kw)

# ======================== MODALS ========================

class DamageModal(discord.ui.Modal, title="Damage Roll"):
    formula = discord.ui.TextInput(
        label="Dice Formula",
        placeholder="e.g.  2d6+3  |  1d8  |  d4-1",
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
                "❌ Invalid formula - try something like `2d6+3` or `d8`.",
                ephemeral=True,
            )
            return
        count, sides, modifier = parsed
        rolls = roll_dice(count, sides)
        total = sum(rolls) + modifier
        text  = fmt_damage_roll(self.formula.value.strip(), rolls, modifier, total)

        await interaction.response.defer(ephemeral=True)
        await _send_as_char(interaction.channel, self.char_key, text)
        await interaction.followup.send("✅ Rolled!", ephemeral=True)
        try:
            await self.roll_interaction.edit_original_response(
                content="✅ Done! Check the channel.", view=None
            )
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
        await interaction.followup.send("✅ Rolled!", ephemeral=True)
        try:
            await self.roll_interaction.edit_original_response(
                content="✅ Done! Check the channel.", view=None
            )
        except Exception:
            pass

# ======================== SELECT MENUS ========================

def _combat_options(char: dict) -> list[discord.SelectOption]:
    atk   = char["attack_stat"]
    atk_b = _mod(char[atk]) + PROF_BONUS
    dex_m = _mod(char["dex"])
    con_m = _mod(char["con"])
    die   = char["hit_die"]

    options = [
        discord.SelectOption(
            label="⚔️  Attack Roll",    value="attack",
            description=f"d20 {_fmt_mod(atk_b)}  ({STAT_ABBR[atk]} mod + Prof +{PROF_BONUS})",
        ),
        discord.SelectOption(
            label="⚡  Initiative",     value="initiative",
            description=f"d20 {_fmt_mod(dex_m)}  (DEX mod)",
        ),
        discord.SelectOption(
            label="💀  Death Save",     value="death_save",
            description="Flat d20 - stabilize or fade",
        ),
        discord.SelectOption(
            label=f"💊  Hit Die  (d{die})", value="hit_die",
            description=f"d{die} {_fmt_mod(con_m)}  (CON mod) - Short Rest",
        ),
        discord.SelectOption(
            label="🔼  Advantage",      value="advantage",
            description="Roll 2d20 - keep highest",
        ),
        discord.SelectOption(
            label="🔽  Disadvantage",   value="disadvantage",
            description="Roll 2d20 - keep lowest",
        ),
        discord.SelectOption(
            label="🗡️  Damage Roll",    value="damage",
            description="Enter weapon / spell dice",
        ),
    ]

    for stat in ("str", "dex", "con", "int", "wis", "cha"):
        mod      = _mod(char[stat])
        has_prof = stat in char["save_profs"]
        total    = mod + (PROF_BONUS if has_prof else 0)
        note     = f" + Prof +{PROF_BONUS}" if has_prof else ""
        options.append(discord.SelectOption(
            label=f"🛡️  {STAT_ABBR[stat]} Save",
            value=f"save_{stat}",
            description=f"d20 {_fmt_mod(total)}{note}",
        ))

    return options  # 13 options


def _check_options(char: dict) -> list[discord.SelectOption]:
    options = []

    for stat in ("str", "dex", "con", "int", "wis", "cha"):
        mod = _mod(char[stat])
        options.append(discord.SelectOption(
            label=f"🎲  {STAT_LABELS[stat]} Check",
            value=f"check_{stat}",
            description=f"d20 {_fmt_mod(mod)}",
        ))

    for sides in (4, 6, 8, 10, 12, 20, 100):
        options.append(discord.SelectOption(
            label=f"🎯  d{sides}",
            value=f"die_{sides}",
            description=f"Straight d{sides} roll",
        ))

    options.append(discord.SelectOption(
        label="✏️  Custom Roll",
        value="custom",
        description="Enter your own dice formula",
    ))

    return options  # 14 options


class CombatSavesSelect(discord.ui.Select):
    def __init__(self, char_key: str, char: dict, roll_interaction: discord.Interaction):
        self.char_key         = char_key
        self.char             = char
        self.roll_interaction = roll_interaction
        super().__init__(
            placeholder="⚔️  Combat, Saves & Utility",
            options=_combat_options(char),
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        choice  = self.values[0]
        channel = interaction.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message("❌ Can't roll here.", ephemeral=True)
            return

        if choice == "damage":
            await interaction.response.send_modal(
                DamageModal(self.char_key, self.roll_interaction)
            )
            return

        await interaction.response.defer(ephemeral=True)
        result = resolve_roll(choice, self.char)
        await _send_as_char(channel, self.char_key, result)
        await interaction.followup.send("✅ Rolled!", ephemeral=True)
        try:
            await self.roll_interaction.edit_original_response(
                content="✅ Done! Check the channel.", view=None
            )
        except Exception:
            pass


class ChecksDiceSelect(discord.ui.Select):
    def __init__(self, char_key: str, char: dict, roll_interaction: discord.Interaction):
        self.char_key         = char_key
        self.char             = char
        self.roll_interaction = roll_interaction
        super().__init__(
            placeholder="🎲  Ability Checks & Dice",
            options=_check_options(char),
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        choice  = self.values[0]
        channel = interaction.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message("❌ Can't roll here.", ephemeral=True)
            return

        if choice == "custom":
            await interaction.response.send_modal(
                CustomRollModal(self.char_key, self.roll_interaction)
            )
            return

        await interaction.response.defer(ephemeral=True)
        result = resolve_roll(choice, self.char)
        await _send_as_char(channel, self.char_key, result)
        await interaction.followup.send("✅ Rolled!", ephemeral=True)
        try:
            await self.roll_interaction.edit_original_response(
                content="✅ Done! Check the channel.", view=None
            )
        except Exception:
            pass


class RollView(discord.ui.View):
    def __init__(self, char_key: str, char: dict, roll_interaction: discord.Interaction):
        super().__init__(timeout=90)
        self.add_item(CombatSavesSelect(char_key, char, roll_interaction))
        self.add_item(ChecksDiceSelect(char_key, char, roll_interaction))

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

# ======================== QUOTE AUTO-SUDO ========================

_QUOTE_STARTERS = ('"', '\u201c', '\u201d', '\u00ab', '\u00bb')


async def process_quote(message: discord.Message) -> bool:
    """
    If the message is in the quote channel and starts with a quote character,
    delete it and re-send via the character's webhook.
    Returns True if handled (caller should skip further processing).
    """
    if message.channel.id != QUOTE_CHANNEL_ID:
        return False
    if not message.content.startswith(_QUOTE_STARTERS):
        return False
    if not isinstance(message.channel, (discord.TextChannel, discord.Thread)):
        return False

    uid   = str(message.author.id)
    is_dm = uid == DM_USER_ID

    if not is_dm and uid not in PLAYER_CHARS:
        return False

    try:
        # Send FIRST (feels instant), then delete — mirrors April Fools behaviour
        if is_dm:
            await _send_as_dm(message.channel, message.author, message.content)
        else:
            await _send_as_char(message.channel, PLAYER_CHARS[uid], message.content)
        await message.delete()
        return True
    except (discord.Forbidden, discord.HTTPException) as e:
        print(f"[DnD] Quote webhook error: {e}")
        return False

# /roll is registered directly in bot.py via @bot.tree.command, same as all other commands.
