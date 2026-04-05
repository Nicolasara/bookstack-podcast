import aiosqlite
from pathlib import Path
from typing import Optional


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    async def init(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bookstack_type TEXT NOT NULL,
                    bookstack_id INTEGER NOT NULL,
                    title TEXT DEFAULT '',
                    description TEXT DEFAULT '',
                    audio_filename TEXT,
                    duration_seconds REAL,
                    file_size INTEGER,
                    voice TEXT DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(bookstack_type, bookstack_id)
                )
            """)
            # Migration: add mode column if missing
            try:
                await db.execute(
                    "ALTER TABLE episodes ADD COLUMN mode TEXT DEFAULT 'narration'"
                )
            except Exception:
                pass  # column already exists
            await db.commit()

    async def create_episode(self, bookstack_type: str, bookstack_id: int) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "INSERT INTO episodes (bookstack_type, bookstack_id, status) VALUES (?, ?, 'pending')",
                (bookstack_type, bookstack_id),
            )
            await db.commit()
            return cursor.lastrowid

    async def get_episodes(self, status: Optional[str] = None) -> list:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if status:
                cursor = await db.execute(
                    "SELECT * FROM episodes WHERE status = ? ORDER BY created_at DESC",
                    (status,),
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM episodes ORDER BY created_at DESC"
                )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_episode(self, episode_id: int) -> Optional[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM episodes WHERE id = ?", (episode_id,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_episode_by_source(
        self, bookstack_type: str, bookstack_id: int
    ) -> Optional[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM episodes WHERE bookstack_type = ? AND bookstack_id = ?",
                (bookstack_type, bookstack_id),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def update_episode(self, episode_id: int, data: dict):
        async with aiosqlite.connect(self.db_path) as db:
            sets = ", ".join(f"{k} = ?" for k in data.keys())
            values = list(data.values()) + [episode_id]
            await db.execute(f"UPDATE episodes SET {sets} WHERE id = ?", values)
            await db.commit()

    async def update_status(self, episode_id: int, status: str, error: str = None):
        data = {"status": status}
        if error:
            data["error_message"] = error
        await self.update_episode(episode_id, data)

    async def delete_episode(self, episode_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM episodes WHERE id = ?", (episode_id,))
            await db.commit()
