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

# Daily question rotation: casual → personality → ...
DAILY_QUESTION_ORDER = ["casual", "personality"]
QUESTION_GAP_HOURS = 24 / len(DAILY_QUESTION_ORDER)  # 12 hours


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


def _embed(title: str, description: str, color_key: str, footer: str, author: bool = True) -> discord.Embed:
    """Shortcut to build a standard embed."""
    e = discord.Embed(
        title=title,
        description=description,
        color=int(config.COLORS[color_key], 16),
        timestamp=datetime.now(timezone.utc),
    )
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


async def post_casual(guild_id: str):
    channel_id = await db.get_channel(guild_id, "casual")
    if not channel_id:
        return
    channel = bot.get_channel(int(channel_id))
    if not channel:
        return

    all_q = (
        [(q, "Would You Rather") for q in config.SPARK_WYR]
        + [(q, "Debate Time") for q in config.SPARK_DEBATES]
        + [(q, "Chill Vibes") for q in config.SPARK_CHILL]
    )

    used = await db.get_used_questions(guild_id, "casual")
    if len(used) >= len(all_q):
        await db.reset_questions(guild_id, "casual")
        used = []
    available = [i for i in range(len(all_q)) if i not in used]
    idx = random.choice(available)
    await db.mark_question_used(guild_id, "casual", idx)
    question, category = all_q[idx]

    embed = _embed(
        config.EMBEDS["casual"]["title"],
        f"*{category}*\n\n{question}",
        "casual",
        config.EMBEDS["casual"]["footer"],
    )

    # Ping casual role
    ping_role_id = await db.get_state(guild_id, "ping_role_casual")
    content = f"<@&{ping_role_id}>" if ping_role_id else None
    await channel.send(content=content, embed=embed)


async def post_personality(guild_id: str):
    channel_id = await db.get_channel(guild_id, "personality")
    if not channel_id:
        return
    channel = bot.get_channel(int(channel_id))
    if not channel:
        return

    # Randomly select from personality sub-categories
    category = random.choice(["lifestyle", "typology"])
    
    if category == "typology":
        # Generate typology comparison question
        type1 = f"{random.choice(config.MBTI_TYPES)} {random.choice(config.ENNEAGRAM_TYPES)}"
        type2 = type1
        while type2 == type1:
            type2 = f"{random.choice(config.MBTI_TYPES)} {random.choice(config.ENNEAGRAM_TYPES)}"
        
        question_template = await get_unused_question(guild_id, "personality_typology", config.TYPOLOGY_QUESTIONS)
        description = f"**{type1}** or **{type2}**\n\n{question_template}"
    else:
        # Lifestyle personality question
        question = await get_unused_question(guild_id, "personality_lifestyle", config.PERSONALITY_QUESTIONS)
        description = question
    
    embed = _embed(
        config.EMBEDS["personality"]["title"],
        description,
        "personality",
        config.EMBEDS["personality"]["footer"],
    )

    # Ping personality role
    ping_role_id = await db.get_state(guild_id, "ping_role_personality")
    content = f"<@&{ping_role_id}>" if ping_role_id else None
    await channel.send(content=content, embed=embed)


# Map question type → post function
QUESTION_POST_FNS = {
    "casual": post_casual,
    "personality": post_personality,
}


async def do_chip_drop(guild_id: str):
    channel_id = await db.get_channel(guild_id, "chipdrop")
    if not channel_id:
        return
    channel = bot.get_channel(int(channel_id))
    if not channel:
        return

    amount = config.CHIPS["rewards"]["chip_drop"]
    announcement = random.choice(config.MESSAGES["chip_drop"]["announcements"]).format(
        amount=amount, emoji=config.CHIPS["emoji"]
    )

    view = ChipDropView(amount, guild_id)
    msg = await channel.send(content=announcement, view=view)
    view.message = msg
    await db.set_state(guild_id, "last_chip_drop", datetime.now(timezone.utc).isoformat())


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

        # --- Code Purple (every hour) ---
        if now_manila.minute == 0:
            await check_code_purple(gid)


@schedule_loop.before_loop
async def before_schedule():
    await bot.wait_until_ready()


async def chip_drop_cycle():
    """Background loop — drops chips at random intervals."""
    await bot.wait_until_ready()
    while not bot.is_closed():
        delay = random.randint(
            config.CHIP_DROP["min_interval"] * 60,
            config.CHIP_DROP["max_interval"] * 60,
        )
        await asyncio.sleep(delay)
        if config.FEATURES.get("chip_drops"):
            for guild in bot.guilds:
                gid = str(guild.id)
                try:
                    await do_chip_drop(gid)
                except Exception as e:
                    print(f"Chip drop error in {guild.name}: {e}")


# ======================== CHIP DROP VIEW ========================


class ChipDropView(discord.ui.View):
    def __init__(self, amount: int, guild_id: str):
        super().__init__(timeout=config.CHIP_DROP["button_timeout"])
        self.amount = amount
        self.guild_id = guild_id
        self.claimed = False
        self.message: discord.Message | None = None

    @discord.ui.button(label="Grab free chips 🥔", style=discord.ButtonStyle.success)
    async def grab(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.claimed:
            await interaction.response.send_message("Already claimed. Better luck next time!", ephemeral=True)
            return

        self.claimed = True
        button.disabled = True
        button.label = f"Claimed by {interaction.user.display_name}"

        await db.add_chips(self.guild_id, str(interaction.user.id), interaction.user.display_name, self.amount)

        msg = random.choice(config.MESSAGES["chip_drop"]["claimed"]).format(
            user=interaction.user.mention,
            amount=self.amount,
            emoji=config.CHIPS["emoji"],
        )
        await interaction.response.edit_message(content=msg, view=self)
        self.stop()

    async def on_timeout(self):
        if not self.claimed and self.message:
            expired = random.choice(config.MESSAGES["chip_drop"]["expired"])
            for child in self.children:
                child.disabled = True
                child.label = "Expired"
            try:
                await self.message.edit(content=expired, view=self)
            except Exception:
                pass


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


@bot.tree.command(name="balance", description="Check your chip balance 🥔")
async def balance_cmd(interaction: discord.Interaction):
    gid, uid = str(interaction.guild_id), str(interaction.user.id)
    bal = await db.get_balance(gid, uid)
    rank = await db.get_rank(gid, uid)

    if bal == 0:
        await interaction.response.send_message(config.MESSAGES["balance"]["no_balance"], ephemeral=True)
    else:
        rank_str = f"#{rank}" if rank else config.MESSAGES["balance"]["unranked"]
        msg = config.MESSAGES["balance"]["response"].format(
            amount=bal, emoji=config.CHIPS["emoji"], rank=rank_str
        )
        await interaction.response.send_message(msg, ephemeral=True)


@bot.tree.command(name="chipleaderboard", description="View the server chip leaderboard 🏆")
async def leaderboard_cmd(interaction: discord.Interaction):
    gid, uid = str(interaction.guild_id), str(interaction.user.id)
    entries = await db.get_leaderboard(gid, config.LEADERBOARD["page_size"])

    if not entries:
        await interaction.response.send_message(config.MESSAGES["leaderboard"]["empty"], ephemeral=True)
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
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text=config.EMBEDS["leaderboard"]["footer"])

    user_rank = await db.get_rank(gid, uid)
    user_bal = await db.get_balance(gid, uid)
    if user_rank and user_rank > config.LEADERBOARD["page_size"]:
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
    await do_chip_drop(str(interaction.guild_id))


@bot.tree.command(name="forcequestion", description="Force post a daily question (admin only)")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(type="Type of question to post")
@app_commands.choices(
    type=[
        app_commands.Choice(name="Typology Daily", value="typology"),
        app_commands.Choice(name="Casual Question Daily", value="casual"),
        app_commands.Choice(name="Personality Daily", value="personality"),
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

    used_t = len(await db.get_used_questions(gid, "typology"))
    used_c = len(await db.get_used_questions(gid, "casual"))
    used_p = len(await db.get_used_questions(gid, "personality"))
    total_t = len(config.TYPOLOGY_QUESTIONS)
    total_c = len(config.SPARK_WYR) + len(config.SPARK_DEBATES) + len(config.SPARK_CHILL)
    total_p = len(config.PERSONALITY_QUESTIONS)

    next_q = await db.get_state(gid, "next_daily_question")
    last_cd = await db.get_state(gid, "last_chip_drop")
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
    embed.add_field(name="❓ Typology Qs", value=f"{used_t}/{total_t}", inline=True)
    embed.add_field(name="💬 Casual Qs", value=f"{used_c}/{total_c}", inline=True)
    embed.add_field(name="🧠 Personality Qs", value=f"{used_p}/{total_p}", inline=True)
    embed.add_field(name="📅 Next Question", value=f"{next_type.title()} {fmt(next_q)}", inline=True)
    embed.add_field(name="🥔 Last Chip Drop", value=fmt(last_cd), inline=True)
    embed.add_field(name="💜 Last Code Purple", value=fmt(last_cp), inline=True)
    embed.add_field(name="⏱️ Question Gap", value=f"{QUESTION_GAP_HOURS:.0f}h", inline=True)
    embed.set_footer(text="CRISPS GC Bot Stats")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="setchannel", description="Set a channel for bot features (admin only)")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(feature="Feature to configure", channel="Channel (defaults to current)")
@app_commands.choices(
    feature=[
        app_commands.Choice(name="Typology Daily", value="typology"),
        app_commands.Choice(name="Casual Question Daily", value="casual"),
        app_commands.Choice(name="Personality Daily", value="personality"),
        app_commands.Choice(name="Code Purple", value="codepurple"),
        app_commands.Choice(name="Chip Drops", value="chipdrop"),
        app_commands.Choice(name="Word Game", value="wordgame"),
    ]
)
async def setchannel_cmd(
    interaction: discord.Interaction,
    feature: app_commands.Choice[str],
    channel: discord.TextChannel = None,
):
    target = channel or interaction.channel
    gid = str(interaction.guild_id)
    await db.set_channel(gid, feature.value, str(target.id))

    # If setting word game channel, always send "Start new story" embed
    if feature.value == "wordgame":
        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(
            title="📖 Word Game",
            description="*Click the button below to start a new story!*",
            color=int(config.WORD_GAME["embed"]["color"], 16),
        )
        embed.set_footer(text="One word per message • Punctuation auto-formats")
        view = WordGameStartView()
        await target.send(embed=embed, view=view)
        await interaction.followup.send(f"{feature.name} channel set to {target.mention}", ephemeral=True)
    else:
        await interaction.response.send_message(f"{feature.name} channel set to {target.mention}", ephemeral=True)


@bot.tree.command(name="viewchannels", description="View current channel settings (admin only)")
@app_commands.default_permissions(administrator=True)
async def viewchannels_cmd(interaction: discord.Interaction):
    gid = str(interaction.guild_id)
    channels = await db.get_all_channels(gid)

    features = {
        "typology": "✨ Typology Daily",
        "casual": "💬 Casual Question Daily",
        "personality": "🧠 Personality Daily",
        "codepurple": "💜 Code Purple",
        "chipdrop": "🥔 Chip Drops",
        "wordgame": "📖 Word Game",
    }

    lines = ["**Current Channel Settings:**", ""]
    for key, name in features.items():
        ch = channels.get(key)
        lines.append(f"{name}: {f'<#{ch}>' if ch else '*not set*'}")
    lines.append("")
    lines.append("*Use `/setchannel` to configure*")

    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@bot.tree.command(name="viewschedule", description="View upcoming scheduled posts (admin only)")
@app_commands.default_permissions(administrator=True)
async def viewschedule_cmd(interaction: discord.Interaction):
    gid = str(interaction.guild_id)
    now_utc = datetime.now(timezone.utc)
    now_manila = datetime.now(MANILA_TZ)

    lines = ["**📅 Upcoming Schedule**", ""]

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
        "typology": "✨ Typology Daily",
        "casual": "💬 Casual Question",
        "personality": "🧠 Personality Daily",
    }
    for i in range(len(DAILY_QUESTION_ORDER)):
        idx = (q_idx + i) % len(DAILY_QUESTION_ORDER)
        qtype = DAILY_QUESTION_ORDER[idx]
        post_time = next_q + timedelta(hours=QUESTION_GAP_HOURS * i)
        ts = int(post_time.timestamp())
        lines.append(f"⏰ **{names[qtype]}** <t:{ts}:R>")

    lines.append("")

    # Chatter rewards
    sched = config.CHATTER_SCHEDULE
    next_chatter = now_manila.replace(hour=sched["hour"], minute=sched["minute"], second=0, microsecond=0)
    if next_chatter <= now_manila:
        next_chatter += timedelta(days=1)
    ts = int(next_chatter.astimezone(timezone.utc).timestamp())
    lines.append(f"⏰ **Chatter Rewards** <t:{ts}:R>")

    lines.append(f"💜 **Code Purple Check** every hour")
    lines.append(f"🥔 **Chip Drops** every {config.CHIP_DROP['min_interval']}-{config.CHIP_DROP['max_interval']}m")
    lines.append("")
    lines.append(f"*Question gap: {QUESTION_GAP_HOURS:.0f}h • {len(DAILY_QUESTION_ORDER)} daily questions*")

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


# ---------- Ping Role ----------

QUESTION_FEATURE_NAMES = {
    "casual": "💬 Casual Question Daily",
    "personality": "🧠 Personality Daily",
}


@bot.tree.command(name="setpingrole", description="Set the role to ping for a daily question type (admin only)")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(feature="Which daily question type", role="The role to ping")
@app_commands.choices(
    feature=[
        app_commands.Choice(name="Casual Question Daily", value="casual"),
        app_commands.Choice(name="Personality Daily", value="personality"),
    ]
)
async def setpingrole_cmd(interaction: discord.Interaction, feature: app_commands.Choice[str], role: discord.Role):
    gid = str(interaction.guild_id)
    await db.set_state(gid, f"ping_role_{feature.value}", str(role.id))
    await interaction.response.send_message(f"{feature.name} ping role set to {role.mention}", ephemeral=True)


@bot.tree.command(name="placepingrolepicker", description="Post a reaction role picker for a daily question type (admin only)")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(feature="Which daily question type")
@app_commands.choices(
    feature=[
        app_commands.Choice(name="Casual Question Daily", value="casual"),
        app_commands.Choice(name="Personality Daily", value="personality"),
    ]
)
async def placepingrolepicker_cmd(interaction: discord.Interaction, feature: app_commands.Choice[str]):
    gid = str(interaction.guild_id)
    role_id = await db.get_state(gid, f"ping_role_{feature.value}")
    if not role_id:
        await interaction.response.send_message(
            f"No ping role set for {feature.name}! Use `/setpingrole {feature.value}` first.", ephemeral=True
        )
        return

    feature_name = QUESTION_FEATURE_NAMES[feature.value]
    embed = discord.Embed(
        title=f"🔔 {feature_name} Notifications",
        description=f"React with 👍 to get the <@&{role_id}> role and be pinged for {feature_name}!\n\nUnreact to remove the role.",
        color=int(config.COLORS[feature.value], 16),
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text="React below to toggle notifications")
    if config.AUTHOR_NAME:
        embed.set_author(name=config.AUTHOR_NAME)

    await interaction.response.defer(ephemeral=True)
    msg = await interaction.channel.send(embed=embed)
    await msg.add_reaction("👍")
    await db.set_state(gid, f"role_picker_message_{feature.value}", str(msg.id))
    await interaction.followup.send(f"{feature.name} role picker posted! ✅", ephemeral=True)


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
        print(f"✅ {bot.user} is online! Synced {len(synced)} commands globally. (v2.1 - rephrased personality questions)")


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    """Handle reaction role picker — add role on 👍 react."""
    if payload.user_id == bot.user.id:
        return
    if str(payload.emoji) != "👍":
        return

    gid = str(payload.guild_id)
    
    # Check all feature pickers
    matched_feature = None
    for feature in ["casual", "personality"]:
        picker_msg_id = await db.get_state(gid, f"role_picker_message_{feature}")
        if picker_msg_id and str(payload.message_id) == picker_msg_id:
            matched_feature = feature
            break
    
    if not matched_feature:
        return

    role_id = await db.get_state(gid, f"ping_role_{matched_feature}")
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
        print(f"[Role] Added {role.name} to {member.display_name}")
    except Exception as e:
        print(f"Failed to add role: {e}")


@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    """Handle reaction role picker — remove role on 👍 unreact."""
    if str(payload.emoji) != "👍":
        return

    gid = str(payload.guild_id)
    
    # Check all feature pickers
    matched_feature = None
    for feature in ["casual", "personality"]:
        picker_msg_id = await db.get_state(gid, f"role_picker_message_{feature}")
        if picker_msg_id and str(payload.message_id) == picker_msg_id:
            matched_feature = feature
            break
    
    if not matched_feature:
        return

    role_id = await db.get_state(gid, f"ping_role_{matched_feature}")
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
        print(f"[Role] Removed {role.name} from {member.display_name}")
    except Exception as e:
        print(f"Failed to remove role: {e}")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return
    gid = str(message.guild.id)

    # Track activity for code purple & chatter rewards
    await db.set_state(gid, "last_message_time", datetime.now(timezone.utc).isoformat())
    await db.increment_chatter(gid, str(message.author.id), message.author.display_name)

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


# ======================== RUN ========================

if __name__ == "__main__":
    if not TOKEN:
        print("❌ DISCORD_TOKEN not set! Copy .env.example to .env and fill in your token.")
    else:
        bot.run(TOKEN)
