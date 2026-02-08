"""
CRISPS GC Discord Bot — discord.py rewrite (24/7)
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
import os

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

# Daily question rotation: warm → chill → typology → ...
DAILY_QUESTION_ORDER = ["warm", "chill", "typology"]
QUESTION_GAP_HOURS = 24 / len(DAILY_QUESTION_ORDER)  # 8 hours


# ======================== HARDCODED CONFIG (Single Server) ========================
# This bot is designed for a single server, so we hardcode all the IDs

HARDCODED = {
    # Ping roles
    "ping_role_warm": "1470111504954032300",
    "ping_role_chill": "1470111189869527131",
    "ping_role_typology": "1470111535559999590",
    
    # Channels
    "channel_warm": "1470111942696767548",      # #qotd
    "channel_chill": "1470111942696767548",     # #qotd
    "channel_typology": "1450418107368738848",  # #typology
    "channel_codepurple": "1446277377771573402", # #general
    "channel_activity_rewards": "1446277377771573402",  # #general
    
    # Reaction role picker message IDs
    "role_picker_message_warm": "1470113538994606160",
    "role_picker_message_chill": "1470113556476334182",
    "role_picker_message_typology": "1470113576017723564",
    
    # Blacklist categories (all channels in these categories are blacklisted from chip drops)
    "blacklist_categories": ["1446269291123966044", "1446277444372791458"],
}


# ======================== HELPERS ========================


async def get_unused_question(guild_id: str, qtype: str, questions: list[str]) -> str:
    """Pick a random unused question (bag randomizer — no repeats until all used)."""
    used = await db.get_used_questions(guild_id, qtype)
    if len(used) >= len(questions):
        await db.reset_questions(guild_id, qtype)
        used = []
    available = [i for i in range(len(questions)) if i not in used]
    idx = random.choice(available)
    await db.mark_question_used(guild_id, qtype, idx)
    return questions[idx]


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
    """Format raw word tokens into a clean story string.
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
            result[-1] += token  # Attach to previous word
        else:
            result.append(token.lower())

    story = " ".join(result)
    if story:
        story = story[0].upper() + story[1:]
    return story


# ======================== POSTING FUNCTIONS ========================


async def post_warm(guild_id: str):
    """Post a warm question (WYR, Debates, or Button)."""
    channel_id = HARDCODED["channel_warm"]
    channel = bot.get_channel(int(channel_id))
    if not channel:
        print(f"[Warm] Could not find channel {channel_id}")
        return

    all_q = (
        [(q, "Would You Rather") for q in config.SPARK_WYR]
        + [(q, "Debate Time") for q in config.SPARK_DEBATES]
        + [(q, "Press The Button") for q in config.BUTTON_QUESTIONS]
    )

    used = await db.get_used_questions(guild_id, "warm")
    if len(used) >= len(all_q):
        await db.reset_questions(guild_id, "warm")
        used = []
    available = [i for i in range(len(all_q)) if i not in used]
    idx = random.choice(available)
    await db.mark_question_used(guild_id, "warm", idx)
    question, category = all_q[idx]

    # Increment and get question counter
    count_str = await db.get_state(guild_id, "warm_question_count") or "0"
    count = int(count_str) + 1
    await db.set_state(guild_id, "warm_question_count", str(count))

    embed = _embed(
        config.EMBEDS["warm"]["title"],
        question,
        "warm",
        footer=f"{category} (#{count})",
    )

    ping_role_id = HARDCODED["ping_role_warm"]
    content = f"<@&{ping_role_id}>"
    await channel.send(content=content, embed=embed, allowed_mentions=discord.AllowedMentions(roles=True))


async def post_chill(guild_id: str):
    """Post a chill question (Chill or Personality lifestyle)."""
    channel_id = HARDCODED["channel_chill"]
    channel = bot.get_channel(int(channel_id))
    if not channel:
        print(f"[Chill] Could not find channel {channel_id}")
        return

    all_q = (
        [(q, "Chill Vibes") for q in config.SPARK_CHILL]
        + [(q, "Lifestyle") for q in config.PERSONALITY_QUESTIONS]
    )

    used = await db.get_used_questions(guild_id, "chill")
    if len(used) >= len(all_q):
        await db.reset_questions(guild_id, "chill")
        used = []
    available = [i for i in range(len(all_q)) if i not in used]
    idx = random.choice(available)
    await db.mark_question_used(guild_id, "chill", idx)
    question, category = all_q[idx]

    # Increment and get question counter
    count_str = await db.get_state(guild_id, "chill_question_count") or "0"
    count = int(count_str) + 1
    await db.set_state(guild_id, "chill_question_count", str(count))

    embed = _embed(
        config.EMBEDS["chill"]["title"],
        question,
        "chill",
        footer=f"{category} (#{count})",
    )

    ping_role_id = HARDCODED["ping_role_chill"]
    content = f"<@&{ping_role_id}>"
    await channel.send(content=content, embed=embed, allowed_mentions=discord.AllowedMentions(roles=True))


async def post_typology(guild_id: str):
    """Post a typology question (Comparing types, Personal typology, or Friend group)."""
    channel_id = HARDCODED["channel_typology"]
    channel = bot.get_channel(int(channel_id))
    if not channel:
        print(f"[Typology] Could not find channel {channel_id}")
        return

    # Randomly select from typology sub-categories
    category = random.choice(["comparing", "personal", "friendgroup"])
    
    if category == "comparing":
        # Generate MBTI x Enneagram comparison question
        type1 = f"{random.choice(config.MBTI_TYPES)} {random.choice(config.ENNEAGRAM_TYPES)}"
        type2 = type1
        while type2 == type1:
            type2 = f"{random.choice(config.MBTI_TYPES)} {random.choice(config.ENNEAGRAM_TYPES)}"
        
        question_template = await get_unused_question(guild_id, "typology_comparing", config.TYPOLOGY_QUESTIONS)
        description = f"**{type1}** or **{type2}**\n\n{question_template}"
        footer_text = "Comparing Types"
    elif category == "personal":
        # Personal typology nerd question
        question = await get_unused_question(guild_id, "typology_personal", config.PERSONAL_TYPOLOGY_QUESTIONS)
        description = question
        footer_text = "Personal Typology"
    else:
        # Friend group "most likely to" question
        question = await get_unused_question(guild_id, "typology_friendgroup", config.FRIEND_GROUP_QUESTIONS)
        description = question
        footer_text = "Friend Group"
    
    # Increment and get question counter
    count_str = await db.get_state(guild_id, "typology_question_count") or "0"
    count = int(count_str) + 1
    await db.set_state(guild_id, "typology_question_count", str(count))

    embed = _embed(
        config.EMBEDS["typology"]["title"],
        description,
        "typology",
        footer=f"{footer_text} (#{count})",
    )

    ping_role_id = HARDCODED["ping_role_typology"]
    content = f"<@&{ping_role_id}>"
    await channel.send(content=content, embed=embed, allowed_mentions=discord.AllowedMentions(roles=True))


# Map question type → post function
QUESTION_POST_FNS = {
    "warm": post_warm,
    "chill": post_chill,
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
    
    # Check if channel is in a blacklisted category
    if channel.category_id and str(channel.category_id) in HARDCODED["blacklist_categories"]:
        print(f"[ChipDrop] Channel {channel_id} is in blacklisted category, skipping")
        return

    # Check if there's already an active drop
    existing = await db.get_chip_drop(guild_id)
    if existing:
        return

    # Random amount between min and max
    amount = random.randint(config.CHIP_DROP["min_amount"], config.CHIP_DROP["max_amount"])
    emoji = config.CHIPS["emoji"]
    
    # 20% chance for math, 80% for grab
    if random.random() < config.CHIP_DROP["math_chance"]:
        equation, answer = generate_math_question()
        announcement = config.MESSAGES["chip_drop"]["math_announcement"].format(
            equation=equation, amount=amount, emoji=emoji
        )
        drop_type = "math"
        answer_str = str(answer)
    else:
        announcement = config.MESSAGES["chip_drop"]["grab_announcement"].format(
            amount=amount, emoji=emoji
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
        # Expired
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

    channel_id = await db.get_channel(guild_id, "codepurple")
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

    # Check cooldown
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
    channel_id = await db.get_channel(guild_id, "chipdrop")  # Post in chip drop channel
    if not channel_id:
        return
    channel = bot.get_channel(int(channel_id))
    if not channel:
        return

    today = datetime.now(MANILA_TZ).date().isoformat()
    chatters = await db.get_top_chatters(guild_id, today)
    emoji = config.CHIPS["emoji"]
    top_reward = config.CHIPS["rewards"]["top_chatter"]
    second_reward = config.CHIPS["rewards"]["second_chatter"]

    if not chatters:
        await channel.send(config.MESSAGES["chatter_reward"]["no_activity"])
        await db.clear_daily_chatter(guild_id, today)
        return

    lines = [config.MESSAGES["chatter_reward"]["announcement"]]

    if len(chatters) == 1 or (len(chatters) >= 2 and chatters[0]["user_id"] == chatters[1]["user_id"]):
        user = chatters[0]
        total = top_reward + second_reward if len(chatters) == 1 else top_reward
        await db.add_chips(guild_id, user["user_id"], user["username"], total)
        lines.append(
            config.MESSAGES["chatter_reward"]["same_user"].format(
                user=f"<@{user['user_id']}>", amount=total, emoji=emoji
            )
        )
    else:
        top = chatters[0]
        await db.add_chips(guild_id, top["user_id"], top["username"], top_reward)
        lines.append(
            config.MESSAGES["chatter_reward"]["top_chatter"].format(
                user=f"<@{top['user_id']}>", amount=top_reward, emoji=emoji
            )
        )
        second = chatters[1]
        await db.add_chips(guild_id, second["user_id"], second["username"], second_reward)
        lines.append(
            config.MESSAGES["chatter_reward"]["second_chatter"].format(
                user=f"<@{second['user_id']}>", amount=second_reward, emoji=emoji
            )
        )

    await channel.send("\n".join(lines))
    await db.clear_daily_chatter(guild_id, today)
    await db.set_state(guild_id, "last_chatter_post", datetime.now(timezone.utc).isoformat())


async def do_activity_rewards(guild_id: str):
    """Daily activity rewards: messages + VC time"""
    channel_id = await db.get_channel(guild_id, "activity_rewards")
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
                amount=rewards[i],
                emoji=emoji,
                points=user["total"]
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

        # --- Daily Questions (rotating with auto-calculated gap) ---
        next_q_iso = await db.get_state(gid, "next_daily_question")
        if not next_q_iso:
            # First run — schedule first question in 1 minute for quick start
            next_time = now_utc + timedelta(minutes=1)
            await db.set_state(gid, "next_daily_question", next_time.isoformat())
            await db.set_state(gid, "daily_question_index", "0")
        else:
            next_q = datetime.fromisoformat(next_q_iso)
            if next_q.tzinfo is None:
                next_q = next_q.replace(tzinfo=timezone.utc)

            if now_utc >= next_q:
                # Time to post!
                idx_str = await db.get_state(gid, "daily_question_index") or "0"
                idx = int(idx_str) % len(DAILY_QUESTION_ORDER)
                qtype = DAILY_QUESTION_ORDER[idx]
                post_fn = QUESTION_POST_FNS.get(qtype)

                if post_fn:
                    try:
                        await post_fn(gid)
                    except Exception as e:
                        print(f"Error posting {qtype}: {e}")

                # Schedule next question
                next_idx = (idx + 1) % len(DAILY_QUESTION_ORDER)
                next_time = now_utc + timedelta(hours=QUESTION_GAP_HOURS)
                await db.set_state(gid, "next_daily_question", next_time.isoformat())
                await db.set_state(gid, "daily_question_index", str(next_idx))

        # --- Chatter Rewards (fixed Manila time) ---
        sched = config.CHATTER_SCHEDULE
        if now_manila.hour == sched["hour"] and now_manila.minute == sched["minute"]:
            last = await db.get_state(gid, "last_chatter_post")
            should_post = True
            if last:
                ld = datetime.fromisoformat(last)
                if ld.tzinfo is None:
                    ld = ld.replace(tzinfo=timezone.utc)
                if ld.astimezone(MANILA_TZ).date() >= now_manila.date():
                    should_post = False
            if should_post:
                try:
                    await do_chatter_rewards(gid)
                except Exception as e:
                    print(f"Error doing chatter rewards: {e}")

        # --- Activity Rewards (fixed Manila time) ---
        act_sched = config.ACTIVITY_REWARDS
        if now_manila.hour == act_sched["hour"] and now_manila.minute == act_sched["minute"]:
            last = await db.get_state(gid, "last_activity_post")
            should_post = True
            if last:
                ld = datetime.fromisoformat(last)
                if ld.tzinfo is None:
                    ld = ld.replace(tzinfo=timezone.utc)
                if ld.astimezone(MANILA_TZ).date() >= now_manila.date():
                    should_post = False
            if should_post and config.FEATURES.get("activity_rewards"):
                try:
                    await do_activity_rewards(gid)
                except Exception as e:
                    print(f"Error doing activity rewards: {e}")

        # --- Code Purple (every hour) ---
        if now_manila.minute == 0:
            await check_code_purple(gid)


@schedule_loop.before_loop
async def before_schedule():
    await bot.wait_until_ready()


async def chip_drop_cycle():
    """Background loop — manages chip drops based on activity."""
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        # Check every minute
        await asyncio.sleep(60)
        
        if not config.FEATURES.get("chip_drops"):
            continue
            
        for guild in bot.guilds:
            gid = str(guild.id)
            try:
                # Check for expired drops
                await check_chip_drop_expired(gid)
                
                # Check if there's already an active drop
                existing = await db.get_chip_drop(gid)
                if existing:
                    continue
                
                # Check cooldown from last claimed drop
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
                
                # Check if there was any activity in last 30 minutes
                last_msg = await db.get_state(gid, "last_message_time")
                if not last_msg:
                    continue
                
                last_msg_dt = datetime.fromisoformat(last_msg)
                if last_msg_dt.tzinfo is None:
                    last_msg_dt = last_msg_dt.replace(tzinfo=timezone.utc)
                
                mins_since_activity = (datetime.now(timezone.utc) - last_msg_dt).total_seconds() / 60
                if mins_since_activity > config.CHIP_DROP["activity_window"]:
                    continue
                
                # Check if we need to schedule a drop
                scheduled = await db.get_state(gid, "chip_drop_scheduled_at")
                if not scheduled:
                    # Schedule a drop in 1-60 minutes
                    delay = random.randint(config.CHIP_DROP["min_delay"], config.CHIP_DROP["max_delay"])
                    drop_time = datetime.now(timezone.utc) + timedelta(minutes=delay)
                    await db.set_state(gid, "chip_drop_scheduled_at", drop_time.isoformat())
                else:
                    # Check if scheduled time has passed
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

        # Delete current message
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

        # Delete this message (the completed story / start prompt)
        try:
            await interaction.message.delete()
        except Exception:
            pass

        # Start new game
        embed = build_word_game_embed("", 0, True)
        view = WordGameActiveView()
        msg = await interaction.channel.send(embed=embed, view=view)
        await db.create_word_game(gid, str(interaction.channel.id), str(msg.id))


# ======================== SLASH COMMANDS ========================

# ---------- Public ----------

BOT_VERSION = "v1.55"


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
            amount=bal, emoji=config.CHIPS["emoji"], rank=rank_str
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
                amount=entry["chips"],
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
                rank=user_rank, amount=user_bal, currency=config.CHIPS["name"]
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
        f"Set {user.mention}'s chips to **{amount} {config.CHIPS['emoji']}**", ephemeral=True
    )


@bot.tree.command(name="forcedrop", description="Force a chip drop (admin only)")
@app_commands.default_permissions(administrator=True)
async def forcedrop_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(config.MESSAGES["success"]["force_drop"], ephemeral=True)
    await do_chip_drop(str(interaction.guild_id), str(interaction.channel_id))


@bot.tree.command(name="forcequestion", description="Force post a daily question (admin only)")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(type="Type of question to post")
@app_commands.choices(
    type=[
        app_commands.Choice(name="Warm Questions", value="warm"),
        app_commands.Choice(name="Chill Questions", value="chill"),
        app_commands.Choice(name="Typology Questions", value="typology"),
    ]
)
async def forcequestion_cmd(interaction: discord.Interaction, type: app_commands.Choice[str]):
    gid = str(interaction.guild_id)
    fn = QUESTION_POST_FNS.get(type.value)
    if fn:
        await fn(gid)
        ch = await db.get_channel(gid, type.value)
        await interaction.response.send_message(f"Posted {type.name} to <#{ch}>", ephemeral=True)
    else:
        await interaction.response.send_message(config.MESSAGES["errors"]["generic"], ephemeral=True)


@bot.tree.command(name="codepurple", description="Force a Code Purple message (admin only)")
@app_commands.default_permissions(administrator=True)
async def codepurple_cmd(interaction: discord.Interaction):
    gid = str(interaction.guild_id)
    channel_id = await db.get_channel(gid, "codepurple")
    if not channel_id:
        await interaction.response.send_message("No code purple channel set! Use `/setchannel`.", ephemeral=True)
        return
    channel = bot.get_channel(int(channel_id))
    if not channel:
        await interaction.response.send_message("Channel not found!", ephemeral=True)
        return
    await channel.send(random.choice(config.MESSAGES["code_purple"]))
    await db.set_state(gid, "last_code_purple", datetime.now(timezone.utc).isoformat())
    await interaction.response.send_message(f"Code purple posted to <#{channel_id}>", ephemeral=True)


@bot.tree.command(name="stats", description="View bot statistics (admin only)")
@app_commands.default_permissions(administrator=True)
async def stats_cmd(interaction: discord.Interaction):
    gid = str(interaction.guild_id)
    total_users = await db.get_total_users(gid)

    used_warm = len(await db.get_used_questions(gid, "warm"))
    used_chill = len(await db.get_used_questions(gid, "chill"))
    used_typo = len(await db.get_used_questions(gid, "typology"))
    total_warm = len(config.SPARK_WYR) + len(config.SPARK_DEBATES) + len(config.BUTTON_QUESTIONS)
    total_chill = len(config.SPARK_CHILL) + len(config.PERSONALITY_QUESTIONS)
    total_typo = len(config.TYPOLOGY_QUESTIONS) + len(config.PERSONAL_TYPOLOGY_QUESTIONS) + len(config.FRIEND_GROUP_QUESTIONS)

    next_q = await db.get_state(gid, "next_daily_question")
    last_cd = await db.get_state(gid, "last_chip_drop_claimed")
    last_cp = await db.get_state(gid, "last_code_purple")
    q_idx = await db.get_state(gid, "daily_question_index") or "0"
    next_type = DAILY_QUESTION_ORDER[int(q_idx) % len(DAILY_QUESTION_ORDER)]

    def fmt(iso):
        if not iso:
            return "Never"
        t = datetime.fromisoformat(iso)
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return f"<t:{int(t.timestamp())}:R>"

    embed = discord.Embed(title="📊 Bot Statistics", color=0x00BFFF, timestamp=datetime.now(timezone.utc))
    embed.add_field(name="👥 Users", value=str(total_users), inline=True)
    embed.add_field(name="🔥 Warm Qs", value=f"{used_warm}/{total_warm}", inline=True)
    embed.add_field(name="🌙 Chill Qs", value=f"{used_chill}/{total_chill}", inline=True)
    embed.add_field(name="✨ Typology Qs", value=f"{used_typo}/{total_typo}", inline=True)
    embed.add_field(name="📅 Next Question", value=f"{next_type.title()} {fmt(next_q)}", inline=True)
    embed.add_field(name="🥔 Last Chip Drop", value=fmt(last_cd), inline=True)
    embed.add_field(name="💜 Last Code Purple", value=fmt(last_cp), inline=True)
    embed.add_field(name="⏱️ Question Gap", value=f"{QUESTION_GAP_HOURS:.0f}h", inline=True)
    embed.set_footer(text="CRISPS GC Bot Stats")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# COMMENTED OUT - Using hardcoded channels (v1.55)
# @bot.tree.command(name="setchannel", description="Set a channel for bot features (admin only)")
# @app_commands.default_permissions(administrator=True)
# @app_commands.describe(feature="Feature to configure", channel="Channel (defaults to current)")
# @app_commands.choices(
#     feature=[
#         app_commands.Choice(name="Warm Questions", value="warm"),
#         app_commands.Choice(name="Chill Questions", value="chill"),
#         app_commands.Choice(name="Typology Questions", value="typology"),
#         app_commands.Choice(name="Code Purple", value="codepurple"),
#         app_commands.Choice(name="Activity Rewards", value="activity_rewards"),
#         app_commands.Choice(name="Word Game", value="wordgame"),
#     ]
# )
# async def setchannel_cmd(
#     interaction: discord.Interaction,
#     feature: app_commands.Choice[str],
#     channel: discord.TextChannel = None,
# ):
#     target = channel or interaction.channel
#     gid = str(interaction.guild_id)
#     await db.set_channel(gid, feature.value, str(target.id))
#
#     # If setting word game channel, always send "Start new story" embed
#     if feature.value == "wordgame":
#         await interaction.response.defer(ephemeral=True)
#         embed = discord.Embed(
#             title="📖 Word Game",
#             description="*Click the button below to start a new story!*",
#             color=int(config.WORD_GAME["embed"]["color"], 16),
#         )
#         embed.set_footer(text="One word per message • Punctuation auto-formats")
#         view = WordGameStartView()
#         await target.send(embed=embed, view=view)
#         await interaction.followup.send(f"{feature.name} channel set to {target.mention}", ephemeral=True)
#     else:
#         await interaction.response.send_message(f"{feature.name} channel set to {target.mention}", ephemeral=True)


@bot.tree.command(name="viewchannels", description="View current channel settings (admin only)")
@app_commands.default_permissions(administrator=True)
async def viewchannels_cmd(interaction: discord.Interaction):
    lines = ["**Current Channel Settings (Hardcoded):**", ""]
    lines.append(f"🔥 Warm Questions: <#{HARDCODED['channel_warm']}>")
    lines.append(f"🌙 Chill Questions: <#{HARDCODED['channel_chill']}>")
    lines.append(f"✨ Typology Questions: <#{HARDCODED['channel_typology']}>")
    lines.append(f"💜 Code Purple: <#{HARDCODED['channel_codepurple']}>")
    lines.append(f"🏆 Activity Rewards: <#{HARDCODED['channel_activity_rewards']}>")
    lines.append("📖 Word Game: *uses database*")
    lines.append("🥔 Chip Drops: *Drops in active channels*")
    
    # Blacklisted categories
    lines.append("")
    lines.append("**🚫 Chip Drop Blacklist (by category):**")
    for cat_id in HARDCODED["blacklist_categories"]:
        lines.append(f"• Category ID: {cat_id}")
    
    lines.append("")
    lines.append("*Config is hardcoded in bot.py*")

    await interaction.response.send_message("\n".join(lines), ephemeral=True)


# COMMENTED OUT - Using hardcoded category blacklist (v1.55)
# @bot.tree.command(name="blacklistchannel", description="Blacklist a channel from chip drops (admin only)")
# @app_commands.default_permissions(administrator=True)
# @app_commands.describe(channel="Channel to blacklist")
# async def blacklistchannel_cmd(interaction: discord.Interaction, channel: discord.TextChannel):
#     gid = str(interaction.guild_id)
#     added = await db.add_blacklisted_channel(gid, str(channel.id))
#     if added:
#         await interaction.response.send_message(f"✅ {channel.mention} blacklisted from chip drops", ephemeral=True)
#     else:
#         await interaction.response.send_message(f"⚠️ {channel.mention} is already blacklisted", ephemeral=True)
#
#
# @bot.tree.command(name="unblacklistchannel", description="Remove a channel from chip drop blacklist (admin only)")
# @app_commands.default_permissions(administrator=True)
# @app_commands.describe(channel="Channel to unblacklist")
# async def unblacklistchannel_cmd(interaction: discord.Interaction, channel: discord.TextChannel):
#     gid = str(interaction.guild_id)
#     removed = await db.remove_blacklisted_channel(gid, str(channel.id))
#     if removed:
#         await interaction.response.send_message(f"✅ {channel.mention} removed from blacklist", ephemeral=True)
#     else:
#         await interaction.response.send_message(f"⚠️ {channel.mention} wasn't blacklisted", ephemeral=True)


@bot.tree.command(name="viewschedule", description="View upcoming scheduled posts (admin only)")
@app_commands.default_permissions(administrator=True)
async def viewschedule_cmd(interaction: discord.Interaction):
    gid = str(interaction.guild_id)
    now_utc = datetime.now(timezone.utc)
    now_manila = datetime.now(MANILA_TZ)

    lines = ["**📅 Schedule & Status**", ""]

    # --- Channel Status ---
    lines.append("**📌 Channel Setup**")
    channel_types = ["warm", "chill", "typology", "codepurple", "activity_rewards"]
    channel_names = {
        "warm": "🔥 Warm Questions",
        "chill": "🌙 Chill Questions", 
        "typology": "✨ Typology Questions",
        "codepurple": "💜 Code Purple",
        "activity_rewards": "🏆 Activity Rewards",
    }
    for ctype in channel_types:
        ch_id = await db.get_channel(gid, ctype)
        if ch_id:
            lines.append(f"✅ {channel_names[ctype]}: <#{ch_id}>")
        else:
            lines.append(f"❌ {channel_names[ctype]}: Not set")
    # Chip drops don't need a channel - they drop in active channels
    lines.append("✅ 🥔 Chip Drops: Drops in active channels")
    
    lines.append("")

    # --- Ping Roles Status ---
    lines.append("**🔔 Ping Roles**")
    for qtype in ["warm", "chill", "typology"]:
        role_id = await db.get_state(gid, f"ping_role_{qtype}")
        qname = {"warm": "🔥 Warm", "chill": "🌙 Chill", "typology": "✨ Typology"}[qtype]
        if role_id:
            lines.append(f"✅ {qname}: <@&{role_id}>")
        else:
            lines.append(f"❌ {qname}: Not set")
    
    lines.append("")

    # --- Upcoming Schedule ---
    lines.append("**⏰ Upcoming Posts**")
    
    # Daily questions — show next 3 in rotation
    next_q_iso = await db.get_state(gid, "next_daily_question")
    q_idx = int(await db.get_state(gid, "daily_question_index") or "0")

    if next_q_iso:
        next_q = datetime.fromisoformat(next_q_iso)
        if next_q.tzinfo is None:
            next_q = next_q.replace(tzinfo=timezone.utc)
    else:
        next_q = now_utc + timedelta(minutes=1)

    names = {
        "warm": "🔥 Warm Question",
        "chill": "🌙 Chill Question",
        "typology": "✨ Typology Question",
    }
    for i in range(len(DAILY_QUESTION_ORDER)):
        idx = (q_idx + i) % len(DAILY_QUESTION_ORDER)
        qtype = DAILY_QUESTION_ORDER[idx]
        post_time = next_q + timedelta(hours=QUESTION_GAP_HOURS * i)
        ts = int(post_time.timestamp())
        ch_id = await db.get_channel(gid, qtype)
        status = f"→ <#{ch_id}>" if ch_id else "→ ⚠️ No channel"
        lines.append(f"{names[qtype]} <t:{ts}:R> {status}")

    lines.append("")

    # Activity rewards
    act_sched = config.ACTIVITY_REWARDS
    next_activity = now_manila.replace(hour=act_sched["hour"], minute=act_sched["minute"], second=0, microsecond=0)
    if next_activity <= now_manila:
        next_activity += timedelta(days=1)
    ts = int(next_activity.astimezone(timezone.utc).timestamp())
    ch_id = await db.get_channel(gid, "activity_rewards")
    status = f"→ <#{ch_id}>" if ch_id else "→ ⚠️ No channel"
    lines.append(f"🏆 Activity Rewards <t:{ts}:R> {status}")

    lines.append("")
    lines.append(f"💜 Code Purple: Checks every hour")
    lines.append(f"🥔 Chip Drops: {config.CHIP_DROP['min_delay']}-{config.CHIP_DROP['max_delay']}m after activity")
    lines.append("")
    lines.append(f"*Question gap: {QUESTION_GAP_HOURS:.0f}h • {len(DAILY_QUESTION_ORDER)} daily types*")

    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@bot.tree.command(name="resettimer", description="Reset the daily question timer (admin only)")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(feature="What to reset")
@app_commands.choices(
    feature=[
        app_commands.Choice(name="Next Daily Question (posts in ~1 min)", value="daily"),
        app_commands.Choice(name="Chip Drop (triggers in ~1 min)", value="chipdrop"),
    ]
)
async def resettimer_cmd(interaction: discord.Interaction, feature: app_commands.Choice[str]):
    gid = str(interaction.guild_id)
    now = datetime.now(timezone.utc)

    if feature.value == "daily":
        await db.set_state(gid, "next_daily_question", (now + timedelta(minutes=1)).isoformat())
        q_idx = int(await db.get_state(gid, "daily_question_index") or "0")
        next_type = DAILY_QUESTION_ORDER[q_idx % len(DAILY_QUESTION_ORDER)]
        await interaction.response.send_message(
            f"Daily question timer reset — **{next_type.title()}** will post in ~1 minute", ephemeral=True
        )
    elif feature.value == "chipdrop":
        await interaction.response.send_message("Chip drop timer reset — will trigger in ~1 minute", ephemeral=True)
        await do_chip_drop(gid)


@bot.tree.command(name="fastforward", description="Fast forward daily question timer (admin only)")
@app_commands.default_permissions(administrator=True)
async def fastforward_cmd(interaction: discord.Interaction):
    gid = str(interaction.guild_id)
    
    next_q_iso = await db.get_state(gid, "next_daily_question")
    if not next_q_iso:
        await interaction.response.send_message("No question scheduled yet!", ephemeral=True)
        return
    
    next_q = datetime.fromisoformat(next_q_iso)
    if next_q.tzinfo is None:
        next_q = next_q.replace(tzinfo=timezone.utc)
    
    # Fast forward by (gap - 3 seconds)
    skip_time = timedelta(hours=QUESTION_GAP_HOURS) - timedelta(seconds=3)
    new_time = next_q - skip_time
    
    await db.set_state(gid, "next_daily_question", new_time.isoformat())
    
    q_idx = int(await db.get_state(gid, "daily_question_index") or "0")
    next_type = DAILY_QUESTION_ORDER[q_idx % len(DAILY_QUESTION_ORDER)]
    
    ts = int(new_time.timestamp())
    await interaction.response.send_message(
        f"⏩ Fast forwarded! **{next_type.title()}** question will post <t:{ts}:R>", ephemeral=True
    )


# ---------- Ping Role ----------

QUESTION_FEATURE_NAMES = {
    "warm": "🔥 Warm Questions",
    "chill": "🌙 Chill Questions",
    "typology": "✨ Typology Questions",
}


# COMMENTED OUT - Using hardcoded ping roles and role picker messages (v1.55)
# @bot.tree.command(name="setpingrole", description="Set the role to ping for a daily question type (admin only)")
# @app_commands.default_permissions(administrator=True)
# @app_commands.describe(feature="Which daily question type", role="The role to ping")
# @app_commands.choices(
#     feature=[
#         app_commands.Choice(name="Warm Questions", value="warm"),
#         app_commands.Choice(name="Chill Questions", value="chill"),
#         app_commands.Choice(name="Typology Questions", value="typology"),
#     ]
# )
# async def setpingrole_cmd(interaction: discord.Interaction, feature: app_commands.Choice[str], role: discord.Role):
#     gid = str(interaction.guild_id)
#     await db.set_state(gid, f"ping_role_{feature.value}", str(role.id))
#     await interaction.response.send_message(f"{feature.name} ping role set to {role.mention}", ephemeral=True)
#
#
# @bot.tree.command(name="placepingrolepicker", description="Post a reaction role picker for a daily question type (admin only)")
# @app_commands.default_permissions(administrator=True)
# @app_commands.describe(feature="Which daily question type")
# @app_commands.choices(
#     feature=[
#         app_commands.Choice(name="Warm Questions", value="warm"),
#         app_commands.Choice(name="Chill Questions", value="chill"),
#         app_commands.Choice(name="Typology Questions", value="typology"),
#     ]
# )
# async def placepingrolepicker_cmd(interaction: discord.Interaction, feature: app_commands.Choice[str]):
#     gid = str(interaction.guild_id)
#     role_id = await db.get_state(gid, f"ping_role_{feature.value}")
#     if not role_id:
#         await interaction.response.send_message(
#             f"No ping role set for {feature.name}! Use `/setpingrole {feature.value}` first.", ephemeral=True
#         )
#         return
#
#     feature_name = QUESTION_FEATURE_NAMES[feature.value]
#     
#     # Feature descriptions
#     feature_descriptions = {
#         "warm": "Would You Rather, debates, and Press the Button questions",
#         "chill": "Chill vibes and lifestyle-related questions",
#         "typology": "Typology-related questions, comparing types, and friend group questions",
#     }
#     
#     # Remove emoji from feature name for description text
#     feature_name_no_emoji = feature_name.split(" ", 1)[1]  # Remove first word (emoji)
#     description_text = feature_descriptions.get(feature.value, "")
#     
#     embed = discord.Embed(
#         title=f"🔔 {feature_name} Notifications",
#         description=f"React with 👍 to get the <@&{role_id}> role and be pinged for {feature_name_no_emoji}\n\n**Includes:** {description_text}",
#         color=int(config.COLORS[feature.value], 16),
#     )
#     embed.set_footer(text="Unreact to remove the role.")
#
#     await interaction.response.defer(ephemeral=True)
#     msg = await interaction.channel.send(embed=embed)
#     await msg.add_reaction("👍")
#     await db.set_state(gid, f"role_picker_message_{feature.value}", str(msg.id))
#     await interaction.followup.send(f"{feature.name} role picker posted! ✅", ephemeral=True)


# ======================== EVENTS ========================


@bot.event
async def on_ready():
    if not hasattr(bot, "_initialized"):
        bot._initialized = True
        await db.init()
        # Register persistent views so buttons survive restarts
        bot.add_view(WordGameActiveView())
        bot.add_view(WordGameStartView())
        schedule_loop.start()
        bot.loop.create_task(chip_drop_cycle())
        synced = await bot.tree.sync()
        print(f"✅ {bot.user} is online! Synced {len(synced)} commands globally. ({BOT_VERSION})")


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    """Handle reaction role picker — add role on 👍 react."""
    if payload.user_id == bot.user.id:
        return
    if str(payload.emoji) != "👍":
        return

    # Check all feature pickers using hardcoded message IDs
    matched_feature = None
    msg_id = str(payload.message_id)
    for feature in ["warm", "chill", "typology"]:
        if msg_id == HARDCODED[f"role_picker_message_{feature}"]:
            matched_feature = feature
            break
    
    if not matched_feature:
        return

    role_id = HARDCODED[f"ping_role_{matched_feature}"]

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
    for feature in ["warm", "chill", "typology"]:
        if msg_id == HARDCODED[f"role_picker_message_{feature}"]:
            matched_feature = feature
            break
    
    if not matched_feature:
        return

    role_id = HARDCODED[f"ping_role_{matched_feature}"]

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

    # Track activity for code purple
    await db.set_state(gid, "last_message_time", datetime.now(timezone.utc).isoformat())
    await db.set_state(gid, "last_message_channel", str(message.channel.id))
    
    # Anti-spam: Only count activity if message sent >3 seconds after user's last message
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

    # --- Chip Drop handling (grab or math answer) ---
    drop = await db.get_chip_drop(gid)
    if drop and str(message.channel.id) == drop["channel_id"]:
        content = message.content.strip()
        claimed = False
        
        if drop["drop_type"] == "grab" and content.lower() == "~grab":
            claimed = True
        elif drop["drop_type"] == "math":
            # Check if answer matches (strip whitespace)
            if content == drop["answer"]:
                claimed = True
        
        if claimed:
            amount = drop["amount"]
            emoji = config.CHIPS["emoji"]
            
            await db.add_chips(gid, str(message.author.id), message.author.display_name, amount)
            
            # Reply to the winner's message
            claimed_msg = random.choice(config.MESSAGES["chip_drop"]["claimed"]).format(
                user=message.author.mention,
                amount=amount,
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
            # Same person can't go twice in a row
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
                game = await db.get_word_game(gid)

                # Delete old bot message (forward pattern)
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
