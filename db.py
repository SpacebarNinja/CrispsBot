"""
Database layer - Turso (cloud) or SQLite (local fallback)
Uses libsql for Turso, aiosqlite for local development
"""

import os
import asyncio
from datetime import datetime, timezone
from contextlib import asynccontextmanager

# Check for Turso configuration
TURSO_URL = os.environ.get("TURSO_DATABASE_URL")
TURSO_TOKEN = os.environ.get("TURSO_AUTH_TOKEN")
USE_TURSO = bool(TURSO_URL and TURSO_TOKEN)

if USE_TURSO:
    import libsql_experimental as libsql
    print(f"[DB] Using Turso cloud database")
else:
    import aiosqlite
    DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_data.db")
    print(f"[DB] Using local SQLite: {DB_PATH}")


# ==================== CONNECTION WRAPPER ====================

class TursoConnection:
    """Wrapper to make libsql work like aiosqlite"""
    def __init__(self, conn):
        self._conn = conn
        self._cursor = None
    
    async def execute(self, sql, params=None):
        def _exec():
            if params:
                return self._conn.execute(sql, params)
            return self._conn.execute(sql)
        result = await asyncio.to_thread(_exec)
        self._cursor = result
        return self
    
    async def executescript(self, sql):
        def _exec():
            return self._conn.executescript(sql)
        await asyncio.to_thread(_exec)
        return self
    
    async def fetchone(self):
        if self._cursor is None:
            return None
        def _fetch():
            return self._cursor.fetchone()
        return await asyncio.to_thread(_fetch)
    
    async def fetchall(self):
        if self._cursor is None:
            return []
        def _fetch():
            return self._cursor.fetchall()
        return await asyncio.to_thread(_fetch)
    
    async def commit(self):
        def _commit():
            self._conn.commit()
        await asyncio.to_thread(_commit)
    
    async def close(self):
        pass  # Turso connections don't need explicit close


@asynccontextmanager
async def get_connection():
    """Get a database connection - works with both Turso and local SQLite"""
    if USE_TURSO:
        def _connect():
            return libsql.connect(TURSO_URL, auth_token=TURSO_TOKEN)
        conn = await asyncio.to_thread(_connect)
        wrapper = TursoConnection(conn)
        try:
            yield wrapper
        finally:
            await wrapper.close()
    else:
        async with aiosqlite.connect(DB_PATH) as conn:
            yield conn


# ==================== INIT ====================

async def init():
    """Create all tables if they don't exist"""
    async with get_connection() as conn:
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

            CREATE TABLE IF NOT EXISTS daily_activity (
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                username TEXT DEFAULT '',
                message_points INTEGER DEFAULT 0,
                vc_minutes INTEGER DEFAULT 0,
                date TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id, date)
            );

            CREATE TABLE IF NOT EXISTS vc_sessions (
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                username TEXT DEFAULT '',
                join_time TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS active_chip_drop (
                guild_id TEXT PRIMARY KEY,
                channel_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                amount INTEGER NOT NULL,
                drop_type TEXT NOT NULL,
                answer TEXT DEFAULT '',
                created_at TEXT NOT NULL
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
        await conn.commit()
        
        # Migrations (safe to run multiple times)
        migrations = [
            "UPDATE bot_state SET key = 'channel_casual' WHERE key = 'channel_spark'",
            "UPDATE question_usage SET question_type = 'casual' WHERE question_type = 'spark'",
            "UPDATE bot_state SET key = 'channel_warm' WHERE key = 'channel_casual'",
            "UPDATE bot_state SET key = 'ping_role_warm' WHERE key = 'ping_role_casual'",
            "UPDATE bot_state SET key = 'role_picker_message_warm' WHERE key = 'role_picker_message_casual'",
            "UPDATE bot_state SET key = 'channel_chill' WHERE key = 'channel_personality'",
            "UPDATE bot_state SET key = 'ping_role_chill' WHERE key = 'ping_role_personality'",
            "UPDATE bot_state SET key = 'role_picker_message_chill' WHERE key = 'role_picker_message_personality'",
        ]
        for sql in migrations:
            await conn.execute(sql)
        await conn.commit()


# ==================== USERS / CHIPS ====================

async def ensure_user(guild_id: str, user_id: str, username: str):
    async with get_connection() as conn:
        await conn.execute(
            """INSERT INTO users (guild_id, user_id, username, chips, created_at)
               VALUES (?, ?, ?, 0, ?)
               ON CONFLICT(guild_id, user_id) DO UPDATE SET username = excluded.username""",
            (guild_id, user_id, username, datetime.now(timezone.utc).isoformat())
        )
        await conn.commit()


async def add_chips(guild_id: str, user_id: str, username: str, amount: int):
    await ensure_user(guild_id, user_id, username)
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE users SET chips = chips + ? WHERE guild_id = ? AND user_id = ?",
            (amount, guild_id, user_id)
        )
        await conn.commit()


async def set_chips(guild_id: str, user_id: str, username: str, amount: int):
    await ensure_user(guild_id, user_id, username)
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE users SET chips = ? WHERE guild_id = ? AND user_id = ?",
            (amount, guild_id, user_id)
        )
        await conn.commit()


async def get_balance(guild_id: str, user_id: str) -> int:
    async with get_connection() as conn:
        cursor = await conn.execute(
            "SELECT chips FROM users WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def get_rank(guild_id: str, user_id: str) -> int | None:
    async with get_connection() as conn:
        cursor = await conn.execute(
            """SELECT COUNT(*) + 1 FROM users
               WHERE guild_id = ? AND chips > (
                   SELECT COALESCE(chips, 0) FROM users WHERE guild_id = ? AND user_id = ?
               )""",
            (guild_id, guild_id, user_id)
        )
        row = await cursor.fetchone()
        cursor2 = await conn.execute(
            "SELECT 1 FROM users WHERE guild_id = ? AND user_id = ? AND chips > 0",
            (guild_id, user_id)
        )
        exists = await cursor2.fetchone()
        return row[0] if (row and exists) else None


async def get_leaderboard(guild_id: str, limit: int = 10) -> list[dict]:
    async with get_connection() as conn:
        cursor = await conn.execute(
            "SELECT user_id, username, chips FROM users WHERE guild_id = ? ORDER BY chips DESC LIMIT ?",
            (guild_id, limit)
        )
        rows = await cursor.fetchall()
        return [{"user_id": r[0], "username": r[1], "chips": r[2]} for r in rows]


async def get_total_users(guild_id: str) -> int:
    async with get_connection() as conn:
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM users WHERE guild_id = ?", (guild_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


# ==================== DAILY CHATTER ====================

async def increment_chatter(guild_id: str, user_id: str, username: str):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    async with get_connection() as conn:
        await conn.execute(
            """INSERT INTO daily_chatter (guild_id, user_id, username, message_count, date)
               VALUES (?, ?, ?, 1, ?)
               ON CONFLICT(guild_id, user_id, date) DO UPDATE SET
               message_count = message_count + 1, username = excluded.username""",
            (guild_id, user_id, username, today)
        )
        await conn.commit()


async def get_top_chatters(guild_id: str, date: str) -> list[dict]:
    async with get_connection() as conn:
        cursor = await conn.execute(
            """SELECT user_id, username, message_count FROM daily_chatter
               WHERE guild_id = ? AND date = ?
               ORDER BY message_count DESC LIMIT 3""",
            (guild_id, date)
        )
        rows = await cursor.fetchall()
        return [{"user_id": r[0], "username": r[1], "message_count": r[2]} for r in rows]


async def clear_daily_chatter(guild_id: str, date: str):
    async with get_connection() as conn:
        await conn.execute(
            "DELETE FROM daily_chatter WHERE guild_id = ? AND date = ?",
            (guild_id, date)
        )
        await conn.commit()


# ==================== QUESTION USAGE ====================

async def get_used_questions(guild_id: str, question_type: str) -> list[int]:
    async with get_connection() as conn:
        cursor = await conn.execute(
            "SELECT question_index FROM question_usage WHERE guild_id = ? AND question_type = ?",
            (guild_id, question_type)
        )
        rows = await cursor.fetchall()
        return [r[0] for r in rows]


async def mark_question_used(guild_id: str, question_type: str, index: int):
    async with get_connection() as conn:
        await conn.execute(
            "INSERT INTO question_usage (guild_id, question_type, question_index, used_at) VALUES (?, ?, ?, ?)",
            (guild_id, question_type, index, datetime.now(timezone.utc).isoformat())
        )
        await conn.commit()


async def reset_questions(guild_id: str, question_type: str):
    async with get_connection() as conn:
        await conn.execute(
            "DELETE FROM question_usage WHERE guild_id = ? AND question_type = ?",
            (guild_id, question_type)
        )
        await conn.commit()


# ==================== BOT STATE ====================

async def get_state(guild_id: str, key: str) -> str | None:
    async with get_connection() as conn:
        cursor = await conn.execute(
            "SELECT value FROM bot_state WHERE guild_id = ? AND key = ?",
            (guild_id, key)
        )
        row = await cursor.fetchone()
        return row[0] if row else None


async def set_state(guild_id: str, key: str, value: str):
    async with get_connection() as conn:
        await conn.execute(
            """INSERT INTO bot_state (guild_id, key, value) VALUES (?, ?, ?)
               ON CONFLICT(guild_id, key) DO UPDATE SET value = excluded.value""",
            (guild_id, key, value)
        )
        await conn.commit()


async def delete_state(guild_id: str, key: str):
    async with get_connection() as conn:
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
    features = ["warm", "chill", "typology", "codepurple", "chipdrop", "activity_rewards", "wordgame"]
    result = {}
    for f in features:
        result[f] = await get_channel(guild_id, f)
    return result


# ==================== BLACKLIST ====================

async def get_blacklisted_channels(guild_id: str) -> list[str]:
    blacklist_str = await get_state(guild_id, "chipdrop_blacklist")
    if not blacklist_str:
        return []
    return [ch for ch in blacklist_str.split(",") if ch]


async def add_blacklisted_channel(guild_id: str, channel_id: str) -> bool:
    blacklist = await get_blacklisted_channels(guild_id)
    if channel_id in blacklist:
        return False
    blacklist.append(channel_id)
    await set_state(guild_id, "chipdrop_blacklist", ",".join(blacklist))
    return True


async def remove_blacklisted_channel(guild_id: str, channel_id: str) -> bool:
    blacklist = await get_blacklisted_channels(guild_id)
    if channel_id not in blacklist:
        return False
    blacklist.remove(channel_id)
    await set_state(guild_id, "chipdrop_blacklist", ",".join(blacklist))
    return True


async def is_channel_blacklisted(guild_id: str, channel_id: str) -> bool:
    blacklist = await get_blacklisted_channels(guild_id)
    return channel_id in blacklist


# ==================== WORD GAME ====================

async def get_word_game(guild_id: str) -> dict | None:
    async with get_connection() as conn:
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
    async with get_connection() as conn:
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
    async with get_connection() as conn:
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
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE word_games SET active = 0 WHERE guild_id = ?",
            (guild_id,)
        )
        await conn.commit()


async def update_word_game_message(guild_id: str, message_id: str):
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE word_games SET message_id = ? WHERE guild_id = ? AND active = 1",
            (message_id, guild_id)
        )
        await conn.commit()


# ==================== DAILY ACTIVITY ====================

async def increment_activity_message(guild_id: str, user_id: str, username: str):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    async with get_connection() as conn:
        await conn.execute(
            """INSERT INTO daily_activity (guild_id, user_id, username, message_points, vc_minutes, date)
               VALUES (?, ?, ?, 1, 0, ?)
               ON CONFLICT(guild_id, user_id, date) DO UPDATE SET
               message_points = message_points + 1, username = excluded.username""",
            (guild_id, user_id, username, today)
        )
        await conn.commit()


async def add_vc_minutes(guild_id: str, user_id: str, username: str, minutes: int):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    async with get_connection() as conn:
        await conn.execute(
            """INSERT INTO daily_activity (guild_id, user_id, username, message_points, vc_minutes, date)
               VALUES (?, ?, ?, 0, ?, ?)
               ON CONFLICT(guild_id, user_id, date) DO UPDATE SET
               vc_minutes = vc_minutes + ?, username = excluded.username""",
            (guild_id, user_id, username, minutes, today, minutes)
        )
        await conn.commit()


async def get_top_activity(guild_id: str, date: str) -> list[dict]:
    async with get_connection() as conn:
        cursor = await conn.execute(
            """SELECT user_id, username, message_points, vc_minutes, (message_points + vc_minutes) as total
               FROM daily_activity
               WHERE guild_id = ? AND date = ?
               ORDER BY total DESC LIMIT 3""",
            (guild_id, date)
        )
        rows = await cursor.fetchall()
        return [{"user_id": r[0], "username": r[1], "message_points": r[2], "vc_minutes": r[3], "total": r[4]} for r in rows]


async def clear_daily_activity(guild_id: str, date: str):
    async with get_connection() as conn:
        await conn.execute(
            "DELETE FROM daily_activity WHERE guild_id = ? AND date = ?",
            (guild_id, date)
        )
        await conn.commit()


# ==================== VC SESSIONS ====================

async def start_vc_session(guild_id: str, user_id: str, username: str):
    async with get_connection() as conn:
        await conn.execute(
            """INSERT INTO vc_sessions (guild_id, user_id, username, join_time)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(guild_id, user_id) DO UPDATE SET
               join_time = excluded.join_time, username = excluded.username""",
            (guild_id, user_id, username, datetime.now(timezone.utc).isoformat())
        )
        await conn.commit()


async def end_vc_session(guild_id: str, user_id: str) -> int:
    async with get_connection() as conn:
        cursor = await conn.execute(
            "SELECT username, join_time FROM vc_sessions WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        )
        row = await cursor.fetchone()
        if not row:
            return 0
        
        username, join_time = row[0], row[1]
        join_dt = datetime.fromisoformat(join_time)
        if join_dt.tzinfo is None:
            join_dt = join_dt.replace(tzinfo=timezone.utc)
        
        minutes = int((datetime.now(timezone.utc) - join_dt).total_seconds() / 60)
        
        await conn.execute(
            "DELETE FROM vc_sessions WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        )
        await conn.commit()
        
        if minutes > 0:
            await add_vc_minutes(guild_id, user_id, username, minutes)
        
        return minutes


async def get_all_vc_sessions(guild_id: str) -> list[dict]:
    async with get_connection() as conn:
        cursor = await conn.execute(
            "SELECT user_id, username, join_time FROM vc_sessions WHERE guild_id = ?",
            (guild_id,)
        )
        rows = await cursor.fetchall()
        return [{"user_id": r[0], "username": r[1], "join_time": r[2]} for r in rows]


# ==================== ACTIVE CHIP DROP ====================

async def create_chip_drop(guild_id: str, channel_id: str, message_id: str, amount: int, drop_type: str, answer: str = ""):
    async with get_connection() as conn:
        await conn.execute(
            """INSERT INTO active_chip_drop (guild_id, channel_id, message_id, amount, drop_type, answer, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(guild_id) DO UPDATE SET
               channel_id = excluded.channel_id, message_id = excluded.message_id,
               amount = excluded.amount, drop_type = excluded.drop_type,
               answer = excluded.answer, created_at = excluded.created_at""",
            (guild_id, channel_id, message_id, amount, drop_type, answer, datetime.now(timezone.utc).isoformat())
        )
        await conn.commit()


async def get_chip_drop(guild_id: str) -> dict | None:
    async with get_connection() as conn:
        cursor = await conn.execute(
            "SELECT channel_id, message_id, amount, drop_type, answer, created_at FROM active_chip_drop WHERE guild_id = ?",
            (guild_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return {
            "channel_id": row[0],
            "message_id": row[1],
            "amount": row[2],
            "drop_type": row[3],
            "answer": row[4],
            "created_at": row[5],
        }


async def delete_chip_drop(guild_id: str):
    async with get_connection() as conn:
        await conn.execute(
            "DELETE FROM active_chip_drop WHERE guild_id = ?",
            (guild_id,)
        )
        await conn.commit()
