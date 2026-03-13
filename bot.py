"""
CRISPS GC Discord Bot
All commands, scheduled tasks, and event handlers in one file.
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
import random
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Optional
import os
import yaml
from pathlib import Path

from dotenv import load_dotenv
import config
import db

# ======================== SETUP ========================

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
MANILA_TZ = ZoneInfo(config.TIMEZONE)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

def load_yaml(filename):
    with open(Path(__file__).parent / "config" / filename, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
    
settings_data = load_yaml("settings.yaml")
haiku_data = load_yaml("haiku_data.yaml")


QUESTION_SCHEDULES = settings_data["question_schedules"]
HARDCODED = settings_data["ids"]

# Compatibility
HARDCODED["blacklist_categories"] = settings_data["blacklist_categories"]
HARDCODED["blacklist_channels"] = settings_data["blacklist_channels"]

# Hall of Fame: track which messages have been forwarded (in-memory cache)
_hall_of_fame_forwarded: set[int] = set()


def fmt_num(n: int) -> str:
    """Format number with comma separators: 1000000 -> 1,000,000"""
    return f"{n:,}"


# ======================== HAIKU DETECTION ========================

# Slang/abbreviations that disqualify a message from being a haiku
HAIKU_DISQUALIFY_WORDS = set(haiku_data["disqualify_words"])

# Words that the vowel-counting algorithm gets wrong
SYLLABLE_OVERRIDES = haiku_data["syllable_overrides"]


def count_syllables(word: str) -> int | None:
    """
    Count syllables in a word using dictionary lookup + vowel patterns fallback.
    Returns None if the word cannot be reliably syllable-counted (slang, numbers, etc).
    """
    word = word.lower().strip()
    
    # Skip empty or pure punctuation
    if not word or not any(c.isalpha() for c in word):
        return 0
    
    # Remove non-alpha characters for counting
    clean = ''.join(c for c in word if c.isalpha())
    
    if not clean:
        return 0
    
    # Check dictionary first
    if clean in SYLLABLE_OVERRIDES:
        return SYLLABLE_OVERRIDES[clean]
    
    # Check if it's a disqualified slang word
    if clean in HAIKU_DISQUALIFY_WORDS:
        return None
    
    # Check for numbers mixed with letters (like "2day") or pure numbers spelled
    if any(c.isdigit() for c in word):
        return None
    
    # Check for excessive consonant clusters that suggest abbreviation
    vowels = set('aeiouy')
    if len(clean) >= 3 and not any(c in vowels for c in clean):
        return None
    
    # Basic syllable counting algorithm
    count = 0
    prev_was_vowel = False
    
    for i, char in enumerate(clean):
        is_vowel = char in vowels
        if is_vowel and not prev_was_vowel:
            count += 1
        prev_was_vowel = is_vowel
    
    # Handle silent 'e' at end
    if clean.endswith('e') and count > 1 and len(clean) > 2:
        if clean[-2] not in vowels:  # consonant before final e
            count -= 1
    
    # Handle 'le' endings (like "table", "apple")
    if clean.endswith('le') and len(clean) > 2 and clean[-3] not in vowels:
        count += 1
    
    # Minimum 1 syllable for any real word
    return max(1, count)


def check_haiku(text: str) -> tuple[bool, list[str] | None]:
    """
    Check if text is a valid haiku (5-7-5 syllables).
    Returns (is_haiku, [line1, line2, line3]) or (False, None).
    """
    # Clean the text - remove extra whitespace, keep only words
    words = text.split()
    if not words:
        return False, None
    
    # Count syllables for each word
    syllable_counts = []
    word_list = []
    
    for word in words:
        # Strip punctuation from edges
        clean_word = word.strip('.,!?;:"\'()-[]{}…—–')
        if not clean_word:
            continue
        
        count = count_syllables(clean_word)
        if count is None:  # Disqualified word
            return False, None
        
        if count > 0:
            syllable_counts.append(count)
            word_list.append(clean_word)
    
    # Check if total syllables is 17 (5+7+5)
    total = sum(syllable_counts)
    if total != 17:
        return False, None
    
    # Try to split into 5-7-5 pattern
    line1_words = []
    line2_words = []
    line3_words = []
    
    current_count = 0
    line_idx = 0
    targets = [5, 7, 5]
    
    for i, (word, syl_count) in enumerate(zip(word_list, syllable_counts)):
        if line_idx == 0:
            line1_words.append(word)
            current_count += syl_count
            if current_count == targets[0]:
                line_idx = 1
                current_count = 0
            elif current_count > targets[0]:
                return False, None
        elif line_idx == 1:
            line2_words.append(word)
            current_count += syl_count
            if current_count == targets[1]:
                line_idx = 2
                current_count = 0
            elif current_count > targets[1]:
                return False, None
        else:
            line3_words.append(word)
            current_count += syl_count
    
    # Verify we got exactly 5-7-5
    if line_idx != 2 or current_count != 5:
        return False, None
    
    if not line1_words or not line2_words or not line3_words:
        return False, None
    
    return True, [
        " ".join(line1_words),
        " ".join(line2_words),
        " ".join(line3_words),
    ]


# ======================== HELPERS ========================


async def get_unused_question(guild_id: str, qtype: str, questions: list[str]) -> str:
    """Pick a random unused question (bag randomizer — no repeats until all used).
    Uses text-based tracking so adding/removing questions won't break the bag.
    """
    used = await db.get_used_questions(guild_id, qtype)
    if len(used) >= len(questions):
        await db.reset_questions(guild_id, qtype)
        used = []
    # Filter to questions not in the used set
    available = [q for q in questions if q not in used]
    if not available:
        # Fallback if all are somehow used
        await db.reset_questions(guild_id, qtype)
        available = questions
    chosen = random.choice(available)
    await db.mark_question_used(guild_id, qtype, chosen)
    return chosen


def _embed(title: str, description: str, color_key: str, footer: str = "", author: bool = True) -> discord.Embed:
    """Shortcut to build a standard embed."""
    e = discord.Embed(
        title=title,
        description=description,
        color=int(config.COLORS[color_key], 16),
    )
    if footer:
        e.set_footer(text=footer)
    if author and config.AUTHOR_NAME:
        e.set_author(name=config.AUTHOR_NAME)
    return e


def format_story(words_str: str) -> str:
    """Format raw word tokens into a clean story string
    - Punctuation attaches to previous word (no space before)
    - Auto-lowercase everything
    - Capitalize first character
    """
    if not words_str:
        return ""
    tokens = words_str.split()
    if not tokens:
        return ""

    PUNCT = set(".,!?;:-…'\"")
    result = []

    for token in tokens:
        is_punct = all(c in PUNCT for c in token)
        if is_punct and result:
            result[-1] += token
        else:
            result.append(token.lower())

    story = " ".join(result)
    if story:
        story = story[0].upper() + story[1:]
    return story


# ======================== TYPOLOGY FORMATTING ========================

SUPERSCRIPT_MAP = {"w": "ʷ", "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹", "?": "ˀ"}
SUBSCRIPT_MAP = {"0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄", "5": "₅", "6": "₆", "7": "₇", "8": "₈", "9": "₉"}


def format_mbti(raw: str) -> str:
    """Format MBTI input: '  isTp' → 'ISTP', 'xSFJ' → 'xSFJ' (preserves x)."""
    raw = raw.strip().upper()
    # Allow x for uncertain types
    if len(raw) == 4 and all(c in "IESFNTJPX" for c in raw):
        # Make the x lowercase for style: XSFJ → xSFJ
        return raw.replace("X", "x")
    return raw


def format_enneagram(raw: str) -> str:
    """Format enneagram: '3w2' stays as is, '3w?' allowed, '549w651' → '5ʷ⁶4ʷ⁵9ʷ¹'."""
    raw = raw.strip().lower().replace(" ", "")
    
    # Simple enneagram: digit + w + digit or ?
    if re.match(r"^[1-9]w[1-9?]$", raw):
        return raw
    
    # Full tritype with wings format: '549w651' or '549651' → '5ʷ⁶4ʷ⁵9ʷ¹'
    match = re.match(r"^([1-9])([1-9])([1-9])w?([1-9?])([1-9?])([1-9?])$", raw)
    if match:
        c1, c2, c3, w1, w2, w3 = match.groups()
        result = f"{c1}{SUPERSCRIPT_MAP['w']}{SUPERSCRIPT_MAP.get(w1, w1)}"
        result += f"{c2}{SUPERSCRIPT_MAP['w']}{SUPERSCRIPT_MAP.get(w2, w2)}"
        result += f"{c3}{SUPERSCRIPT_MAP['w']}{SUPERSCRIPT_MAP.get(w3, w3)}"
        return result
    
    return raw


def format_tritype(raw: str) -> str:
    """Format tritype: '963w874' → '9ʷ⁸6ʷ⁷3ʷ⁴', '963' → '963', allows ? for unknown wings."""
    raw = raw.strip().lower().replace(" ", "")
    
    # Check if it's a 6-digit+wing format like '963w874' or '963874'
    # Pattern: 3 core types + 'w' (optional) + 3 wings
    match = re.match(r"^([1-9])([1-9])([1-9])w?([1-9?])([1-9?])([1-9?])$", raw)
    if match:
        c1, c2, c3, w1, w2, w3 = match.groups()
        result = f"{c1}{SUPERSCRIPT_MAP['w']}{SUPERSCRIPT_MAP.get(w1, w1)}"
        result += f"{c2}{SUPERSCRIPT_MAP['w']}{SUPERSCRIPT_MAP.get(w2, w2)}"
        result += f"{c3}{SUPERSCRIPT_MAP['w']}{SUPERSCRIPT_MAP.get(w3, w3)}"
        return result
    
    # Simple tritype without wings: '963'
    if re.match(r"^[1-9]{3}$", raw):
        return raw
    
    # Already formatted or other format - return as is
    return raw


def format_instinct(raw: str) -> str:
    """Format instinctual stacking: 'so/sp', 'so/?', 'sp/sx', etc."""
    raw = raw.strip().lower().replace(" ", "")
    instincts = ["so", "sp", "sx", "?"]
    parts = raw.split("/")
    if len(parts) == 2 and parts[0] in instincts and parts[1] in instincts:
        return f"{parts[0]}/{parts[1]}"
    return raw


def format_ap(raw: str) -> str:
    """Format Attitudinal Psyche: 'fvle' → 'FVLE', allows ? for unknowns."""
    raw = raw.strip().upper()
    valid = set("FVLE?")
    if len(raw) == 4 and all(c in valid for c in raw):
        return raw
    return raw


def get_mbti_color(mbti: str) -> int:
    """Get embed color for an MBTI type. Returns Discord blurple for unknown/x types."""
    if not mbti or "x" in mbti.lower():
        return int(config.MBTI_DEFAULT_COLOR, 16)
    mbti_upper = mbti.upper()
    hex_color = config.MBTI_COLORS.get(mbti_upper, config.MBTI_DEFAULT_COLOR)
    return int(hex_color, 16)


def get_mbti_display(mbti: str) -> str:
    """Get MBTI with cognitive functions: 'ESTJ' → 'ESTJ (𝘛𝘦𝘚𝘪𝘕𝘦𝘍𝘪)'."""
    if not mbti:
        return "?"
    mbti_upper = mbti.upper().replace("X", "x")
    functions = config.MBTI_FUNCTIONS.get(mbti_upper.upper(), "")
    if functions:
        return f"{mbti_upper} ({functions})"
    return mbti_upper


def build_typology_embed(target: discord.Member, profile: dict | None, attach_mbti: bool = False) -> tuple[discord.Embed, discord.File | None]:
    """Build a typology profile embed. Returns (embed, file) where file is the MBTI avatar if available."""
    mbti = profile.get("mbti", "") if profile else ""
    enneagram = profile.get("enneagram", "") if profile else ""
    tritype = profile.get("tritype", "") if profile else ""
    instinct = profile.get("instinct", "") if profile else ""
    ap = profile.get("ap", "") if profile else ""
    
    mbti_display = get_mbti_display(mbti) if mbti else "?"
    enneagram_display = enneagram or "?"
    tritype_display = tritype or "?"
    ap_display = ap or "?"
    
    if instinct and enneagram:
        core = enneagram[0] if enneagram else ""
        dom = instinct.split("/")[0] if "/" in instinct else instinct
        instinct_display = f"{instinct} ({dom}{core})" if core else instinct
    else:
        instinct_display = instinct or "?"
    
    color = get_mbti_color(mbti)
    embed = discord.Embed(color=color)
    
    profile_text = (
        f"**MBTI:** {mbti_display}\n"
        f"**Enneagram:** {enneagram_display}\n"
        f"**Tritype:** {tritype_display}\n"
        f"**Instinct:** {instinct_display}\n"
        f"**AP:** {ap_display}"
    )
    embed.description = profile_text
    embed.set_thumbnail(url=target.display_avatar.url)
    
    id_url = f"https://typology.id/{target.id}"
    file = None
    if attach_mbti and mbti:
        mbti_clean = mbti.upper().replace("X", "").replace("x", "")
        if mbti_clean in config.MBTI_TYPES:
            avatar_path = os.path.join(os.path.dirname(__file__), "MBTI_Avatars", f"{mbti_clean}.png")
            if os.path.exists(avatar_path):
                file = discord.File(avatar_path, filename=f"{mbti_clean}.png")
                embed.set_author(name=target.display_name, icon_url=f"attachment://{mbti_clean}.png", url=id_url)
            else:
                embed.set_author(name=target.display_name, url=id_url)
        else:
            embed.set_author(name=target.display_name, url=id_url)
    else:
        embed.set_author(name=target.display_name, url=id_url)
    
    return embed, file


# ======================== POSTING FUNCTIONS ========================


async def post_casual(guild_id: str, ping: bool = True, channel: discord.TextChannel = None, exclude_polls: bool = False):
    """Post a casual question (Fun Questions, Polls, WYR, Debates, or Button) using type+question bags."""
    if not channel:
        channel_id = HARDCODED["channel_casual"]
        channel = bot.get_channel(int(channel_id))
    if not channel:
        print(f"[Casual] Could not find channel")
        return

    categories = ["fun", "poll"]
    if exclude_polls:
        categories = [c for c in categories if c != "poll"]
    category_map = {
        "fun": (config.CASUAL_QUESTIONS, "casual_fun", "Question"),
        "poll": (config.CASUAL_POLLS, "casual_poll", "Poll"),
    }
    
    # Use text-based tracking for category rotation
    used_types = await db.get_used_questions(guild_id, "casual_type")
    if len(used_types) >= len(categories):
        await db.reset_questions(guild_id, "casual_type")
        used_types = []
    available_types = [cat for cat in categories if cat not in used_types]
    selected_cat = random.choice(available_types)
    await db.mark_question_used(guild_id, "casual_type", selected_cat)
    
    questions, qtype_key, display_name = category_map[selected_cat]
    
    question = await get_unused_question(guild_id, qtype_key, questions)

    count_str = await db.get_state(guild_id, "casual_question_count") or "0"
    count = int(count_str) + 1
    await db.set_state(guild_id, "casual_question_count", str(count))

    embed = _embed(
        config.EMBEDS["casual"]["title"],
        question,
        "casual",
        footer=f"{display_name} (#{count})",
    )

    view = NewQuestionView("casual")
    
    if ping:
        ping_role_id = HARDCODED["ping_role_casual"]
        content = f"<@&{ping_role_id}>"
        msg = await channel.send(content=content, embed=embed, view=view, allowed_mentions=discord.AllowedMentions(roles=True))
    else:
        msg = await channel.send(embed=embed, view=view)
    
    # For polls, add yes/no reactions
    if selected_cat == "poll":
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")


async def post_typology(guild_id: str, ping: bool = True, channel: discord.TextChannel = None):
    """Post a typology question (Matchups, Hot Takes, or Scenarios) using type+question bags."""
    if not channel:
        channel_id = HARDCODED["channel_typology"]
        channel = bot.get_channel(int(channel_id))
    if not channel:
        print(f"[Typology] Could not find channel")
        return

    categories = ["matchups", "hottakes", "who"]
    
    # Use text-based tracking for category rotation
    used_types = await db.get_used_questions(guild_id, "typology_type")
    if len(used_types) >= len(categories):
        await db.reset_questions(guild_id, "typology_type")
        used_types = []
    available_types = [cat for cat in categories if cat not in used_types]
    category = random.choice(available_types)
    await db.mark_question_used(guild_id, "typology_type", category)
    
    reactions_to_add = []
    
    if category == "matchups":
        # Pick unused matchup using type combo as key
        matchups = config.REALISTIC_TYPE_MATCHUPS
        used_matchups = await db.get_used_questions(guild_id, "typology_matchups")
        # Build available matchups (key = "type1 vs type2")
        available_matchups = [m for m in matchups if f"{m['type1']} vs {m['type2']}" not in used_matchups]
        if not available_matchups:
            await db.reset_questions(guild_id, "typology_matchups")
            available_matchups = matchups
        matchup = random.choice(available_matchups)
        matchup_key = f"{matchup['type1']} vs {matchup['type2']}"
        await db.mark_question_used(guild_id, "typology_matchups", matchup_key)
        
        question = random.choice(matchup["questions"])
        description = f"1️⃣ **{matchup['type1']}**  vs  2️⃣ **{matchup['type2']}**\n\n{question}"
        footer_text = "Type Matchup"
        reactions_to_add = ["1️⃣", "2️⃣"]
    elif category == "hottakes":
        # Pick unused hot take (already text-based via get_unused_question)
        hot_take = await get_unused_question(guild_id, "typology_hottakes", config.TYPOLOGY_HOT_TAKES)
        description = f"\n\"{hot_take}\"\n\n👍 Agree  ·  👎 Disagree"
        footer_text = "Hot Take"
        reactions_to_add = ["👍", "👎"]
    else:
        # Pick unused "who" question
        question = await get_unused_question(guild_id, "typology_who", config.TYPOLOGY_WHO_QUESTIONS)
        description = question
        footer_text = "Most Likely To"
    
    count_str = await db.get_state(guild_id, "typology_question_count") or "0"
    count = int(count_str) + 1
    await db.set_state(guild_id, "typology_question_count", str(count))

    embed = _embed(
        config.EMBEDS["typology"]["title"],
        description,
        "typology",
        footer=f"{footer_text} (#{count})",
    )

    view = NewQuestionView("typology")
    if ping:
        ping_role_id = HARDCODED["ping_role_typology"]
        content = f"<@&{ping_role_id}>"
        msg = await channel.send(content=content, embed=embed, view=view, allowed_mentions=discord.AllowedMentions(roles=True))
    else:
        msg = await channel.send(embed=embed, view=view)
    
    # Add voting reactions
    for reaction in reactions_to_add:
        try:
            await msg.add_reaction(reaction)
        except Exception:
            pass


# Map question type → post function
QUESTION_POST_FNS = {
    "casual": post_casual,
    "typology": post_typology,
}


def generate_math_question() -> tuple[str, int]:
    """Generate a random math question and answer"""
    ops = [
        ("+", lambda a, b: a + b),
        ("-", lambda a, b: a - b),
        ("×", lambda a, b: a * b),
    ]
    
    # Generate 2-3 operand expression
    num_ops = random.choice([1, 2])
    
    if num_ops == 1:
        a = random.randint(1, 50)
        b = random.randint(1, 50)
        op_symbol, op_func = random.choice(ops)
        equation = f"{a} {op_symbol} {b}"
        answer = op_func(a, b)
    else:
        # 3 operands - follow order of operations
        a = random.randint(1, 20)
        b = random.randint(1, 20)
        c = random.randint(1, 20)
        op1_symbol, op1_func = random.choice(ops)
        op2_symbol, op2_func = random.choice(ops)
        equation = f"{a} {op1_symbol} {b} {op2_symbol} {c}"
        
        # Calculate following order of operations (×/÷ before +/-)
        if op2_symbol == "×":
            answer = op1_func(a, op2_func(b, c))
        elif op1_symbol == "×":
            answer = op2_func(op1_func(a, b), c)
        else:
            answer = op2_func(op1_func(a, b), c)
    
    return equation, answer


async def do_chip_drop(guild_id: str, channel_id: str = None):
    """Create a new chip drop event"""
    # Use provided channel or fall back to last message channel
    if not channel_id:
        channel_id = await db.get_state(guild_id, "last_message_channel")
    if not channel_id:
        print(f"[ChipDrop] No channel available for guild {guild_id}")
        return
    
    channel = bot.get_channel(int(channel_id))
    if not channel:
        print(f"[ChipDrop] Could not find channel {channel_id}")
        return
    
    if channel.category_id and str(channel.category_id) in HARDCODED["blacklist_categories"]:
        print(f"[ChipDrop] Channel {channel_id} is in blacklisted category, skipping")
        return
    if str(channel_id) in HARDCODED["blacklist_channels"]:
        print(f"[ChipDrop] Channel {channel_id} is blacklisted, skipping")
        return

    existing = await db.get_chip_drop(guild_id)
    if existing:
        return

    # Random amount between min and max
    amount = random.randint(config.CHIP_DROP["min_amount"], config.CHIP_DROP["max_amount"])
    emoji = config.CHIPS["emoji"]
    
    if random.random() < config.CHIP_DROP["math_chance"]:
        equation, answer = generate_math_question()
        announcement = config.MESSAGES["chip_drop"]["math_announcement"].format(
            equation=equation, amount=fmt_num(amount), emoji=emoji
        )
        drop_type = "math"
        answer_str = str(answer)
    else:
        announcement = config.MESSAGES["chip_drop"]["grab_announcement"].format(
            amount=fmt_num(amount), emoji=emoji
        )
        drop_type = "grab"
        answer_str = ""

    msg = await channel.send(announcement)
    await db.create_chip_drop(guild_id, str(channel.id), str(msg.id), amount, drop_type, answer_str)


async def check_chip_drop_expired(guild_id: str):
    """Check if active chip drop has expired"""
    drop = await db.get_chip_drop(guild_id)
    if not drop:
        return
    
    created = datetime.fromisoformat(drop["created_at"])
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    
    elapsed = (datetime.now(timezone.utc) - created).total_seconds()
    if elapsed >= config.CHIP_DROP["timeout"]:
        channel = bot.get_channel(int(drop["channel_id"]))
        if channel:
            try:
                msg = await channel.fetch_message(int(drop["message_id"]))
                expired_msg = random.choice(config.MESSAGES["chip_drop"]["expired"])
                await msg.edit(content=f"~~{msg.content}~~\n\n{expired_msg}")
            except Exception:
                pass
        await db.delete_chip_drop(guild_id)


async def check_code_purple(guild_id: str):
    if not config.FEATURES.get("code_purple"):
        return

    channel_id = HARDCODED["channel_codepurple"]
    if not channel_id:
        return

    last_msg_time = await db.get_state(guild_id, "last_message_time")
    if not last_msg_time:
        return

    last = datetime.fromisoformat(last_msg_time)
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    hours = (datetime.now(timezone.utc) - last).total_seconds() / 3600

    if hours < config.CODE_PURPLE["inactivity_hours"]:
        return

    last_purple = await db.get_state(guild_id, "last_code_purple")
    if last_purple:
        lp = datetime.fromisoformat(last_purple)
        if lp.tzinfo is None:
            lp = lp.replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - lp).total_seconds() / 3600 < config.CODE_PURPLE["cooldown_hours"]:
            return

    channel = bot.get_channel(int(channel_id))
    if not channel:
        return

    await channel.send(random.choice(config.MESSAGES["code_purple"]))
    await db.set_state(guild_id, "last_code_purple", datetime.now(timezone.utc).isoformat())


async def do_chatter_rewards(guild_id: str):
    channel_id = HARDCODED["channel_chatter_rewards"]
    if not channel_id:
        return
    channel = bot.get_channel(int(channel_id))
    if not channel:
        return

    today = datetime.now(MANILA_TZ).date().isoformat()
    chatters = await db.get_top_chatters(guild_id, today)
    emoji = config.CHIPS["emoji"]
    
    rewards = [
        config.CHIPS["rewards"]["top_chatter"],
        config.CHIPS["rewards"]["second_chatter"],
        config.CHIPS["rewards"]["third_chatter"],
    ]
    msg_templates = [
        config.MESSAGES["chatter_reward"]["top_chatter"],
        config.MESSAGES["chatter_reward"]["second_chatter"],
        config.MESSAGES["chatter_reward"]["third_chatter"],
    ]

    if not chatters:
        await channel.send(config.MESSAGES["chatter_reward"]["no_activity"])
        await db.clear_daily_chatter(guild_id, today)
        return

    lines = [config.MESSAGES["chatter_reward"]["announcement"]]

    for i, user in enumerate(chatters):
        if i >= 3:
            break
        await db.add_chips(guild_id, user["user_id"], user["username"], rewards[i])
        lines.append(
            msg_templates[i].format(
                user=f"<@{user['user_id']}>",
                amount=fmt_num(rewards[i]),
                emoji=emoji,
                messages=user["message_count"]
            )
        )

    await channel.send("\n".join(lines))
    await db.clear_daily_chatter(guild_id, today)
    await db.set_state(guild_id, "last_chatter_post", datetime.now(timezone.utc).isoformat())


async def do_activity_rewards(guild_id: str):
    """Daily activity rewards: messages + VC time"""
    channel_id = HARDCODED["channel_activity_rewards"]
    if not channel_id:
        return
    channel = bot.get_channel(int(channel_id))
    if not channel:
        return

    today = datetime.now(MANILA_TZ).date().isoformat()
    top_activity = await db.get_top_activity(guild_id, today)
    emoji = config.CHIPS["emoji"]
    
    rewards = [
        config.ACTIVITY_REWARDS["first_place"],
        config.ACTIVITY_REWARDS["second_place"],
        config.ACTIVITY_REWARDS["third_place"],
    ]
    msg_templates = [
        config.MESSAGES["activity_rewards"]["first_place"],
        config.MESSAGES["activity_rewards"]["second_place"],
        config.MESSAGES["activity_rewards"]["third_place"],
    ]

    if not top_activity:
        await channel.send(config.MESSAGES["activity_rewards"]["no_activity"])
        await db.clear_daily_activity(guild_id, today)
        return

    lines = [config.MESSAGES["activity_rewards"]["announcement"]]

    for i, user in enumerate(top_activity):
        if i >= 3:
            break
        await db.add_chips(guild_id, user["user_id"], user["username"], rewards[i])
        lines.append(
            msg_templates[i].format(
                user=f"<@{user['user_id']}>",
                amount=fmt_num(rewards[i]),
                emoji=emoji,
                points=fmt_num(user["total"])
            )
        )

    await channel.send("\n".join(lines))
    await db.clear_daily_activity(guild_id, today)
    await db.set_state(guild_id, "last_activity_post", datetime.now(timezone.utc).isoformat())


# ======================== SCHEDULED TASKS ========================


@tasks.loop(seconds=60)
async def schedule_loop():
    """Main schedule loop — checks daily questions and chatter every minute."""
    now_utc = datetime.now(timezone.utc)
    now_manila = datetime.now(MANILA_TZ)

    for guild in bot.guilds:
        gid = str(guild.id)

        # DISABLED: Automatic QOTD and typology posting
        # for qtype, sched in QUESTION_SCHEDULES.items():
        #     if now_manila.hour == sched["hour"] and now_manila.minute == sched["minute"]:
        #         # Check if already posted recently (within 23 hours) - prevents race conditions
        #         last_iso = await db.get_state(gid, f"last_{qtype}_question")
        #         should_post = True
        #         if last_iso:
        #             last_dt = datetime.fromisoformat(last_iso)
        #             if last_dt.tzinfo is None:
        #                 last_dt = last_dt.replace(tzinfo=timezone.utc)
        #             hours_since = (now_utc - last_dt).total_seconds() / 3600
        #             if hours_since < 23:  # Posted within last 23 hours = skip
        #                 should_post = False
        #         
        #         if should_post:
        #             await db.set_state(gid, f"last_{qtype}_question", now_utc.isoformat())
        #             
        #             post_fn = QUESTION_POST_FNS.get(qtype)
        #             if post_fn:
        #                 try:
        #                     await post_fn(gid)
        #                     print(f"[Schedule] Posted {qtype} question for guild {gid}")
        #                 except Exception as e:
        #                     print(f"Error posting {qtype}: {e}")

        # --- Chatter Rewards (fixed Manila time) ---
        sched = config.CHATTER_SCHEDULE
        if now_manila.hour == sched["hour"] and now_manila.minute == sched["minute"]:
            last = await db.get_state(gid, "last_chatter_post")
            should_post = True
            if last:
                ld = datetime.fromisoformat(last)
                if ld.tzinfo is None:
                    ld = ld.replace(tzinfo=timezone.utc)
                hours_since = (now_utc - ld).total_seconds() / 3600
                if hours_since < 23:  # Posted within last 23 hours = skip
                    should_post = False
            if should_post:
                await db.set_state(gid, "last_chatter_post", now_utc.isoformat())
                try:
                    await do_chatter_rewards(gid)
                except Exception as e:
                    print(f"Error doing chatter rewards: {e}")

        act_sched = config.ACTIVITY_REWARDS
        if now_manila.hour == act_sched["hour"] and now_manila.minute == act_sched["minute"]:
            if config.FEATURES.get("activity_rewards"):
                last = await db.get_state(gid, "last_activity_post")
                should_post = True
                if last:
                    ld = datetime.fromisoformat(last)
                    if ld.tzinfo is None:
                        ld = ld.replace(tzinfo=timezone.utc)
                    hours_since = (now_utc - ld).total_seconds() / 3600
                    if hours_since < 23:
                        should_post = False
                if should_post:
                    await db.set_state(gid, "last_activity_post", now_utc.isoformat())
                    try:
                        await do_activity_rewards(gid)
                    except Exception as e:
                        print(f"Error doing activity rewards: {e}")

        if now_manila.minute == 0:
            await check_code_purple(gid)

        if now_manila.minute % 10 == 0:
            try:
                await auto_start_word_game(gid)
            except Exception as e:
                print(f"Error checking word game auto-start: {e}")


@schedule_loop.before_loop
async def before_schedule():
    await bot.wait_until_ready()
    await asyncio.sleep(random.uniform(0, 30))


async def chip_drop_cycle():
    """Background loop — manages chip drops based on activity."""
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        await asyncio.sleep(60)
        
        if not config.FEATURES.get("chip_drops"):
            continue
            
        for guild in bot.guilds:
            gid = str(guild.id)
            try:
                await check_chip_drop_expired(gid)
                
                existing = await db.get_chip_drop(gid)
                if existing:
                    continue
                
                last_drop = await db.get_state(gid, "last_chip_drop_claimed")
                if last_drop:
                    last_dt = datetime.fromisoformat(last_drop)
                    if last_dt.tzinfo is None:
                        last_dt = last_dt.replace(tzinfo=timezone.utc)
                    hours_passed = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600
                    
                    # Get random cooldown for this guild
                    cooldown = await db.get_state(gid, "chip_drop_cooldown_hours")
                    if cooldown:
                        if hours_passed < float(cooldown):
                            continue
                
                last_msg = await db.get_state(gid, "last_message_time")
                if not last_msg:
                    continue
                
                last_msg_dt = datetime.fromisoformat(last_msg)
                if last_msg_dt.tzinfo is None:
                    last_msg_dt = last_msg_dt.replace(tzinfo=timezone.utc)
                
                mins_since_activity = (datetime.now(timezone.utc) - last_msg_dt).total_seconds() / 60
                if mins_since_activity > config.CHIP_DROP["activity_window"]:
                    continue
                
                scheduled = await db.get_state(gid, "chip_drop_scheduled_at")
                if not scheduled:
                    delay = random.randint(config.CHIP_DROP["min_delay"], config.CHIP_DROP["max_delay"])
                    drop_time = datetime.now(timezone.utc) + timedelta(minutes=delay)
                    await db.set_state(gid, "chip_drop_scheduled_at", drop_time.isoformat())
                else:
                    sched_dt = datetime.fromisoformat(scheduled)
                    if sched_dt.tzinfo is None:
                        sched_dt = sched_dt.replace(tzinfo=timezone.utc)
                    
                    if datetime.now(timezone.utc) >= sched_dt:
                        await do_chip_drop(gid)
                        await db.delete_state(gid, "chip_drop_scheduled_at")
                        
            except Exception as e:
                print(f"Chip drop cycle error in {guild.name}: {e}")


# ======================== WORD GAME ========================


def build_word_game_embed(story: str, word_count: int, active: bool, last_user=None) -> discord.Embed:
    wg = config.WORD_GAME
    if active:
        title = wg["embed"]["title"]
        footer = wg["embed"]["footer"]
    else:
        title = wg["embed"]["title_ended"]
        footer = f"{word_count} {wg['embed']['footer_ended']}"

    display = story if story else wg["embed"]["empty_story"]
    color = int(wg["embed"]["color"], 16)

    embed = discord.Embed(title=title, description=display, color=color)
    embed.set_footer(text=footer)

    if last_user and active:
        embed.set_author(
            name=f"{wg['embed']['last_word_by']} {last_user.display_name}",
            icon_url=last_user.display_avatar.url,
        )

    return embed


class WordGameActiveView(discord.ui.View):
    """Persistent view with 'End this story' button on active game embeds."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="End this story", style=discord.ButtonStyle.danger, custom_id="wordgame_end")
    async def end_story(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = str(interaction.guild_id)
        game = await db.get_word_game(gid)
        if not game or not game["active"]:
            await interaction.response.send_message("No active game to end.", ephemeral=True)
            return

        await interaction.response.defer()
        await db.end_word_game(gid)
        game = await db.get_word_game(gid)
        
        await db.set_state(gid, "last_wordgame_activity", datetime.now(timezone.utc).isoformat())

        try:
            await interaction.message.delete()
        except Exception:
            pass

        # Post completed story with Start button
        story = format_story(game["words"])
        embed = build_word_game_embed(story, game["word_count"], False)
        view = WordGameStartView()
        end_text = f"📖 {interaction.user.mention} ended the story! ({game['word_count']} words total)."
        msg = await interaction.channel.send(content=end_text, embed=embed, view=view)
        await db.update_word_game_message(gid, str(msg.id))


class WordGameStartView(discord.ui.View):
    """Persistent view with 'Start new story' button on ended game embeds."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Start new story", style=discord.ButtonStyle.success, custom_id="wordgame_start")
    async def start_story(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = str(interaction.guild_id)
        game = await db.get_word_game(gid)
        if game and game["active"]:
            await interaction.response.send_message("A game is already active!", ephemeral=True)
            return

        await interaction.response.defer()

        # Remove the button from the completed story message (preserve the story)
        try:
            await interaction.message.edit(view=None)
        except Exception:
            pass

        embed = build_word_game_embed("", 0, True)
        view = WordGameActiveView()
        msg = await interaction.channel.send(embed=embed, view=view)
        await db.create_word_game(gid, str(interaction.channel.id), str(msg.id))


class NewQuestionView(discord.ui.View):
    """Persistent view with 'New Question' button on question embeds."""

    def __init__(self, question_type: str = None):
        super().__init__(timeout=None)
        self.question_type = question_type
        # Set custom_id based on type for persistence
        if question_type:
            self.new_question_btn.custom_id = f"newquestion_{question_type}"

    @discord.ui.button(label="New Question", style=discord.ButtonStyle.secondary, custom_id="newquestion_default")
    async def new_question_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = str(interaction.guild_id)
        qtype = button.custom_id.replace("newquestion_", "")
        
        await interaction.response.defer()
        
        try:
            await interaction.message.edit(view=None)
        except Exception:
            pass
        
        # Show who requested the new question
        await interaction.channel.send(f"-# {interaction.user.display_name} requested a new question")
        
        if qtype == "casual":
            await post_casual(gid, ping=False, channel=interaction.channel, exclude_polls=True)
        elif qtype == "typology":
            await post_typology(gid, ping=False, channel=interaction.channel)


async def auto_start_word_game(gid: str) -> bool:
    """Auto-start a word game if it's been waiting too long. Returns True if started."""
    game = await db.get_word_game(gid)
    if not game:
        return False
    
    # Only auto-start if game exists but is NOT active (waiting for someone to start)
    if game["active"]:
        return False
    
    channel_id = game.get("channel_id")
    if not channel_id:
        return False
    
    # Check if it's been 3+ hours since last activity
    last_activity_iso = await db.get_state(gid, "last_wordgame_activity")
    if not last_activity_iso:
        # No tracking yet - start tracking now but don't auto-start yet
        await db.set_state(gid, "last_wordgame_activity", datetime.now(timezone.utc).isoformat())
        return False
    
    last_activity = datetime.fromisoformat(last_activity_iso)
    if last_activity.tzinfo is None:
        last_activity = last_activity.replace(tzinfo=timezone.utc)
    
    hours_since = (datetime.now(timezone.utc) - last_activity).total_seconds() / 3600
    if hours_since < 3:
        return False
    
    # Find the channel
    guild = bot.get_guild(int(gid))
    if not guild:
        return False
    
    channel = guild.get_channel(int(channel_id))
    if not channel:
        return False
    
    # Remove button from old completed story message (preserve the story)
    try:
        old_msg_id = game.get("message_id")
        if old_msg_id:
            old_msg = await channel.fetch_message(int(old_msg_id))
            await old_msg.edit(view=None)
    except Exception:
        pass
    
    embed = build_word_game_embed("", 0, True)
    view = WordGameActiveView()
    msg = await channel.send(embed=embed, view=view)
    await db.create_word_game(gid, channel_id, str(msg.id))
    
    print(f"[WordGame] Auto-started game in guild {gid} after {hours_since:.1f}h inactivity")
    return True


# ======================== SLASH COMMANDS ========================

# ---------- Public ----------

BOT_VERSION = "v2.0.3"


@bot.tree.command(name="version", description="Check bot version (debug)")
async def version_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(f"Bot version: **{BOT_VERSION}**", ephemeral=True)


@bot.tree.command(name="balance", description="Check your chip balance 🥔")
async def balance_cmd(interaction: discord.Interaction):
    gid, uid = str(interaction.guild_id), str(interaction.user.id)
    bal = await db.get_balance(gid, uid)
    rank = await db.get_rank(gid, uid)

    if bal == 0:
        await interaction.response.send_message(config.MESSAGES["balance"]["no_balance"])
    else:
        rank_str = f"#{rank}" if rank else config.MESSAGES["balance"]["unranked"]
        msg = config.MESSAGES["balance"]["response"].format(
            amount=fmt_num(bal), emoji=config.CHIPS["emoji"], rank=rank_str
        )
        await interaction.response.send_message(msg)


@bot.tree.command(name="chipleaderboard", description="View the server chip leaderboard 🏆")
async def leaderboard_cmd(interaction: discord.Interaction):
    gid, uid = str(interaction.guild_id), str(interaction.user.id)
    entries = await db.get_leaderboard(gid, 10)

    if not entries:
        embed = discord.Embed(
            title=config.EMBEDS["leaderboard"]["title"],
            description="No one has earned chips yet! Be the first! 🥔",
            color=int(config.COLORS["leaderboard"], 16),
        )
        await interaction.response.send_message(embed=embed)
        return

    rank_emojis = config.EMBEDS["leaderboard"]["rank_emojis"]
    lines = []
    for i, entry in enumerate(entries, 1):
        emoji = rank_emojis.get(str(i), rank_emojis["default"])
        lines.append(
            config.MESSAGES["leaderboard"]["entry"].format(
                emoji=emoji,
                rank=i,
                user=f"<@{entry['user_id']}>",
                amount=fmt_num(entry["chips"]),
                currency=config.CHIPS["name"],
            )
        )

    embed = discord.Embed(
        title=config.EMBEDS["leaderboard"]["title"],
        description="\n".join(lines),
        color=int(config.COLORS["leaderboard"], 16),
    )

    user_rank = await db.get_rank(gid, uid)
    user_bal = await db.get_balance(gid, uid)
    if user_rank and user_rank > 10:
        embed.add_field(
            name="Your Position",
            value=config.MESSAGES["leaderboard"]["your_position"].format(
                rank=user_rank, amount=fmt_num(user_bal), currency=config.CHIPS["name"]
            ),
        )

    await interaction.response.send_message(embed=embed)

# ---------- Admin ----------


@bot.tree.command(name="chips", description="Set a user's chip balance (admin only)")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(user="The user", amount="The amount to set")
async def chips_cmd(interaction: discord.Interaction, user: discord.Member, amount: int):
    gid = str(interaction.guild_id)
    await db.set_chips(gid, str(user.id), user.display_name, amount)
    await interaction.response.send_message(
        f"Set {user.mention}'s chips to **{fmt_num(amount)} {config.CHIPS['emoji']}**", ephemeral=True
    )


# @bot.tree.command(name="codepurple", description="Force a Code Purple message (admin only)")
# @app_commands.default_permissions(administrator=True)
# async def codepurple_cmd(interaction: discord.Interaction):
#     gid = str(interaction.guild_id)
#     channel_id = HARDCODED["channel_codepurple"]
#     channel = bot.get_channel(int(channel_id))
#     if not channel:
#         await interaction.response.send_message("Channel not found!", ephemeral=True)
#         return
#     await channel.send(random.choice(config.MESSAGES["code_purple"]))
#     await db.set_state(gid, "last_code_purple", datetime.now(timezone.utc).isoformat())
#     await interaction.response.send_message(f"Code purple posted to <#{channel_id}>", ephemeral=True)

# @bot.tree.command(name="viewchannels", description="View current channel settings (admin only)")
# @app_commands.default_permissions(administrator=True)
# async def viewchannels_cmd(interaction: discord.Interaction):
#     ...

# @bot.tree.command(name="viewschedule", description="View upcoming scheduled posts (admin only)")
# @app_commands.default_permissions(administrator=True)
# async def viewschedule_cmd(interaction: discord.Interaction):
#     ...

# @bot.tree.command(name="forcepost", description="Force post a question or trigger chip drop (admin only)")
# @app_commands.default_permissions(administrator=True)
# async def forcepost_cmd(interaction: discord.Interaction, feature: app_commands.Choice[str]):
#     ...


# ======================== GAMBLING ========================

CARD_SUITS = ['♠', '♥', '♦', '♣']
CARD_RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
CARD_VALUES = {r: i for i, r in enumerate(CARD_RANKS)}


def create_deck() -> list[tuple[str, str]]:
    """Create a shuffled 52-card deck."""
    deck = [(rank, suit) for suit in CARD_SUITS for rank in CARD_RANKS]
    random.shuffle(deck)
    return deck


def card_str(card: tuple[str, str]) -> str:
    """Format card as emoji-style string: [K♠]"""
    return f"`[{card[0]}{card[1]}]`"


def compare_cards(current: tuple, next_card: tuple) -> str:
    """Compare two cards. Returns 'higher', 'lower', or 'tie'."""
    curr_val = CARD_VALUES[current[0]]
    next_val = CARD_VALUES[next_card[0]]
    if next_val > curr_val:
        return 'higher'
    elif next_val < curr_val:
        return 'lower'
    return 'tie'


def hl_multiplier(streak: int) -> float:
    """0.25x per correct guess. Break even at 4."""
    return streak * 0.25


# Store active games: {(guild_id, user_id): game_state}
_active_games: dict[tuple[str, str], dict] = {}


class BetModal(discord.ui.Modal, title="Place Your Bet!"):
    """Modal to enter bet amount."""
    
    bet_input = discord.ui.TextInput(
        label="How many chips would you like to bet?",
        placeholder="e.g. 500",
        min_length=1,
        max_length=10,
    )
    
    def __init__(self, game_type: str):
        super().__init__()
        self.game_type = game_type
    
    async def on_submit(self, interaction: discord.Interaction):
        gid, uid = str(interaction.guild_id), str(interaction.user.id)
        
        # Parse bet amount
        try:
            bet = int(self.bet_input.value.replace(",", "").strip())
        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number.", ephemeral=True)
            return
        
        if bet <= 0:
            await interaction.response.send_message("❌ Bet must be greater than 0.", ephemeral=True)
            return
        
        # Check balance
        balance = await db.get_balance(gid, uid)
        if bet > balance:
            emoji = config.CHIPS["emoji"]
            await interaction.response.send_message(
                f"❌ You don't have enough crisps! You have **{fmt_num(balance)}** {emoji}",
                ephemeral=True
            )
            return
        
        # Check for existing game
        if (gid, uid) in _active_games:
            await interaction.response.send_message("❌ You already have a game in progress!", ephemeral=True)
            return
        
        # Deduct bet and start game
        await db.add_chips(gid, uid, interaction.user.display_name, -bet)
        
        if self.game_type == "higher_lower":
            await start_higher_lower(interaction, bet)


async def start_higher_lower(interaction: discord.Interaction, bet: int):
    """Start a new Higher or Lower game."""
    gid, uid = str(interaction.guild_id), str(interaction.user.id)
    emoji = config.CHIPS["emoji"]
    
    deck = create_deck()
    current = deck.pop()
    
    # Store game state
    _active_games[(gid, uid)] = {
        "type": "higher_lower",
        "deck": deck,
        "current": current,
        "bet": bet,
        "streak": 0,
    }
    
    multiplier = hl_multiplier(0)
    potential = int(bet * multiplier)
    
    embed = discord.Embed(
        title="🎴 Higher or Lower",
        description=(
            f"**Current card:** {card_str(current)}\n\n"
            f"Will the next card be **higher** or **lower**?\n\n"
            f"Streak: **0** • Multiplier: **{multiplier:.1f}x** • Value: **{fmt_num(potential)}** {emoji}"
        ),
        color=0x9b59b6
    )
    embed.set_footer(text=f"Bet: {fmt_num(bet)} {emoji}")
    
    view = HigherLowerView()
    await interaction.response.send_message(embed=embed, view=view)


class HigherLowerView(discord.ui.View):
    """Game controls for Higher or Lower."""
    
    def __init__(self):
        super().__init__(timeout=120)
    
    async def on_timeout(self):
        # Game expires - player loses bet
        pass
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        gid, uid = str(interaction.guild_id), str(interaction.user.id)
        if (gid, uid) not in _active_games:
            await interaction.response.send_message("❌ This isn't your game!", ephemeral=True)
            return False
        return True
    
    @discord.ui.button(label="⬆️ Higher", style=discord.ButtonStyle.primary)
    async def higher_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.make_guess(interaction, "higher")
    
    @discord.ui.button(label="⬇️ Lower", style=discord.ButtonStyle.primary)
    async def lower_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.make_guess(interaction, "lower")
    
    async def make_guess(self, interaction: discord.Interaction, guess: str):
        gid, uid = str(interaction.guild_id), str(interaction.user.id)
        game = _active_games.get((gid, uid))
        
        if not game:
            await interaction.response.send_message("❌ No active game found.", ephemeral=True)
            return
        
        emoji = config.CHIPS["emoji"]
        deck = game["deck"]
        current = game["current"]
        
        # Reshuffle if deck is low
        if len(deck) < 5:
            deck = create_deck()
            game["deck"] = deck
        
        # Draw next card
        next_card = deck.pop()
        result = compare_cards(current, next_card)
        
        if result == "tie":
            # Tie - no change, continue
            game["current"] = next_card
            multiplier = hl_multiplier(game["streak"])
            potential = int(game["bet"] * multiplier)
            
            embed = discord.Embed(
                title="🎴 Higher or Lower — Tie!",
                description=(
                    f"**Previous:** {card_str(current)} → **Next:** {card_str(next_card)}\n\n"
                    f"It's a tie! Your streak continues.\n\n"
                    f"Streak: **{game['streak']}** • Multiplier: **{multiplier:.1f}x** • Value: **{fmt_num(potential)}** {emoji}"
                ),
                color=0xf39c12
            )
            embed.set_footer(text=f"Bet: {fmt_num(game['bet'])} {emoji}")
            await interaction.response.edit_message(embed=embed, view=self)
        
        elif guess == result:
            # Correct guess!
            game["streak"] += 1
            game["current"] = next_card
            multiplier = hl_multiplier(game["streak"])
            potential = int(game["bet"] * multiplier)
            
            embed = discord.Embed(
                title="🎴 Higher or Lower — Correct! ✓",
                description=(
                    f"**Previous:** {card_str(current)} → **Next:** {card_str(next_card)}\n\n"
                    f"The card was **{result}**! Keep going!\n\n"
                    f"Streak: **{game['streak']}** • Multiplier: **{multiplier:.1f}x** • Value: **{fmt_num(potential)}** {emoji}"
                ),
                color=0x3498db
            )
            embed.set_footer(text=f"Bet: {fmt_num(game['bet'])} {emoji}")
            await interaction.response.edit_message(embed=embed, view=self)
        
        else:
            # Wrong guess
            del _active_games[(gid, uid)]
            
            # If streak >= 4 (1.0x+), they still win!
            if game["streak"] >= 4:
                multiplier = hl_multiplier(game["streak"])
                winnings = int(game["bet"] * multiplier)
                await db.add_chips(gid, uid, interaction.user.display_name, winnings)
                new_balance = await db.get_balance(gid, uid)
                profit = winnings - game["bet"]
                
                embed = discord.Embed(
                    title="🎴 Higher or Lower — You Win! ✓",
                    description=(
                        f"**Previous:** {card_str(current)} → **Next:** {card_str(next_card)}\n\n"
                        f"The card was **{result}**, but your streak saved you!\n\n"
                        f"Streak: **{game['streak']}** • Multiplier: **{multiplier:.1f}x**\n"
                        f"💰 You won **{fmt_num(winnings)}** {emoji} (+{fmt_num(profit)} profit)\n"
                        f"Balance: **{fmt_num(new_balance)}** {emoji}"
                    ),
                    color=0x2ecc71
                )
            else:
                # Partial refund based on multiplier (streak 1-3 gives 0.25x-0.75x back)
                multiplier = hl_multiplier(game["streak"])
                refund = int(game["bet"] * multiplier)
                loss = game["bet"] - refund
                
                if refund > 0:
                    await db.add_chips(gid, uid, interaction.user.display_name, refund)
                
                new_balance = await db.get_balance(gid, uid)
                
                embed = discord.Embed(
                    title="🎴 Higher or Lower — Busted! ✗",
                    description=(
                        f"**Previous:** {card_str(current)} → **Next:** {card_str(next_card)}\n\n"
                        f"The card was **{result}**. You guessed **{guess}**.\n\n"
                        f"Streak: **{game['streak']}** • Multiplier: **{multiplier:.1f}x**\n"
                        f"💸 You lost **{fmt_num(loss)}** {emoji}" + (f" (kept {fmt_num(refund)})" if refund > 0 else "") + "\n"
                        f"Balance: **{fmt_num(new_balance)}** {emoji}\n"
                        f"(Reach streak 4+ to keep your winnings!)"
                    ),
                    color=0xe74c3c
                )
            
            self.disable_all()
            await interaction.response.edit_message(embed=embed, view=self)
    
    def disable_all(self):
        for item in self.children:
            item.disabled = True


@bot.tree.command(name="gamble", description="Play gambling games to win chips! 🎰")
@app_commands.describe(game="Choose a game to play")
@app_commands.choices(
    game=[
        app_commands.Choice(name="🎴 Higher or Lower", value="higher_lower"),
    ]
)
async def gamble_cmd(interaction: discord.Interaction, game: app_commands.Choice[str]):
    gid, uid = str(interaction.guild_id), str(interaction.user.id)
    
    # Check for existing game
    if (gid, uid) in _active_games:
        await interaction.response.send_message(
            "❌ You already have a game in progress! Finish it first.",
            ephemeral=True
        )
        return
    
    # Show bet modal
    modal = BetModal(game.value)
    await interaction.response.send_modal(modal)


# ---------- Ping Role ----------

QUESTION_FEATURE_NAMES = {
    "casual": "💬 Casual Questions",
    "typology": "✨ Typology Questions",
}

# ======================== EVENTS ========================


@bot.event
async def on_ready():
    if not hasattr(bot, "_initialized"):
        bot._initialized = True
        await db.init()
        bot.add_view(WordGameActiveView())
        bot.add_view(WordGameStartView())
        bot.add_view(NewQuestionView("casual"))
        bot.add_view(NewQuestionView("typology"))
        schedule_loop.start()
        bot.loop.create_task(chip_drop_cycle())
        synced = await bot.tree.sync()
        print(f"✅ {bot.user} is online! Synced {len(synced)} commands globally. ({BOT_VERSION})")


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    """Handle reaction role picker and Hall of Fame forwarding."""
    if payload.user_id == bot.user.id:
        return
    
    # --- Hall of Fame: forward messages with 4+ reactions of the SAME emoji ---
    # Only for messages from real users (not bots)
    HOF_THRESHOLD = 4
    hof_channel_id = HARDCODED.get("channel_hall_of_fame")
    if hof_channel_id and payload.message_id not in _hall_of_fame_forwarded:
        try:
            channel = bot.get_channel(payload.channel_id)
            if channel:
                message = await channel.fetch_message(payload.message_id)
                # Skip bot messages (polls, reaction roles, etc.)
                if message.author.bot:
                    pass  # Don't process bot messages for Hall of Fame
                else:
                    # Check if any single emoji has reached threshold
                    qualifying_reaction = None
                    for r in message.reactions:
                        if r.count >= HOF_THRESHOLD:
                            qualifying_reaction = r
                            break
                    if qualifying_reaction:
                        # Mark as forwarded to prevent duplicates
                        _hall_of_fame_forwarded.add(payload.message_id)
                        
                        hof_channel = bot.get_channel(int(hof_channel_id))
                        if hof_channel:
                            # Build the forward embed
                            embed = discord.Embed(
                                description=message.content or "*[No text content]*",
                                color=discord.Color.gold(),
                                timestamp=message.created_at
                            )
                            embed.set_author(
                                name=message.author.display_name,
                                icon_url=message.author.display_avatar.url if message.author.display_avatar else None
                            )
                            embed.add_field(
                                name="Reactions",
                                value=" ".join([f"{r.emoji} {r.count}" for r in message.reactions]),
                                inline=False
                            )
                            embed.add_field(
                                name="Source",
                                value=f"[Jump to message]({message.jump_url})",
                                inline=False
                            )
                            
                            # Handle attachments
                            if message.attachments:
                                embed.set_image(url=message.attachments[0].url)
                            
                            await hof_channel.send(embed=embed)
                            print(f"[HallOfFame] Forwarded message {payload.message_id}")
        except Exception as e:
            print(f"[HallOfFame] Error: {e}")
    
    # --- Reaction Role Picker (👍 only) ---
    if str(payload.emoji) != "👍":
        return

    # Check all feature pickers using hardcoded message IDs
    matched_feature = None
    msg_id = str(payload.message_id)
    for feature in ["casual", "typology"]:
        if msg_id == HARDCODED.get(f"role_picker_message_{feature}"):
            matched_feature = feature
            break
    
    if not matched_feature:
        return

    role_id = HARDCODED.get(f"ping_role_{matched_feature}")
    if not role_id:
        return

    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    member = guild.get_member(payload.user_id)
    if not member:
        try:
            member = await guild.fetch_member(payload.user_id)
        except Exception:
            return

    role = guild.get_role(int(role_id))
    if not role:
        return

    try:
        await member.add_roles(role)
        print(f"[ReactionRole] ✅ Added {role.name} to {member.display_name}")
    except Exception as e:
        print(f"[ReactionRole] ❌ Failed to add role: {e}")


@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    """Handle reaction role picker — remove role on 👍 unreact."""
    if str(payload.emoji) != "👍":
        return

    # Check all feature pickers using hardcoded message IDs
    matched_feature = None
    msg_id = str(payload.message_id)
    for feature in ["casual", "typology"]:
        if msg_id == HARDCODED.get(f"role_picker_message_{feature}"):
            matched_feature = feature
            break
    
    if not matched_feature:
        return

    role_id = HARDCODED.get(f"ping_role_{matched_feature}")
    if not role_id:
        return

    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    member = guild.get_member(payload.user_id)
    if not member:
        try:
            member = await guild.fetch_member(payload.user_id)
        except Exception:
            return

    role = guild.get_role(int(role_id))
    if not role:
        return

    try:
        await member.remove_roles(role)
        print(f"[ReactionRole] Removed {role.name} from {member.display_name}")
    except Exception as e:
        print(f"[ReactionRole] Failed to remove role: {e}")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return
    gid = str(message.guild.id)
    uid = str(message.author.id)

    await db.set_state(gid, "last_message_time", datetime.now(timezone.utc).isoformat())
    await db.set_state(gid, "last_message_channel", str(message.channel.id))
    
    now = datetime.now(timezone.utc)
    last_msg_key = f"user_last_msg_{uid}"
    last_msg_time = await db.get_state(gid, last_msg_key)
    
    is_spam = False
    if last_msg_time:
        last_dt = datetime.fromisoformat(last_msg_time)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        if (now - last_dt).total_seconds() < 3:
            is_spam = True
    
    # Update user's last message time
    await db.set_state(gid, last_msg_key, now.isoformat())
    
    # Only count for rewards if not spam
    if not is_spam:
        await db.increment_chatter(gid, uid, message.author.display_name)
        await db.increment_activity_message(gid, uid, message.author.display_name)

    # --- Haiku Detection ---
    is_haiku, haiku_lines = check_haiku(message.content)
    if is_haiku:
        haiku_reply = "Nice haiku bro:\n"
        syllable_pattern = [5, 7, 5]
        haiku_reply += "\n".join([f"> *{line}* ({syllable_pattern[i]})" for i, line in enumerate(haiku_lines)])
        await message.reply(haiku_reply, mention_author=False)

    # --- !typology or !t command to create typology cards ---
    content_lower = message.content.lower().strip()
    if content_lower.startswith("!typology") or content_lower.startswith("!t ") or content_lower == "!t":
        # Parse target user: user ID, username, mention, or default to self
        parts = message.content.strip().split(maxsplit=1)
        target = None
        
        if len(parts) > 1:
            arg = parts[1].strip()
            # Remove mention formatting if present
            if arg.startswith("<@") and arg.endswith(">"):
                arg = arg.strip("<@!>")
            
            # Try as user ID first
            if arg.isdigit():
                try:
                    target = await message.guild.fetch_member(int(arg))
                except Exception:
                    pass
            
            # Try as username/display name
            if not target:
                arg_lower = arg.lower()
                for member in message.guild.members:
                    if member.name.lower() == arg_lower or member.display_name.lower() == arg_lower:
                        target = member
                        break
        
        # Default to message author if no target found
        if not target:
            target = message.author
        
        target_uid = str(target.id)
        
        # Get profile data
        profile = await db.get_typology_profile(gid, target_uid)
        
        # Build embed with MBTI avatar
        embed, file = build_typology_embed(target, profile, attach_mbti=True)
        
        # Send card and delete command for clean UX
        try:
            if file:
                await message.channel.send(embed=embed, file=file)
            else:
                await message.channel.send(embed=embed)
            await message.delete()
        except Exception:
            pass
        return

    # --- !startwordgame command (admin only) ---
    if content_lower == "!startwordgame":
        # Check admin permission
        if not message.author.guild_permissions.administrator:
            return
        
        game = await db.get_word_game(gid)
        if game and game["active"]:
            await message.channel.send("❌ A word game is already active!", delete_after=5)
            try:
                await message.delete()
            except Exception:
                pass
            return
        
        # If there was a completed game, remove its button
        if game:
            try:
                channel = message.guild.get_channel(int(game["channel_id"]))
                if channel and game.get("message_id"):
                    old_msg = await channel.fetch_message(int(game["message_id"]))
                    await old_msg.edit(view=None)
            except Exception:
                pass
        
        embed = build_word_game_embed("", 0, True)
        view = WordGameActiveView()
        msg = await message.channel.send(embed=embed, view=view)
        await db.create_word_game(gid, str(message.channel.id), str(msg.id))
        
        try:
            await message.delete()
        except Exception:
            pass
        return

    # --- !update command for typology profiles ---
    if content_lower.startswith("!update "):
        # Must be a reply to a typology card (bot's message)
        if not message.reference:
            confirm = await message.channel.send(f"{message.author.mention} ❌ Reply to a typology card to update it!", delete_after=5)
            try:
                await message.delete()
            except Exception:
                pass
            return
        
        # Get the replied message
        try:
            replied_msg = await message.channel.fetch_message(message.reference.message_id)
        except Exception:
            confirm = await message.channel.send(f"{message.author.mention} ❌ Could not find that message.", delete_after=5)
            try:
                await message.delete()
            except Exception:
                pass
            return
        
        # Must be a bot message with an embed containing our footer format
        if replied_msg.author.id != bot.user.id or not replied_msg.embeds:
            confirm = await message.channel.send(f"{message.author.mention} ❌ Reply to a typology card created by me!", delete_after=5)
            try:
                await message.delete()
            except Exception:
                pass
            return
        
        # Extract user ID from author URL
        embed = replied_msg.embeds[0]
        if not embed.author or not embed.author.url or "typology.id/" not in embed.author.url:
            confirm = await message.channel.send(f"{message.author.mention} ❌ That doesn't look like a typology card.", delete_after=5)
            try:
                await message.delete()
            except Exception:
                pass
            return
        
        # Parse user ID from author URL (format: https://typology.id/123456789)
        try:
            target_uid = embed.author.url.split("typology.id/")[1].strip()
        except Exception:
            confirm = await message.channel.send(f"{message.author.mention} ❌ Could not parse user ID from card.", delete_after=5)
            try:
                await message.delete()
            except Exception:
                pass
            return
        
        # Get target member
        try:
            target_user = await message.guild.fetch_member(int(target_uid))
        except Exception:
            confirm = await message.channel.send(f"{message.author.mention} ❌ Could not find that user in the server.", delete_after=5)
            try:
                await message.delete()
            except Exception:
                pass
            return
        
        # Parse the command: !update <field> <value>
        parts = message.content.strip().split(maxsplit=2)
        if len(parts) < 3:
            confirm = await message.channel.send(f"{message.author.mention} ❌ Usage: `!update <field> <value>`\nFields: mbti/m, enneagram/e, tritype/t, instinct/i, ap/a", delete_after=8)
            try:
                await message.delete()
            except Exception:
                pass
            return
        
        field_input = parts[1].lower()
        value_input = parts[2]
        
        # Map field aliases
        field_map = {
            "m": "mbti", "mbti": "mbti",
            "e": "enneagram", "enneagram": "enneagram",
            "t": "tritype", "tritype": "tritype",
            "i": "instinct", "instinct": "instinct",
            "a": "ap", "ap": "ap",
        }
        
        field = field_map.get(field_input)
        if not field:
            confirm = await message.channel.send(f"{message.author.mention} ❌ Unknown field: `{field_input}`\nValid: mbti/m, enneagram/e, tritype/t, instinct/i, ap/a", delete_after=8)
            try:
                await message.delete()
            except Exception:
                pass
            return
        
        # Format the value based on field type
        if field == "mbti":
            formatted = format_mbti(value_input)
        elif field == "enneagram":
            formatted = format_enneagram(value_input)
        elif field == "tritype":
            formatted = format_tritype(value_input)
        elif field == "instinct":
            formatted = format_instinct(value_input)
        elif field == "ap":
            formatted = format_ap(value_input)
        else:
            formatted = value_input
        
        # Save to database
        try:
            await db.set_typology_field(gid, target_uid, field, formatted)
            
            # Get updated profile and rebuild embed
            profile = await db.get_typology_profile(gid, target_uid)
            new_embed, new_file = build_typology_embed(target_user, profile, attach_mbti=True)
            
            # Edit the original card message
            if new_file:
                await replied_msg.edit(embed=new_embed, attachments=[new_file])
            else:
                await replied_msg.edit(embed=new_embed)
            
            # Just delete the command message - card update is the confirmation
            await message.delete()
        except Exception as e:
            confirm = await message.channel.send(f"{message.author.mention} ❌ Error: {str(e)}", delete_after=8)
            try:
                await message.delete()
            except Exception:
                pass
        return

    # --- !updateembed command (temporary, for updating role picker embeds) ---
    # Reply to a role picker message and type !updateembed to auto-update it
    if content_lower == "!updateembed":
        # Admin only
        if not message.author.guild_permissions.administrator:
            return
        
        # Must be a reply
        if not message.reference:
            await message.channel.send("❌ Reply to a role picker message to update it!", delete_after=5)
            try:
                await message.delete()
            except Exception:
                pass
            return
        
        try:
            replied_msg = await message.channel.fetch_message(message.reference.message_id)
            msg_id = str(replied_msg.id)
            
            # Check if it's one of our role picker messages
            if msg_id == HARDCODED["role_picker_message_casual"]:
                new_embed = discord.Embed(
                    title="🔔 💬 Casual Questions Notifications",
                    description=(
                        "React with 👍 to get the <@&1470111189869527131> role and be pinged for Casual Questions\n\n"
                        "Includes: Fun creative questions and yes/no polls\n"
                        "Unreact to remove the role."
                    ),
                    color=int(config.COLORS["casual"], 16)
                )
                await replied_msg.edit(embed=new_embed)
                await message.channel.send("✅ Updated casual role picker!", delete_after=5)
            elif msg_id == HARDCODED["role_picker_message_typology"]:
                new_embed = discord.Embed(
                    title="🔔 ✨ Typology Questions Notifications",
                    description=(
                        "React with 👍 to get the <@&1470111535559999590> role and be pinged for Typology Questions\n\n"
                        "Includes: Typology matchups, hot takes, and 'who is most likely to' questions\n"
                        "Unreact to remove the role."
                    ),
                    color=int(config.COLORS["typology"], 16)
                )
                await replied_msg.edit(embed=new_embed)
                await message.channel.send("✅ Updated typology role picker!", delete_after=5)
            else:
                await message.channel.send("❌ That's not a role picker message I recognize.", delete_after=5)
            
            await message.delete()
        except Exception as e:
            await message.channel.send(f"❌ Error: {str(e)}", delete_after=8)
            try:
                await message.delete()
            except Exception:
                pass
        return

    # --- Chip Drop handling (grab or math answer) ---
    drop = await db.get_chip_drop(gid)
    if drop and str(message.channel.id) == drop["channel_id"]:
        content = message.content.strip()
        claimed = False
        
        if drop["drop_type"] == "grab" and content.lower() == "~grab":
            claimed = True
        elif drop["drop_type"] == "math":
            # Check if answer matches (strip whitespace and commas)
            if content.replace(",", "") == drop["answer"]:
                claimed = True
        
        if claimed:
            amount = drop["amount"]
            emoji = config.CHIPS["emoji"]
            
            await db.add_chips(gid, str(message.author.id), message.author.display_name, amount)
            
            # Reply to the winner's message
            claimed_msg = random.choice(config.MESSAGES["chip_drop"]["claimed"]).format(
                user=message.author.mention,
                amount=fmt_num(amount),
                emoji=emoji
            )
            try:
                await message.reply(claimed_msg, mention_author=False)
            except Exception:
                pass
            
            # Delete the drop and set cooldown
            await db.delete_chip_drop(gid)
            await db.set_state(gid, "last_chip_drop_claimed", datetime.now(timezone.utc).isoformat())
            
            # Set random cooldown for next drop
            cooldown_hours = random.uniform(
                config.CHIP_DROP["min_cooldown_hours"],
                config.CHIP_DROP["max_cooldown_hours"]
            )
            await db.set_state(gid, "chip_drop_cooldown_hours", str(cooldown_hours))

    # Word game — every message in the game channel adds a word
    game = await db.get_word_game(gid)
    if game and game["active"] and str(message.channel.id) == game["channel_id"]:
        word = message.content.strip()
        print(f"[WordGame] Message from {message.author}: '{word}'")

        # Validate — single word/punctuation, not too long, no links/mentions
        is_single_word = word and " " not in word and "\n" not in word
        is_short = len(word) <= 45 if word else False
        is_not_link = not word.startswith("http") if word else True
        is_not_mention = not word.startswith("<") if word else True
        is_word_chars = bool(re.match(r"^[\w''.,!?;:\-…\"\'\`]+$", word, re.UNICODE)) if word else False
        
        valid = is_single_word and is_short and is_not_link and is_not_mention and is_word_chars
        print(f"[WordGame] Valid={valid} (single={is_single_word}, short={is_short}, notlink={is_not_link}, notmention={is_not_mention}, chars={is_word_chars})")

        if valid:
            if game["last_contributor_id"] == str(message.author.id):
                try:
                    await message.channel.send(
                        f"{message.author.mention} You can't add two words in a row! Let someone else go.",
                        delete_after=4,
                    )
                except Exception:
                    pass
            else:
                # Add the word
                await db.add_word(gid, word, str(message.author.id))
                await db.set_state(gid, "last_wordgame_activity", datetime.now(timezone.utc).isoformat())
                game = await db.get_word_game(gid)

                try:
                    old_msg = await message.channel.fetch_message(int(game["message_id"]))
                    await old_msg.delete()
                except Exception:
                    pass

                # Format and send new embed with End button
                story = format_story(game["words"])
                embed = build_word_game_embed(story, game["word_count"], True, message.author)
                view = WordGameActiveView()
                new_msg = await message.channel.send(embed=embed, view=view)
                await db.update_word_game_message(gid, str(new_msg.id))

    await bot.process_commands(message)


@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    """Track VC join/leave for activity rewards"""
    if member.bot:
        return
    
    gid = str(member.guild.id)
    
    # User joined a voice channel
    if before.channel is None and after.channel is not None:
        await db.start_vc_session(gid, str(member.id), member.display_name)
        print(f"[VC] {member.display_name} joined {after.channel.name}")
    
    # User left a voice channel
    elif before.channel is not None and after.channel is None:
        minutes = await db.end_vc_session(gid, str(member.id))
        print(f"[VC] {member.display_name} left {before.channel.name} after {minutes} minutes")
    
    # User moved between channels (still in VC, no action needed)


# ======================== RUN ========================

if __name__ == "__main__":
    if not TOKEN:
        print("❌ DISCORD_TOKEN not set! Copy .env.example to .env and fill in your token.")
    else:
        bot.run(TOKEN)
