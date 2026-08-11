from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Iterable

from .models import Draw


SCHEMA = """
CREATE TABLE IF NOT EXISTS draws (
    round INTEGER PRIMARY KEY,
    draw_date TEXT,
    n1 INTEGER NOT NULL,
    n2 INTEGER NOT NULL,
    n3 INTEGER NOT NULL,
    n4 INTEGER NOT NULL,
    n5 INTEGER NOT NULL,
    n6 INTEGER NOT NULL,
    bonus INTEGER NOT NULL,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class DrawRepository:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    def upsert(self, draw: Draw, source: str) -> None:
        self.upsert_many([draw], source=source)

    def upsert_many(self, draws: Iterable[Draw], source: str) -> None:
        rows = [
            (
                draw.round,
                draw.draw_date.isoformat() if draw.draw_date else None,
                *draw.numbers,
                draw.bonus,
                source,
            )
            for draw in draws
        ]
        if not rows:
            return

        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO draws (
                    round, draw_date, n1, n2, n3, n4, n5, n6, bonus, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(round) DO UPDATE SET
                    draw_date=excluded.draw_date,
                    n1=excluded.n1,
                    n2=excluded.n2,
                    n3=excluded.n3,
                    n4=excluded.n4,
                    n5=excluded.n5,
                    n6=excluded.n6,
                    bonus=excluded.bonus,
                    source=excluded.source,
                    fetched_at=CURRENT_TIMESTAMP
                """,
                rows,
            )

    def list_draws(self) -> list[Draw]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT round, draw_date, n1, n2, n3, n4, n5, n6, bonus
                FROM draws
                ORDER BY round ASC
                """
            ).fetchall()

        return [
            Draw(
                round=int(row["round"]),
                draw_date=date.fromisoformat(row["draw_date"]) if row["draw_date"] else None,
                numbers=tuple(int(row[f"n{i}"]) for i in range(1, 7)),  # type: ignore[arg-type]
                bonus=int(row["bonus"]),
            )
            for row in rows
        ]

    def max_round(self) -> int | None:
        with self._connect() as connection:
            row = connection.execute("SELECT MAX(round) AS max_round FROM draws").fetchone()
        value = row["max_round"] if row else None
        return int(value) if value is not None else None

    def count(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM draws").fetchone()
        return int(row["count"])
