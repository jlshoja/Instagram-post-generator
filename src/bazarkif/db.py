import sqlite3
from pathlib import Path

from .config import Config

SCHEMA_SQL = Path(__file__).resolve().parent.parent.parent / "docs" / "04-database-schema.sql"


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._lock = __import__("threading").RLock()
        self.migrate()

    def migrate(self) -> None:
        sql = SCHEMA_SQL.read_text(encoding="utf-8")
        with self._lock:
            self._conn.executescript(sql)
            self._conn.commit()

    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(query, params)
            self._conn.commit()
            return cur

    def executemany(self, query: str, seq: list) -> None:
        with self._lock:
            self._conn.executemany(query, seq)
            self._conn.commit()

    def query(self, query: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(query, params).fetchall()

    def scalar(self, query: str, params: tuple = ()):
        row = self.query(query, params)
        return row[0][0] if row else None

    def close(self) -> None:
        self._conn.close()

    @classmethod
    def connect(cls, config: Config) -> "Database":
        return cls(config.db_path)