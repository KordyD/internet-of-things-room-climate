from __future__ import annotations

from contextlib import asynccontextmanager
import asyncio
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.collector import (
    apply_automations_from_latest,
    collect_once,
    polling_loop,
    set_device_power,
    set_humidifier_fan_level,
    set_purifier_favorite_level,
)
from src.config import load_config
from src.db import (
    get_settings,
    init_db,
    latest_measurements,
    measurement_history,
    recent_commands,
    recent_events,
    update_settings,
)


STATIC_DIR = Path(__file__).resolve().parent / "static"


class SettingsPatch(BaseModel):
    poll_interval_seconds: int | None = Field(default=None, ge=1, le=3600)
    automations_enabled: bool | None = None
    control_enabled: bool | None = None
    command_cooldown_seconds: int | None = Field(default=None, ge=0, le=86400)
    purifier_pm25_threshold: float | None = Field(default=None, ge=0)
    purifier_pm25_low_threshold: float | None = Field(default=None, ge=0)
    purifier_auto_on_pm25_enabled: bool | None = None
    purifier_auto_off_pm25_enabled: bool | None = None
    humidifier_humidity_high_threshold: float | None = Field(default=None, ge=0, le=100)
    humidifier_humidity_low_threshold: float | None = Field(default=None, ge=0, le=100)
    humidifier_auto_on_low_humidity_enabled: bool | None = None
    humidifier_auto_off_high_humidity_enabled: bool | None = None


class PowerPatch(BaseModel):
    power: bool


class FanLevelPatch(BaseModel):
    level: int = Field(ge=1, le=3)


class FavoriteLevelPatch(BaseModel):
    level: int = Field(ge=1, le=15)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    stop_event = asyncio.Event()
    task = asyncio.create_task(polling_loop(stop_event))
    yield
    stop_event.set()
    await task


app = FastAPI(title="Room Climate Control", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    config = load_config()
    return {
        "status": "ok",
        "devices": {
            "purifier": config.purifier.is_configured,
            "humidifier": config.humidifier.is_configured,
        },
    }


@app.get("/api/settings")
def read_settings() -> dict[str, Any]:
    return get_settings()


@app.patch("/api/settings")
async def patch_settings(patch: SettingsPatch) -> dict[str, Any]:
    if hasattr(patch, "model_dump"):
        changes = patch.model_dump(exclude_none=True)
    else:
        changes = patch.dict(exclude_none=True)

    previous_settings = get_settings()
    automation_related_keys = {
        "automations_enabled",
        "control_enabled",
        "purifier_pm25_threshold",
        "purifier_pm25_low_threshold",
        "purifier_auto_on_pm25_enabled",
        "purifier_auto_off_pm25_enabled",
        "humidifier_humidity_high_threshold",
        "humidifier_humidity_low_threshold",
        "humidifier_auto_on_low_humidity_enabled",
        "humidifier_auto_off_high_humidity_enabled",
    }

    try:
        settings = update_settings(changes)
        should_force_automations = any(
            key in automation_related_keys and previous_settings.get(key) != settings.get(key) for key in changes
        )
        if should_force_automations:
            await asyncio.to_thread(apply_automations_from_latest, settings, force=True)
        await asyncio.to_thread(collect_once)
        return settings
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/poll")
async def poll_now() -> dict[str, str]:
    await asyncio.to_thread(collect_once)
    return {"status": "ok"}


@app.patch("/api/devices/{device_name}/power")
async def patch_device_power(device_name: str, patch: PowerPatch) -> dict[str, str]:
    if device_name not in {"purifier", "humidifier"}:
        raise HTTPException(status_code=404, detail="Unknown device")
    status = await asyncio.to_thread(set_device_power, device_name, patch.power)
    if status == "failed":
        raise HTTPException(status_code=502, detail="Device command failed")
    await asyncio.to_thread(collect_once)
    return {"status": status}


@app.patch("/api/devices/humidifier/fan-level")
async def patch_humidifier_fan_level(patch: FanLevelPatch) -> dict[str, str]:
    status = await asyncio.to_thread(set_humidifier_fan_level, patch.level)
    if status == "failed":
        raise HTTPException(status_code=502, detail="Humidifier mode command failed")
    await asyncio.to_thread(collect_once)
    return {"status": status}


@app.patch("/api/devices/purifier/favorite-level")
async def patch_purifier_favorite_level(patch: FavoriteLevelPatch) -> dict[str, str]:
    status = await asyncio.to_thread(set_purifier_favorite_level, patch.level)
    if status == "failed":
        raise HTTPException(status_code=502, detail="Purifier favorite level command failed")
    await asyncio.to_thread(collect_once)
    return {"status": status}


@app.get("/api/snapshot")
def snapshot() -> dict[str, Any]:
    return {
        "settings": get_settings(),
        "latest": latest_measurements(),
        "history": measurement_history(),
        "events": recent_events(),
        "commands": recent_commands(),
    }
