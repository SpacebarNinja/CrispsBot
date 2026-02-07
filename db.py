"""
Database layer - SQLite via aiosqlite
All bot data stored locally in bot_data.db
"""

import aiosqlite
import os
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_data.db")


# ==================== INIT ====================

async def init():
    """Create all tables if they don't exist"""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                username TEXT DEFAULT '',
                chips INTEGER DEFAULT 0,
                created_at TEXT DEFAULT '',
                PRIMARY KEY (guild_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS daily_chatter (
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                username TEXT DEFAULT '',
                message_count INTEGER DEFAULT 0,
                date TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id, date)
            );

            CREATE TABLE IF NOT EXISTS question_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT NOT NULL,
                question_type TEXT NOT NULL,
                question_index INTEGER NOT NULL,
                used_at TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS bot_state (
                guild_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT DEFAULT '',
                PRIMARY KEY (guild_id, key)
            );

            CREATE TABLE IF NOT EXISTS word_games (
                guild_id TEXT PRIMARY KEY,
                channel_id TEXT DEFAULT '',
                message_id TEXT DEFAULT '',
                words TEXT DEFAULT '',
                last_contributor_id TEXT DEFAULT '',
                word_count INTEGER DEFAULT 0,
                active INTEGER DEFAULT 0
            );
        """)
        # Migration: rename spark → casual
        await conn.execute(
            "UPDATE bot_state SET key = 'channel_casual' WHERE key = 'channel_spark'"
        )
        await conn.execute(
            "UPDATE question_usage SET question_type = 'casual' WHERE question_type = 'spark'"
        )
        await conn.commit()


# ==================== USERS / CHIPS ====================

async def ensure_user(guild_id: str, user_id: str, username: str):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """INSERT INTO users (guild_id, user_id, username, chips, created_at)
               VALUES (?, ?, ?, 0, ?)
               ON CONFLICT(guild_id, user_id) DO UPDATE SET username = excluded.username""",
            (guild_id, user_id, username, datetime.now(timezone.utc).isoformat())
        )
        await conn.commit()


async def add_chips(guild_id: str, user_id: str, username: str, amount: int):
    await ensure_user(guild_id, user_id, username)
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE users SET chips = chips + ? WHERE guild_id = ? AND user_id = ?",
            (amount, guild_id, user_id)
        )
        await conn.commit()


async def set_chips(guild_id: str, user_id: str, username: str, amount: int):
    await ensure_user(guild_id, user_id, username)
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE users SET chips = ? WHERE guild_id = ? AND user_id = ?",
            (amount, guild_id, user_id)
        )
        await conn.commit()


async def get_balance(guild_id: str, user_id: str) -> int:
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT chips FROM users WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def get_rank(guild_id: str, user_id: str) -> int | None:
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """SELECT COUNT(*) + 1 FROM users
               WHERE guild_id = ? AND chips > (
                   SELECT COALESCE(chips, 0) FROM users WHERE guild_id = ? AND user_id = ?
               )""",
            (guild_id, guild_id, user_id)
        )
        row = await cursor.fetchone()
        # Check if user exists
        cursor2 = await conn.execute(
            "SELECT 1 FROM users WHERE guild_id = ? AND user_id = ? AND chips > 0",
            (guild_id, user_id)
        )
        exists = await cursor2.fetchone()
        return row[0] if (row and exists) else None


async def get_leaderboard(guild_id: str, limit: int = 10) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT user_id, username, chips FROM users WHERE guild_id = ? AND chips > 0 ORDER BY chips DESC LIMIT ?",
            (guild_id, limit)
        )
        rows = await cursor.fetchall()
        return [{"user_id": r[0], "username": r[1], "chips": r[2]} for r in rows]


async def get_total_users(guild_id: str) -> int:
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM users WHERE guild_id = ?", (guild_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


# ==================== DAILY CHATTER ====================

async def increment_chatter(guild_id: str, user_id: str, username: str):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """INSERT INTO daily_chatter (guild_id, user_id, username, message_count, date)
               VALUES (?, ?, ?, 1, ?)
               ON CONFLICT(guild_id, user_id, date) DO UPDATE SET
               message_count = message_count + 1, username = excluded.username""",
            (guild_id, user_id, username, today)
        )
        await conn.commit()


async def get_top_chatters(guild_id: str, date: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """SELECT user_id, username, message_count FROM daily_chatter
               WHERE guild_id = ? AND date = ?
               ORDER BY message_count DESC LIMIT 2""",
            (guild_id, date)
        )
        rows = await cursor.fetchall()
        return [{"user_id": r[0], "username": r[1], "message_count": r[2]} for r in rows]


async def clear_daily_chatter(guild_id: str, date: str):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "DELETE FROM daily_chatter WHERE guild_id = ? AND date = ?",
            (guild_id, date)
        )
        await conn.commit()


# ==================== QUESTION USAGE ====================

async def get_used_questions(guild_id: str, question_type: str) -> list[int]:
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT question_index FROM question_usage WHERE guild_id = ? AND question_type = ?",
            (guild_id, question_type)
        )
        rows = await cursor.fetchall()
        return [r[0] for r in rows]


async def mark_question_used(guild_id: str, question_type: str, index: int):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO question_usage (guild_id, question_type, question_index, used_at) VALUES (?, ?, ?, ?)",
            (guild_id, question_type, index, datetime.now(timezone.utc).isoformat())
        )
        await conn.commit()


async def reset_questions(guild_id: str, question_type: str):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "DELETE FROM question_usage WHERE guild_id = ? AND question_type = ?",
            (guild_id, question_type)
        )
        await conn.commit()


# ==================== BOT STATE ====================

async def get_state(guild_id: str, key: str) -> str | None:
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT value FROM bot_state WHERE guild_id = ? AND key = ?",
            (guild_id, key)
        )
        row = await cursor.fetchone()
        return row[0] if row else None


async def set_state(guild_id: str, key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """INSERT INTO bot_state (guild_id, key, value) VALUES (?, ?, ?)
               ON CONFLICT(guild_id, key) DO UPDATE SET value = excluded.value""",
            (guild_id, key, value)
        )
        await conn.commit()


async def delete_state(guild_id: str, key: str):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "DELETE FROM bot_state WHERE guild_id = ? AND key = ?",
            (guild_id, key)
        )
        await conn.commit()


# ==================== CHANNELS ====================

async def get_channel(guild_id: str, feature: str) -> str | None:
    return await get_state(guild_id, f"channel_{feature}")


async def set_channel(guild_id: str, feature: str, channel_id: str):
    await set_state(guild_id, f"channel_{feature}", channel_id)


async def get_all_channels(guild_id: str) -> dict:
    features = ["typology", "casual", "personality", "codepurple", "chipdrop", "wordgame"]
    result = {}
    for f in features:
        result[f] = await get_channel(guild_id, f)
    return result


# ==================== WORD GAME ====================

async def get_word_game(guild_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT channel_id, message_id, words, last_contributor_id, word_count, active FROM word_games WHERE guild_id = ?",
            (guild_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return {
            "channel_id": row[0],
            "message_id": row[1],
            "words": row[2],
            "last_contributor_id": row[3],
            "word_count": row[4],
            "active": bool(row[5]),
        }


async def create_word_game(guild_id: str, channel_id: str, message_id: str):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """INSERT INTO word_games (guild_id, channel_id, message_id, words, last_contributor_id, word_count, active)
               VALUES (?, ?, ?, '', '', 0, 1)
               ON CONFLICT(guild_id) DO UPDATE SET
               channel_id = excluded.channel_id, message_id = excluded.message_id,
               words = '', last_contributor_id = '', word_count = 0, active = 1""",
            (guild_id, channel_id, message_id)
        )
        await conn.commit()


async def add_word(guild_id: str, word: str, contributor_id: str):
    async with aiosqlite.connect(DB_PATH) as conn:
        game = await get_word_game(guild_id)
        if not game:
            return
        new_words = f"{game['words']} {word}".strip() if game['words'] else word
        await conn.execute(
            """UPDATE word_games SET words = ?, last_contributor_id = ?, word_count = word_count + 1
               WHERE guild_id = ? AND active = 1""",
            (new_words, contributor_id, guild_id)
        )
        await conn.commit()


async def end_word_game(guild_id: str):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE word_games SET active = 0 WHERE guild_id = ?",
            (guild_id,)
        )
        await conn.commit()


async def update_word_game_message(guild_id: str, message_id: str):
    """Update the tracked message ID for the word game embed."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE word_games SET message_id = ? WHERE guild_id = ? AND active = 1",
            (message_id, guild_id)
        )
        await conn.commit()
