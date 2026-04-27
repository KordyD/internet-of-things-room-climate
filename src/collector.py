from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from src.config import AppConfig, DeviceConfig, load_config
from src.db import (
    command_seen_after,
    get_settings,
    insert_command,
    insert_event,
    insert_measurements,
    latest_measurements,
    utc_now,
)
from src.devices import DEVICE_PROPS, PropertySpec, specs_as_props, specs_by_did
from src.miot_client import MiotClient, MiotClientError


logger = logging.getLogger(__name__)


def read_device_measurements(device_config: DeviceConfig, specs: list[PropertySpec]) -> list[dict[str, Any]]:
    client = MiotClient(device_config)
    try:
        results = client.get_properties_batched(specs_as_props(specs))
    except MiotClientError as exc:
        if "Unable to discover the device" in str(exc):
            raise

        logger.warning("Batched read failed for %s, retrying properties one-by-one: %s", device_config.name, exc)
        results = []
        errors = 0
        for spec in specs:
            try:
                results.extend(client.get_properties([spec.as_miot_prop()]))
            except MiotClientError as prop_exc:
                errors += 1
                logger.warning(
                    "Skipping %s.%s for %s after read error: %s",
                    spec.siid,
                    spec.piid,
                    device_config.name,
                    prop_exc,
                )
        if not results and errors:
            raise exc

    by_did = specs_by_did(device_config.name)
    measured_at = utc_now()
    rows: list[dict[str, Any]] = []

    for item in results:
        spec = by_did.get(str(item.get("did")))
        value = item.get("value")
        if item.get("code") != 0 or spec is None or spec.metric is None:
            continue
        if isinstance(value, bool):
            numeric_value = 1.0 if value else 0.0
        elif isinstance(value, (int, float)):
            numeric_value = float(value)
        else:
            continue
        rows.append(
            {
                "device": device_config.name,
                "metric": spec.metric,
                "value": numeric_value,
                "unit": spec.unit,
                "measured_at": measured_at,
            }
        )

    return rows


def collect_once(config: AppConfig | None = None) -> None:
    config = config or load_config()
    settings = get_settings()
    all_rows: list[dict[str, Any]] = []

    for device_config in (config.purifier, config.humidifier):
        if not device_config.is_configured:
            continue
        specs = DEVICE_PROPS[device_config.name]
        try:
            rows = read_device_measurements(device_config, specs)
            all_rows.extend(rows)
        except Exception as exc:
            logger.warning("Polling failed for %s: %s", device_config.name, exc)
            insert_event(device_config.name, "error", f"Polling failed: {type(exc).__name__}: {exc}")

    insert_measurements(all_rows)
    evaluate_automations(all_rows, settings)


def apply_automations_from_latest(settings: dict[str, Any] | None = None, *, force: bool = False) -> None:
    evaluate_automations(latest_measurements(), settings or get_settings(), force=force)


def evaluate_automations(rows: list[dict[str, Any]], settings: dict[str, Any], *, force: bool = False) -> None:
    if not settings.get("automations_enabled"):
        return

    latest = {(row["device"], row["metric"]): row for row in rows}
    pm25 = latest.get(("purifier", "pm25"))
    humidity = latest.get(("humidifier", "humidity"))
    control_enabled = bool(settings.get("control_enabled"))

    if settings.get("purifier_auto_on_pm25_enabled") and pm25 and pm25["value"] >= float(settings["purifier_pm25_threshold"]):
        status = dispatch_command(
            "purifier",
            "turn_on",
            {"reason": "pm25_threshold", "pm25": pm25["value"]},
            settings,
            force=force,
        )
        if status:
            insert_event("purifier", "warning", f"PM2.5 is {pm25['value']:.0f}; purifier action {status}.")

    if (
        settings.get("purifier_auto_off_pm25_enabled")
        and pm25
        and pm25["value"] <= float(settings["purifier_pm25_low_threshold"])
    ):
        status = dispatch_command(
            "purifier",
            "turn_off",
            {"reason": "pm25_low_threshold", "pm25": pm25["value"]},
            settings,
            force=force,
        )
        if status:
            insert_event("purifier", "info", f"PM2.5 is {pm25['value']:.0f}; purifier off action {status}.")

    if (
        settings.get("humidifier_auto_off_high_humidity_enabled")
        and humidity
        and humidity["value"] >= float(settings["humidifier_humidity_high_threshold"])
    ):
        status = dispatch_command(
            "humidifier",
            "turn_off",
            {"reason": "humidity_high_threshold", "humidity": humidity["value"]},
            settings,
            force=force,
        )
        if status:
            insert_event("humidifier", "warning", f"Humidity is {humidity['value']:.0f}%; humidifier off action {status}.")

    if (
        settings.get("humidifier_auto_on_low_humidity_enabled")
        and humidity
        and humidity["value"] <= float(settings["humidifier_humidity_low_threshold"])
    ):
        status = dispatch_command(
            "humidifier",
            "turn_on",
            {"reason": "humidity_low_threshold", "humidity": humidity["value"]},
            settings,
            force=force,
        )
        if status:
            insert_event("humidifier", "info", f"Humidity is {humidity['value']:.0f}%; humidifier on action {status}.")


def dispatch_command(
    device_name: str,
    command: str,
    payload: dict[str, Any],
    settings: dict[str, Any],
    *,
    force: bool = False,
) -> str | None:
    cooldown = int(settings.get("command_cooldown_seconds", 300))
    after = (datetime.now(timezone.utc) - timedelta(seconds=cooldown)).isoformat()
    if not force and command_seen_after(device_name, command, after):
        return None

    if not settings.get("control_enabled"):
        insert_command(device_name, command, payload, "planned")
        return "planned"

    config = load_config()
    device_config = getattr(config, device_name)
    if not device_config.is_configured:
        insert_command(device_name, command, payload, "failed")
        insert_event(device_name, "error", f"Command {command} failed: device is not configured.")
        return "failed"

    try:
        client = MiotClient(device_config)
        if command == "turn_on":
            client.set_property(2, 1, True, did="power")
        elif command == "turn_off":
            client.set_property(2, 1, False, did="power")
        else:
            raise ValueError(f"Unsupported command: {command}")
        insert_command(device_name, command, payload, "sent")
        return "sent"
    except Exception as exc:
        logger.warning("Command failed for %s: %s", device_name, exc)
        insert_command(device_name, command, payload, "failed")
        insert_event(device_name, "error", f"Command {command} failed: {type(exc).__name__}: {exc}")
        return "failed"


def set_device_power(device_name: str, power: bool) -> str:
    config = load_config()
    device_config = getattr(config, device_name)
    payload = {"source": "manual", "power": power}
    command = "turn_on" if power else "turn_off"

    if not device_config.is_configured:
        insert_command(device_name, command, payload, "failed")
        insert_event(device_name, "error", f"Manual {command} failed: device is not configured.")
        return "failed"

    try:
        MiotClient(device_config).set_property(2, 1, power, did="power")
        insert_command(device_name, command, payload, "sent")
        insert_event(device_name, "info", f"Manual {command} command sent.")
        return "sent"
    except Exception as exc:
        logger.warning("Manual command failed for %s: %s", device_name, exc)
        insert_command(device_name, command, payload, "failed")
        insert_event(device_name, "error", f"Manual {command} failed: {type(exc).__name__}: {exc}")
        return "failed"


def set_humidifier_fan_level(level: int) -> str:
    config = load_config()
    device_config = config.humidifier
    payload = {"source": "manual", "level": level}
    command = "set_fan_level"

    if not device_config.is_configured:
        insert_command("humidifier", command, payload, "failed")
        insert_event("humidifier", "error", "Manual fan level change failed: device is not configured.")
        return "failed"

    try:
        MiotClient(device_config).set_property(2, 5, level, did="mode")
        insert_command("humidifier", command, payload, "sent")
        insert_event("humidifier", "info", f"Manual humidifier mode set to {level}.")
        return "sent"
    except Exception as exc:
        logger.warning("Manual humidifier fan level change failed: %s", exc)
        insert_command("humidifier", command, payload, "failed")
        insert_event("humidifier", "error", f"Manual humidifier mode change failed: {type(exc).__name__}: {exc}")
        return "failed"


def set_purifier_favorite_level(level: int) -> str:
    config = load_config()
    device_config = config.purifier
    payload = {"source": "manual", "level": level}
    command = "set_favorite_level"

    if not device_config.is_configured:
        insert_command("purifier", command, payload, "failed")
        insert_event("purifier", "error", "Manual favorite level change failed: device is not configured.")
        return "failed"

    try:
        client = MiotClient(device_config)
        client.set_property(2, 4, 2, did="mode")
        client.set_property(9, 11, level, did="favorite_level")
        insert_command("purifier", command, payload, "sent")
        insert_event("purifier", "info", f"Manual purifier favorite level set to {level}.")
        return "sent"
    except Exception as exc:
        logger.warning("Manual purifier favorite level change failed: %s", exc)
        insert_command("purifier", command, payload, "failed")
        insert_event("purifier", "error", f"Manual favorite level change failed: {type(exc).__name__}: {exc}")
        return "failed"


async def polling_loop(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        await asyncio.to_thread(collect_once)
        settings = get_settings()
        interval = max(1, int(settings.get("poll_interval_seconds", 5)))
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
