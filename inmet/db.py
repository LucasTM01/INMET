"""Camada SQLite: schema, escrita por ano e tabela de estações."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pandas as pd

from . import config

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS weather_monthly (
    year          INTEGER NOT NULL,
    month         INTEGER NOT NULL,
    region        TEXT,
    state         TEXT,
    station       TEXT NOT NULL,
    city          TEXT,
    rainfall_mm   REAL,
    temperature_c REAL,
    PRIMARY KEY (station, city, year, month)
);

CREATE INDEX IF NOT EXISTS ix_weather_year  ON weather_monthly (year);
CREATE INDEX IF NOT EXISTS ix_weather_state ON weather_monthly (state);

CREATE TABLE IF NOT EXISTS weather_daily (
    year          INTEGER NOT NULL,
    month         INTEGER NOT NULL,
    day           INTEGER NOT NULL,
    date          TEXT,
    region        TEXT,
    state         TEXT,
    station       TEXT NOT NULL,
    city          TEXT,
    rainfall_mm   REAL,
    temperature_c REAL,
    PRIMARY KEY (station, city, year, month, day)
);

CREATE INDEX IF NOT EXISTS ix_daily_year  ON weather_daily (year);
CREATE INDEX IF NOT EXISTS ix_daily_date  ON weather_daily (date);
CREATE INDEX IF NOT EXISTS ix_daily_state ON weather_daily (state);

CREATE TABLE IF NOT EXISTS stations (
    station    TEXT PRIMARY KEY,
    region     TEXT,
    state      TEXT,
    city       TEXT,
    latitude   REAL,
    longitude  REAL,
    altitude   REAL,
    updated_at TEXT
);
"""


def get_conn(db_path=config.DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def year_exists(conn: sqlite3.Connection, year: int) -> bool:
    cur = conn.execute("SELECT 1 FROM weather_monthly WHERE year = ? LIMIT 1;", (year,))
    return cur.fetchone() is not None


def delete_year(conn: sqlite3.Connection, year: int) -> tuple[int, int]:
    """Apaga o ano das duas tabelas. Retorna (linhas_mensal, linhas_diario)."""
    m = conn.execute("DELETE FROM weather_monthly WHERE year = ?;", (year,)).rowcount
    d = conn.execute("DELETE FROM weather_daily WHERE year = ?;", (year,)).rowcount
    return m, d


def upsert_monthly(conn: sqlite3.Connection, df: pd.DataFrame) -> int:
    """Insere/substitui linhas mensais. Espera as 8 colunas do schema."""
    cols = ["year", "month", "region", "state", "station", "city",
            "rainfall_mm", "temperature_c"]
    rows = [tuple(None if pd.isna(v) else v for v in r)
            for r in df[cols].itertuples(index=False, name=None)]
    conn.executemany(
        "INSERT OR REPLACE INTO weather_monthly "
        "(year, month, region, state, station, city, rainfall_mm, temperature_c) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?);",
        rows,
    )
    return len(rows)


def upsert_daily(conn: sqlite3.Connection, df: pd.DataFrame) -> int:
    """Insere/substitui linhas diárias. Espera as 10 colunas do schema."""
    cols = ["year", "month", "day", "date", "region", "state", "station", "city",
            "rainfall_mm", "temperature_c"]
    rows = [tuple(None if pd.isna(v) else v for v in r)
            for r in df[cols].itertuples(index=False, name=None)]
    conn.executemany(
        "INSERT OR REPLACE INTO weather_daily "
        "(year, month, day, date, region, state, station, city, rainfall_mm, temperature_c) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
        rows,
    )
    return len(rows)


def upsert_stations(conn: sqlite3.Connection, records: list[dict]) -> int:
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        (r["station"], r.get("region"), r.get("state"), r.get("city"),
         r.get("latitude"), r.get("longitude"), r.get("altitude"), now)
        for r in records if r and r.get("station")
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO stations "
        "(station, region, state, city, latitude, longitude, altitude, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?);",
        rows,
    )
    return len(rows)
