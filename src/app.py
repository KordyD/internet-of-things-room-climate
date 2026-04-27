from __future__ import annotations

from contextlib import asynccontextmanager
import asyncio
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.collector import collect_once, polling_loop, set_device_power
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
    humidifier_humidity_high_threshold: float | None = Field(default=None, ge=0, le=100)
    humidifier_humidity_low_threshold: float | None = Field(default=None, ge=0, le=100)


class PowerPatch(BaseModel):
    power: bool


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
def patch_settings(patch: SettingsPatch) -> dict[str, Any]:
    if hasattr(patch, "model_dump"):
        changes = patch.model_dump(exclude_none=True)
    else:
        changes = patch.dict(exclude_none=True)
    try:
        return update_settings(changes)
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


@app.get("/api/snapshot")
def snapshot() -> dict[str, Any]:
    return {
        "settings": get_settings(),
        "latest": latest_measurements(),
        "history": measurement_history(),
        "events": recent_events(),
        "commands": recent_commands(),
    }
