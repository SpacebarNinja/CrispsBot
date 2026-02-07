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


# ======================== POSTING FUNCTIONS ========================


async def post_typology(guild_id: str):
    channel_id = await db.get_channel(guild_id, "typology")
    if not channel_id:
        return
    channel = bot.get_channel(int(channel_id))
    if not channel:
        return

    type1 = f"{random.choice(config.MBTI_TYPES)} {random.choice(config.ENNEAGRAM_TYPES)}"
    type2 = type1
    while type2 == type1:
        type2 = f"{random.choice(config.MBTI_TYPES)} {random.choice(config.ENNEAGRAM_TYPES)}"

    question = await get_unused_question(guild_id, "typology", config.TYPOLOGY_QUESTIONS)
    embed = _embed(
        config.EMBEDS["typology"]["title"],
        f"**{type1}** or **{type2}**\n\n{question}",
        "typology",
        config.EMBEDS["typology"]["footer"],
    )
    await channel.send(embed=embed)
    await db.set_state(guild_id, "last_typology_post", datetime.now(timezone.utc).isoformat())


async def post_spark(guild_id: str):
    channel_id = await db.get_channel(guild_id, "spark")
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

    used = await db.get_used_questions(guild_id, "spark")
    if len(used) >= len(all_q):
        await db.reset_questions(guild_id, "spark")
        used = []
    available = [i for i in range(len(all_q)) if i not in used]
    idx = random.choice(available)
    await db.mark_question_used(guild_id, "spark", idx)
    question, category = all_q[idx]

    embed = _embed(
        config.EMBEDS["spark"]["title"],
        f"*{category}*\n\n{question}",
        "spark",
        config.EMBEDS["spark"]["footer"],
    )
    await channel.send(embed=embed)
    await db.set_state(guild_id, "last_spark_post", datetime.now(timezone.utc).isoformat())


async def post_personality(guild_id: str):
    channel_id = await db.get_channel(guild_id, "personality")
    if not channel_id:
        return
    channel = bot.get_channel(int(channel_id))
    if not channel:
        return

    question = await get_unused_question(guild_id, "personality", config.PERSONALITY_QUESTIONS)
    embed = _embed(
        config.EMBEDS["personality"]["title"],
        question,
        "personality",
        config.EMBEDS["personality"]["footer"],
    )
    await channel.send(embed=embed)
    await db.set_state(guild_id, "last_personality_post", datetime.now(timezone.utc).isoformat())


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

    if len(chatters) == 1 or chatters[0]["user_id"] == chatters[1]["user_id"] if len(chatters) >= 2 else True:
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


async def _check_feature(gid: str, now: datetime, feature: str, post_fn):
    """Generic schedule checker for daily question features."""
    if not config.FEATURES.get(feature):
        return
    sched = config.SCHEDULE.get(feature, {})
    if not sched.get("enabled"):
        return

    # Check for manual timer override (from /resettimer)
    override = await db.get_state(gid, f"next_{feature}")
    if override:
        ot = datetime.fromisoformat(override)
        if ot.tzinfo is None:
            ot = ot.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= ot:
            try:
                await post_fn(gid)
            except Exception as e:
                print(f"Error posting {feature}: {e}")
            await db.delete_state(gid, f"next_{feature}")
        return  # Don't also check regular schedule when override exists

    # Custom schedule from /setschedule (stored in DB)
    custom = await db.get_state(gid, f"schedule_{feature}")
    if custom:
        h, m = map(int, custom.split(":"))
    else:
        h, m = sched["hour"], sched["minute"]

    if now.hour == h and now.minute == m:
        # Already posted today?
        last = await db.get_state(gid, f"last_{feature}_post")
        if last:
            ld = datetime.fromisoformat(last)
            if ld.tzinfo is None:
                ld = ld.replace(tzinfo=timezone.utc)
            if ld.astimezone(MANILA_TZ).date() >= now.date():
                return
        try:
            await post_fn(gid)
        except Exception as e:
            print(f"Error posting {feature}: {e}")


async def _check_chatter(gid: str, now: datetime):
    """Check if it's time for chatter rewards."""
    if not config.FEATURES.get("chatter_rewards"):
        return
    sched = config.SCHEDULE.get("chatter_reward", {})
    if not sched.get("enabled"):
        return

    override = await db.get_state(gid, "next_chatter")
    if override:
        ot = datetime.fromisoformat(override)
        if ot.tzinfo is None:
            ot = ot.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= ot:
            try:
                await do_chatter_rewards(gid)
            except Exception as e:
                print(f"Error doing chatter rewards: {e}")
            await db.delete_state(gid, "next_chatter")
        return

    custom = await db.get_state(gid, "schedule_chatter")
    if custom:
        h, m = map(int, custom.split(":"))
    else:
        h, m = sched["hour"], sched["minute"]

    if now.hour == h and now.minute == m:
        last = await db.get_state(gid, "last_chatter_post")
        if last:
            ld = datetime.fromisoformat(last)
            if ld.tzinfo is None:
                ld = ld.replace(tzinfo=timezone.utc)
            if ld.astimezone(MANILA_TZ).date() >= now.date():
                return
        try:
            await do_chatter_rewards(gid)
        except Exception as e:
            print(f"Error doing chatter rewards: {e}")


@tasks.loop(seconds=60)
async def schedule_loop():
    """Main schedule loop — checks all features every minute."""
    now = datetime.now(MANILA_TZ)

    for guild in bot.guilds:
        gid = str(guild.id)

        for feature, post_fn in [
            ("typology", post_typology),
            ("spark", post_spark),
            ("personality", post_personality),
        ]:
            await _check_feature(gid, now, feature, post_fn)

        await _check_chatter(gid, now)

        # Code purple check at the top of every hour
        if now.minute == 0:
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


# ======================== WORD GAME HELPERS ========================


def build_word_game_embed(words: str, word_count: int, active: bool, last_user=None) -> discord.Embed:
    wg = config.WORD_GAME
    if active:
        title = wg["embed"]["title"]
        footer = wg["embed"]["footer"]
    else:
        title = wg["embed"]["title_ended"]
        footer = f"{word_count} {wg['embed']['footer_ended']}"

    story = words if words else wg["embed"]["empty_story"]
    color = int(wg["embed"]["color"], 16)

    embed = discord.Embed(title=title, description=story, color=color)
    embed.set_footer(text=footer)

    if last_user and active:
        embed.set_author(
            name=f"{wg['embed']['last_word_by']} {last_user.display_name}",
            icon_url=last_user.display_avatar.url,
        )

    return embed


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


# ---------- Word Game ----------


@bot.tree.command(name="wordgame", description="Start, end, or view the word game")
@app_commands.describe(action="What to do")
@app_commands.choices(
    action=[
        app_commands.Choice(name="Start a new game", value="start"),
        app_commands.Choice(name="End the current game", value="end"),
        app_commands.Choice(name="View the current story", value="view"),
    ]
)
async def wordgame_cmd(interaction: discord.Interaction, action: app_commands.Choice[str]):
    gid = str(interaction.guild_id)
    game = await db.get_word_game(gid)

    if action.value == "start":
        if game and game["active"]:
            await interaction.response.send_message(config.MESSAGES["word_game"]["already_active"], ephemeral=True)
            return

        channel_id = await db.get_channel(gid, "wordgame")
        target_channel = bot.get_channel(int(channel_id)) if channel_id else interaction.channel
        if not target_channel:
            await interaction.response.send_message(config.MESSAGES["word_game"]["failed"], ephemeral=True)
            return

        embed = build_word_game_embed("", 0, True)
        msg = await target_channel.send(embed=embed)
        await db.create_word_game(gid, str(target_channel.id), str(msg.id))
        await interaction.response.send_message(config.MESSAGES["word_game"]["started"], ephemeral=True)

    elif action.value == "end":
        if not game or not game["active"]:
            await interaction.response.send_message(config.MESSAGES["word_game"]["no_game_end"], ephemeral=True)
            return
        await db.end_word_game(gid)
        game = await db.get_word_game(gid)
        try:
            ch = bot.get_channel(int(game["channel_id"]))
            m = await ch.fetch_message(int(game["message_id"]))
            await m.edit(embed=build_word_game_embed(game["words"], game["word_count"], False))
        except Exception:
            pass
        reply = config.MESSAGES["word_game"]["ended"].format(user=interaction.user.mention, count=game["word_count"])
        await interaction.response.send_message(reply)

    elif action.value == "view":
        if not game:
            await interaction.response.send_message(config.MESSAGES["word_game"]["no_game"], ephemeral=True)
            return
        embed = build_word_game_embed(game["words"], game["word_count"], game["active"])
        await interaction.response.send_message(embed=embed, ephemeral=True)


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
        app_commands.Choice(name="Daily Spark", value="spark"),
        app_commands.Choice(name="Personality Daily", value="personality"),
    ]
)
async def forcequestion_cmd(interaction: discord.Interaction, type: app_commands.Choice[str]):
    gid = str(interaction.guild_id)
    fns = {"typology": post_typology, "spark": post_spark, "personality": post_personality}
    fn = fns.get(type.value)
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
    used_s = len(await db.get_used_questions(gid, "spark"))
    used_p = len(await db.get_used_questions(gid, "personality"))
    total_t = len(config.TYPOLOGY_QUESTIONS)
    total_s = len(config.SPARK_WYR) + len(config.SPARK_DEBATES) + len(config.SPARK_CHILL)
    total_p = len(config.PERSONALITY_QUESTIONS)

    last_t = await db.get_state(gid, "last_typology_post")
    last_s = await db.get_state(gid, "last_spark_post")
    last_pe = await db.get_state(gid, "last_personality_post")
    last_cd = await db.get_state(gid, "last_chip_drop")
    last_cp = await db.get_state(gid, "last_code_purple")

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
    embed.add_field(name="💬 Spark Qs", value=f"{used_s}/{total_s}", inline=True)
    embed.add_field(name="🧠 Personality Qs", value=f"{used_p}/{total_p}", inline=True)
    embed.add_field(name="📅 Last Typology", value=fmt(last_t), inline=True)
    embed.add_field(name="💫 Last Spark", value=fmt(last_s), inline=True)
    embed.add_field(name="🧠 Last Personality", value=fmt(last_pe), inline=True)
    embed.add_field(name="🥔 Last Chip Drop", value=fmt(last_cd), inline=True)
    embed.add_field(name="💜 Last Code Purple", value=fmt(last_cp), inline=True)
    embed.set_footer(text="CRISPS GC Bot Stats")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="setchannel", description="Set a channel for bot features (admin only)")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(feature="Feature to configure", channel="Channel (defaults to current)")
@app_commands.choices(
    feature=[
        app_commands.Choice(name="Typology Daily", value="typology"),
        app_commands.Choice(name="Daily Spark", value="spark"),
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
    await interaction.response.send_message(f"{feature.name} channel set to {target.mention}", ephemeral=True)


@bot.tree.command(name="viewchannels", description="View current channel settings (admin only)")
@app_commands.default_permissions(administrator=True)
async def viewchannels_cmd(interaction: discord.Interaction):
    gid = str(interaction.guild_id)
    channels = await db.get_all_channels(gid)

    features = {
        "typology": "✨ Typology Daily",
        "spark": "💫 Daily Spark",
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
    now = datetime.now(MANILA_TZ)

    lines = ["**📅 Upcoming Scheduled Posts**", ""]

    for feature, name in [("typology", "Typology Daily"), ("spark", "Daily Spark"), ("personality", "Personality Daily")]:
        override = await db.get_state(gid, f"next_{feature}")
        if override:
            ot = datetime.fromisoformat(override)
            if ot.tzinfo is None:
                ot = ot.replace(tzinfo=timezone.utc)
            ts = int(ot.timestamp())
            lines.append(f"⏰ **{name}** <t:{ts}:R>")
        else:
            custom = await db.get_state(gid, f"schedule_{feature}")
            if custom:
                sh, sm = map(int, custom.split(":"))
            else:
                sched = config.SCHEDULE.get(feature, {})
                sh, sm = sched.get("hour", 0), sched.get("minute", 0)
            next_time = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
            if next_time <= now:
                next_time += timedelta(days=1)
            # Convert to UTC timestamp for Discord
            ts = int(next_time.astimezone(timezone.utc).timestamp())
            lines.append(f"⏰ **{name}** <t:{ts}:R>")

    # Chatter rewards
    sched = config.SCHEDULE.get("chatter_reward", {})
    sh, sm = sched.get("hour", 23), sched.get("minute", 59)
    next_chatter = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
    if next_chatter <= now:
        next_chatter += timedelta(days=1)
    ts = int(next_chatter.astimezone(timezone.utc).timestamp())
    lines.append(f"⏰ **Chatter Rewards** <t:{ts}:R>")

    lines.append(f"💜 **Code Purple Check** every hour")
    lines.append(f"🥔 **Chip Drops** every {config.CHIP_DROP['min_interval']}-{config.CHIP_DROP['max_interval']}m")
    lines.append("")
    lines.append(f"*Current time: {now.strftime('%I:%M %p')} Manila*")

    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@bot.tree.command(name="resettimer", description="Reset timer for scheduled features (admin only)")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(feature="Feature to reset")
@app_commands.choices(
    feature=[
        app_commands.Choice(name="All Features", value="all"),
        app_commands.Choice(name="Chip Drop", value="chipdrop"),
        app_commands.Choice(name="Typology Daily", value="typology"),
        app_commands.Choice(name="Daily Spark", value="spark"),
        app_commands.Choice(name="Personality Daily", value="personality"),
        app_commands.Choice(name="Chatter Rewards", value="chatter"),
    ]
)
async def resettimer_cmd(interaction: discord.Interaction, feature: app_commands.Choice[str]):
    gid = str(interaction.guild_id)
    now = datetime.now(timezone.utc)
    msgs = []

    targets = {
        "chipdrop": ("next_chip_drop", "🥔 chip drop → ~1 minute", 1),
        "typology": ("next_typology", "✨ typology → ~2 minutes", 2),
        "spark": ("next_spark", "💫 spark → ~2 minutes", 2),
        "personality": ("next_personality", "🧠 personality → ~2 minutes", 2),
        "chatter": ("next_chatter", "💬 chatter → ~2 minutes", 2),
    }

    if feature.value == "all":
        for state_key, msg, mins in targets.values():
            await db.set_state(gid, state_key, (now + timedelta(minutes=mins)).isoformat())
            msgs.append(msg)
    elif feature.value in targets:
        state_key, msg, mins = targets[feature.value]
        await db.set_state(gid, state_key, (now + timedelta(minutes=mins)).isoformat())
        msgs.append(msg)

    await interaction.response.send_message(
        f"Timers reset:\n" + "\n".join(msgs) if msgs else "No timers reset",
        ephemeral=True,
    )


@bot.tree.command(name="setschedule", description="Set the time for scheduled posts (admin only)")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(feature="Feature to schedule", hour="Hour (0-23, Manila time)", minute="Minute (0-59)")
@app_commands.choices(
    feature=[
        app_commands.Choice(name="Typology Daily", value="typology"),
        app_commands.Choice(name="Daily Spark", value="spark"),
        app_commands.Choice(name="Personality Daily", value="personality"),
        app_commands.Choice(name="Chatter Rewards", value="chatter"),
    ]
)
async def setschedule_cmd(
    interaction: discord.Interaction,
    feature: app_commands.Choice[str],
    hour: int,
    minute: int,
):
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        await interaction.response.send_message("Invalid time. Hour: 0-23, Minute: 0-59", ephemeral=True)
        return
    gid = str(interaction.guild_id)
    await db.set_state(gid, f"schedule_{feature.value}", f"{hour}:{minute}")
    await interaction.response.send_message(
        f"{feature.name} scheduled for **{hour:02d}:{minute:02d}** Manila time", ephemeral=True
    )


# ======================== EVENTS ========================


@bot.event
async def on_ready():
    if not hasattr(bot, "_initialized"):
        bot._initialized = True
        await db.init()
        schedule_loop.start()
        bot.loop.create_task(chip_drop_cycle())
        synced = await bot.tree.sync()
        print(f"✅ {bot.user} is online! Synced {len(synced)} commands globally.")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return
    gid = str(message.guild.id)
    # Track activity for code purple & chatter rewards
    await db.set_state(gid, "last_message_time", datetime.now(timezone.utc).isoformat())
    await db.increment_chatter(gid, str(message.author.id), message.author.display_name)

    # Word game - check if message is in active word game channel
    game = await db.get_word_game(gid)
    if game and game["active"] and str(message.channel.id) == game["channel_id"]:
        word = message.content.strip()

        # Validate - single word only
        if " " in word or not re.match(r"^[\w''.,!?;:\-]+$", word):
            # Not a valid word, just ignore (don't spam errors for normal chat)
            pass
        elif game["last_contributor_id"] == str(message.author.id):
            # Same person can't go twice
            try:
                await message.delete()
                warn = await message.channel.send(
                    f"{message.author.mention} You can't add two words in a row! Let someone else go.",
                    delete_after=3,
                )
            except Exception:
                pass
        elif word.upper() == "END":
            # End the game
            await db.end_word_game(gid)
            game = await db.get_word_game(gid)
            try:
                await message.delete()
                old_msg = await message.channel.fetch_message(int(game["message_id"]))
                await old_msg.delete()
            except Exception:
                pass
            embed = build_word_game_embed(game["words"], game["word_count"], False)
            end_msg = f"📖 {message.author.mention} ended the story! ({game['word_count']} words total)."
            await message.channel.send(content=end_msg, embed=embed)
        else:
            # Valid word - add it
            await db.add_word(gid, word, str(message.author.id))
            game = await db.get_word_game(gid)

            # Delete user's message
            try:
                await message.delete()
            except Exception:
                pass

            # Delete old bot message and send new one
            try:
                old_msg = await message.channel.fetch_message(int(game["message_id"]))
                await old_msg.delete()
            except Exception:
                pass

            embed = build_word_game_embed(game["words"], game["word_count"], True, message.author)
            new_msg = await message.channel.send(embed=embed)
            # Update stored message ID
            await db.update_word_game_message(gid, str(new_msg.id))

    await bot.process_commands(message)


# ======================== RUN ========================

if __name__ == "__main__":
    if not TOKEN:
        print("❌ DISCORD_TOKEN not set! Copy .env.example to .env and fill in your token.")
    else:
        bot.run(TOKEN)
