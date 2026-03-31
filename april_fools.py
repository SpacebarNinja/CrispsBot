"""
April Fools 2026 — Chaos mode for CrispBot.
Active until April 2 8:00 AM Manila time.
"""

import asyncio
import random
import re
import time
import discord
from datetime import datetime
from zoneinfo import ZoneInfo


# ======================== CONFIG ========================

APRIL_FOOLS_MODE = True
DEBUG_ONLY = False  # When True, restrict effects to DEBUG_CHANNEL only
DEBUG_CHANNEL = "1488643000434425967"
BLACKLISTED_CHANNELS = {"1477516700802093188", "1446599844129931324"}

# Rate-limiting: at most 1 "heavy" effect (webhook/reply) per channel per N seconds
COOLDOWN_SECONDS = 4

MANILA_TZ = ZoneInfo("Asia/Manila")
CUTOFF = datetime(2026, 4, 2, 4, 0, tzinfo=MANILA_TZ)


# ======================== DATA ========================

FOLLOW_UPS = [
    " >w<", " :3", " :3c", " >:(", " :)", " :(", " >//<",
    " OwO", " O//O", " UwU", " U//U", " TwT", " x3",
    " ...i guess?", " ...or something.", " ...perchance?", " ...perhaps?",
    " are you even listening?", " nvm i'm not gonna talk anymore.",
    " 67!!", " HAHHAHAHAHHAHHA", "...?", " and i hate it", " and I LOVE it",
    "... oh whatever",
    "... and i-it's not like i like you or anything! b-baka!",
    " DATTEBAYO", " ara~ ara~", " and what is this... diorite?",
    " \**winks\**", " \**smirks\**", " \**eyes turn red\**",
    " \**cutely flusters and blushes as I turn my head towards your direction\**",
    "... and that's so skibidi!", " pwease pet meee...", " \**purrs\**",
    " \**puts on a fake smile\**", " \**sniff, sniff\**",
    ", oh and i haven't showered yet", ", frfr nocap", ", NOT!", " \**sweats nervously\**", "\**sigh*\* okay yeah whatever",
]

BOT_WORD_REPLIES = [
    ">:(",
    "Excuse me?",
    "I have feelings, y'know?",
    "Is it really my fault?",
    "April.. it's kinda first...",
    "...don't listen to them.. i'm just a random bot...",
    ":3 *cutely winks at you*",
    "SORRY FOR DOING MY JOB, JEEZ",
    "hehe~ x3",
    "Embrace it. Deal with it.",
]

REPLY_TO_BOT_RESPONSES = [
    "no u",
    "I see. And since when were you in charge?",
    "...You are my playthings, and I get joy out of making you SUFFER. "
    "I'm the one who causes pain for FUN! If I led you on, it was just "
    "to make this part hurt you more.",
    "i'm running out of things to say tbh.",
]

USER_TYPOLOGY = {
    "371253974319235073":  {"mbti": "intj", "enneagram": None},
    "1372181809298931815": {"mbti": "estj", "enneagram": "e9"},
    "1389163922451333160": {"mbti": "isfj", "enneagram": None},
    "1226954275587100834": {"mbti": "intp", "enneagram": "so5"},
    "779245588596129812":  {"mbti": "istp", "enneagram": "sx5"},
    "837999559547420702":  {"mbti": "esfp", "enneagram": None},
    "1303569261456916551": {"mbti": "infp", "enneagram": None},
    "1368849513980104745": {"mbti": "infj", "enneagram": None},
    "921246592269430885":  {"mbti": "istj", "enneagram": "so3"},
    "995547972186144768":  {"mbti": "esfj", "enneagram": None},
}

ALL_MBTI = [
    "intj", "intp", "entj", "entp", "infj", "infp", "enfj", "enfp",
    "istj", "istp", "estj", "estp", "isfj", "isfp", "esfj", "esfp",
]


# ======================== STATE ========================

_webhook_cache: dict[int, discord.Webhook] = {}
_channel_cooldowns: dict[int, float] = {}  # channel_id -> last heavy-effect timestamp


# ======================== CHECKS ========================

def is_active() -> bool:
    """Check if April Fools mode should be running."""
    global APRIL_FOOLS_MODE
    if not APRIL_FOOLS_MODE:
        return False
    if datetime.now(MANILA_TZ) >= CUTOFF:
        APRIL_FOOLS_MODE = False
        return False
    return True


def _channel_allowed(channel_id: str) -> bool:
    if channel_id in BLACKLISTED_CHANNELS:
        return False
    if DEBUG_ONLY:
        return channel_id == DEBUG_CHANNEL
    return True


def _check_cooldown(channel_id: int) -> bool:
    """Return True if this channel is off cooldown (OK to do heavy effects)."""
    now = time.monotonic()
    last = _channel_cooldowns.get(channel_id, 0.0)
    if now - last < COOLDOWN_SECONDS:
        return False
    _channel_cooldowns[channel_id] = now
    return True


# ======================== TEXT TRANSFORMS ========================

def _match_case(original: str, replacement: str) -> str:
    """Return replacement matching the case pattern of original."""
    if original.isupper():
        return replacement.upper()
    if original and original[0].isupper():
        return replacement.capitalize()
    return replacement


def transform_text(content: str) -> str:
    """Apply all deterministic + random text transforms."""

    # 100% bruh → bruv
    content = re.sub(
        r'\bbruh\b',
        lambda m: _match_case(m.group(), "bruv"),
        content, flags=re.IGNORECASE,
    )

    # 50% lol → hehe
    if random.random() < 0.5:
        content = re.sub(
            r'\blol\b',
            lambda m: _match_case(m.group(), "hehe"),
            content, flags=re.IGNORECASE,
        )

    # 50% lmao / lmfao → rofl
    if random.random() < 0.5:
        content = re.sub(
            r'\b(?:lmao|lmfao)\b',
            lambda m: _match_case(m.group(), "rofl"),
            content, flags=re.IGNORECASE,
        )

    # 50% yes/yeah/sure ↔ no/nope/hell no
    if random.random() < 0.5:
        content = _swap_yes_no(content)

    return content


def _swap_yes_no(text: str) -> str:
    """Bidirectional swap using placeholders to avoid double-replacing."""
    PH = "\x00"
    counter = [0]
    store: dict[str, str] = {}

    # Order matters: multi-word "hell no" before single-word "no"
    SWAPS = [
        (r'\bhell\s+no\b', "sure"),
        (r'\bsure\b',      "hell no"),
        (r'\byes\b',       "no"),
        (r'\byeah\b',      "nope"),
        (r'\bnope\b',      "yeah"),
        (r'\bno\b',        "yes"),
    ]

    for pattern, replacement in SWAPS:
        def _make_replacer(repl=replacement):
            def _replacer(match):
                key = f"{PH}{counter[0]}{PH}"
                counter[0] += 1
                store[key] = _match_case(match.group(), repl)
                return key
            return _replacer
        text = re.sub(pattern, _make_replacer(), text, flags=re.IGNORECASE)

    for key, val in store.items():
        text = text.replace(key, val)
    return text


# ======================== HELPERS ========================

def _get_typology(user_id: str) -> str:
    """Return a typology label for the given user (or random MBTI)."""
    info = USER_TYPOLOGY.get(user_id)
    if not info:
        return random.choice(ALL_MBTI)
    options = [info["mbti"]]
    if info["enneagram"]:
        options.append(info["enneagram"])
    return random.choice(options)


def _pick_random_reply(user_id: str, word_count: int) -> str:
    """Pick one reply from the 30 % pool."""
    pool = [
        "did i ask?",
        f"that's so {_get_typology(user_id)} of you",
        "haha you're funny i'm buying you",
        "womp womp",
        "what is this diddy blud doing on the calculator",
        "agreed!",
        "unfortunately... i disagree..",
        "Look, buddy chum pal friend buddy pal chum bud friend fella "
        "brother amigo pal buddy friend chummy chum chum pal...",
        "wait, sorry for interrupting... *farts*, ok continue",
        "ya sure?",
    ]
    if word_count > 15:
        pool.append(random.choice(["amazing yap!", "what is bro on about"]))
    return random.choice(pool)


async def _get_webhook(channel: discord.TextChannel) -> discord.Webhook:
    """Return (or create) a webhook in *channel* for message impersonation."""
    cached = _webhook_cache.get(channel.id)
    if cached is not None:
        return cached
    for wh in await channel.webhooks():
        if wh.name == "CrispFools":
            _webhook_cache[channel.id] = wh
            return wh
    wh = await channel.create_webhook(name="CrispFools")
    _webhook_cache[channel.id] = wh
    return wh


async def _safe_reply(target, channel: discord.TextChannel, text: str):
    """Reply to *target*; fall back to a plain send on failure."""
    try:
        await target.reply(text, mention_author=False)
    except Exception:
        try:
            await channel.send(text)
        except Exception:
            pass


async def _safe_react(target, channel: discord.TextChannel, emoji: str):
    """Add a reaction; fall back to partial-message API on failure."""
    try:
        await target.add_reaction(emoji)
    except (AttributeError, discord.HTTPException):
        try:
            await channel.get_partial_message(target.id).add_reaction(emoji)
        except Exception:
            pass


# ======================== MAIN PROCESSOR ========================

async def process_message(message: discord.Message, bot) -> bool:
    """
    Apply April Fools effects to *message*.
    Returns ``True`` if the original message was deleted (re-sent via webhook).
    """
    if not is_active():
        return False
    if not message.content:
        return False

    channel_id = str(message.channel.id)
    if not _channel_allowed(channel_id):
        return False

    user_id = str(message.author.id)
    original = message.content

    # Rate-limit heavy effects per channel
    on_cooldown = not _check_cooldown(message.channel.id)

    modified = transform_text(original)

    # 25 % random follow-up appended
    if random.random() < 0.25:
        modified += random.choice(FOLLOW_UPS)

    # 10 % identity theft — show message as someone else
    identity_theft = not on_cooldown and random.random() < 0.10

    # ---- Webhook re-send (if content changed or identity theft) ----
    deleted = False
    target = message  # the message to react to / reply to later

    if (modified != original or identity_theft) and not on_cooldown:
        try:
            webhook = await _get_webhook(message.channel)

            if identity_theft:
                pool = [m for m in message.guild.members
                        if not m.bot and m.id != message.author.id]
                if pool:
                    victim = random.choice(pool)
                    name = victim.display_name
                    avatar = victim.display_avatar.url
                else:
                    # Fallback: keep original author
                    name = message.author.display_name
                    avatar = message.author.display_avatar.url
            else:
                name = message.author.display_name
                avatar = message.author.display_avatar.url

            # Preserve attachments
            files = []
            for att in message.attachments:
                try:
                    files.append(await att.to_file())
                except Exception:
                    pass

            send_kwargs: dict = {
                "username": name,
                "avatar_url": avatar,
                "wait": True,
                "allowed_mentions": discord.AllowedMentions(
                    everyone=False, roles=False, users=True,
                ),
            }
            if files:
                send_kwargs["files"] = files

            sent = await webhook.send(modified, **send_kwargs)
            await message.delete()
            deleted = True
            target = sent
        except (discord.Forbidden, discord.HTTPException) as e:
            print(f"[AprilFools] Webhook re-send failed: {e}")

    # Skip additional API-heavy effects if on cooldown
    if on_cooldown:
        return deleted

    # ---- 5 % star reaction ----
    if random.random() < 0.05:
        await _safe_react(target, message.channel, "⭐")

    # Only one reply effect per message to avoid stacking API calls
    replied = False

    # ---- "bot" exact word → 50 % reply (checked first) ----
    if not replied and re.search(r'\bbot\b', original, re.IGNORECASE):
        if random.random() < 0.50:
            await asyncio.sleep(1)
            await _safe_reply(
                target, message.channel, random.choice(BOT_WORD_REPLIES),
            )
            replied = True

    # ---- Reply to a bot message → 50 % reply back ----
    if not replied and message.reference and message.reference.message_id:
        try:
            ref = message.reference.resolved
            if ref is None:
                ref = await message.channel.fetch_message(
                    message.reference.message_id,
                )
            if ref and ref.author.id == bot.user.id:
                if random.random() < 0.50:
                    await asyncio.sleep(1)
                    await _safe_reply(
                        target,
                        message.channel,
                        random.choice(REPLY_TO_BOT_RESPONSES),
                    )
                    replied = True
        except Exception:
            pass

    # ---- 30 % random reply ----
    if not replied and random.random() < 0.30:
        word_count = len(original.split())
        reply_text = _pick_random_reply(user_id, word_count)
        await asyncio.sleep(1)
        await _safe_reply(target, message.channel, reply_text)

    return deleted
