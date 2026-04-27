from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PropertySpec:
    did: str
    siid: int
    piid: int
    metric: str | None = None
    unit: str | None = None

    def as_miot_prop(self) -> dict[str, Any]:
        return {"did": self.did, "siid": self.siid, "piid": self.piid}


PURIFIER_PROPS = [
    PropertySpec("power", 2, 1, "purifier_power", None),
    PropertySpec("fault", 2, 2),
    PropertySpec("mode", 2, 4, "purifier_mode", None),
    PropertySpec("pm25", 3, 4, "pm25", "ug/m3"),
    PropertySpec("filter_life_remaining", 4, 1, "filter_life_remaining", "%"),
    PropertySpec("filter_hours_used", 4, 3),
    PropertySpec("filter_left_time", 4, 4),
    PropertySpec("buzzer", 6, 1),
    PropertySpec("child_lock", 8, 1),
    PropertySpec("motor_speed", 9, 1, "purifier_motor_speed", "rpm"),
    PropertySpec("favorite_level", 9, 11, "purifier_favorite_level", None),
    PropertySpec("aqi_realtime_update_duration", 11, 4),
    PropertySpec("led_brightness", 13, 2),
]


HUMIDIFIER_PROPS = [
    PropertySpec("power", 2, 1, "humidifier_power", None),
    PropertySpec("fault", 2, 2),
    PropertySpec("mode", 2, 5, "humidifier_mode", None),
    PropertySpec("target_humidity", 2, 6, "target_humidity", "%"),
    PropertySpec("status", 2, 7, "humidifier_status", None),
    PropertySpec("relative_humidity", 3, 1, "humidity", "%"),
    PropertySpec("temperature", 3, 7, "temperature", "C"),
    PropertySpec("fan_level", 4, 5, "humidifier_fan_level", None),
    PropertySpec("buzzer", 5, 1),
    PropertySpec("led_light", 6, 1),
    PropertySpec("water_shortage_fault", 7, 1),
    PropertySpec("tank_filled", 7, 2, "water_tank_filled", None),
    PropertySpec("overwet_protect", 7, 3),
]


HUMIDIFIER_DISCOVERY_CANDIDATES = [
    PropertySpec("humidifier_extra_2_7_candidate", 2, 7),
    PropertySpec("humidifier_extra_2_8_candidate", 2, 8),
]


DEVICE_PROPS = {
    "purifier": PURIFIER_PROPS,
    "humidifier": HUMIDIFIER_PROPS,
}


def specs_as_props(specs: list[PropertySpec]) -> list[dict[str, Any]]:
    return [spec.as_miot_prop() for spec in specs]


def specs_by_did(device_name: str) -> dict[str, PropertySpec]:
    return {spec.did: spec for spec in DEVICE_PROPS[device_name]}
