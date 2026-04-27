from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from src.config import PROJECT_ROOT


DB_PATH = PROJECT_ROOT / "data" / "climate.sqlite3"

DEFAULT_SETTINGS: dict[str, Any] = {
    "poll_interval_seconds": 5,
    "automations_enabled": True,
    "control_enabled": False,
    "command_cooldown_seconds": 300,
    "purifier_pm25_threshold": 35,
    "humidifier_humidity_high_threshold": 65,
    "humidifier_humidity_low_threshold": 40,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect(db_path: Path = DB_PATH) -> Iterator[sqlite3.Connection]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db() -> None:
    with connect() as db:
        db.executescript(
            """
            create table if not exists measurements (
                id integer primary key autoincrement,
                device text not null,
                metric text not null,
                value real not null,
                unit text,
                measured_at text not null
            );

            create index if not exists idx_measurements_metric_time
                on measurements(device, metric, measured_at);

            create table if not exists events (
                id integer primary key autoincrement,
                device text not null,
                severity text not null,
                message text not null,
                created_at text not null
            );

            create table if not exists commands (
                id integer primary key autoincrement,
                device text not null,
                command text not null,
                payload text not null,
                status text not null,
                created_at text not null
            );

            create table if not exists settings (
                key text primary key,
                value text not null
            );
            """
        )
        for key, value in DEFAULT_SETTINGS.items():
            db.execute(
                "insert or ignore into settings(key, value) values (?, ?)",
                (key, json.dumps(value)),
            )


def get_settings() -> dict[str, Any]:
    with connect() as db:
        rows = db.execute("select key, value from settings").fetchall()
    values = DEFAULT_SETTINGS.copy()
    values.update({row["key"]: json.loads(row["value"]) for row in rows})
    return values


def update_settings(changes: dict[str, Any]) -> dict[str, Any]:
    allowed = set(DEFAULT_SETTINGS)
    unknown = set(changes) - allowed
    if unknown:
        raise ValueError(f"Unknown settings: {', '.join(sorted(unknown))}")

    with connect() as db:
        for key, value in changes.items():
            db.execute(
                """
                insert into settings(key, value) values (?, ?)
                on conflict(key) do update set value = excluded.value
                """,
                (key, json.dumps(value)),
            )
    return get_settings()


def insert_measurements(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with connect() as db:
        db.executemany(
            """
            insert into measurements(device, metric, value, unit, measured_at)
            values (:device, :metric, :value, :unit, :measured_at)
            """,
            rows,
        )


def insert_event(device: str, severity: str, message: str) -> None:
    with connect() as db:
        db.execute(
            "insert into events(device, severity, message, created_at) values (?, ?, ?, ?)",
            (device, severity, message, utc_now()),
        )


def insert_command(device: str, command: str, payload: dict[str, Any], status: str) -> None:
    with connect() as db:
        db.execute(
            "insert into commands(device, command, payload, status, created_at) values (?, ?, ?, ?, ?)",
            (device, command, json.dumps(payload, ensure_ascii=False), status, utc_now()),
        )


def latest_measurements() -> list[dict[str, Any]]:
    with connect() as db:
        rows = db.execute(
            """
            select m.device, m.metric, m.value, m.unit, m.measured_at
            from measurements m
            join (
                select device, metric, max(measured_at) as measured_at
                from measurements
                group by device, metric
            ) latest
              on latest.device = m.device
             and latest.metric = m.metric
             and latest.measured_at = m.measured_at
            order by m.device, m.metric
            """
        ).fetchall()
    return [dict(row) for row in rows]


def measurement_history(limit: int = 60) -> list[dict[str, Any]]:
    with connect() as db:
        rows = db.execute(
            """
            select device, metric, value, unit, measured_at
            from measurements
            where metric in ('pm25', 'temperature', 'humidity', 'purifier_motor_speed')
            order by measured_at desc
            limit ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in reversed(rows)]


def recent_events(limit: int = 20) -> list[dict[str, Any]]:
    with connect() as db:
        rows = db.execute(
            "select device, severity, message, created_at from events order by created_at desc limit ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def recent_commands(limit: int = 20) -> list[dict[str, Any]]:
    with connect() as db:
        rows = db.execute(
            "select device, command, payload, status, created_at from commands order by created_at desc limit ?",
            (limit,),
        ).fetchall()
    commands = [dict(row) for row in rows]
    for command in commands:
        command["payload"] = json.loads(command["payload"])
    return commands


def command_seen_after(device: str, command: str, after: str) -> bool:
    with connect() as db:
        row = db.execute(
            """
            select 1
            from commands
            where device = ?
              and command = ?
              and created_at >= ?
              and status in ('planned', 'sent')
            limit 1
            """,
            (device, command, after),
        ).fetchone()
    return row is not None
