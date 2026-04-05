import aiosqlite
from pathlib import Path
from typing import Optional


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    async def init(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            # Check if we need to migrate the schema
            cursor = await db.execute("SELECT sql FROM sqlite_master WHERE name='episodes'")
            row = await cursor.fetchone()

            if row and "book_name" not in row[0]:
                # Migrate: add book columns
                await db.execute("ALTER TABLE episodes RENAME TO episodes_old")
                await self._create_table(db)
                # Copy data, filling missing columns with defaults
                cols = await db.execute("PRAGMA table_info(episodes_old)")
                old_cols = [r[1] for r in await cols.fetchall()]
                shared = [c for c in old_cols if c in (
                    "id", "bookstack_type", "bookstack_id", "title", "description",
                    "audio_filename", "duration_seconds", "file_size", "voice",
                    "mode", "status", "error_message", "created_at",
                )]
                col_list = ", ".join(shared)
                await db.execute(
                    f"INSERT INTO episodes ({col_list}) SELECT {col_list} FROM episodes_old"
                )
                await db.execute("DROP TABLE episodes_old")
            elif not row:
                await self._create_table(db)

            await db.commit()

    async def _create_table(self, db):
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
                mode TEXT DEFAULT 'narration',
                book_id INTEGER,
                book_name TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(bookstack_type, bookstack_id, mode, voice)
            )
        """)

    async def create_episode(
        self, bookstack_type: str, bookstack_id: int, mode: str, voice: str
    ) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "INSERT INTO episodes (bookstack_type, bookstack_id, mode, voice, status) "
                "VALUES (?, ?, ?, ?, 'pending')",
                (bookstack_type, bookstack_id, mode, voice),
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
        self, bookstack_type: str, bookstack_id: int, mode: str, voice: str
    ) -> Optional[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM episodes WHERE bookstack_type = ? AND bookstack_id = ? "
                "AND mode = ? AND voice = ?",
                (bookstack_type, bookstack_id, mode, voice),
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
